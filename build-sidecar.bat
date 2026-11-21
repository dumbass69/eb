@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r backend\requirements.txt
for /f %%T in ('rustc --print host-tuple') do set TARGET=%%T
pyinstaller --noconfirm --clean --onefile --windowed --name wiseman-backend --paths backend --collect-all customtkinter --collect-submodules playwright --collect-submodules patchright --collect-submodules youtube_transcript_api backend\bridge.py
copy /y dist\wiseman-backend.exe src-tauri\binaries\wiseman-backend-%TARGET%.exe
