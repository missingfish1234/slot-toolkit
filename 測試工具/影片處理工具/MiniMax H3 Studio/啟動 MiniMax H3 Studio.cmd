@echo off
setlocal
chcp 65001 >nul
title MiniMax H3 Studio Launcher

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_or_launch_h3.ps1"
if errorlevel 1 (
  echo.
  echo MiniMax H3 Studio 啟動失敗，請查看上方訊息。
  pause
)

endlocal
