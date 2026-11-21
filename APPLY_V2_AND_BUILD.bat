@echo off
setlocal
cd /d "%~dp0"
set "PROJECT=C:\WisemanTauri"
if not exist "%PROJECT%\package.json" (echo [ERROR] C:\WisemanTauri not found.&pause&exit /b 1)
copy /y "%~dp0apply_update_v2.py" "%PROJECT%\apply_update_v2.py" >nul
cd /d "%PROJECT%"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" apply_update_v2.py "%PROJECT%"
if errorlevel 1 goto :fail
call build-sidecar.bat
if errorlevel 1 goto :fail
call npm run build
if errorlevel 1 goto :fail
call npm run tauri build -- --bundles nsis
if errorlevel 1 goto :fail
explorer "src-tauri\target\release\bundle\nsis"
echo UPDATE SUCCEEDED
pause
exit /b 0
:fail
echo UPDATE OR BUILD FAILED
pause
exit /b 1
