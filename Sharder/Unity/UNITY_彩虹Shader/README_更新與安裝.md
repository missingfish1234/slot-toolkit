# UNITY_彩虹Shader

版本 1.0.1（2026-09-05）

Unity UGUI／BMFont 彩虹材質、UV 填充與美術材質面板。

Unity 6.3＋UGUI，整個資料夾匯入 Assets，Editor 子資料夾必須保留。BMFontUv2Filler 僅用於每字 4 頂點 Quad 的 UGUI 圖文元件，會補 TexCoord1／TexCoord2；不保證任意 MeshEffect／TMP 拓樸，異常會警告。

本次更新：Editor 面板移入 Editor 目錄；自動補 Canvas UV 通道並檢查 Quad 頂點數。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
