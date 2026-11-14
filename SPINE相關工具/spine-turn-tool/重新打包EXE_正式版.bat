@echo off
setlocal
cd /d "%~dp0"
call "%~dp0tools\ensure_env.bat"
if errorlevel 1 goto failed
"%~dp0.build\venv\Scripts\python.exe" "%~dp0tools\build_release.py" %*
if errorlevel 1 goto failed
echo Release completed in this project folder.
pause
exit /b 0
:failed
echo Release stopped. Check the version, local evidence and existing output.
echo Existing release files have not been overwritten.
pause
exit /b 1
