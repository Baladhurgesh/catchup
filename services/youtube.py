from __future__ import annotations

from pydantic import BaseModel, Field

import httpx

from config import settings
from models import VideoSource
from services.cache import cache_key, get_or_set_model
from util import extract_video_id, parse_iso8601_duration


YOUTUBE_API = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeError(RuntimeError):
    pass


class VideoSourceList(BaseModel):
    items: list[VideoSource] = Field(default_factory=list)


def canonical_url(video_id: str, original: str | None = None) -> str:
    if original and extract_video_id(original) == video_id:
        return original
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_video_ids(urls: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url in urls:
        video_id = extract_video_id(url)
        if not video_id:
            raise YouTubeError(f"Could not parse a YouTube video ID from: {url}")
        if video_id in seen:
            continue
        seen.add(video_id)
        pairs.append((video_id, url))
    return pairs


def _map_item(item: dict, original_url: str | None = None) -> VideoSource:
    video_id = item["id"]
    snippet = item.get("snippet") or {}
    details = item.get("contentDetails") or {}
    return VideoSource(
        video_id=video_id,
        url=canonical_url(video_id, original_url),
        title=snippet.get("title") or video_id,
        channel=snippet.get("channelTitle") or "Unknown channel",
        duration_seconds=parse_iso8601_duration(details.get("duration") or "PT0S"),
        description=snippet.get("description") or None,
    )


async def fetch_metadata(urls: list[str]) -> list[VideoSource]:
    if not settings.youtube_api_key:
        raise YouTubeError("YOUTUBE_API_KEY is not set")

    pairs = parse_video_ids(urls)
    if not pairs:
        raise YouTubeError("No YouTube URLs provided")
    if len(pairs) > settings.max_videos:
        raise YouTubeError(f"Please submit at most {settings.max_videos} videos")

    key = cache_key("yt-meta", *[video_id for video_id, _ in pairs])

    async def _load() -> VideoSourceList:
        ids = [video_id for video_id, _ in pairs]
        url_by_id = {video_id: url for video_id, url in pairs}
        params = {
            "part": "snippet,contentDetails",
            "id": ",".join(ids),
            "key": settings.youtube_api_key,
        }
        timeout = httpx.Timeout(settings.request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(YOUTUBE_API, params=params)
            try:
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                raise YouTubeError(f"YouTube Data API request failed: {exc}") from exc

        if payload.get("error"):
            message = payload["error"].get("message", "unknown YouTube API error")
            raise YouTubeError(f"YouTube Data API error: {message}")

        items = payload.get("items") or []
        found = {item["id"] for item in items}
        missing = [video_id for video_id, _ in pairs if video_id not in found]
        if missing:
            raise YouTubeError(f"YouTube videos not found: {', '.join(missing)}")

        return VideoSourceList(
            items=[_map_item(item, url_by_id.get(item["id"])) for item in items]
        )

    return (await get_or_set_model("youtube", key, VideoSourceList, _load)).items
