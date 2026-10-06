# LoRA Character Overlap Finder

Windows desktop utility for finding duplicate and overlapping character LoRAs, DoRAs, and LyCORIS models.

## Default Stability Matrix folders

The application scans these locations by default:

- `C:\StabilityMatrix\Data\Models\Lora` — LoRA and DoRA
- `C:\StabilityMatrix\Data\Models\LyCORIS` — LyCORIS

Both are scanned recursively. Missing folders are skipped. You can also choose any folder manually.

## Current functionality

- Recursive `.safetensors` scanning
- Embedded and sidecar metadata reading
- SHA-256 calculation
- Exact duplicate analysis foundation
- Civitai hash lookup client
- Windows GUI

Character/concept overlap detection is under active development.

## Windows EXE

GitHub Actions builds a standalone Windows executable with PyInstaller.

Open the repository's **Actions** tab, run **Build Windows EXE**, and download the `lora-character-overlap-finder-windows` artifact after the build completes.

The resulting executable is:

`LoRA-Character-Overlap-Finder.exe`

Python is not required on the PC running the built EXE.

## Local development

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m lora_overlap_finder.app
```

## Safety

The scanner is read-only. It does not move or delete model files.
