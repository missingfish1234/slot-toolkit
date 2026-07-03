@echo off
chcp 65001 > nul
title 影片最後一幀輸出工具

cd /d "%~dp0"

echo 正在啟動影片最後一幀輸出工具...
echo 如果第一次啟動缺少套件，工具會自動安裝。
echo.

py -3 last_frame_exporter_auto.py

if errorlevel 1 (
    echo.
    echo 使用 py -3 啟動失敗，改用 python 啟動...
    python last_frame_exporter_auto.py
)

pause
