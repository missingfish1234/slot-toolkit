@echo off
chcp 65001 > nul
title 影片最後一幀輸出工具

cd /d "%~dp0"

echo 正在啟動影片最後一幀輸出工具...
echo 若缺少套件，請先執行 fix_package.bat。
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" last_frame_exporter_auto.py
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        python last_frame_exporter_auto.py
    ) else (
        py -3 last_frame_exporter_auto.py
    )
)

pause
