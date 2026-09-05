# Unity63_NumberRollerTool

版本 1.0.1（2026-09-05）

Unity UGUI／TMP／Sprite／BMFont 的數字滾分與輪帶測試。

Unity 6.3＋UGUI/TMP，匯入 Runtime 與 Editor 目錄。指定輸出模式、字型與 imageRoot。工具只管理 NumberRollerGeneratedNode 標記的子物件。字型物件內容被外部腳本原地修改時呼叫 RebuildDisplay()；來源引用切換會刷新 ImageLine 快取。BMFont 目前單頁 PNG，不支援多頁字型。

本次更新：快取 Glyph 與自建 Sprite、重用圖片字元、只清理自身標記節點。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
