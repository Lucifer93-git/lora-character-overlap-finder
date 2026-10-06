from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .civitai import CivitaiClient
from .models import LoraRecord

STOP_WORDS = {
    "lora", "locon", "lycoris", "dora", "character", "characters", "pack", "set",
    "model", "style", "version", "ver", "v1", "v2", "v3", "sdxl", "pony",
    "illustrious", "flux", "anime", "trained", "trigger", "woman", "man", "girl",
    "boy", "solo", "1girl", "1boy", "masterpiece", "best", "quality",
}
GENERIC_TRIGGERS = {
    "1girl", "1boy", "solo", "female", "male", "woman", "man", "masterpiece",
    "best quality", "high quality", "looking at viewer",
}


@dataclass(slots=True)
class Candidate:
    name: str
    normalized: str
    score: int
    evidence: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Overlap:
    character: str
    confidence: str
    records: list[LoraRecord]
    evidence: str


def normalize_name(value: str) -> str:
    value = html.unescape(value).casefold()
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("_", " ").replace("-", " ")
    value = re.sub(r"\b(?:v|ver|version)\s*\d+(?:\.\d+)*\b", " ", value)
    value = re.sub(r"\b(?:sdxl|sd15|sd1\.5|pony|illustrious|flux)\b", " ", value)
    value = re.sub(r"[^a-z0-9\s']", " ", value)
    words = [w for w in value.split() if w not in STOP_WORDS and len(w) > 1]
    return " ".join(words).strip()


def _humanize(value: str) -> str:
    value = re.sub(r"[_\-]+", " ", value).strip()
    return re.sub(r"\s+", " ", value)


def _add(store: dict[str, Candidate], value: str, score: int, evidence: str) -> None:
    display = _humanize(value)
    normalized = normalize_name(display)
    if not normalized or normalized in GENERIC_TRIGGERS or len(normalized) < 3:
        return
    item = store.get(normalized)
    if item is None:
        store[normalized] = Candidate(display, normalized, score, {evidence})
    else:
        item.score = max(item.score, score)
        item.evidence.add(evidence)


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _metadata_triggers(record: LoraRecord) -> list[str]:
    triggers: list[str] = []
    keys = ("trainedWords", "trained_words", "ss_tag_frequency", "trigger_words")
    blobs = [record.metadata, record.sidecar_metadata]
    for blob in blobs:
        for key in keys:
            raw = blob.get(key) if isinstance(blob, dict) else None
            if isinstance(raw, list):
                triggers.extend(str(x) for x in raw)
            elif isinstance(raw, str):
                try:
                    decoded = json.loads(raw)
                    if isinstance(decoded, list):
                        triggers.extend(str(x) for x in decoded)
                except json.JSONDecodeError:
                    pass
    return triggers


def candidates_from_record(record: LoraRecord) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    _add(found, record.path.stem, 45, "filename")

    for trigger in _metadata_triggers(record):
        _add(found, trigger, 70, "embedded trigger")

    for text in _walk_strings(record.sidecar_metadata):
        # Sidecars often contain explicit trainedWords arrays and model names.
        if len(text) <= 80:
            _add(found, text, 35, "sidecar metadata")

    for trigger in record.trained_words:
        _add(found, trigger, 90, "Civitai trained word")

    model_name = record.metadata.get("_civitai_model_name")
    if isinstance(model_name, str):
        _add(found, model_name, 85, "Civitai model name")

    return sorted(found.values(), key=lambda c: (-c.score, c.normalized))


def enrich_from_civitai(records: list[LoraRecord], client: CivitaiClient | None = None) -> None:
    client = client or CivitaiClient()
    hashed = [record for record in records if record.sha256]
    if not hashed:
        return

    versions = client.get_model_versions_by_hashes([r.sha256 for r in hashed if r.sha256])
    by_hash: dict[str, dict] = {}
    for version in versions:
        for file in version.get("files", []):
            sha = ((file.get("hashes") or {}).get("SHA256") or "").upper()
            if sha:
                by_hash[sha] = version

    model_cache: dict[int, dict] = {}
    for record in hashed:
        version = by_hash.get((record.sha256 or "").upper())
        if not version:
            continue
        record.civitai_model_version_id = version.get("id")
        record.civitai_model_id = version.get("modelId")
        record.base_model = version.get("baseModel")
        record.trained_words = [str(x) for x in version.get("trainedWords", []) if x]
        model = version.get("model") or {}
        if model.get("name"):
            record.metadata["_civitai_model_name"] = str(model["name"])

        mid = record.civitai_model_id
        if mid:
            if mid not in model_cache:
                try:
                    model_cache[mid] = client.get_model(mid) or {}
                except Exception:
                    model_cache[mid] = {}
            full = model_cache[mid]
            if full.get("name"):
                record.metadata["_civitai_model_name"] = str(full["name"])
            tags = full.get("tags")
            if isinstance(tags, list):
                record.metadata["_civitai_tags"] = tags


def detect_overlaps(records: list[LoraRecord]) -> list[Overlap]:
    candidates: dict[int, list[Candidate]] = {}
    for index, record in enumerate(records):
        candidates[index] = candidates_from_record(record)
        record.character_candidates = [c.normalized for c in candidates[index] if c.score >= 70]

    groups: dict[str, list[tuple[int, Candidate]]] = defaultdict(list)
    for index, items in candidates.items():
        for candidate in items:
            if candidate.score >= 70:
                groups[candidate.normalized].append((index, candidate))

    overlaps: list[Overlap] = []
    for key, matches in groups.items():
        unique_indices = sorted({idx for idx, _ in matches})
        if len(unique_indices) < 2:
            continue
        best = max((candidate for _, candidate in matches), key=lambda c: c.score)
        min_score = min(max(c.score for i, c in matches if i == idx) for idx in unique_indices)
        confidence = "High" if min_score >= 85 else "Medium"
        evidence = "; ".join(sorted({e for _, c in matches for e in c.evidence}))
        overlaps.append(
            Overlap(
                character=best.name,
                confidence=confidence,
                records=[records[idx] for idx in unique_indices],
                evidence=evidence,
            )
        )

    # Same Civitai model is a strong relation even if its trigger words changed.
    model_groups: dict[int, list[LoraRecord]] = defaultdict(list)
    for record in records:
        if record.civitai_model_id:
            model_groups[record.civitai_model_id].append(record)
    for model_id, items in model_groups.items():
        if len(items) > 1:
            overlaps.append(
                Overlap(
                    character=f"Civitai model {model_id}",
                    confidence="High",
                    records=items,
                    evidence="same Civitai model ID",
                )
            )

    return sorted(overlaps, key=lambda x: (-len(x.records), x.character.casefold()))
