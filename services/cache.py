from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from config import settings

T = TypeVar("T", bound=BaseModel)


def cache_key(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _path(namespace: str, key: str) -> Path:
    return settings.cache_dir / f"{namespace}_{key}.json"


def load_model(namespace: str, key: str, model: type[T]) -> T | None:
    if not settings.demo_mode or settings.force_regenerate:
        return None
    path = _path(namespace, key)
    if not path.exists():
        return None
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def save_model(namespace: str, key: str, value: BaseModel) -> None:
    if not settings.demo_mode:
        return
    path = _path(namespace, key)
    path.write_text(value.model_dump_json(indent=2), encoding="utf-8")


def load_json(namespace: str, key: str) -> object | None:
    if not settings.demo_mode or settings.force_regenerate:
        return None
    path = _path(namespace, key)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(namespace: str, key: str, value: object) -> None:
    if not settings.demo_mode:
        return
    path = _path(namespace, key)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


async def get_or_set_model(
    namespace: str,
    key: str,
    model: type[T],
    producer: Callable[[], Awaitable[T]],
) -> T:
    cached = load_model(namespace, key, model)
    if cached is not None:
        return cached
    value = await producer()
    save_model(namespace, key, value)
    return value


def cached_file_path(namespace: str, key: str, suffix: str) -> Path | None:
    if not settings.demo_mode or settings.force_regenerate:
        return None
    path = settings.cache_dir / f"{namespace}_{key}{suffix}"
    return path if path.exists() and path.stat().st_size > 1024 else None


def remember_file(namespace: str, key: str, source: Path, suffix: str) -> Path:
    dest = settings.cache_dir / f"{namespace}_{key}{suffix}"
    if settings.demo_mode and source.exists():
        dest.write_bytes(source.read_bytes())
    return dest
