"""Private artifact storage on local disk (swap for an object store in production). Files are never
served directly; every download passes through an authorised API route."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from .config import settings


def _safe(key: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_\-./]+", key) or ".." in key.split("/"):
        raise ValueError("invalid storage key")
    p = (settings.storage_dir / key).resolve()
    if settings.storage_dir not in p.parents:
        raise ValueError("invalid storage key")
    return p


def put(key: str, data: bytes) -> tuple[str, int]:
    p = _safe(key)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)
    return hashlib.sha256(data).hexdigest(), len(data)


def get(key: str) -> bytes:
    return _safe(key).read_bytes()


def exists(key: str) -> bool:
    try:
        return _safe(key).exists()
    except ValueError:
        return False


def delete(key: str) -> None:
    try:
        _safe(key).unlink(missing_ok=True)
    except ValueError:
        pass
