"""Apply slack-manifest.yaml to the CatchUp Slack app.

Requires an app configuration token from:
https://api.slack.com/apps  →  Your App Configuration Tokens  →  Generate Token

Usage:
  SLACK_APP_CONFIG_TOKEN=xoxe-... python scripts/apply_slack_manifest.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

APP_ID = os.getenv("SLACK_APP_ID", "")
TOKEN = os.getenv("SLACK_APP_CONFIG_TOKEN", "")
MANIFEST_PATH = ROOT / "slack-manifest.yaml"


def main() -> None:
    if not TOKEN or not APP_ID:
        raise SystemExit(
            "Set SLACK_APP_ID and SLACK_APP_CONFIG_TOKEN in .env.\n"
            "Create the config token at https://api.slack.com/apps under Your App Configuration Tokens."
        )
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    payload = {
        "app_id": APP_ID,
        "manifest": json.dumps(manifest),
    }
    response = httpx.post(
        "https://slack.com/api/apps.manifest.update",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data=payload,
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise SystemExit(f"Slack rejected the manifest: {body.get('error')} {body}")
    print("Manifest applied. Reinstall the app from OAuth & Permissions, then run /catchup.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
