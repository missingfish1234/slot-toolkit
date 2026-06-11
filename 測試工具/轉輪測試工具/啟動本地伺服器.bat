@echo off
echo ============================================
echo    老虎機測試工具 - 本地伺服器啟動器
echo ============================================
echo.
echo 這個批次檔案將啟動本地 HTTP 伺服器
echo 以支援 Spine 動畫功能
echo.
echo 啟動後，請在瀏覽器中開啟:
echo http://localhost:8000/slot_test.html
echo.
echo 按任意鍵啟動伺服器...
pause > nul

echo.
echo 正在檢查 Python...
python --version > nul 2>&1
if %errorlevel% equ 0 (
    echo 發現 Python，正在啟動 HTTP 伺服器...
    cd /d "%~dp0"
    python -m http.server 8000
) else (
    echo Python 未安裝，嘗試使用 Node.js...
    node --version > nul 2>&1
    if %errorlevel% equ 0 (
        echo 發現 Node.js，正在檢查 http-server...
        npm list -g http-server > nul 2>&1
        if %errorlevel% neq 0 (
            echo 安裝 http-server...
            npm install -g http-server
        )
        cd /d "%~dp0"
        http-server -p 8000
    ) else (
        echo 請安裝 Python 或 Node.js 來啟動本地伺服器
        echo 或者手動下載 Spine Player 檔案到本地
        pause
    )
)