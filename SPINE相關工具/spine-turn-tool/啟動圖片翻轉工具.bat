@echo off
setlocal
cd /d "%~dp0"
call "%~dp0tools\ensure_env.bat"
if errorlevel 1 goto failed
"%~dp0.build\venv\Scripts\python.exe" "%~dp0tools\workspace.py" launch
if errorlevel 1 goto failed
exit /b 0
:failed
echo Launch failed. No older source or EXE was used.
pause
exit /b 1
