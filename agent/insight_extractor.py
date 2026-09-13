from __future__ import annotations

import asyncio

from config import settings
from models import ChunkAnalysisResult, SourceChunk
from services.cache import cache_key, get_or_set_model
from services.llm import complete_json


async def analyze_chunk(
    chunk: SourceChunk,
    *,
    focus: str,
    expertise: str,
) -> SourceChunk:
    key = cache_key("chunk", chunk.chunk_id, chunk.video_id, focus, expertise, chunk.text)

    async def _load() -> ChunkAnalysisResult:
        prompt = f"""Analyze this timestamped lecture chunk for a personalized podcast.

User focus:
{focus}

Audience expertise: {expertise}

Score relevance from 0.0 to 1.0 relative to the user's focus.
- Generic background the user already knows should score low (e.g. 0.2).
- A section that directly addresses the focus should score high (e.g. 0.9+).

Do not invent details that are not in the chunk.

Video ID: {chunk.video_id}
Time range: {chunk.start_seconds:.1f}s - {chunk.end_seconds:.1f}s

Chunk:
{chunk.text}
"""
        return await complete_json(prompt, ChunkAnalysisResult)

    analysis = await get_or_set_model("chunk", key, ChunkAnalysisResult, _load)
    return chunk.model_copy(
        update={
            "summary": analysis.summary,
            "concepts": analysis.concepts,
            "relevance_score": analysis.relevance_score,
        }
    )


async def analyze_chunks(
    chunks: list[SourceChunk],
    *,
    focus: str,
    expertise: str,
) -> list[SourceChunk]:
    semaphore = asyncio.Semaphore(settings.llm_concurrency)

    async def _bound(chunk: SourceChunk) -> SourceChunk:
        async with semaphore:
            return await analyze_chunk(chunk, focus=focus, expertise=expertise)

    return list(await asyncio.gather(*[_bound(chunk) for chunk in chunks]))
