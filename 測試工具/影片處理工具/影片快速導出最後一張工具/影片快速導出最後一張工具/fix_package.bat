@echo off
chcp 65001 > nul
title 安裝影片工具專用 Python 環境
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 (
    echo 建立環境失敗，請安裝 Python 3 並勾選 Python Launcher。
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo 安裝失敗，請確認網路後重試；現有影片不受影響。
  pause
  exit /b 1
)
echo 安裝完成，請執行 run_tool.bat。
pause
