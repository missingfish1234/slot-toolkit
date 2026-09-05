# 粒子淡入淡出_發光

版本 1.0.1（2026-09-05）

Cocos Creator 3.8 ParticleSystem2D 的生命週期淡入淡出與發光。

匯入 ParticleGlow.effect.effect，材質套 ParticleSystem2D。Start Color Alpha=255、End Color Alpha=0，alpha 不加隨機差異；生命進度由此反推。fadeParams 建議 [0.1,0.7,1.5,0]，startTint/endTint 設白色先測。需要疊加發光時 BlendDst=ONE。若父層透明度也被修改，請另外驗證生命視覺。

本次更新：保護淡入／淡出端點及倒置參數，附可重現的初始設定。

驗證範圍：原始碼／隔離回歸與引擎編譯結果見本次更新驗證報告；畫面效果與實際素材需按專案環境驗收。舊版說明保留供操作參考，以本文件的新參數與限制為準。
