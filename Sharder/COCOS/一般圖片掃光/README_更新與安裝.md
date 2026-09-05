# 一般圖片掃光

版本 1.0.1（2026-09-05）

Cocos Creator 3.8 Sprite 圖片掃光材質與播放控制器。

將 .effect／.ts 匯入 Cocos Creator 3.8，建立材質掛 Sprite，再掛 SweepLightController。Independent Material 預設開啟；如需要一顆共享材質同步播放，關閉並僅保留一個控制器。獨立材質可能增加 DrawCall。

本次更新：各 Sprite 預設隔離材質進度，加入 duration 保護及啟停重置。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
