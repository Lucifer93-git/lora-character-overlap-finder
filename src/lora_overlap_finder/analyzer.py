from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import LoraRecord


@dataclass(slots=True)
class AnalysisResult:
    exact_duplicates: list[list[LoraRecord]] = field(default_factory=list)
    character_overlaps: dict[str, list[LoraRecord]] = field(default_factory=dict)


def find_exact_duplicates(records: list[LoraRecord]) -> list[list[LoraRecord]]:
    grouped: dict[str, list[LoraRecord]] = defaultdict(list)
    for record in records:
        if record.sha256:
            grouped[record.sha256].append(record)
    return [items for items in grouped.values() if len(items) > 1]


def find_character_overlaps(records: list[LoraRecord]) -> dict[str, list[LoraRecord]]:
    grouped: dict[str, list[LoraRecord]] = defaultdict(list)
    for record in records:
        for character in record.character_candidates:
            key = character.strip().casefold()
            if key:
                grouped[key].append(record)
    return {character: items for character, items in grouped.items() if len(items) > 1}


def analyze(records: list[LoraRecord]) -> AnalysisResult:
    return AnalysisResult(
        exact_duplicates=find_exact_duplicates(records),
        character_overlaps=find_character_overlaps(records),
    )
