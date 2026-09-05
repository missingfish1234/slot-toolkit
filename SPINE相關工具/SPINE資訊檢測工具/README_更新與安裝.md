# SPINE資訊檢測工具

版本 1.0.3（2026-09-05）

掃描 Spine JSON／SKEL 的骨架、網格與貼圖資訊，匯出 QC CSV。

Windows 開啟 dist/SpineQC工具.exe。JSON 可離線直接掃描；SKEL／SKEL.BYTES 需要合法可用的 Spine.exe 及對應版本。輸出 CSV。DrawCall 只粗估 slots blend 變更，不含貼圖頁、動態可見性與引擎批次；正式效能須以引擎量測。

本次更新：修正標準 JSON 加權網格計數；純 JSON 不要求 Spine.exe；明示 DrawCall 粗估。

無視窗自測：`dist\SpineQC工具.exe --self-test "C:\Temp\spineqc-test.json"`。成功退出碼為 0，報告 `ok` 為 true；只在自有暫存資料夾建立測試 JSON，不掃描正式素材。重建可用 Python 3.12 + PyInstaller 執行現有 `SpineQC工具.spec`；發布前請保留舊 EXE 並跑此自測。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
