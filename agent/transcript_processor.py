from __future__ import annotations

from models import SourceChunk, TranscriptSegment
from services.transcript import TranscriptDocument


TARGET_CHUNK_SECONDS = 6.5 * 60
MIN_CHUNK_SECONDS = 5 * 60
MAX_CHUNK_SECONDS = 8 * 60


def chunk_segments(
    video_id: str,
    segments: list[TranscriptSegment],
    *,
    target_seconds: float = TARGET_CHUNK_SECONDS,
) -> list[SourceChunk]:
    if not segments:
        return []

    chunks: list[SourceChunk] = []
    bucket: list[TranscriptSegment] = []
    start = segments[0].start_seconds

    def close_bucket(remaining: list[TranscriptSegment]) -> None:
        if not remaining:
            return
        end = remaining[-1].start_seconds + remaining[-1].duration_seconds
        index = len(chunks) + 1
        chunks.append(
            SourceChunk(
                chunk_id=f"{video_id}-{index:03d}",
                video_id=video_id,
                start_seconds=remaining[0].start_seconds,
                end_seconds=end,
                text=" ".join(seg.text for seg in remaining).strip(),
            )
        )

    for segment in segments:
        if not bucket:
            start = segment.start_seconds
            bucket.append(segment)
            continue

        tentative_end = segment.start_seconds + segment.duration_seconds
        if tentative_end - start <= target_seconds:
            bucket.append(segment)
            continue

        duration = bucket[-1].start_seconds + bucket[-1].duration_seconds - start
        if duration < MIN_CHUNK_SECONDS and tentative_end - start <= MAX_CHUNK_SECONDS:
            bucket.append(segment)
            continue

        close_bucket(bucket)
        bucket = [segment]
        start = segment.start_seconds

    close_bucket(bucket)
    return chunks


def chunk_documents(documents: list[TranscriptDocument]) -> list[SourceChunk]:
    chunks: list[SourceChunk] = []
    for document in documents:
        chunks.extend(chunk_segments(document.video_id, document.segments))
    return chunks
