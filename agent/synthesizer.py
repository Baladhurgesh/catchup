from __future__ import annotations

from models import Insight, SourceChunk, SynthesisResult, VideoSource
from services.cache import cache_key, get_or_set_model
from services.llm import complete_json
from util import format_timestamp


RELEVANCE_FLOOR = 0.35
MIN_CHUNKS = 4


def select_high_value_chunks(chunks: list[SourceChunk]) -> list[SourceChunk]:
    ranked = sorted(chunks, key=lambda c: c.relevance_score, reverse=True)
    selected = [chunk for chunk in ranked if chunk.relevance_score >= RELEVANCE_FLOOR]
    if len(selected) < MIN_CHUNKS:
        selected = ranked[: max(MIN_CHUNKS, min(8, len(ranked)))]
    return selected


def _chunk_brief(chunk: SourceChunk, videos: dict[str, VideoSource]) -> str:
    video = videos.get(chunk.video_id)
    title = video.title if video else chunk.video_id
    return (
        f"- chunk_id={chunk.chunk_id} | {title} | "
        f"{format_timestamp(chunk.start_seconds)}-{format_timestamp(chunk.end_seconds)} | "
        f"relevance={chunk.relevance_score:.2f}\n"
        f"  concepts: {', '.join(chunk.concepts) or 'n/a'}\n"
        f"  summary: {chunk.summary}"
    )


async def merge_and_deduplicate(
    chunks: list[SourceChunk],
    videos: list[VideoSource],
    *,
    focus: str,
    expertise: str,
) -> tuple[list[Insight], list[str], list[str]]:
    selected = select_high_value_chunks(chunks)
    videos_by_id = {video.video_id: video for video in videos}
    payload = "\n".join(_chunk_brief(chunk, videos_by_id) for chunk in selected)
    key = cache_key("synth", focus, expertise, payload)

    async def _load() -> SynthesisResult:
        prompt = f"""Synthesize cross-video insights for a grounded podcast.

User focus: {focus}
Audience expertise: {expertise}

Rules:
- Deduplicate repeated concepts. If three talks explain the same idea, write one insight and cite all of them.
- Prefer synthesis like "Three speakers independently emphasized..." over repeating the same explanation.
- Every insight needs at least one citation using the provided video_id and timestamps.
- Do not invent facts, numbers, or benchmarks.
- If sources disagree, create an insight that states the disagreement.
- Use only the chunk ids and timestamps below.

High-value chunks:
{payload}
"""
        return await complete_json(prompt, SynthesisResult)

    result = await get_or_set_model("synth", key, SynthesisResult, _load)
    insights: list[Insight] = []
    for index, draft in enumerate(result.insights, start=1):
        insights.append(
            Insight(
                id=f"insight-{index:03d}",
                title=draft.title,
                explanation=draft.explanation,
                importance=draft.importance,
                source_chunks=draft.source_chunk_ids,
                source_citations=draft.citations,
            )
        )
    return insights, result.made_the_cut, result.skipped
