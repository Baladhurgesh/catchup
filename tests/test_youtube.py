from util import extract_video_id, parse_iso8601_duration, parse_youtube_urls
from services.youtube import _map_item, parse_video_ids


def test_extract_video_id_from_watch_url() -> None:
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9wgXcQ") == "dQw4w9wgXcQ"


def test_extract_video_id_from_short_url() -> None:
    assert extract_video_id("https://youtu.be/dQw4w9wgXcQ") == "dQw4w9wgXcQ"


def test_parse_youtube_urls_dedupes() -> None:
    raw = """
    https://www.youtube.com/watch?v=dQw4w9wgXcQ
    https://youtu.be/dQw4w9wgXcQ
    https://www.youtube.com/watch?v=aaaaaaaaaaa
    """
    urls = parse_youtube_urls(raw)
    assert len(urls) == 2
    assert extract_video_id(urls[1]) == "aaaaaaaaaaa"


def test_parse_iso8601_duration() -> None:
    assert parse_iso8601_duration("PT15M33S") == 933
    assert parse_iso8601_duration("PT2H41M") == 9660
    assert parse_iso8601_duration("PT45S") == 45


def test_map_youtube_item() -> None:
    source = _map_item(
        {
            "id": "dQw4w9wgXcQ",
            "snippet": {
                "title": "Never Gonna Give You Up",
                "channelTitle": "Rick Astley",
                "description": "Official video",
            },
            "contentDetails": {"duration": "PT3M33S"},
        }
    )
    assert source.video_id == "dQw4w9wgXcQ"
    assert source.channel == "Rick Astley"
    assert source.duration_seconds == 213


def test_parse_video_ids_skips_duplicates() -> None:
    pairs = parse_video_ids(
        [
            "https://www.youtube.com/watch?v=dQw4w9wgXcQ",
            "https://youtu.be/dQw4w9wgXcQ",
        ]
    )
    assert pairs == [("dQw4w9wgXcQ", "https://www.youtube.com/watch?v=dQw4w9wgXcQ")]
