@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "SCRIPT=%~dp0spine_alpha_upscale_tool.py"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%SCRIPT%" --gui
  goto :check_error
)

where python >nul 2>nul
if not errorlevel 1 (
  python "%SCRIPT%" --gui
  goto :check_error
)

echo Python was not found.
echo Please install Python 3 and Pillow, then run this tool again.
pause
exit /b 1

:check_error
if errorlevel 1 (
  echo.
  echo Failed to launch the Spine image upscale tool.
  echo Please confirm Python 3 and Pillow are installed.
  pause
  exit /b 1
)

exit /b 0
