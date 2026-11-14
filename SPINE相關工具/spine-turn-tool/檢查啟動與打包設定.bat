@echo off
setlocal
cd /d "%~dp0"
call "%~dp0tools\ensure_env.bat"
if errorlevel 1 goto failed
"%~dp0.build\venv\Scripts\python.exe" -B "%~dp0tools\workspace.py" launch --check
if errorlevel 1 goto failed
"%~dp0.build\venv\Scripts\python.exe" -B "%~dp0tools\build_release.py" --check
set "CHECK_CODE=%errorlevel%"
echo This only checks settings; it does not launch or build.
echo An existing version or historical evidence is intentionally rejected for a new release.
pause
exit /b %CHECK_CODE%
:failed
echo Local environment or launch-path check failed. No older copy was used.
pause
exit /b 1
