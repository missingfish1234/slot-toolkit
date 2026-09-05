@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo 轉輪工具本地伺服器：僅接受本機連線。
where py >nul 2>nul
if not errorlevel 1 (
  py -3 serve_tool.py
  goto :done
)
where python >nul 2>nul
if not errorlevel 1 (
  python serve_tool.py
  goto :done
)
where node >nul 2>nul
if not errorlevel 1 (
  node serve_tool.js
  goto :done
)
echo 請先安裝 Python 3 或 Node.js；本工具不會自動安裝全域套件。
pause
exit /b 1
:done
if errorlevel 1 pause
