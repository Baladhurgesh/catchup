from __future__ import annotations

from datetime import date

from config import settings
from models import EpisodeEval, PodcastEpisode, VideoSource
from util import format_duration, format_timestamp, youtube_timestamp_url


class NotionError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.notion_token.strip() and settings.notion_parent_page_id.strip())


def _text(content: str, url: str | None = None) -> dict:
    payload: dict = {"type": "text", "text": {"content": content[:1900]}}
    if url:
        payload["text"]["link"] = {"url": url}
    return payload


def _rich(content: str, url: str | None = None) -> list[dict]:
    if not content:
        return [_text(" ")]
    chunks = [content[i : i + 1800] for i in range(0, len(content), 1800)]
    return [_text(chunk, url if index == 0 else None) for index, chunk in enumerate(chunks)]


def _paragraph(content: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich(content)}}


def _heading(content: str, level: int = 2) -> dict:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _rich(content)}}


def _bullet(content: str, url: str | None = None) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich(content, url)},
    }


def _is_real_description(text: str) -> bool:
    cleaned = " ".join(text.lower().split())
    if len(cleaned) < 12:
        return False
    placeholders = {
        "personalized recap of the submitted talks.",
        "local catchup integration test for drive and notion.",
    }
    return cleaned not in placeholders


def _fallback_lead(episode: PodcastEpisode, focus: str) -> str:
    titles = [video.title.strip() for video in episode.sources if video.title.strip()]
    if not titles:
        lead = "This CatchUp episode recaps the submitted talks."
    elif len(titles) == 1:
        lead = f'This CatchUp episode recaps "{titles[0]}."'
    else:
        quoted = ", ".join(f'"{title}"' for title in titles[:-1])
        lead = f'This CatchUp episode compares {quoted}, and "{titles[-1]}."'
    if focus.strip():
        lead += f" The focus is {focus.strip()}."
    return lead


def executive_summary_paragraphs(episode: PodcastEpisode, *, focus: str = "") -> list[str]:
    description = (episode.description or "").strip()
    lead = description if _is_real_description(description) else _fallback_lead(episode, focus)

    ranked = sorted(episode.insights, key=lambda insight: insight.importance, reverse=True)
    recap_parts: list[str] = []
    for insight in ranked[:5]:
        explanation = " ".join((insight.explanation or "").split())
        if explanation:
            first = explanation.split(". ")[0].rstrip(".")
            recap_parts.append(first)
        elif insight.title.strip():
            recap_parts.append(insight.title.strip().rstrip("."))

    paragraphs = [lead]
    if recap_parts:
        recap = " ".join(part.rstrip(".") + "." for part in recap_parts)
        if recap.lower() not in lead.lower():
            paragraphs.append(recap)
    return paragraphs


def build_blocks(
    episode: PodcastEpisode,
    *,
    focus: str,
    drive_url: str | None,
    evaluation: EpisodeEval | None,
) -> list[dict]:
    source_seconds = sum(video.duration_seconds for video in episode.sources)
    podcast_label = f"{episode.target_minutes}m target"
    if evaluation:
        spoken = max(1, round(evaluation.actual_words / 150))
        podcast_label = f"{spoken}m spoken"

    blocks: list[dict] = [
        _paragraph(f"Generated: {date.today().strftime('%B %d, %Y')}"),
        _paragraph(f"Original material: {format_duration(source_seconds)}"),
        _paragraph(f"Podcast: {podcast_label}"),
        _paragraph(f"Focus: {focus}"),
        _heading("Executive Summary", 2),
        *[
            _paragraph(paragraph)
            for paragraph in executive_summary_paragraphs(episode, focus=focus)
        ],
        _heading("Key Ideas", 2),
    ]

    for index, insight in enumerate(episode.insights[:12], start=1):
        blocks.append(_heading(f"{index}. {insight.title}", 3))
        blocks.append(_paragraph(insight.explanation))
        if insight.source_citations:
            blocks.append(_paragraph("Sources:"))
            for citation in insight.source_citations[:6]:
                video = _lookup(episode.sources, citation.video_id)
                label = video.title if video else citation.video_id
                stamp = format_timestamp(citation.start_seconds)
                url = youtube_timestamp_url(citation.video_id, citation.start_seconds)
                blocks.append(_bullet(f"{label} — {stamp}", url))

    blocks.append(_heading("Source Videos", 2))
    for index, video in enumerate(episode.sources, start=1):
        blocks.append(
            _bullet(
                f"{index}. {video.title} ({video.channel})",
                video.url,
            )
        )

    blocks.append(_heading("Podcast", 2))
    if drive_url:
        blocks.append(_bullet("Listen on Google Drive", drive_url))
    else:
        blocks.append(_paragraph("Audio is attached in the Slack thread."))
    return blocks[:100]


def _lookup(videos: list[VideoSource], video_id: str) -> VideoSource | None:
    for video in videos:
        if video.video_id == video_id:
            return video
    return None


def create_episode(
    episode: PodcastEpisode,
    *,
    focus: str,
    drive_url: str | None = None,
    evaluation: EpisodeEval | None = None,
) -> str:
    if not is_configured():
        raise NotionError("NOTION_TOKEN and NOTION_PARENT_PAGE_ID are not set")
    try:
        from notion_client import Client
    except ImportError as exc:
        raise NotionError("Install notion-client") from exc

    client = Client(auth=settings.notion_token, timeout_ms=int(settings.request_timeout_seconds * 1000))
    parent_id = settings.notion_parent_page_id.replace("-", "")
    title = f"CatchUp: {episode.title}"[:80]
    try:
        page = client.pages.create(
            parent={"type": "page_id", "page_id": parent_id},
            properties={"title": [{"type": "text", "text": {"content": title}}]},
            children=build_blocks(
                episode,
                focus=focus,
                drive_url=drive_url,
                evaluation=evaluation,
            ),
        )
    except Exception as exc:
        raise NotionError(
            f"Notion page create failed: {exc}. "
            "Open the parent page → Share → invite the CatchUp integration."
        ) from exc

    url = page.get("url")
    if not url:
        raise NotionError("Notion created a page but returned no URL")
    return str(url)
