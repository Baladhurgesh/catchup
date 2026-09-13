from __future__ import annotations

from models import CatchUpJob, EpisodeEval, JobResult, PodcastEpisode, VideoSource
from util import format_duration, format_timestamp, youtube_timestamp_url


def catchup_modal() -> dict:
    return {
        "type": "modal",
        "callback_id": "catchup_submit",
        "title": {"type": "plain_text", "text": "CatchUp"},
        "submit": {"type": "plain_text", "text": "Generate"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "urls_block",
                "label": {"type": "plain_text", "text": "YouTube URLs"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "urls_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...",
                    },
                },
            },
            {
                "type": "input",
                "block_id": "minutes_block",
                "label": {"type": "plain_text", "text": "Target podcast minutes"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "minutes_input",
                    "initial_value": "10",
                },
            },
            {
                "type": "input",
                "block_id": "focus_block",
                "label": {"type": "plain_text", "text": "Focus / instructions"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "focus_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Focus on inference optimization. Skip transformer intros.",
                    },
                },
            },
            {
                "type": "input",
                "block_id": "expertise_block",
                "label": {"type": "plain_text", "text": "Audience expertise"},
                "element": {
                    "type": "static_select",
                    "action_id": "expertise_select",
                    "initial_option": _option("Intermediate", "intermediate"),
                    "options": [
                        _option("Beginner", "beginner"),
                        _option("Intermediate", "intermediate"),
                        _option("Expert", "expert"),
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "style_block",
                "label": {"type": "plain_text", "text": "Podcast style"},
                "element": {
                    "type": "static_select",
                    "action_id": "style_select",
                    "initial_option": _option("Conversational", "conversational"),
                    "options": [
                        _option("Concise", "concise"),
                        _option("Conversational", "conversational"),
                        _option("Technical", "technical"),
                        _option("Debate", "debate"),
                    ],
                },
            },
        ],
    }


def start_button_blocks() -> list[dict]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "🎧 *CatchUp* turns YouTube talks into a short podcast.\n"
                    "Click below to add URLs, focus, and target length."
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Start CatchUp"},
                    "style": "primary",
                    "action_id": "open_catchup_modal",
                }
            ],
        },
    ]


def home_view() -> dict:
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "CatchUp"},
            },
            *start_button_blocks(),
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "You can also use the lightning-bolt shortcut *CatchUp*, or `/catchup` once that command is created.",
                    }
                ],
            },
        ],
    }


def progress_blocks(text: str) -> list[dict]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        }
    ]


def result_blocks(result: JobResult) -> list[dict]:
    episode = result.episode
    evaluation = result.evaluation
    if episode is None:
        return progress_blocks("CatchUp finished without an episode.")

    source_minutes = sum(video.duration_seconds for video in episode.sources)
    podcast_label = f"{episode.target_minutes}m target"
    if evaluation:
        spoken_minutes = max(1, round(evaluation.actual_words / 150))
        podcast_label = f"{spoken_minutes}m spoken"

    bullets = "\n".join(f"• {item}" for item in episode.made_the_cut[:6]) or "• Key ideas from the talks"
    skipped = "\n".join(f"• {item}" for item in episode.skipped[:4])
    coverage = ""
    if evaluation:
        coverage = (
            f"*Source coverage:* {evaluation.source_coverage}/{evaluation.source_total} videos\n"
            f"*Grounded claims:* {evaluation.grounded_claim_count}\n"
            f"*Compression:* {format_duration(source_minutes)} → {podcast_label}"
        )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Your CatchUp is ready"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"🎧 *Your CatchUp is ready*\n\n"
                    f"*{episode.title}*\n"
                    f"`{format_duration(source_minutes)} → {podcast_label}`\n\n"
                    f"I analyzed *{len(episode.sources)} YouTube talks* and condensed the sections most relevant to:\n"
                    f"> {result.job.focus}"
                ),
            },
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*What made the cut*\n{bullets}"},
        },
    ]
    if skipped:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Skipped*\n{skipped}"},
            }
        )
    if coverage:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": coverage}})

    links = []
    if result.drive_url:
        links.append(f"🎧 *Listen to podcast*\n<{result.drive_url}|Google Drive>")
    if result.notion_url:
        links.append(f"📚 *Notes + timestamped sources*\n<{result.notion_url}|Notion>")
    if links:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(links)}})

    if result.warnings:
        warning_text = "\n".join(f"• {item}" for item in result.warnings[:5])
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"⚠️ {warning_text}"}],
            }
        )

    actions = []
    if result.drive_url:
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Listen"},
                "url": result.drive_url,
                "action_id": "listen_drive",
            }
        )
    elif result.mp3_path:
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Listen"},
                "action_id": "listen_info",
                "value": result.job.job_id,
            }
        )
    if result.notion_url:
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open Notes"},
                "url": result.notion_url,
                "action_id": "open_notes",
            }
        )
    actions.append(
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "Show Sources"},
            "action_id": "show_sources",
            "value": result.job.job_id,
        }
    )
    blocks.append({"type": "actions", "block_id": "catchup_actions", "elements": actions})
    return blocks


def sources_blocks(episode: PodcastEpisode) -> list[dict]:
    lines = []
    for index, video in enumerate(episode.sources, start=1):
        lines.append(f"{index}. <{video.url}|{video.title}> — {video.channel}")
    for insight in episode.insights[:8]:
        cites = []
        for citation in insight.source_citations[:3]:
            video = _video(episode.sources, citation.video_id)
            label = video.title if video else citation.video_id
            url = youtube_timestamp_url(citation.video_id, citation.start_seconds)
            cites.append(f"<{url}|{label} {format_timestamp(citation.start_seconds)}>")
        if cites:
            lines.append(f"• *{insight.title}*: {', '.join(cites)}")
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Sources*\n" + "\n".join(lines)},
        }
    ]


def _video(videos: list[VideoSource], video_id: str) -> VideoSource | None:
    for video in videos:
        if video.video_id == video_id:
            return video
    return None


def _option(label: str, value: str) -> dict:
    return {"text": {"type": "plain_text", "text": label}, "value": value}


def parse_modal(view: dict) -> dict:
    values = view["state"]["values"]
    return {
        "urls": values["urls_block"]["urls_input"]["value"] or "",
        "minutes": values["minutes_block"]["minutes_input"]["value"] or "10",
        "focus": values["focus_block"]["focus_input"]["value"] or "",
        "expertise": values["expertise_block"]["expertise_select"]["selected_option"]["value"],
        "style": values["style_block"]["style_select"]["selected_option"]["value"],
    }


def validate_modal(form: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    from util import parse_youtube_urls

    if not parse_youtube_urls(form["urls"]):
        errors["urls_block"] = "Add at least one valid YouTube URL"
    try:
        minutes = int(form["minutes"])
        if minutes < 3 or minutes > 30:
            errors["minutes_block"] = "Use a target between 3 and 30 minutes"
    except ValueError:
        errors["minutes_block"] = "Enter a whole number of minutes"
    if not form["focus"].strip():
        errors["focus_block"] = "Tell CatchUp what to focus on"
    return errors


def started_text(job: CatchUpJob) -> str:
    return (
        f"🎧 *CatchUp started.*\n\n"
        f"{len(job.urls)} videos received.\n"
        f"Target: {job.target_minutes} minutes\n"
        f"Focus: {job.focus}\n\n"
        f"⏳ Reading sources..."
    )
