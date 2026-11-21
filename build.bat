@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo [1/4] Installing required Python packages...
if exist ".venv\Scripts\python.exe" (
    set "PY_BIN=.venv\Scripts\python.exe"
) else (
    set "PY_BIN=python"
)

"%PY_BIN%" -m pip install --upgrade customtkinter playwright youtube-transcript-api pyinstaller pillow

echo [2/4] Checking application icon (logo.ico)...
set "ICON_ARGS="
if not exist "logo.ico" (
    if exist "logo.png" (
        echo   + Converting logo.png to logo.ico...
        "%PY_BIN%" -c "from PIL import Image; Image.open('logo.png').save('logo.ico', sizes=[(16,16),(32,32),(48,48),(256,256)])"
    )
)
if exist "logo.ico" (
    echo   + Using custom icon: logo.ico
    set "ICON_ARGS=--icon "logo.ico" --add-data "logo.ico;.""
) else (
    echo   ! logo.ico not found; building with default icon.
)

echo [3/4] Collecting all codebase versions (run_*.py)...
set "SCRIPT_ARGS="
for %%F in (run_*.py) do (
    echo   + Bundling %%F
    set "SCRIPT_ARGS=!SCRIPT_ARGS! --add-data "%%F;scripts""
)

echo [4/4] Building standalone WisemanAgent.exe...
"%PY_BIN%" -m PyInstaller --noconfirm --clean --onefile --console ^
  --name "WisemanAgent" ^
  !ICON_ARGS! ^
  --collect-all customtkinter ^
  --collect-submodules playwright ^
  --collect-submodules youtube_transcript_api ^
  !SCRIPT_ARGS! ^
  run_ultrafast.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check the message above.
    pause
    exit /b 1
)

echo.
echo Done! Your standalone executable is ready at:
echo   dist\WisemanAgent.exe
echo.
pause