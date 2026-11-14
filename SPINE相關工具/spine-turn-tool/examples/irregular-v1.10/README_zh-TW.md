# 不規則透明輪廓翻轉

在工具開啟 `irregular.spturn` 可繼續調整；編輯檔保存原圖、輪廓門檻、誤差及全部動畫設定。此星花徽章圖片是本工具原創範例，透明外框的凹口保留實際厚度側邊。正面與背面均有獨立原始透明PNG。

三版本原生專案位於 `spine-3.8/`、`spine-4.0/`、`spine-4.2/`，分別用3.8.99、4.0.56、4.2.43開啟。

`preview.gif`、`preview-contact-sheet.png` 與 `png-sequence/` 的60張512×512透明PNG，使用相同設定與整段固定取景。

交付預覽以 Spine4.0.56 原生專案重新匯出的 Binary，由官方runtime計算實際網格、骨骼與繪製順序，再用共用CPU繪圖器產生；不是Spine GPU截圖。
