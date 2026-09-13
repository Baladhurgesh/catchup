from agent.transcript_processor import chunk_segments
from models import TranscriptSegment
from services.transcript import segments_from_payload


def _segments(video_id: str, minutes: int, step: int = 30) -> list[TranscriptSegment]:
    segments = []
    for start in range(0, minutes * 60, step):
        segments.append(
            TranscriptSegment(
                video_id=video_id,
                start_seconds=float(start),
                duration_seconds=float(step),
                text=f"spoken content at {start}",
            )
        )
    return segments


def test_chunks_are_five_to_eight_minutes() -> None:
    chunks = chunk_segments("abc", _segments("abc", 20))
    assert len(chunks) >= 2
    for chunk in chunks[:-1]:
        duration = chunk.end_seconds - chunk.start_seconds
        assert 5 * 60 <= duration <= 8 * 60


def test_chunk_ids_are_stable_and_sequential() -> None:
    chunks = chunk_segments("talk1", _segments("talk1", 14))
    assert chunks[0].chunk_id == "talk1-001"
    assert chunks[1].chunk_id == "talk1-002"


def test_empty_segments_return_no_chunks() -> None:
    assert chunk_segments("abc", []) == []


def test_segments_from_dict_payload() -> None:
    segments = segments_from_payload(
        "abc",
        [{"text": "hello", "start": 1.5, "duration": 2.0}],
    )
    assert segments[0].text == "hello"
    assert segments[0].start_seconds == 1.5


def test_segments_from_object_payload() -> None:
    class Snippet:
        text = "hello\nthere"
        start = 0
        duration = 1.2

    class Fetched:
        snippets = [Snippet()]

    segments = segments_from_payload("abc", Fetched())
    assert segments[0].text == "hello there"
