"""One-time Google user login for Drive uploads on a personal Gmail account."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def _ensure_project_venv() -> None:
    if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


_ensure_project_venv()

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.google_drive import authorize_user


if __name__ == "__main__":
    path = authorize_user()
    print(f"Saved Drive OAuth token to {path}")
    print("Re-run the local CatchUp Drive test after this.")
