from __future__ import annotations

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from config import settings
from slack.handlers import register


def create_app() -> App:
    kwargs = {"token": settings.slack_bot_token}
    if settings.slack_signing_secret:
        kwargs["signing_secret"] = settings.slack_signing_secret
    app = App(**kwargs)
    register(app)
    return app


def start() -> None:
    if not settings.slack_bot_token or not settings.slack_app_token:
        raise SystemExit(
            "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in .env before starting the bot."
        )
    handler = SocketModeHandler(create_app(), settings.slack_app_token)
    handler.start()
