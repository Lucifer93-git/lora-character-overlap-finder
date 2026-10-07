from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import requests

from . import __version__

REPOSITORY = "Lucifer93-git/lora-character-overlap-finder"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases"
EXE_ASSET_NAME = "LoRA-Character-Overlap-Finder.exe"


@dataclass(slots=True)
class UpdateInfo:
    version: str
    download_url: str
    release_url: str


def _version_tuple(value: str) -> tuple[int, ...]:
    clean = value.strip().lower().lstrip("v")
    parts = clean.split(".")
    numbers: list[int] = []
    for part in parts:
        digits = "".join(ch for ch in part if ch.isdigit())
        numbers.append(int(digits or 0))
    return tuple(numbers)


def check_for_update(timeout: float = 5.0) -> UpdateInfo | None:
    response = requests.get(
        RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"lora-overlap-finder/{__version__}"},
        params={"per_page": 20},
        timeout=timeout,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()

    candidates: list[tuple[tuple[int, ...], dict]] = []
    for release in response.json():
        if release.get("draft"):
            continue
        version = str(release.get("tag_name", "")).lstrip("v")
        version_key = _version_tuple(version)
        if version and version_key > _version_tuple(__version__):
            candidates.append((version_key, release))

    for _, release in sorted(candidates, key=lambda item: item[0], reverse=True):
        version = str(release.get("tag_name", "")).lstrip("v")
        for asset in release.get("assets", []):
            if asset.get("name") == EXE_ASSET_NAME:
                return UpdateInfo(
                    version=version,
                    download_url=asset["browser_download_url"],
                    release_url=release.get("html_url", ""),
                )
    return None


def install_update(update: UpdateInfo) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Automatic replacement is only available in the packaged Windows EXE.")

    current_exe = Path(sys.executable).resolve()
    temp_dir = Path(tempfile.mkdtemp(prefix="lora-overlap-update-"))
    new_exe = temp_dir / EXE_ASSET_NAME

    with requests.get(update.download_url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with new_exe.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)

    # The updater waits for this process to exit, replaces the EXE, then relaunches it.
    script = temp_dir / "update.cmd"
    script.write_text(
        "@echo off\n"
        "setlocal\n"
        f'set "PID={os.getpid()}"\n'
        f'set "OLD={current_exe}"\n'
        f'set "NEW={new_exe}"\n'
        ":waitloop\n"
        'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL\n'
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto waitloop)\n"
        'copy /Y "%NEW%" "%OLD%" >NUL\n'
        'if errorlevel 1 (timeout /t 2 /nobreak >NUL & goto waitloop)\n'
        'timeout /t 3 /nobreak >NUL\n'
        'start "" "%OLD%"\n'
        'timeout /t 3 /nobreak >NUL\n'
        'rmdir /S /Q "%~dp0" 2>NUL\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
