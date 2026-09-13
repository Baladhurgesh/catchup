from __future__ import annotations

import re
from datetime import datetime

YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|"
    r"youtube\.com/shorts/|youtube\.com/live/)([A-Za-z0-9_-]{11})"
)
ISO_DURATION_RE = re.compile(
    r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def extract_video_id(url: str) -> str | None:
    text = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    match = YOUTUBE_ID_RE.search(text)
    return match.group(1) if match else None


def parse_youtube_urls(raw: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for line in raw.replace(",", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        video_id = extract_video_id(line)
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        if line.startswith("http"):
            urls.append(line)
        else:
            urls.append(f"https://www.youtube.com/watch?v={video_id}")
    return urls


def parse_iso8601_duration(value: str) -> int:
    match = ISO_DURATION_RE.fullmatch(value)
    if not match:
        return 0
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    if minutes:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    return f"{secs}s"


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def youtube_timestamp_url(video_id: str, start_seconds: float) -> str:
    return f"https://youtube.com/watch?v={video_id}&t={int(start_seconds)}s"


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def target_words(target_minutes: int) -> int:
    return target_minutes * 150


def slugify(text: str, max_length: int = 60) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return cleaned[:max_length] or "catchup-episode"


def dated_filename(title: str, suffix: str) -> str:
    date = datetime.now().strftime("%Y-%m-%d")
    return f"{date}_{slugify(title)}{suffix}"
