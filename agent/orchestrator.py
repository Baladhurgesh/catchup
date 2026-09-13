from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from agent.grounding import evaluate_episode, extract_claims
from agent.insight_extractor import analyze_chunks
from agent.script_writer import create as write_script
from agent.synthesizer import merge_and_deduplicate
from agent.transcript_processor import chunk_documents
from config import settings
from models import CatchUpJob, JobResult, PodcastEpisode, SourceError
from services.google_drive import DriveError, is_configured as drive_configured, upload_episode
from services.notion import NotionError, create_episode, is_configured as notion_configured
from services.podcastfy import PodcastGenerationError, PodcastGenerator
from services.transcript import get_all
from services.youtube import YouTubeError, fetch_metadata
from util import dated_filename, format_duration


ProgressFn = Callable[[str], Awaitable[None]]


async def _noop_progress(_message: str) -> None:
    return None


def persist_job(job: CatchUpJob, extra: dict | None = None) -> Path:
    path = settings.jobs_dir / f"{job.job_id}.json"
    payload = job.model_dump()
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


async def process_job(
    job: CatchUpJob,
    *,
    update_slack: ProgressFn | None = None,
) -> JobResult:
    progress = update_slack or _noop_progress
    warnings = list(job.warnings)
    persist_job(job)

    try:
        job.status = "reading"
        await progress(
            f"🎧 *CatchUp started.*\n\n"
            f"{len(job.urls)} videos received.\n"
            f"Target: {job.target_minutes} minutes\n"
            f"Focus: {job.focus}\n\n"
            f"⏳ Reading sources..."
        )

        try:
            videos = await fetch_metadata(job.urls)
        except YouTubeError as exc:
            job.status = "failed"
            job.warnings.append(str(exc))
            persist_job(job)
            await progress(f"❌ Couldn't fetch YouTube metadata.\n`{exc}`")
            return JobResult(job=job, warnings=job.warnings)

        transcripts, failures = await get_all(videos)
        for video, message in failures:
            job.source_errors.append(
                SourceError(
                    url=video.url,
                    video_id=video.video_id,
                    stage="transcript",
                    message=message,
                )
            )
            warning = (
                f"⚠️ Couldn't process *{video.title}*. "
                f"Continuing with remaining sources.\n`{message}`"
            )
            warnings.append(warning)
            await progress(warning)

        if not transcripts:
            job.status = "failed"
            job.warnings = warnings + ["No transcripts could be retrieved."]
            persist_job(job)
            await progress("❌ No public transcripts were available for these videos.")
            return JobResult(job=job, warnings=job.warnings)

        processed_ids = {doc.video_id for doc in transcripts}
        processed_videos = [video for video in videos if video.video_id in processed_ids]
        total = sum(video.duration_seconds for video in processed_videos)
        job.status = "analyzing"
        persist_job(job)
        await progress(
            f"✅ YouTube sources analyzed\n"
            f"{len(processed_videos)} talks · {format_duration(total)} total\n\n"
            f"⏳ Finding the most important ideas..."
        )

        chunks = chunk_documents(transcripts)
        analyzed = await analyze_chunks(
            chunks,
            focus=job.focus,
            expertise=job.expertise.value,
        )

        job.status = "synthesizing"
        persist_job(job)
        insights, made_the_cut, skipped = await merge_and_deduplicate(
            analyzed,
            processed_videos,
            focus=job.focus,
            expertise=job.expertise.value,
        )
        claims = await extract_claims(insights, analyzed, focus=job.focus)
        await progress(
            f"✅ {len(insights)} important concepts identified\n"
            f"✅ Deduplicated overlapping explanations\n"
            f"⏳ Generating your podcast..."
        )

        job.status = "writing"
        persist_job(job)
        script_result = await write_script(
            insights,
            processed_videos,
            target_minutes=job.target_minutes,
            focus=job.focus,
            expertise=job.expertise.value,
            style=job.style,
        )
        if script_result.made_the_cut:
            made_the_cut = script_result.made_the_cut
        if script_result.skipped:
            skipped = script_result.skipped

        episode = PodcastEpisode(
            title=script_result.title,
            description=script_result.description,
            target_minutes=job.target_minutes,
            script=script_result.script,
            insights=insights,
            sources=processed_videos,
            claims=claims,
            made_the_cut=made_the_cut,
            skipped=skipped,
        )
        evaluation = evaluate_episode(episode, videos, processed_ids)
        warnings.extend(evaluation.warnings)

        script_path = settings.transcripts_dir / dated_filename(episode.title, ".txt")
        script_path.write_text(episode.script, encoding="utf-8")

        job.status = "rendering"
        persist_job(job)
        await progress("⏳ Generating audio...")

        mp3_path: Path | None = None
        try:
            generated = await _generate_audio(episode.script)
            dest = settings.audio_dir / dated_filename(episode.title, ".mp3")
            dest.write_bytes(generated.read_bytes())
            mp3_path = dest
        except PodcastGenerationError as exc:
            warning = f"⚠️ Audio generation failed. Returning the script instead. `{exc}`"
            warnings.append(warning)
            await progress(warning)

        drive_url: str | None = None
        notion_url: str | None = None
        if mp3_path or notion_configured():
            await progress("⏳ Saving notes and uploading audio...")

        if mp3_path and drive_configured():
            try:
                drive_url = await asyncio.to_thread(upload_episode, episode, mp3_path)
            except DriveError as exc:
                warning = f"⚠️ Google Drive upload failed. The MP3 will still be attached in Slack. `{exc}`"
                warnings.append(warning)
                await progress(warning)

        if notion_configured():
            try:
                notion_url = await asyncio.to_thread(
                    create_episode,
                    episode,
                    focus=job.focus,
                    drive_url=drive_url,
                    evaluation=evaluation,
                )
            except NotionError as exc:
                warning = f"⚠️ Notion notes failed. The podcast is still ready. `{exc}`"
                warnings.append(warning)
                await progress(warning)

        job.status = "complete"
        job.warnings = warnings
        persist_job(
            job,
            extra={
                "title": episode.title,
                "mp3_path": str(mp3_path) if mp3_path else None,
                "script_path": str(script_path),
                "drive_url": drive_url,
                "notion_url": notion_url,
                "evaluation": evaluation.model_dump(),
            },
        )
        return JobResult(
            job=job,
            episode=episode,
            evaluation=evaluation,
            mp3_path=str(mp3_path) if mp3_path else None,
            script_path=str(script_path),
            drive_url=drive_url,
            notion_url=notion_url,
            warnings=warnings,
        )
    except Exception as exc:
        job.status = "failed"
        job.warnings.append(str(exc))
        persist_job(job)
        await progress(f"❌ CatchUp failed.\n`{exc}`")
        return JobResult(job=job, warnings=job.warnings)


async def _generate_audio(script: str) -> Path:
    generator = PodcastGenerator()
    result = await asyncio.to_thread(generator.generate_from_host_script, script)
    return result.audio_path


def new_job(
    urls: list[str],
    *,
    focus: str,
    target_minutes: int = 10,
    expertise: str = "intermediate",
    style: str = "conversational",
    channel_id: str | None = None,
    user_id: str | None = None,
) -> CatchUpJob:
    return CatchUpJob(
        job_id=uuid.uuid4().hex[:12],
        urls=urls,
        target_minutes=target_minutes,
        focus=focus,
        expertise=expertise,
        style=style,
        channel_id=channel_id,
        user_id=user_id,
    )
