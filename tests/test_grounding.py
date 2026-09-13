from agent.grounding import citation_is_valid, evaluate_episode
from models import Citation, GroundedClaim, Insight, PodcastEpisode, VideoSource
from services.podcastfy import host_transcript_to_podcastfy


def _video(video_id: str, duration: int = 3600) -> VideoSource:
    return VideoSource(
        video_id=video_id,
        url=f"https://youtube.com/watch?v={video_id}",
        title=f"Talk {video_id}",
        channel="Conf",
        duration_seconds=duration,
    )


def test_citation_must_fall_inside_video() -> None:
    videos = {"abc12345678": _video("abc12345678", 600)}
    assert citation_is_valid(
        Citation(video_id="abc12345678", start_seconds=30, end_seconds=90),
        videos,
    )
    assert not citation_is_valid(
        Citation(video_id="abc12345678", start_seconds=900, end_seconds=960),
        videos,
    )


def test_citation_coverage_and_length() -> None:
    video = _video("abc12345678")
    episode = PodcastEpisode(
        title="Test",
        description="desc",
        target_minutes=10,
        script="word " * 1500,
        insights=[
            Insight(
                id="insight-001",
                title="Memory",
                explanation="Bandwidth matters",
                importance=0.9,
                source_citations=[
                    Citation(video_id="abc12345678", start_seconds=10, end_seconds=40)
                ],
            )
        ],
        sources=[video],
        claims=[
            GroundedClaim(
                claim="Memory bandwidth is the bottleneck",
                citations=[Citation(video_id="abc12345678", start_seconds=10, end_seconds=40)],
                confidence=0.9,
            )
        ],
    )
    evaluation = evaluate_episode(episode, [video], {"abc12345678"})
    assert evaluation.citation_coverage == 1.0
    assert evaluation.citation_validity is True
    assert evaluation.length_adherence < 0.15
    assert evaluation.source_coverage == 1


def test_host_script_converts_to_podcastfy_pairs() -> None:
    xml = host_transcript_to_podcastfy(
        "HOST_A: Memory movement dominates.\nHOST_B: More than arithmetic?\nHOST_A: Yes."
    )
    assert "<Person1>Memory movement dominates.</Person1>" in xml
    assert "<Person2>More than arithmetic?</Person2>" in xml
    assert xml.strip().endswith("</Person2>")
