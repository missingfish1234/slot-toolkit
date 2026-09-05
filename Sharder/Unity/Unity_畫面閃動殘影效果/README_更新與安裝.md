# Unity_畫面閃動殘影效果

版本 1.0.1（2026-09-05）

Unity Built-in Camera 全畫面殘影與閃光後處理。

Unity 6.3 Built-in 管線、Camera + FullScreenAfterimageEffect + 對應材質。History Downsample=1 保持原圖；2／4 可降低 history 像素量。Preserve Source Format 可保留來源 HDR 格式；先在目標裝置驗證。OnRenderImage 不適用 URP／HDRP。

本次更新：History 增加可選解析度倍率與來源色彩格式，預設維持原 ARGB32 全尺寸。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
