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
    "boy", "solo", "1girl", "1boy", "masterpiece", "best", "quality", "monochrome",
    "greyscale", "grayscale", "simple", "background", "white", "black", "rating",
    "safe", "general", "sensitive", "explicit", "source", "game", "cg",
    "apron", "ponytail", "eyes", "eye", "hair", "dress", "shirt", "skirt", "uniform",
}
GENERIC_TRIGGERS = {
    "1girl", "1boy", "solo", "female", "male", "woman", "man", "masterpiece",
    "best quality", "high quality", "looking at viewer", "monochrome", "greyscale",
    "grayscale", "white background", "simple background", "black background",
    "smile", "closed mouth", "open mouth", "long hair", "short hair", "blush",
    "standing", "sitting", "upper body", "full body", "portrait", "game cg",
    "official art", "official artwork", "screenshot", "visual novel",
    "apron", "ponytail", "black eyes", "blue eyes", "brown eyes", "green eyes",
    "red eyes", "blonde hair", "black hair", "brown hair", "red hair", "blue hair",
    "white hair", "grey hair", "gray hair",
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
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, raw in value.items():
                if key in keys:
                    if isinstance(raw, list):
                        triggers.extend(str(x) for x in raw)
                    elif isinstance(raw, str):
                        try:
                            decoded = json.loads(raw)
                            if isinstance(decoded, list):
                                triggers.extend(str(x) for x in decoded)
                            else:
                                triggers.append(raw)
                        except json.JSONDecodeError:
                            triggers.append(raw)
                visit(raw)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(record.metadata)
    visit(record.sidecar_metadata)
    return triggers


def candidates_from_record(record: LoraRecord) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    _add(found, record.path.stem, 45, "filename")


    for text in _walk_strings(record.sidecar_metadata):
        # Sidecars often contain explicit trainedWords arrays and model names.
        if len(text) <= 80:
            _add(found, text, 35, "sidecar metadata")


    model_name = record.metadata.get("_civitai_model_name")
    if isinstance(model_name, str):
        _add(found, model_name, 85, "Civitai model name")

    return sorted(found.values(), key=lambda c: (-c.score, c.normalized))


def _apply_civitai(record: LoraRecord, version: dict) -> None:
    record.civitai_model_version_id = version.get("id")
    record.civitai_model_id = version.get("modelId")
    record.base_model = version.get("baseModel")
    record.trained_words = [str(x) for x in version.get("trainedWords", []) if x]
    model = version.get("model") or {}
    if model.get("name"):
        record.metadata["_civitai_model_name"] = str(model["name"])
    tags = model.get("tags")
    if isinstance(tags, list):
        record.metadata["_civitai_tags"] = tags


def enrich_from_civitai(
    records: list[LoraRecord],
    client: CivitaiClient | None = None,
    cache=None,
) -> tuple[int, int]:
    client = client or CivitaiClient()
    hashed = [record for record in records if record.sha256]
    missing: list[LoraRecord] = []
    cache_hits = 0

    for record in hashed:
        if cache:
            found, payload = cache.get_civitai(record.sha256 or "")
            if found:
                cache_hits += 1
                if payload:
                    _apply_civitai(record, payload)
                continue
        missing.append(record)

    if not missing:
        return cache_hits, 0

    versions = client.get_model_versions_by_hashes([r.sha256 for r in missing if r.sha256])
    by_hash: dict[str, dict] = {}
    for version in versions:
        for file in version.get("files", []):
            sha = ((file.get("hashes") or {}).get("SHA256") or "").upper()
            if sha:
                by_hash[sha] = version

    for record in missing:
        sha = (record.sha256 or "").upper()
        version = by_hash.get(sha)
        if cache:
            cache.save_civitai(sha, version)
        if version:
            _apply_civitai(record, version)

    return cache_hits, len(missing)


def _record_identity_candidates(record: LoraRecord) -> list[Candidate]:
    return [c for c in candidates_from_record(record) if c.score >= 80 and "Civitai model name" in c.evidence]


def _is_pack(items: list[Candidate]) -> bool:
    # Multiple strong, distinct character-like identities are a good pack signal.
    strong = {c.normalized for c in items if c.score >= 85}
    return len(strong) >= 2


def detect_overlaps(records: list[LoraRecord]) -> list[Overlap]:
    candidates: dict[int, list[Candidate]] = {}
    packs: set[int] = set()
    for index, record in enumerate(records):
        if record.classification == "style":
            candidates[index] = []
            record.character_candidates = []
            continue
        items = _record_identity_candidates(record)
        candidates[index] = items
        record.character_candidates = [c.normalized for c in items]
        if _is_pack(items):
            packs.add(index)

    groups: dict[str, list[tuple[int, Candidate]]] = defaultdict(list)
    for index, items in candidates.items():
        for candidate in items:
            groups[candidate.normalized].append((index, candidate))

    overlaps: list[Overlap] = []
    for key, matches in groups.items():
        unique_indices = sorted({idx for idx, _ in matches})
        if len(unique_indices) < 2:
            continue

        # Prefer groups anchored by a multi-character pack. If no pack contains
        # the identity, multiple standalone LoRAs for the same character still group.
        pack_indices = [idx for idx in unique_indices if idx in packs]
        ordered = pack_indices + [idx for idx in unique_indices if idx not in packs]
        best = max((candidate for _, candidate in matches), key=lambda item: item.score)
        min_score = min(max(c.score for i, c in matches if i == idx) for idx in unique_indices)
        confidence = "High" if pack_indices or min_score >= 85 else "Medium"
        evidence_bits = {e for _, candidate in matches for e in candidate.evidence}
        if pack_indices:
            evidence_bits.add("multi-character pack cross-match")
        evidence = "; ".join(sorted(evidence_bits))
        overlaps.append(Overlap(
            character=best.name,
            confidence=confidence,
            records=[records[idx] for idx in ordered],
            evidence=evidence,
        ))

    # Same Civitai model is retained as a strong fallback relation.
    model_groups: dict[int, list[LoraRecord]] = defaultdict(list)
    for record in records:
        if record.classification != "style" and record.civitai_model_id:
            model_groups[record.civitai_model_id].append(record)
    for model_id, items in model_groups.items():
        if len(items) > 1:
            overlaps.append(Overlap(
                character=f"Civitai model {model_id}",
                confidence="High",
                records=items,
                evidence="same Civitai model ID",
            ))

    def priority(overlap: Overlap) -> tuple[int, int, str]:
        anchored = "multi-character pack cross-match" in overlap.evidence
        return (0 if anchored else 1, -len(overlap.records), overlap.character.casefold())

    return sorted(overlaps, key=priority)
