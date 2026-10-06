@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found.
  echo Install Python 3.11 or newer and try again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
pip install pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed --name "LoRA-Character-Overlap-Finder" --paths src src\lora_overlap_finder\app.py

echo.
echo Build complete:
echo %CD%\dist\LoRA-Character-Overlap-Finder.exe
pause
