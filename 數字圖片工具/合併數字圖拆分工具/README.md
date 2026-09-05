# 合併數字圖拆分工具 1.0.1

完整解壓後用 Chrome／Edge 開啟 split_glyph_tool_dragdrop_v5.html；vendor 內含離線 JSZip。

輸入橫排字圖、字元順序，調整透明度／背景容差、合併間隙與忽略雜點，確認框線與字元一致。偵測數量與字元數不同、或同一字元重複時，會停止配對與批次匯出，避免產生錯字。修正參數或字元順序後重新拆分。

輸出單張 PNG 或 ZIP。ZIP 的 glyph-map.json 記錄圖片／字元／Unicode 對照。小數點為 dot.png、逗號為 comma.png，其他不安全或小寫名稱使用 uXXXX.png，避免 Windows 的 X/x 重名。數字包圖工具 1.3.1 支援這些命名；舊版本請手動配對標點。

驗證：`node tests/regression.test.js`，涵蓋檔名、重複與數量不符的阻擋。自動分割以逐欄空隙為基礎，外光相連時仍需調整容差與間隙；不宣稱自動辨識字體語意。
