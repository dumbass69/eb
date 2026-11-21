@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PROJECT=C:\WisemanTauri"
if not exist "%PROJECT%\package.json" (echo [ERROR] C:\WisemanTauri not found.&pause&exit /b 1)
copy /y "%~dp0apply_premium_chrome.py" "%PROJECT%\apply_premium_chrome.py" >nul
xcopy /y /e /i "%~dp0assets" "%PROJECT%\premium-assets" >nul
cd /d "%PROJECT%"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo [1/4] Applying premium installer and title bar...
"%PY%" apply_premium_chrome.py "%PROJECT%"
if errorlevel 1 goto :fail
echo [2/4] Checking React and TypeScript...
call npm run build
if errorlevel 1 goto :fail
echo [3/4] Loading Windows release tools...
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
echo [4/4] Building branded NSIS installer...
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
