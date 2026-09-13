from models import Citation, Insight, PodcastEpisode, VideoSource
from services.google_drive import FOLDER_NAME, is_configured as drive_configured
from services.notion import (
    build_blocks,
    executive_summary_paragraphs,
    is_configured as notion_configured,
)
from util import youtube_timestamp_url


def test_drive_and_notion_default_to_unconfigured() -> None:
    assert drive_configured() is False
    assert notion_configured() is False


def test_notion_blocks_include_timestamp_links() -> None:
    video = VideoSource(
        video_id="abc12345678",
        url="https://youtube.com/watch?v=abc12345678",
        title="NVIDIA talk",
        channel="NVIDIA",
        duration_seconds=3600,
    )
    episode = PodcastEpisode(
        title="Local LLM Inference",
        description="Memory bandwidth is the bottleneck.",
        target_minutes=10,
        script="HOST_A: hello\nHOST_B: hi",
        sources=[video],
        insights=[
            Insight(
                id="insight-001",
                title="Memory bandwidth is becoming the bottleneck",
                explanation="Speakers agreed that moving weights dominates.",
                importance=0.9,
                source_citations=[
                    Citation(video_id="abc12345678", start_seconds=1934, end_seconds=2000)
                ],
            )
        ],
    )
    blocks = build_blocks(
        episode,
        focus="CUDA kernels",
        drive_url="https://drive.google.com/file/d/xyz",
        evaluation=None,
    )
    dumped = str(blocks)
    assert "Executive Summary" in dumped
    assert "Memory bandwidth is the bottleneck." in dumped
    assert "Speakers agreed that moving weights dominates" in dumped
    assert youtube_timestamp_url("abc12345678", 1934) in dumped
    assert "Listen on Google Drive" in dumped
    assert FOLDER_NAME == "CatchUp Podcasts"


def test_notion_summary_expands_placeholder_description() -> None:
    episode = PodcastEpisode(
        title="Local LLM Inference",
        description="Local CatchUp integration test for Drive and Notion.",
        target_minutes=10,
        script="HOST_A: hello\nHOST_B: hi",
        sources=[
            VideoSource(
                video_id="abc12345678",
                url="https://youtube.com/watch?v=abc12345678",
                title="NVIDIA talk",
                channel="NVIDIA",
                duration_seconds=3600,
            )
        ],
        insights=[
            Insight(
                id="insight-001",
                title="Memory bandwidth is becoming the bottleneck",
                explanation="Speakers agreed that moving weights dominates inference cost.",
                importance=0.9,
            )
        ],
    )
    paragraphs = executive_summary_paragraphs(episode, focus="CUDA kernels")
    assert "NVIDIA talk" in paragraphs[0]
    assert "CUDA kernels" in paragraphs[0]
    assert any("moving weights dominates" in paragraph for paragraph in paragraphs)
    assert "integration test" not in " ".join(paragraphs)
