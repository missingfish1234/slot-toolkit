@echo off
setlocal
for %%I in ("%~dp0..") do set "STUDIO_ROOT=%%~fI"
set "STUDIO_PY=%STUDIO_ROOT%\.build\venv\Scripts\python.exe"
if exist "%STUDIO_PY%" goto verify
where py >nul 2>nul
if errorlevel 1 goto system_python
py -3.12 "%STUDIO_ROOT%\tools\workspace.py" setup
exit /b %errorlevel%
:system_python
python "%STUDIO_ROOT%\tools\workspace.py" setup
exit /b %errorlevel%
:verify
"%STUDIO_PY%" -B "%STUDIO_ROOT%\tools\workspace.py" check >nul
exit /b %errorlevel%
