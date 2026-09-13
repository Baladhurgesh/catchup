from pathlib import Path

import pytest

from config import settings


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "force_regenerate", False)
    monkeypatch.setattr(settings, "google_service_account_file", "")
    monkeypatch.setattr(settings, "google_drive_folder_id", "")
    monkeypatch.setattr(settings, "notion_token", "")
    monkeypatch.setattr(settings, "notion_parent_page_id", "")
