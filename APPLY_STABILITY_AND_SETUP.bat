@echo off
setlocal EnableExtensions
set "PROJECT=C:\WisemanTauri"
set "LOG=%PROJECT%\stability-setup-build.log"
if not exist "%PROJECT%\package.json" (echo [ERROR] C:\WisemanTauri not found.&pause&exit /b 1)
>"%LOG%" echo Stability and setup rebuild started %DATE% %TIME%
echo [1/6] Backing up current source...
if not exist "%PROJECT%\backup-before-stability-setup" mkdir "%PROJECT%\backup-before-stability-setup"
copy /y "%PROJECT%\src\App.tsx" "%PROJECT%\backup-before-stability-setup\App.tsx" >nul 2>&1
copy /y "%PROJECT%\src\styles.css" "%PROJECT%\backup-before-stability-setup\styles.css" >nul 2>&1
copy /y "%PROJECT%\backend\bridge.py" "%PROJECT%\backup-before-stability-setup\bridge.py" >nul 2>&1
copy /y "%PROJECT%\src-tauri\src\lib.rs" "%PROJECT%\backup-before-stability-setup\lib.rs" >nul 2>&1
copy /y "%PROJECT%\src-tauri\src\main.rs" "%PROJECT%\backup-before-stability-setup\main.rs" >nul 2>&1

echo [2/6] Replacing frontend and bridges...
xcopy /y /e /i "%~dp0payload\src" "%PROJECT%\src" >>"%LOG%" 2>&1
xcopy /y /e /i "%~dp0payload\backend" "%PROJECT%\backend" >>"%LOG%" 2>&1
xcopy /y /e /i "%~dp0payload\src-tauri" "%PROJECT%\src-tauri" >>"%LOG%" 2>&1
if errorlevel 1 goto :fail
cd /d "%PROJECT%"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [3/6] Checking Python and TypeScript...
"%PY%" -m py_compile backend\bridge.py backend\run_ultrafast.py >>"%LOG%" 2>&1
if errorlevel 1 goto :fail
call npm run build >>"%LOG%" 2>&1
if errorlevel 1 goto :fail

echo [4/6] Building a consoleless Python sidecar...
for /f %%T in ('rustc --print host-tuple 2^>nul') do set "TARGET=%%T"
if not defined TARGET for /f "tokens=2" %%T in ('rustc -Vv ^| findstr /b "host:"') do set "TARGET=%%T"
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name wiseman-backend --paths backend --collect-all customtkinter --collect-submodules playwright --collect-submodules patchright --collect-submodules youtube_transcript_api backend\bridge.py >>"%LOG%" 2>&1
if errorlevel 1 goto :fail
copy /y "dist\wiseman-backend.exe" "src-tauri\binaries\wiseman-backend-%TARGET%.exe" >>"%LOG%" 2>&1
if errorlevel 1 goto :fail

echo [5/6] Verifying Rust without a console subsystem...
pushd src-tauri
call cargo check >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" goto :fail

echo [6/6] Building Tauri NSIS installer...
call npm run tauri build -- --bundles nsis >>"%LOG%" 2>&1
if errorlevel 1 goto :fail
set "OUT=src-tauri\target\release\bundle\nsis"
if not exist "%OUT%" goto :fail
echo.
echo BUILD SUCCEEDED
for %%F in ("%OUT%\*.exe") do echo Installer: %%~fF
explorer "%OUT%"
pause
exit /b 0
:fail
echo.
echo BUILD FAILED. Log: %LOG%
powershell -NoProfile -Command "if(Test-Path '%LOG%'){Get-Content -LiteralPath '%LOG%' -Tail 140}"
pause
exit /b 1
