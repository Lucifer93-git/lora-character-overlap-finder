# LoRA Character Overlap Finder

A Windows desktop tool for scanning local Stable Diffusion / Stability Matrix LoRA libraries and finding character overlap across separate LoRAs and multi-character packs.

## Goals

- Recursively scan `.safetensors` LoRA files
- Read embedded metadata and common sidecar metadata
- Calculate SHA-256 hashes
- Detect exact duplicate files
- Detect different versions of the same Civitai model
- Detect character overlap between multi-character packs and standalone character LoRAs
- Cache scan and Civitai lookup results locally
- Provide a searchable GUI report
- Stay read-only by default

## Planned classifications

- **Exact Duplicate** — identical SHA-256
- **Same Civitai Model** — different local files / versions of the same Civitai model
- **Character Overlap** — the same character appears in multiple distinct LoRAs
- **Character Pack** — one LoRA appears to contain multiple characters
- **Unique** — no detected overlap

## Tech stack

- Python 3.11+
- PySide6
- safetensors
- requests
- SQLite for local caching

## Status

Early development.
