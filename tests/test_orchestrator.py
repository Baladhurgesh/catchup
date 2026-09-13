from pathlib import Path

import pytest

from agent.orchestrator import new_job, process_job
from models import (
    GroundedClaim,
    PodcastScriptResult,
    SourceChunk,
    TranscriptSegment,
    VideoSource,
)
from services.transcript import TranscriptDocument


def _video(video_id: str, title: str) -> VideoSource:
    return VideoSource(
        video_id=video_id,
        url=f"https://youtube.com/watch?v={video_id}",
        title=title,
        channel="Conf",
        duration_seconds=1800,
        description="talk",
    )


def _transcript(video_id: str) -> TranscriptDocument:
    return TranscriptDocument(
        video_id=video_id,
        segments=[
            TranscriptSegment(
                video_id=video_id,
                start_seconds=0,
                duration_seconds=400,
                text="KV cache and memory bandwidth dominate inference.",
            ),
            TranscriptSegment(
                video_id=video_id,
                start_seconds=400,
                duration_seconds=400,
                text="Triton kernels on Blackwell improve attention.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_process_job_happy_path(monkeypatch, tmp_path: Path) -> None:
    from config import settings

    settings.data_dir = tmp_path
    settings.demo_mode = False

    videos = [_video("aaaaaaaaaaa", "Talk One"), _video("bbbbbbbbbbb", "Talk Two")]

    async def fake_metadata(urls):
        return videos

    async def fake_transcripts(items):
        return [_transcript(video.video_id) for video in items], []

    async def fake_analyze(chunks, focus, expertise):
        return [
            SourceChunk(
                chunk_id=chunk.chunk_id,
                video_id=chunk.video_id,
                start_seconds=chunk.start_seconds,
                end_seconds=chunk.end_seconds,
                text=chunk.text,
                summary="Memory bandwidth matters",
                concepts=["KV cache"],
                relevance_score=0.9,
            )
            for chunk in chunks
        ]

    async def fake_synth(chunks, videos, focus, expertise):
        return (
            [],
            ["KV cache"],
            ["Transformer intro"],
        )

    async def fake_claims(insights, chunks, focus):
        return [
            GroundedClaim(
                claim="Memory bandwidth is the bottleneck",
                citations=[],
                confidence=0.8,
            )
        ]

    async def fake_script(*args, **kwargs):
        return PodcastScriptResult(
            title="Efficient Local LLM Inference",
            description="A short recap",
            script="HOST_A: " + ("memory " * 200) + "\nHOST_B: " + ("question " * 200),
            made_the_cut=["KV cache"],
            skipped=["Intros"],
        )

    class FakePodcast:
        def generate_from_host_script(self, script: str):
            path = tmp_path / "episode.mp3"
            path.write_bytes(b"x" * 2048)

            class Result:
                audio_path = path

            return Result()

    monkeypatch.setattr("agent.orchestrator.fetch_metadata", fake_metadata)
    monkeypatch.setattr("agent.orchestrator.get_all", fake_transcripts)
    monkeypatch.setattr("agent.orchestrator.analyze_chunks", fake_analyze)
    monkeypatch.setattr("agent.orchestrator.merge_and_deduplicate", fake_synth)
    monkeypatch.setattr("agent.orchestrator.extract_claims", fake_claims)
    monkeypatch.setattr("agent.orchestrator.write_script", fake_script)
    monkeypatch.setattr("agent.orchestrator.PodcastGenerator", FakePodcast)

    job = new_job(
        ["https://youtube.com/watch?v=aaaaaaaaaaa", "https://youtube.com/watch?v=bbbbbbbbbbb"],
        focus="inference",
    )
    result = await process_job(job)
    assert result.episode is not None
    assert result.mp3_path
    assert Path(result.mp3_path).exists()
    assert result.job.status == "complete"


@pytest.mark.asyncio
async def test_process_job_continues_when_one_transcript_fails(monkeypatch, tmp_path: Path) -> None:
    from config import settings

    settings.data_dir = tmp_path
    settings.demo_mode = False

    videos = [_video("aaaaaaaaaaa", "Talk One"), _video("bbbbbbbbbbb", "Talk Two")]

    async def fake_metadata(urls):
        return videos

    async def fake_transcripts(items):
        return [_transcript("aaaaaaaaaaa")], [(videos[1], "no captions")]

    async def fake_analyze(chunks, focus, expertise):
        return [
            chunk.model_copy(update={"summary": "ok", "concepts": ["x"], "relevance_score": 0.8})
            for chunk in chunks
        ]

    async def fake_synth(chunks, videos, focus, expertise):
        return [], ["x"], []

    async def fake_claims(insights, chunks, focus):
        return []

    async def fake_script(*args, **kwargs):
        return PodcastScriptResult(
            title="Partial",
            description="desc",
            script="HOST_A: hello\nHOST_B: hi",
            made_the_cut=[],
            skipped=[],
        )

    class FakePodcast:
        def generate_from_host_script(self, script: str):
            path = tmp_path / "episode.mp3"
            path.write_bytes(b"x" * 2048)

            class Result:
                audio_path = path

            return Result()

    monkeypatch.setattr("agent.orchestrator.fetch_metadata", fake_metadata)
    monkeypatch.setattr("agent.orchestrator.get_all", fake_transcripts)
    monkeypatch.setattr("agent.orchestrator.analyze_chunks", fake_analyze)
    monkeypatch.setattr("agent.orchestrator.merge_and_deduplicate", fake_synth)
    monkeypatch.setattr("agent.orchestrator.extract_claims", fake_claims)
    monkeypatch.setattr("agent.orchestrator.write_script", fake_script)
    monkeypatch.setattr("agent.orchestrator.PodcastGenerator", FakePodcast)

    job = new_job(["https://youtube.com/watch?v=aaaaaaaaaaa"], focus="inference")
    result = await process_job(job)
    assert result.episode is not None
    assert len(result.episode.sources) == 1
    assert any("Talk Two" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_process_job_returns_script_if_podcastfy_fails(monkeypatch, tmp_path: Path) -> None:
    from config import settings
    from services.podcastfy import PodcastGenerationError

    settings.data_dir = tmp_path
    settings.demo_mode = False

    async def fake_metadata(urls):
        return [_video("aaaaaaaaaaa", "Talk One")]

    async def fake_transcripts(items):
        return [_transcript("aaaaaaaaaaa")], []

    async def fake_analyze(chunks, focus, expertise):
        return chunks

    async def fake_synth(chunks, videos, focus, expertise):
        return [], [], []

    async def fake_claims(insights, chunks, focus):
        return []

    async def fake_script(*args, **kwargs):
        return PodcastScriptResult(
            title="Script Only",
            description="desc",
            script="HOST_A: hello\nHOST_B: hi",
            made_the_cut=[],
            skipped=[],
        )

    class FakePodcast:
        def generate_from_host_script(self, script: str):
            raise PodcastGenerationError("tts down")

    monkeypatch.setattr("agent.orchestrator.fetch_metadata", fake_metadata)
    monkeypatch.setattr("agent.orchestrator.get_all", fake_transcripts)
    monkeypatch.setattr("agent.orchestrator.analyze_chunks", fake_analyze)
    monkeypatch.setattr("agent.orchestrator.merge_and_deduplicate", fake_synth)
    monkeypatch.setattr("agent.orchestrator.extract_claims", fake_claims)
    monkeypatch.setattr("agent.orchestrator.write_script", fake_script)
    monkeypatch.setattr("agent.orchestrator.PodcastGenerator", FakePodcast)

    job = new_job(["https://youtube.com/watch?v=aaaaaaaaaaa"], focus="inference")
    result = await process_job(job)
    assert result.episode is not None
    assert result.mp3_path is None
    assert result.script_path
    assert any("Audio generation failed" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_process_job_survives_drive_and_notion_failures(monkeypatch, tmp_path: Path) -> None:
    from services.google_drive import DriveError
    from services.notion import NotionError

    async def fake_metadata(urls):
        return [_video("aaaaaaaaaaa", "Talk One")]

    async def fake_transcripts(items):
        return [_transcript("aaaaaaaaaaa")], []

    async def fake_analyze(chunks, focus, expertise):
        return chunks

    async def fake_synth(chunks, videos, focus, expertise):
        return [], [], []

    async def fake_claims(insights, chunks, focus):
        return []

    async def fake_script(*args, **kwargs):
        return PodcastScriptResult(
            title="Ready",
            description="desc",
            script="HOST_A: hello\nHOST_B: hi",
            made_the_cut=[],
            skipped=[],
        )

    class FakePodcast:
        def generate_from_host_script(self, script: str):
            path = tmp_path / "episode.mp3"
            path.write_bytes(b"x" * 2048)

            class Result:
                audio_path = path

            return Result()

    def boom_drive(*args, **kwargs):
        raise DriveError("quota")

    def boom_notion(*args, **kwargs):
        raise NotionError("unavailable")

    monkeypatch.setattr("agent.orchestrator.fetch_metadata", fake_metadata)
    monkeypatch.setattr("agent.orchestrator.get_all", fake_transcripts)
    monkeypatch.setattr("agent.orchestrator.analyze_chunks", fake_analyze)
    monkeypatch.setattr("agent.orchestrator.merge_and_deduplicate", fake_synth)
    monkeypatch.setattr("agent.orchestrator.extract_claims", fake_claims)
    monkeypatch.setattr("agent.orchestrator.write_script", fake_script)
    monkeypatch.setattr("agent.orchestrator.PodcastGenerator", FakePodcast)
    monkeypatch.setattr("agent.orchestrator.drive_configured", lambda: True)
    monkeypatch.setattr("agent.orchestrator.notion_configured", lambda: True)
    monkeypatch.setattr("agent.orchestrator.upload_episode", boom_drive)
    monkeypatch.setattr("agent.orchestrator.create_episode", boom_notion)

    result = await process_job(new_job(["https://youtube.com/watch?v=aaaaaaaaaaa"], focus="inference"))
    assert result.episode is not None
    assert result.mp3_path
    assert result.drive_url is None
    assert result.notion_url is None
    assert any("Google Drive" in warning for warning in result.warnings)
    assert any("Notion" in warning for warning in result.warnings)
