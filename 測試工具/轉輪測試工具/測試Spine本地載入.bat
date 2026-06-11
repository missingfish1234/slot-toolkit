@echo off
echo ============================================
echo    Spine Player 本地測試
echo ============================================
echo.
echo 測試檔案存在性...
echo.

if exist "spine-player.js" (
    echo ✅ spine-player.js 存在
    for %%A in ("spine-player.js") do echo    檔案大小: %%~zA bytes
) else (
    echo ❌ spine-player.js 不存在
)

if exist "spine-player.css" (
    echo ✅ spine-player.css 存在
    for %%A in ("spine-player.css") do echo    檔案大小: %%~zA bytes
) else (
    echo ❌ spine-player.css 不存在
)

echo.
echo 測試 HTML 載入邏輯...
findstr /C:"loadLocalSpinePlayer" slot_test.html > nul
if %errorlevel% equ 0 (
    echo ✅ HTML 中包含本地載入邏輯
) else (
    echo ❌ HTML 中缺少本地載入邏輯
)

echo.
echo ============================================
echo    使用說明
echo ============================================
echo.
echo 現在你可以直接在瀏覽器中開啟 slot_test.html
echo 系統會自動優先使用本地 Spine Player 檔案
echo.
echo 如果遇到問題，可以使用啟動本地伺服器.bat
echo.
pause