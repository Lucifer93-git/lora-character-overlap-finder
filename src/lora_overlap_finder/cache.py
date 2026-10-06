from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .models import LoraRecord


def cache_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    folder = base / "LoRACharacterOverlapFinder"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "cache.sqlite3"


class Cache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or cache_path()
        self.db = sqlite3.connect(self.path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                sha256 TEXT, metadata TEXT NOT NULL, sidecar TEXT NOT NULL
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS civitai (
                sha256 TEXT PRIMARY KEY, payload TEXT, checked INTEGER NOT NULL DEFAULT 1
            )"""
        )
        self.db.commit()

    def load_file(self, path: Path, size: int, mtime_ns: int) -> LoraRecord | None:
        row = self.db.execute(
            "SELECT sha256, metadata, sidecar FROM files WHERE path=? AND size=? AND mtime_ns=?",
            (str(path), size, mtime_ns),
        ).fetchone()
        if not row:
            return None
        return LoraRecord(
            path=path, file_size=size, sha256=row[0],
            metadata=json.loads(row[1]), sidecar_metadata=json.loads(row[2]),
            from_cache=True,
        )

    def save_file(self, record: LoraRecord, mtime_ns: int) -> None:
        self.db.execute(
            """INSERT INTO files(path,size,mtime_ns,sha256,metadata,sidecar)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET size=excluded.size, mtime_ns=excluded.mtime_ns,
               sha256=excluded.sha256, metadata=excluded.metadata, sidecar=excluded.sidecar""",
            (str(record.path), record.file_size, mtime_ns, record.sha256,
             json.dumps(record.metadata), json.dumps(record.sidecar_metadata)),
        )
        self.db.commit()

    def get_civitai(self, sha256: str) -> tuple[bool, dict[str, Any] | None]:
        row = self.db.execute("SELECT payload FROM civitai WHERE sha256=?", (sha256.upper(),)).fetchone()
        if row is None:
            return False, None
        return True, json.loads(row[0]) if row[0] else None

    def save_civitai(self, sha256: str, payload: dict[str, Any] | None) -> None:
        self.db.execute(
            """INSERT INTO civitai(sha256,payload) VALUES(?,?)
               ON CONFLICT(sha256) DO UPDATE SET payload=excluded.payload""",
            (sha256.upper(), json.dumps(payload) if payload is not None else None),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
