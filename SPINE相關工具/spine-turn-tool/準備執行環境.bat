@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto system_python
py -3.12 "%~dp0tools\workspace.py" setup
goto result
:system_python
python "%~dp0tools\workspace.py" setup
:result
if errorlevel 1 goto failed
echo Local environment is ready in this folder's .build\venv directory.
pause
exit /b 0
:failed
echo Setup failed. See .build\setup.log. No older copy was used.
pause
exit /b 1
