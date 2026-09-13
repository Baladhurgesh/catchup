from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field
from youtube_transcript_api import YouTubeTranscriptApi

from models import TranscriptSegment, VideoSource
from services.cache import cache_key, get_or_set_model


class TranscriptError(RuntimeError):
    pass


class TranscriptDocument(BaseModel):
    video_id: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    method: str = "youtube-transcript-api"


PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]


def _snippet_fields(snippet: object) -> tuple[str, float, float]:
    if isinstance(snippet, dict):
        text = snippet.get("text") or ""
        start = snippet.get("start") or 0
        duration = snippet.get("duration") or 0
    else:
        text = getattr(snippet, "text", "") or ""
        start = getattr(snippet, "start", 0) or 0
        duration = getattr(snippet, "duration", 0) or 0
    return str(text).replace("\n", " ").strip(), float(start), float(duration)


def segments_from_payload(video_id: str, payload: object) -> list[TranscriptSegment]:
    snippets = getattr(payload, "snippets", payload)
    segments: list[TranscriptSegment] = []
    for snippet in snippets:
        text, start, duration = _snippet_fields(snippet)
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                video_id=video_id,
                start_seconds=start,
                duration_seconds=duration,
                text=text,
            )
        )
    if not segments:
        raise TranscriptError(f"Empty transcript for {video_id}")
    return segments


def _fetch_v1(video_id: str) -> list[TranscriptSegment]:
    api = YouTubeTranscriptApi()
    try:
        return segments_from_payload(
            video_id, api.fetch(video_id, languages=PREFERRED_LANGUAGES)
        )
    except Exception:
        listing = api.list(video_id)
        try:
            transcript = listing.find_transcript(PREFERRED_LANGUAGES)
        except Exception:
            transcript = next(iter(listing))
        if transcript.language_code not in PREFERRED_LANGUAGES and transcript.is_translatable:
            transcript = transcript.translate("en")
        return segments_from_payload(video_id, transcript.fetch())


def _fetch_v0(video_id: str) -> list[TranscriptSegment]:
    try:
        payload = YouTubeTranscriptApi.get_transcript(video_id, languages=PREFERRED_LANGUAGES)
        return segments_from_payload(video_id, payload)
    except Exception:
        listing = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = listing.find_transcript(PREFERRED_LANGUAGES)
        except Exception:
            transcript = next(iter(listing))
        if transcript.language_code not in PREFERRED_LANGUAGES and transcript.is_translatable:
            transcript = transcript.translate("en")
        return segments_from_payload(video_id, transcript.fetch())


def _fetch_sync(video_id: str) -> list[TranscriptSegment]:
    if hasattr(YouTubeTranscriptApi, "fetch"):
        return _fetch_v1(video_id)
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        return _fetch_v0(video_id)
    raise TranscriptError("youtube-transcript-api is missing both fetch() and get_transcript()")


async def get_transcript(video: VideoSource) -> TranscriptDocument:
    key = cache_key("transcript", video.video_id)

    async def _load() -> TranscriptDocument:
        try:
            segments = await asyncio.to_thread(_fetch_sync, video.video_id)
        except TranscriptError:
            raise
        except Exception as exc:
            raise TranscriptError(
                f"Transcript fetch failed for '{video.title}' ({video.video_id}): {exc}"
            ) from exc
        return TranscriptDocument(video_id=video.video_id, segments=segments)

    return await get_or_set_model("transcript", key, TranscriptDocument, _load)


async def get_all(
    videos: list[VideoSource],
) -> tuple[list[TranscriptDocument], list[tuple[VideoSource, str]]]:
    documents: list[TranscriptDocument] = []
    failures: list[tuple[VideoSource, str]] = []
    for video in videos:
        try:
            documents.append(await get_transcript(video))
        except TranscriptError as exc:
            failures.append((video, str(exc)))
    return documents, failures
