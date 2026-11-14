@echo off
setlocal
cd /d "%~dp0"
call "%~dp0tools\ensure_env.bat"
if errorlevel 1 goto failed
"%~dp0.build\venv\Scripts\python.exe" "%~dp0tools\workspace.py" dev-build
if errorlevel 1 goto failed
echo Development build completed in this folder's dist\dev directory.
pause
exit /b 0
:failed
echo Packaging stopped. Tests and failures cannot be skipped.
pause
exit /b 1
