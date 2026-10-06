from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from safetensors import safe_open

from .models import LoraRecord


SIDECAR_SUFFIXES = (
    ".json",
    ".civitai.info",
)


def iter_lora_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.safetensors")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_embedded_metadata(path: Path) -> dict:
    with safe_open(path, framework="pt", device="cpu") as handle:
        return dict(handle.metadata() or {})


def _candidate_sidecars(path: Path) -> Iterable[Path]:
    # foo.safetensors -> foo.json / foo.civitai.info
    stem = path.with_suffix("")
    for suffix in SIDECAR_SUFFIXES:
        yield stem.with_suffix(suffix)

    # Some tools use foo.safetensors.json
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


def scan_lora(path: Path, with_hash: bool = True) -> LoraRecord:
    record = LoraRecord(path=path, file_size=path.stat().st_size)

    if with_hash:
        try:
            record.sha256 = sha256_file(path)
        except OSError as exc:
            record.scan_errors.append(f"Hashing failed: {exc}")

    try:
        record.metadata = read_embedded_metadata(path)
    except Exception as exc:  # safetensors may raise format-specific exceptions
        record.scan_errors.append(f"Metadata read failed: {exc}")

    record.sidecar_metadata = read_sidecar_metadata(path)
    return record


def scan_folder(root: Path, with_hash: bool = True) -> list[LoraRecord]:
    return [scan_lora(path, with_hash=with_hash) for path in iter_lora_files(root)]
