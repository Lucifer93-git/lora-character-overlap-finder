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


def test_generic_monochrome_is_not_overlap():
    a = LoraRecord(Path("A.safetensors"), trained_words=["monochrome"])
    b = LoraRecord(Path("B.safetensors"), trained_words=["monochrome"])
    assert not detect_overlaps([a, b])


def test_style_records_are_excluded():
    a = LoraRecord(Path("Tifa_style.safetensors"), trained_words=["Tifa Lockhart"], classification="style")
    b = LoraRecord(Path("Tifa.safetensors"), trained_words=["Tifa Lockhart"])
    assert not detect_overlaps([a, b])


def test_game_cg_is_not_overlap():
    a = LoraRecord(Path("A.safetensors"), trained_words=["game cg"])
    b = LoraRecord(Path("B.safetensors"), trained_words=["game cg"])
    assert not detect_overlaps([a, b])


def test_pack_is_prioritized_over_standalone_character():
    pack = LoraRecord(Path("Final_Fantasy_7_Characters.safetensors"))
    tifa_a = LoraRecord(Path("Tifa_A.safetensors"))
    tifa_b = LoraRecord(Path("Tifa_B.safetensors"))
    pack.trained_words = ["Tifa Lockhart", "Aerith Gainsborough", "Cloud Strife"]
    tifa_a.trained_words = ["Tifa Lockhart"]
    tifa_b.trained_words = ["Tifa Lockhart"]
    overlaps = detect_overlaps([tifa_a, pack, tifa_b])
    tifa = next(item for item in overlaps if normalize_name(item.character) == "tifa lockhart")
    assert tifa.records[0] is pack
    assert len(tifa.records) == 3
    assert "multi-character pack cross-match" in tifa.evidence


def test_appearance_tags_are_not_character_groups():
    a = LoraRecord(Path("A.safetensors"), trained_words=["apron", "ponytail", "black eyes"])
    b = LoraRecord(Path("B.safetensors"), trained_words=["apron", "ponytail", "black eyes"])
    assert not detect_overlaps([a, b])
