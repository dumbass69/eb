@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PROJECT=C:\WisemanTauri"
if not exist "%PROJECT%\package.json" (
  echo [ERROR] C:\WisemanTauri was not found.
  pause
  exit /b 1
)
cd /d "%PROJECT%"

echo [0/8] Closing stale build and application processes...
for %%P in (wiseman-autopilot.exe wiseman-backend.exe cargo.exe rustc.exe rc.exe link.exe mt.exe makensis.exe) do taskkill /f /im %%P >nul 2>nul
timeout /t 2 /nobreak >nul

echo [1/8] Loading Microsoft C++ and Windows SDK tools...
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :missing_vs
set "VSROOT="
for /f "usebackq tokens=*" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSROOT=%%I"
if not defined VSROOT goto :missing_cpp
call "%VSROOT%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 goto :fail
set "RC_PATH="
for /f "delims=" %%R in ('where rc.exe 2^>nul') do if not defined RC_PATH set "RC_PATH=%%R"
if not defined RC_PATH goto :missing_sdk
for %%D in ("%RC_PATH%") do set "PATH=%%~dpD;%PATH%"
set "RC=%RC_PATH%"
set "RC_x86_64_pc_windows_msvc=%RC_PATH%"
echo Using RC.EXE: %RC_PATH%

echo [2/8] Backing up current source files...
if not exist "backup-final-stable-v3" mkdir "backup-final-stable-v3"
copy /y "src\App.tsx" "backup-final-stable-v3\App.tsx" >nul
copy /y "src\styles.css" "backup-final-stable-v3\styles.css" >nul
copy /y "backend\bridge.py" "backup-final-stable-v3\bridge.py" >nul
copy /y "src-tauri\src\lib.rs" "backup-final-stable-v3\lib.rs" >nul
copy /y "src-tauri\src\main.rs" "backup-final-stable-v3\main.rs" >nul

echo [3/8] Installing the complete replacement source set...
robocopy "%~dp0payload\src" "%PROJECT%\src" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copy_fail
robocopy "%~dp0payload\backend" "%PROJECT%\backend" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copy_fail
robocopy "%~dp0payload\src-tauri" "%PROJECT%\src-tauri" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :copy_fail

if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")

echo [4/8] Validating Python, React, TypeScript, and Rust...
"%PY%" -m py_compile backend\bridge.py backend\run_ultrafast.py
if errorlevel 1 goto :fail
call npm run build
if errorlevel 1 goto :fail
pushd src-tauri
call cargo check
set "CHECK_RESULT=%ERRORLEVEL%"
popd
if not "%CHECK_RESULT%"=="0" goto :fail

echo [5/8] Building the hidden Python sidecar...
set "TARGET="
for /f %%T in ('rustc --print host-tuple 2^>nul') do set "TARGET=%%T"
if not defined TARGET for /f "tokens=2" %%T in ('rustc -Vv ^| findstr /b "host:"') do set "TARGET=%%T"
if not defined TARGET goto :fail
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name wiseman-backend --paths backend --collect-all customtkinter --collect-submodules playwright --collect-submodules patchright --collect-submodules youtube_transcript_api backend\bridge.py
if errorlevel 1 goto :fail
if not exist "dist\wiseman-backend.exe" goto :fail
if not exist "src-tauri\binaries" mkdir "src-tauri\binaries"
copy /y "dist\wiseman-backend.exe" "src-tauri\binaries\wiseman-backend-%TARGET%.exe"
if errorlevel 1 goto :fail

echo [6/8] Cleaning only stale release intermediates...
if exist "src-tauri\target\release\build" rmdir /s /q "src-tauri\target\release\build"
if exist "src-tauri\target\release\bundle\nsis" rmdir /s /q "src-tauri\target\release\bundle\nsis"

echo [7/8] Building the Tauri application and NSIS installer...
call npm run tauri build -- --bundles nsis
if errorlevel 1 goto :fail

echo [8/8] Verifying the generated installer...
set "OUT=src-tauri\target\release\bundle\nsis"
if not exist "%OUT%" goto :fail
set "FOUND_INSTALLER="
for %%F in ("%OUT%\*.exe") do set "FOUND_INSTALLER=%%~fF"
if not defined FOUND_INSTALLER goto :fail

echo.
echo =====================================================
echo BUILD SUCCEEDED
for %%F in ("%OUT%\*.exe") do echo Installer: %%~fF
echo =====================================================
explorer "%OUT%"
pause
exit /b 0

:missing_vs
echo [ERROR] Visual Studio Installer was not found.
goto :fail
:missing_cpp
echo [ERROR] Desktop development with C++ / MSVC tools were not found.
goto :fail
:missing_sdk
echo [ERROR] Windows SDK RC.EXE was not found.
goto :fail
:copy_fail
echo [ERROR] Source replacement failed. Close Visual Studio Code, Notepad++, and any app viewing C:\WisemanTauri source files, then retry.
goto :fail
:fail
echo.
echo =====================================================
echo BUILD FAILED AT THE STEP SHOWN ABOVE.
echo No shared log file is used, so no log-file lock can break this build.
echo =====================================================
pause
exit /b 1
