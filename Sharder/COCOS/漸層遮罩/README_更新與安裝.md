# 漸層遮罩

版本 1.0.1（2026-09-05）

Cocos Creator 3.8 可動畫化的方向漸層遮罩。

匯入 .effect 與 .ts，建立材質；Driver 必須指定 Target Sprite 與 Target Material。Independent Material 預設開啟；同步共享模式只掛一個控制器。Preview In Editor 關閉即停止編輯預覽並還原材質。遮罩 Sprite 依原說明關閉 Packable。

本次更新：加入獨立材質模式、參數快取、停用还原及完整編輯器預覽開關。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
