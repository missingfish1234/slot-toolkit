@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Cocos38Extension.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed. Please check the message above.
)
echo.
pause
