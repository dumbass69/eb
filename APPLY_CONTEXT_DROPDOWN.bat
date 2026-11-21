@echo off
setlocal
set "PROJECT=C:\WisemanTauri"
if not exist "%PROJECT%\package.json" (echo [ERROR] C:\WisemanTauri not found.&pause&exit /b 1)
copy /y "%~dp0refine_context_dropdown.py" "%PROJECT%\refine_context_dropdown.py" >nul
cd /d "%PROJECT%"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
echo [1/2] Applying polished context selector...
"%PY%" refine_context_dropdown.py "%PROJECT%"
if errorlevel 1 goto :fail
echo [2/2] Validating React and TypeScript...
call npm run build
if errorlevel 1 goto :fail
echo.
echo UPDATE SUCCEEDED.
echo Run your existing fancy-installer build script to generate the installer.
pause
exit /b 0
:fail
echo UPDATE FAILED.
pause
exit /b 1
