# SPINE合圖工具

版本 1.1.0（2026-10-29）

合併多份 Spine Atlas 與 PNG，保留角色 Region 資料。

用新版 Chrome／Edge 開啟 `spine_atlas_merge_v1.1.html`，不需安裝或連網。拖入 Atlas 與其引用的全部 PNG，也可直接拖入包含子資料夾的資料夾。輸出合併 PNG／Atlas／報告；來源 PMA、filter、repeat、format 必須一致，支援 0／90 度旋轉。

本次更新：

- 直接編解碼 PNG 像素，保留 PMA／低 alpha 光效；交錯等無法直接解析的 PNG 會改用瀏覽器解碼並顯示「非無損讀取」提示，16-bit PNG 轉為 8-bit。
- MaxRects 包圖、不同名稱相同像素共用、Padding 與邊緣外擴（Extrude）。
- 可分別設定最大寬高；單頁放不下時可自動輸出多頁 PNG。
- 設定自動記憶，支援指定資料夾輸出與同名檔覆蓋確認。
- 保留 compact／舊 Atlas 解析、完整 metadata 去重與衝突檢查；來源皆為 `.atlas.txt` 時沿用此副檔名。

先選擇輸出資料夾，再按「開始合併」，可一次保存 PNG、原 atlas 名稱別名與報告。需要主 atlas 時勾選「另外輸出主 atlas」；未選資料夾也可使用個別下載按鈕，別名 atlas 則透過資料夾輸出。

同名不同內容需連同 Atlas 引用改名。本工具不修改 `.skel`／`.json`；交付前請逐個骨架在實際引擎播放驗收。Unity 若要合批，需讓骨架共用同一主 AtlasAsset，使用別名 atlas 不會自動共用 Material。
