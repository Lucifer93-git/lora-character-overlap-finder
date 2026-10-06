from pathlib import Path

from lora_overlap_finder.detection import detect_overlaps, normalize_name
from lora_overlap_finder.models import LoraRecord


def test_normalize_name():
    assert normalize_name("Tifa_Lockhart-Pony-v2") == "tifa lockhart"


def test_overlap_from_civitai_trained_words():
    a = LoraRecord(Path("Final_Fantasy_7_Characters.safetensors"))
    b = LoraRecord(Path("Tifa_Lockhart.safetensors"))
    a.trained_words = ["Tifa Lockhart", "Aerith Gainsborough", "Cloud Strife"]
    b.trained_words = ["Tifa_Lockhart"]
    overlaps = detect_overlaps([a, b])
    names = {item.character.casefold().replace("_", " ") for item in overlaps}
    assert "tifa lockhart" in names
