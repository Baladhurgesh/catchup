from __future__ import annotations

from models import Insight, PodcastScriptResult, PodcastStyle, VideoSource
from services.cache import cache_key, get_or_set_model
from services.llm import complete_json
from util import format_timestamp, target_words


STYLE_GUIDANCE = {
    PodcastStyle.CONCISE: "Keep turns short. Favor density over banter.",
    PodcastStyle.CONVERSATIONAL: "Natural back-and-forth. Intelligent, not cheesy or overly enthusiastic.",
    PodcastStyle.TECHNICAL: "Stay precise. Use the speakers' technical terms when they used them.",
    PodcastStyle.DEBATE: "HOST_B should pressure-test claims and surface disagreements between talks.",
}


def _source_line(video: VideoSource) -> str:
    return f"- {video.video_id}: {video.title} ({video.channel})"


def _insight_line(insight: Insight, videos: dict[str, VideoSource]) -> str:
    cites = []
    for citation in insight.source_citations:
        video = videos.get(citation.video_id)
        title = video.title if video else citation.video_id
        cites.append(f"{title} @ {format_timestamp(citation.start_seconds)}")
    return (
        f"### {insight.title} (importance={insight.importance:.2f})\n"
        f"{insight.explanation}\n"
        f"Sources: {'; '.join(cites) or 'none'}"
    )


async def create(
    insights: list[Insight],
    videos: list[VideoSource],
    *,
    target_minutes: int,
    focus: str,
    expertise: str,
    style: PodcastStyle | str,
) -> PodcastScriptResult:
    style_enum = PodcastStyle(style)
    videos_by_id = {video.video_id: video for video in videos}
    words = target_words(target_minutes)
    insight_block = "\n\n".join(_insight_line(insight, videos_by_id) for insight in insights)
    key = cache_key("script", target_minutes, focus, expertise, style_enum.value, insight_block)

    async def _load() -> PodcastScriptResult:
        prompt = f"""Write a two-host podcast script grounded ONLY in the insights below.

HOST_A = knowledgeable technical host
HOST_B = curious engineer who asks useful questions

Target length: {target_minutes} minutes ≈ {words} spoken words (allow ±15%).

User focus: {focus}
Audience expertise: {expertise}
Style: {style_enum.value}. {STYLE_GUIDANCE[style_enum]}

Structure:
1. 20-30 second introduction
2. 3-6 major themes
3. Transitions that compare or connect sources
4. Explicit disagreements when talks conflict
5. Practical takeaways
6. 20-30 second conclusion

Rules:
- Never introduce technical factual claims unsupported by the insights.
- Do not fabricate benchmarks or numbers.
- Hosts may briefly interpret, but must mark interpretation as theirs.
- Mention source talks by title when citing, e.g. "In the first talk, around the 32-minute mark..."
- Do NOT speak raw URLs or citation IDs.
- Do NOT be overly enthusiastic or cheesy.
- Format EVERY line as:
HOST_A: ...
HOST_B: ...
- Alternate speakers. No narrator lines.

Sources:
{chr(10).join(_source_line(video) for video in videos)}

Insights:
{insight_block}
"""
        return await complete_json(prompt, PodcastScriptResult, temperature=0.5)

    return await get_or_set_model("script", key, PodcastScriptResult, _load)
