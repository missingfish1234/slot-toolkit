@echo off
chcp 65001 > nul
title 修復 Python 套件

echo 正在用目前 Python 安裝必要套件...
py -3 -m pip install --upgrade pip
py -3 -m pip install opencv-python pillow

echo.
echo 如果上面顯示 Successfully installed，就可以重新執行 run_tool.bat
pause
