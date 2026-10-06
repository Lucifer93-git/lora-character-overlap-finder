from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LoraRecord:
    path: Path
    sha256: str | None = None
    file_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    sidecar_metadata: dict[str, Any] = field(default_factory=dict)
    civitai_model_id: int | None = None
    civitai_model_version_id: int | None = None
    base_model: str | None = None
    trained_words: list[str] = field(default_factory=list)
    character_candidates: list[str] = field(default_factory=list)
    scan_errors: list[str] = field(default_factory=list)
    from_cache: bool = False
    classification: str = "character"
