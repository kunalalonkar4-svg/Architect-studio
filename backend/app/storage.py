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


def _check(key: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_\-./]+", key) or ".." in key.split("/"):
        raise ValueError("invalid storage key")


def put(key: str, data: bytes) -> tuple[str, int]:
    if settings.storage_backend == "db":
        return _db_put(key, data)
    p = _safe(key)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, p)
    return hashlib.sha256(data).hexdigest(), len(data)


def get(key: str) -> bytes:
    if settings.storage_backend == "db":
        return _db_get(key)
    return _safe(key).read_bytes()


def exists(key: str) -> bool:
    if settings.storage_backend == "db":
        return _db_exists(key)
    try:
        return _safe(key).exists()
    except ValueError:
        return False


def delete(key: str) -> None:
    if settings.storage_backend == "db":
        return _db_delete(key)
    try:
        _safe(key).unlink(missing_ok=True)
    except ValueError:
        pass


# ---- PostgreSQL-backed blobs (STORAGE_BACKEND=db): survive restarts on hosts with no persistent disk.
def _db_put(key: str, data: bytes) -> tuple[str, int]:
    from sqlalchemy import text
    from .db import engine
    _check(key)
    with engine.begin() as c:
        c.execute(text("INSERT INTO blobs(key, data) VALUES (:k, :d) ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data"), dict(k=key, d=data))
    return hashlib.sha256(data).hexdigest(), len(data)


def _db_get(key: str) -> bytes:
    from sqlalchemy import text
    from .db import engine
    _check(key)
    with engine.connect() as c:
        row = c.execute(text("SELECT data FROM blobs WHERE key = :k"), dict(k=key)).first()
    if row is None:
        raise FileNotFoundError(key)
    return bytes(row[0])


def _db_exists(key: str) -> bool:
    from sqlalchemy import text
    from .db import engine
    try:
        _check(key)
    except ValueError:
        return False
    with engine.connect() as c:
        return c.execute(text("SELECT 1 FROM blobs WHERE key = :k"), dict(k=key)).first() is not None


def _db_delete(key: str) -> None:
    from sqlalchemy import text
    from .db import engine
    try:
        _check(key)
    except ValueError:
        return
    with engine.begin() as c:
        c.execute(text("DELETE FROM blobs WHERE key = :k"), dict(k=key))
