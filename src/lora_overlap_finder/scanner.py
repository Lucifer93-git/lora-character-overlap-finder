from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Iterable

from .cache import Cache
from .models import LoraRecord

SIDECAR_SUFFIXES = (".json", ".civitai.info")


def iter_lora_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.safetensors")


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_embedded_metadata(path: Path) -> dict:
    # Safetensors starts with an unsigned 64-bit little-endian JSON header length.
    # Reading it directly avoids importing PyTorch just to inspect metadata.
    with path.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError("Invalid safetensors header")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length > 100 * 1024 * 1024:
            raise ValueError("Safetensors header is unexpectedly large")
        header = json.loads(handle.read(header_length))
    metadata = header.get("__metadata__", {})
    return dict(metadata) if isinstance(metadata, dict) else {}


def _candidate_sidecars(path: Path) -> Iterable[Path]:
    stem = path.with_suffix("")
    for suffix in SIDECAR_SUFFIXES:
        yield stem.with_suffix(suffix)
    yield Path(str(path) + ".json")


def read_sidecar_metadata(path: Path) -> dict:
    merged: dict = {}
    for candidate in _candidate_sidecars(path):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                merged[candidate.name] = data
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
    return merged


def scan_lora(path: Path, cache: Cache | None = None) -> LoraRecord:
    stat = path.stat()
    if cache:
        cached = cache.load_file(path, stat.st_size, stat.st_mtime_ns)
        if cached is not None:
            cached.classification = cache.get_classification(path)
            return cached

    record = LoraRecord(path=path, file_size=stat.st_size)
    if cache:
        record.classification = cache.get_classification(path)
    try:
        record.sha256 = sha256_file(path)
    except OSError as exc:
        record.scan_errors.append(f"Hashing failed: {exc}")
    try:
        record.metadata = read_embedded_metadata(path)
    except Exception as exc:
        record.scan_errors.append(f"Metadata read failed: {exc}")
    record.sidecar_metadata = read_sidecar_metadata(path)
    if cache:
        cache.save_file(record, stat.st_mtime_ns)
    return record


def scan_folder(root: Path, cache: Cache | None = None) -> list[LoraRecord]:
    return [scan_lora(path, cache=cache) for path in iter_lora_files(root)]
