from __future__ import annotations

from models import (
    Citation,
    EpisodeEval,
    GroundedClaim,
    GroundedClaimsResult,
    Insight,
    PodcastEpisode,
    SourceChunk,
    VideoSource,
)
from services.cache import cache_key, get_or_set_model
from services.llm import complete_json
from util import target_words, word_count


def _insight_brief(insight: Insight) -> str:
    cites = ", ".join(
        f"{c.video_id} {c.start_seconds:.0f}-{c.end_seconds:.0f}"
        for c in insight.source_citations
    )
    return f"- {insight.title}: {insight.explanation} [chunks={insight.source_chunks}; cites={cites}]"


async def extract_claims(
    insights: list[Insight],
    chunks: list[SourceChunk],
    *,
    focus: str,
) -> list[GroundedClaim]:
    chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}
    supporting = []
    for insight in insights:
        for chunk_id in insight.source_chunks:
            chunk = chunk_lookup.get(chunk_id)
            if chunk:
                supporting.append(
                    f"{chunk.chunk_id} ({chunk.video_id} {chunk.start_seconds:.0f}-{chunk.end_seconds:.0f}): {chunk.summary}"
                )
    key = cache_key("claims", focus, *[insight.title for insight in insights])

    async def _load() -> GroundedClaimsResult:
        prompt = f"""Extract major factual claims from these synthesized insights.

Each claim MUST have at least one citation from the provided source chunks.
Do not add facts that are not in the insights or chunk summaries.
If a statement is interpretation rather than a source fact, omit it or mark confidence below 0.5.

Focus: {focus}

Insights:
{chr(10).join(_insight_brief(insight) for insight in insights)}

Source chunks:
{chr(10).join(supporting)}
"""
        return await complete_json(prompt, GroundedClaimsResult)

    return (await get_or_set_model("claims", key, GroundedClaimsResult, _load)).claims


def citation_is_valid(citation: Citation, videos: dict[str, VideoSource]) -> bool:
    video = videos.get(citation.video_id)
    if video is None:
        return False
    if citation.start_seconds < 0 or citation.end_seconds < citation.start_seconds:
        return False
    return citation.start_seconds <= video.duration_seconds + 1


def evaluate_episode(
    episode: PodcastEpisode,
    videos: list[VideoSource],
    processed_video_ids: set[str],
) -> EpisodeEval:
    videos_by_id = {video.video_id: video for video in videos}
    claims = episode.claims
    cited = [claim for claim in claims if claim.citations]
    coverage = (len(cited) / len(claims)) if claims else 1.0

    all_citations = [cite for claim in claims for cite in claim.citations]
    all_citations.extend(
        cite for insight in episode.insights for cite in insight.source_citations
    )
    validity = all(citation_is_valid(cite, videos_by_id) for cite in all_citations) if all_citations else True

    words = word_count(episode.script)
    target = target_words(episode.target_minutes)
    adherence = abs(words - target) / target if target else 0.0

    represented = {cite.video_id for cite in all_citations if cite.video_id in processed_video_ids}
    if not represented:
        represented = {insight.source_citations[0].video_id for insight in episode.insights if insight.source_citations}

    warnings: list[str] = []
    if coverage < 0.95:
        warnings.append(f"Citation coverage is {coverage:.0%} (target >95%)")
    if not validity:
        warnings.append("One or more citations fall outside a source video's duration")
    if adherence > 0.15:
        warnings.append(
            f"Script length is off-target ({words} words vs {target} ±15%)"
        )
    if videos and len(represented) < len(processed_video_ids):
        warnings.append(
            f"Source coverage is {len(represented)}/{len(processed_video_ids)} videos"
        )

    return EpisodeEval(
        citation_coverage=coverage,
        citation_validity=validity,
        length_adherence=adherence,
        actual_words=words,
        target_words=target,
        source_coverage=len(represented),
        source_total=len(processed_video_ids),
        grounded_claim_count=len(claims),
        warnings=warnings,
    )
