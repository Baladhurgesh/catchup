from __future__ import annotations

import json
from pathlib import Path

from config import settings
from models import PodcastEpisode
from util import dated_filename

FOLDER_NAME = "CatchUp Podcasts"
FOLDER_MIME = "application/vnd.google-apps.folder"
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]


class DriveError(RuntimeError):
    pass


def _oauth_token_path() -> Path:
    return Path(settings.google_oauth_token_file).expanduser()


def _oauth_client_path() -> Path | None:
    raw = settings.google_oauth_client_file.strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.exists() else None


def is_configured() -> bool:
    if _oauth_token_path().exists():
        return True
    path = settings.google_service_account_file.strip()
    return bool(path) and Path(path).expanduser().exists()


def _user_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = _oauth_token_path()
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), DRIVE_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds if creds and creds.valid else None


def _oauth_client_config(client_path: Path) -> dict:
    raw = json.loads(client_path.read_text(encoding="utf-8"))
    if "installed" in raw:
        block = raw["installed"]
    elif "web" in raw:
        block = raw["web"]
    else:
        raise DriveError(
            f"{client_path} is not a Google OAuth client JSON (expected keys 'installed' or 'web')."
        )
    client_id = str(block.get("client_id") or "")
    if ".apps.googleusercontent.com" not in client_id:
        raise DriveError(
            f"{client_path} has an invalid client_id ({client_id!r}). "
            "Download a fresh OAuth client JSON from Google Cloud "
            "(APIs & Services → Credentials → Create OAuth client ID → Desktop app)."
        )
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": block.get("client_secret"),
            "auth_uri": block.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": block.get("token_uri", "https://oauth2.googleapis.com/token"),
            "redirect_uris": ["http://localhost"],
        }
    }


def authorize_user() -> Path:
    """Open a browser once and store a user OAuth token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise DriveError("Install google-auth-oauthlib") from exc

    client_path = _oauth_client_path()
    if client_path is None:
        raise DriveError(
            "Set GOOGLE_OAUTH_CLIENT_FILE to an OAuth client JSON and make sure the file exists."
        )
    flow = InstalledAppFlow.from_client_config(_oauth_client_config(client_path), DRIVE_SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    token_path = _oauth_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return token_path


def _service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise DriveError("Install google-api-python-client and google-auth") from exc

    creds = _user_credentials()
    if creds is None:
        creds_path = Path(settings.google_service_account_file).expanduser()
        if not creds_path.exists():
            raise DriveError(
                "Drive is not authorized. Run: python scripts/auth_google_drive.py"
            )
        creds = service_account.Credentials.from_service_account_file(
            str(creds_path),
            scopes=DRIVE_SCOPES,
        )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _drive_kwargs() -> dict:
    return {"supportsAllDrives": True}


def _folder_accessible(service, folder_id: str) -> bool:
    try:
        service.files().get(
            fileId=folder_id,
            fields="id, name",
            **_drive_kwargs(),
        ).execute()
        return True
    except Exception:
        return False


def _using_user_oauth() -> bool:
    return _oauth_token_path().exists()


def _find_or_create_folder(service, name: str = FOLDER_NAME) -> str:
    configured = settings.google_drive_folder_id.strip()
    if configured and _folder_accessible(service, configured):
        return configured

    if _using_user_oauth():
        query = f"name='{name}' and mimeType='{FOLDER_MIME}' and trashed=false"
        found = (
            service.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
            .execute()
            .get("files")
            or []
        )
        if found:
            return found[0]["id"]
        created = (
            service.files()
            .create(body={"name": name, "mimeType": FOLDER_MIME}, fields="id")
            .execute()
        )
        return created["id"]

    if configured:
        raise DriveError(
            f"Drive folder {configured} is not writable with a service account. "
            "Personal Google accounts cannot give service accounts storage quota. "
            "Run python scripts/auth_google_drive.py instead."
        )
    raise DriveError(
        "Personal Google accounts block service-account uploads. "
        "Create a Desktop OAuth client and run python scripts/auth_google_drive.py"
    )


def _share_and_link(service, file_id: str) -> str:
    try:
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            **_drive_kwargs(),
        ).execute()
    except Exception:
        pass
    meta = (
        service.files()
        .get(fileId=file_id, fields="webViewLink,webContentLink", **_drive_kwargs())
        .execute()
    )
    return meta.get("webViewLink") or meta.get("webContentLink") or ""


def upload_file(path: Path, *, mime_type: str, name: str | None = None) -> str:
    if not is_configured():
        raise DriveError("Google Drive is not configured")
    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise DriveError("Install google-api-python-client") from exc

    try:
        service = _service()
        folder_id = _find_or_create_folder(service)
        media = MediaFileUpload(str(path), mimetype=mime_type, resumable=True)
        created = (
            service.files()
            .create(
                body={"name": name or path.name, "parents": [folder_id]},
                media_body=media,
                fields="id",
                **_drive_kwargs(),
            )
            .execute()
        )
        link = _share_and_link(service, created["id"])
    except DriveError:
        raise
    except Exception as exc:
        message = str(exc)
        if "storageQuotaExceeded" in message or "do not have storage quota" in message:
            raise DriveError(
                "Google blocked the service-account upload (no Drive quota). "
                "Create a Desktop OAuth client and run: python scripts/auth_google_drive.py"
            ) from exc
        raise DriveError(f"Drive upload failed: {exc}") from exc
    if not link:
        raise DriveError("Drive upload succeeded but no shareable link was returned")
    return link


def upload_episode(episode: PodcastEpisode, mp3_path: Path) -> str:
    drive_url = upload_file(
        mp3_path,
        mime_type="audio/mpeg",
        name=dated_filename(episode.title, ".mp3"),
    )
    try:
        sources_path = settings.cache_dir / dated_filename(episode.title, "_sources.json")
        sources_path.write_text(
            json.dumps([source.model_dump() for source in episode.sources], indent=2),
            encoding="utf-8",
        )
        upload_file(
            sources_path,
            mime_type="application/json",
            name=dated_filename(episode.title, "_sources.json"),
        )
    except Exception:
        pass
    return drive_url
