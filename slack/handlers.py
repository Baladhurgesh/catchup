from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path

from slack_bolt import App
from slack_sdk.errors import SlackApiError

from agent.orchestrator import new_job, process_job
from models import JobResult
from slack.blocks import (
    catchup_modal,
    home_view,
    parse_modal,
    progress_blocks,
    result_blocks,
    sources_blocks,
    start_button_blocks,
    started_text,
    validate_modal,
)
from util import parse_youtube_urls

logger = logging.getLogger(__name__)

_RESULTS: dict[str, JobResult] = {}


def _open_modal(client, trigger_id: str, channel_id: str | None, user_id: str | None) -> None:
    view = catchup_modal()
    view["private_metadata"] = json.dumps(
        {
            "channel_id": channel_id or user_id,
            "user_id": user_id,
        }
    )
    client.views_open(trigger_id=trigger_id, view=view)


def register(app: App) -> None:
    @app.command("/catchup")
    def open_modal(ack, body, client, logger):  # type: ignore[no-untyped-def]
        ack()
        _open_modal(client, body["trigger_id"], body.get("channel_id"), body.get("user_id"))

    @app.shortcut("catchup_open")
    def open_from_shortcut(ack, body, client):  # type: ignore[no-untyped-def]
        ack()
        _open_modal(
            client,
            body["trigger_id"],
            body.get("channel", {}).get("id") if isinstance(body.get("channel"), dict) else None,
            body.get("user", {}).get("id"),
        )

    @app.action("open_catchup_modal")
    def open_from_button(ack, body, client):  # type: ignore[no-untyped-def]
        ack()
        channel = body.get("channel") or {}
        _open_modal(
            client,
            body["trigger_id"],
            channel.get("id"),
            body.get("user", {}).get("id"),
        )

    @app.event("app_home_opened")
    def show_home(event, client):  # type: ignore[no-untyped-def]
        client.views_publish(user_id=event["user"], view=home_view())

    @app.event("app_mention")
    def mention_start(event, client, say):  # type: ignore[no-untyped-def]
        say(
            text="Click Start CatchUp to generate a podcast.",
            blocks=start_button_blocks(),
            thread_ts=event.get("ts"),
        )

    @app.event("message")
    def dm_start(event, say):  # type: ignore[no-untyped-def]
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id") or event.get("subtype"):
            return
        say(
            text="Click Start CatchUp to generate a podcast.",
            blocks=start_button_blocks(),
        )

    @app.view("catchup_submit")
    def handle_submit(ack, body, client, view, logger):  # type: ignore[no-untyped-def]
        form = parse_modal(view)
        errors = validate_modal(form)
        if errors:
            ack(response_action="errors", errors=errors)
            return
        ack()

        meta = json.loads(view.get("private_metadata") or "{}")
        job = new_job(
            parse_youtube_urls(form["urls"]),
            focus=form["focus"].strip(),
            target_minutes=int(form["minutes"]),
            expertise=form["expertise"],
            style=form["style"],
            channel_id=meta.get("channel_id"),
            user_id=meta.get("user_id"),
        )
        threading.Thread(
            target=_run_job,
            args=(client, job),
            daemon=True,
        ).start()

    @app.action("show_sources")
    def show_sources(ack, body, client):  # type: ignore[no-untyped-def]
        ack()
        job_id = body["actions"][0]["value"]
        result = _RESULTS.get(job_id)
        channel = body["channel"]["id"]
        thread_ts = body["message"].get("thread_ts") or body["message"]["ts"]
        if result is None or result.episode is None:
            client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Sources are no longer in memory. Re-run `/catchup`.",
            )
            return
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="CatchUp sources",
            blocks=sources_blocks(result.episode),
        )

    @app.action("listen_drive")
    @app.action("open_notes")
    def ack_link_buttons(ack):  # type: ignore[no-untyped-def]
        ack()

    @app.action("listen_info")
    def listen_info(ack, body, client):  # type: ignore[no-untyped-def]
        ack()
        channel = body["channel"]["id"]
        thread_ts = body["message"].get("thread_ts") or body["message"]["ts"]
        result = _RESULTS.get(body["actions"][0].get("value"))
        if result and result.drive_url:
            text = f"Listen here: {result.drive_url}"
        else:
            text = "The MP3 is attached in this thread."
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=text,
        )


def _run_job(client, job) -> None:  # type: ignore[no-untyped-def]
    try:
        posted = client.chat_postMessage(
            channel=job.channel_id,
            text=started_text(job),
            blocks=progress_blocks(started_text(job)),
        )
        job.thread_ts = posted["ts"]
    except SlackApiError as exc:
        logger.exception("Failed to post CatchUp start message: %s", exc)
        return

    async def update(message: str) -> None:
        try:
            client.chat_update(
                channel=job.channel_id,
                ts=job.thread_ts,
                text=message,
                blocks=progress_blocks(message),
            )
        except SlackApiError as exc:
            logger.warning("Failed to update Slack progress: %s", exc)

    result = asyncio.run(process_job(job, update_slack=update))
    _RESULTS[job.job_id] = result
    _complete(client, result)


def _complete(client, result: JobResult) -> None:
    job = result.job
    if result.episode is None:
        return

    try:
        client.chat_update(
            channel=job.channel_id,
            ts=job.thread_ts,
            text="🎧 Your CatchUp is ready",
            blocks=result_blocks(result),
        )
    except SlackApiError as exc:
        logger.warning("Failed to post CatchUp result: %s", exc)

    if result.mp3_path and Path(result.mp3_path).exists():
        try:
            uploaded = client.files_upload_v2(
                channel=job.channel_id,
                thread_ts=job.thread_ts,
                file=result.mp3_path,
                filename=Path(result.mp3_path).name,
                title=result.episode.title,
                initial_comment="🎧 Listen to your CatchUp podcast",
            )
            files = uploaded.get("files") or []
            if files:
                result.slack_file_url = files[0].get("permalink")
        except SlackApiError as exc:
            logger.warning("Slack file upload failed: %s", exc)
            try:
                client.chat_postMessage(
                    channel=job.channel_id,
                    thread_ts=job.thread_ts,
                    text=f"⚠️ Couldn't upload the MP3 to Slack: `{exc}`",
                )
            except SlackApiError:
                pass
    elif result.script_path:
        try:
            client.files_upload_v2(
                channel=job.channel_id,
                thread_ts=job.thread_ts,
                file=result.script_path,
                filename=Path(result.script_path).name,
                title=f"{result.episode.title} script",
                initial_comment="📄 Audio failed, so here is the grounded podcast script.",
            )
        except SlackApiError as exc:
            logger.warning("Slack script upload failed: %s", exc)
