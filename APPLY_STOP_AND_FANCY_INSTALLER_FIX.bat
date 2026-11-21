@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PROJECT=C:\WisemanTauri"
if not exist "%PROJECT%\package.json" (echo [ERROR] C:\WisemanTauri not found.&pause&exit /b 1)
copy /y "%~dp0apply_stop_installer_fix.py" "%PROJECT%\apply_stop_installer_fix.py" >nul
xcopy /y /e /i "%~dp0assets" "%PROJECT%\stop-installer-assets" >nul
cd /d "%PROJECT%"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo [1/6] Applying stop-state and installer-schema fixes...
"%PY%" apply_stop_installer_fix.py "%PROJECT%"
if errorlevel 1 goto :fail
echo [2/6] Validating Python and React...
"%PY%" -m py_compile backend\bridge.py backend\run_ultrafast.py
if errorlevel 1 goto :fail
call npm run build
if errorlevel 1 goto :fail
echo [3/6] Loading Windows release tools...
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq tokens=*" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSROOT=%%I"
if not defined VSROOT goto :fail
call "%VSROOT%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 goto :fail
set "RC_PATH="
for /f "delims=" %%R in ('where rc.exe 2^>nul') do if not defined RC_PATH set "RC_PATH=%%R"
if not defined RC_PATH goto :fail
for %%D in ("%RC_PATH%") do set "PATH=%%~dpD;%PATH%"
set "RC=%RC_PATH%"
set "RC_x86_64_pc_windows_msvc=%RC_PATH%"
echo [4/6] Rebuilding the hidden Python sidecar...
for /f %%T in ('rustc --print host-tuple 2^>nul') do set "TARGET=%%T"
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name wiseman-backend --paths backend --collect-all customtkinter --collect-submodules playwright --collect-submodules patchright --collect-submodules youtube_transcript_api backend\bridge.py
if errorlevel 1 goto :fail
copy /y dist\wiseman-backend.exe src-tauri\binaries\wiseman-backend-%TARGET%.exe >nul
if errorlevel 1 goto :fail
echo [5/6] Checking Rust and Tauri configuration...
pushd src-tauri
call cargo check
set "CHECK_RC=%ERRORLEVEL%"
popd
if not "%CHECK_RC%"=="0" goto :fail
echo [6/6] Building branded NSIS installer...
taskkill /f /im wiseman-autopilot.exe >nul 2>nul
call npm run tauri build -- --bundles nsis
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
echo UPDATE OR BUILD FAILED AT THE STEP ABOVE.
pause
exit /b 1
