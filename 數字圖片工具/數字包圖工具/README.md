# 數字包圖工具 1.3.4

只需將 `makefont.html` 單檔傳給同事，以 Chrome／Edge 開啟即可使用與離線匯出 ZIP；JSZip 3.10.1 已內嵌，不需另外附上 `vendor`。輸入的 PNG 字圖仍須由使用者自行匯入。

## 單檔交付（1.3.4）

請傳送新版 `makefont.html` 本身，不要傳舊版、備份版或只有捷徑。若開啟後顯示「ZIP 元件初始化失敗」，請重新取得完整 HTML 檔案；不需要另外解壓 `vendor`。

## Cocos 垂直置中（1.3.3）

勾選「整體置中」與「Cocos基線修正」，重新匯出 PNG／FNT 成對使用。現在依 `info.size` 及 0–9 整組可見像素邊界計算共同 `yoffset`；沒有數字時用字母，只有符號時才用符號範圍。保留原圖 Y／未裁切的透明留白會納入補償，不再把 374px 圖格誤當成 72px 字級的置中範圍。負 `yoffset` 是合法補償，不應歸零。每字 Y 與全域 Y 仍會套用；要自動置中請先把刻意微調值設為 0。

補償不修改 `info.size`、字圖縮放、水平字距或圖集位置。所有字元共用移動量，保留小數點／逗號／小寫字母的相對基線，避免逐字硬置中。關閉 Cocos 修正則保留一般行高排版；「Cocos保持行高」只控制 FNT 中繼資料，Creator 3.8.6 實際使用 Label 組件上的行高。

在 Cocos 設水平／垂直 CENTER、Anchor 0.5／0.5。置中不等於縮小：如果可見字高大於 Label 框，置中後仍會超出上下邊緣，請另調 Label 字級或行高。新版預覽使用與 Cocos CENTER 相同的字級原點（以圖集像素顯示），不再只模擬 FNT 行高中央；仍不代替實際 Scene／GPU 驗收。既有已匯出的舊 FNT 不會自動修正。

輸入每個字元的 PNG；輸出 ZIP 內含 PNG 圖集與 BMFont 文字格式 FNT。dot.png、comma.png 分別代表小數點、逗號；u0078.png、u1f600.png 等 Unicode 名稱可從拆圖工具直接往返。原有 NUM_X-1.png 仍辨識為 X。

每次匯入會先顯示「圖片 → 字元」確認視窗，核對後才加入，取消／Esc 不會變更原字形。bU.png、kU.png 會建議 B、K（依命名慣例推測，並非 OCR）；X2.png、X_a.png 建議 X，請依圖片確認大小寫或指定其他字元。未知名稱留空待填，不再取最後一字。同一批若有重複字元，須改配對或取消勾選；與現有字形重複時，必須明確勾選「取代現有字形」。不能同時把兩張變體圖配成相同字元。

每張圖片只能對應一個 Unicode 字元，不能直接將 WIN 等整個單字當成 BMFont 字元；整個單字圖若指定代碼 W，輸入 W 才會顯示整張圖，不會自動切成 W／I／N。建議一般字形使用 B.png、K.png、X.png、u0078.png 等明確檔名。

滾分請勾等寬數字及 Cocos 固定數字格。固定格使 0–9 的 xadvance 相同，且 xoffset + width 等於 xadvance。光學補寬是外觀選擇，不等同實際字級縮放。此工具預覽不能取代 Cocos Label 的 SHRINK／材質／Scene 驗收。

單張輸出圖集上限 4096×4096；過大會清空失效預覽並阻擋匯出，可降低匯出比例或分批字元。偏移／預覽修改重用原圖透明邊界快取，換圖才重新掃描。

驗證：`node tests/regression.test.js`。涵蓋標點與 Unicode、圖片替換快取、1／0.67／0.75 固定格邊界及超限／無效縮放。

`node tests/standalone-browser.test.js` 會只複製 `makefont.html` 到沒有 `vendor` 的暫存目錄，使用獨立 Chrome 視窗驗證字圖打包與 ZIP 內的 PNG／FNT；不修改原始素材。

`node tests/vertical-centering.test.js` 驗證 128 組縮放、鎖定字號、裁切／保留 Y 與行高設定，另測手動偏移及不改水平幾何。引擎垂直驗證可執行 `node tests/import-browser.test.js "Chrome執行檔路徑" "截圖資料夾" "Creator版本資料夾" "問題字型.fnt"`；讀取同層 PNG、在記憶體重建原字格，以新工具實際匯出並交給已安裝 Creator 原碼核對可見範圍與頂點位置，不修改傳入的 FNT／PNG 或專案。

匯入流程驗證：`node tests/import-browser.test.js "Chrome執行檔路徑" "可選的截圖資料夾"`。使用獨立暫存瀏覽器測試圖片配對、取消、重複保護、明確取代、壞圖與 PNG/FNT 輸出；本機若有「測試用」「測試2組」「測試3組/數字」「NUM_X-1」，會額外驗證原始素材，不修改原圖。

`node tests/browser-smoke.js "Chrome執行檔路徑" "Creator版本資料夾" "可選的來源PNG資料夾"` 用獨立暫存瀏覽器驗證三個數字工具的真 PNG／ZIP／FNT 輸出；可選的 Creator 參數會把導出的 FNT 交給該安裝版本的 TextProcessing／FontAtlas 原碼檢查變字、UV 與 SHRINK。已在 Chromium 與 Creator3.8.6 原碼跑過，也驗證 NUM_X-1 的21張原圖、1／0.67／0.75比例；引擎核心測試的 CanvasPool／數值物件為測試介面，未啟動完整 Scene／GPU，仍需在目標專案驗收材質與實際場景。
