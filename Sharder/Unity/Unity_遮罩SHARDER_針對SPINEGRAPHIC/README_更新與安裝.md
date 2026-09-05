# Unity_遮罩SHARDER_針對SPINEGRAPHIC

版本 1.0.1（2026-09-05）

Unity Spine SkeletonGraphic 圖片與柔邊矩形遮罩。

Unity 6.3＋Spine-Unity，Driver 與 Shader 必須一起更新。指定 Mask Rect Transform、Mask Texture；支援平面內平移／旋轉／縮放。此版以單材質 SkeletonGraphic 為主要對象，多頁多材質需在實際 Spine-Unity 版本驗證。

本次更新：停用還原原材質；遮罩改用座標矩陣支援旋轉，清除遮罩貼圖時使用白圖。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
