# UNITY螢幕扭曲效果

版本 1.0.1（2026-09-05）

Unity Built-in 的可定位螢幕扭曲 Shader 與 Prefab 控制器。

Unity 6.3 Built-in：建立 Quad + Renderer，套 PrefabScreenDistortion_BuiltIn 材質，掛 Controller，指定實際輸出 Camera／Renderer。先用 strength=0.25、radius=0.25、feather=0.08、opacity=1。GrabPass 需要前方已繪製內容；URP/HDRP 無此實作，請勿直接套用。

本次更新：補齊 Built-in／GrabPass 限制、初始設定及驗收方式；保留 MaterialPropertyBlock 控制。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
