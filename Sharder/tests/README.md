# 隔離回歸測試

`node cocos-material-regression.js` 以實際 TS 原始碼測試材質隔離、參數快取、停用／移除目標／預覽開關與零秒 duration。需要 TypeScript；可設定 `COCOS_TYPESCRIPT` 指向安裝的 TypeScript 套件。預設也尋找 Creator 3.8.6 的內附套件。這是生命週期 mock 測試，不代表 Cocos GPU 畫面驗收。

完整工具包 checkout 可跑 `node check-cocos-types.js`：使用安裝的 Creator `cc.d.ts` 檢查控制器及 Timeline runtime；可用 `COCOS_ENGINE_ROOT` 指向其他 3.8.x 引擎目錄。`cc/env` 僅補建置時 EDITOR 布林宣告。此命令不編譯 `.effect` Shader。

`UnityEditor~/ToolkitEngineQA.cs` 不會自動匯入正式專案。建立新的 Built-in Unity 6.3 空白測試專案，匯入本分類全部 7 個 Unity 工具、UGUI/TMP 2.0.0 及相容的官方 Spine-Unity runtime；把此檔複製到測試專案 `Assets/Editor`，把工具放於 `Assets/Tools`。

在自己的隔離專案執行 Unity `-batchmode -nographics -projectPath <QA路徑> -executeMethod ToolkitEngineQA.Run -logFile <log>`：檢查 10,000 次數字刷新 glyph 快取／節點有界、使用者子節點保留、字源替換／刪除資源清理、遮罩旋轉與材質還原、Canvas UV channels、Shader 匯入錯誤。再執行 `ToolkitEngineQA.RunPlay`：測試 100 次真實 Play Mode 溶解材質建立／還原／銷毀及外部材質重新指定；這個測試會修改隔離專案 Enter Play Mode Options。兩者自行以 0／1 結束，請勿加 `-quit`。

2026-09-05 已以 Unity 6000.3.20f1、UGUI 2.0.0、Spine runtimes 4.2 commit `e7dc1435fa4a0083ab431f1b28e083c14a1f5c68` 通過。無圖形模式只能證明編譯／資料與生命週期，不包含顏色、透明混合、GPU 性能或真實素材外觀；不能取代正式裝置驗收。
