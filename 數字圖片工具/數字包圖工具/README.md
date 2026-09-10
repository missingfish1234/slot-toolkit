# 數字包圖工具 1.3.2

完整解壓此資料夾後，用 Chrome／Edge 開啟 makefont.html。JSZip 3.10.1 隨 vendor 配送，可離線打包。

輸入每個字元的 PNG；輸出 ZIP 內含 PNG 圖集與 BMFont 文字格式 FNT。dot.png、comma.png 分別代表小數點、逗號；u0078.png、u1f600.png 等 Unicode 名稱可從拆圖工具直接往返。原有 NUM_X-1.png 仍辨識為 X。

每次匯入會先顯示「圖片 → 字元」確認視窗，核對後才加入，取消／Esc 不會變更原字形。bU.png、kU.png 會建議 B、K（依命名慣例推測，並非 OCR）；X2.png、X_a.png 建議 X，請依圖片確認大小寫或指定其他字元。未知名稱留空待填，不再取最後一字。同一批若有重複字元，須改配對或取消勾選；與現有字形重複時，必須明確勾選「取代現有字形」。不能同時把兩張變體圖配成相同字元。

每張圖片只能對應一個 Unicode 字元，不能直接將 WIN 等整個單字當成 BMFont 字元；整個單字圖若指定代碼 W，輸入 W 才會顯示整張圖，不會自動切成 W／I／N。建議一般字形使用 B.png、K.png、X.png、u0078.png 等明確檔名。

滾分請勾等寬數字及 Cocos 固定數字格。固定格使 0–9 的 xadvance 相同，且 xoffset + width 等於 xadvance。光學補寬是外觀選擇，不等同實際字級縮放。此工具預覽不能取代 Cocos Label 的 SHRINK／材質／Scene 驗收。

單張輸出圖集上限 4096×4096；過大會清空失效預覽並阻擋匯出，可降低匯出比例或分批字元。偏移／預覽修改重用原圖透明邊界快取，換圖才重新掃描。

驗證：`node tests/regression.test.js`。涵蓋標點與 Unicode、圖片替換快取、1／0.67／0.75 固定格邊界及超限／無效縮放。

匯入流程驗證：`node tests/import-browser.test.js "Chrome執行檔路徑" "可選的截圖資料夾"`。使用獨立暫存瀏覽器測試圖片配對、取消、重複保護、明確取代、壞圖與 PNG/FNT 輸出；本機若有「測試用」「測試2組」「測試3組/數字」「NUM_X-1」，會額外驗證原始素材，不修改原圖。

`node tests/browser-smoke.js "Chrome執行檔路徑" "Creator版本資料夾" "可選的來源PNG資料夾"` 用獨立暫存瀏覽器驗證三個數字工具的真 PNG／ZIP／FNT 輸出；可選的 Creator 參數會把導出的 FNT 交給該安裝版本的 TextProcessing／FontAtlas 原碼檢查變字、UV 與 SHRINK。已在 Chromium 與 Creator3.8.6 原碼跑過，也驗證 NUM_X-1 的21張原圖、1／0.67／0.75比例；引擎核心測試的 CanvasPool／數值物件為測試介面，未啟動完整 Scene／GPU，仍需在目標專案驗收材質與實際場景。
