from pathlib import Path

from lora_overlap_finder.analyzer import find_exact_duplicates
from lora_overlap_finder.models import LoraRecord


def test_find_exact_duplicates() -> None:
    records = [
        LoraRecord(Path("a.safetensors"), sha256="abc"),
        LoraRecord(Path("b.safetensors"), sha256="abc"),
        LoraRecord(Path("c.safetensors"), sha256="def"),
    ]

    groups = find_exact_duplicates(records)

    assert len(groups) == 1
    assert {record.path.name for record in groups[0]} == {
        "a.safetensors",
        "b.safetensors",
    }
