# SPINE合圖工具

版本 1.0.1（2026-09-05）

合併多份 Spine Atlas 與 PNG，保留角色 Region 資料。

用 Chrome／Edge 開啟 spine_atlas_merge.html，輸入 Atlas 與其引用 PNG，輸出合併 PNG／Atlas／報告。來源 PMA、filter、repeat、format 必須一致；支援 0／90 度旋轉，其他角度會明確拒絕。同名不同內容需連同 Atlas 引用改名。

本次更新：支援 compact／舊 Atlas、完整 metadata 去重、同名檔衝突及尺寸／頁面模式檢查。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
