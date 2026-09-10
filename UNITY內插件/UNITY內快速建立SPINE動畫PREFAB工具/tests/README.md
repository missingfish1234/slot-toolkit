# 機種名前綴回歸測試

2026-09-10：Unity 6000.3.20f1 + Spine 4.2 獨立專案通過 **92 項斷言**。

涵蓋空值／空白相容、中文、分隔底線、非法字元阻擋、專案專屬設定與重開載入；實際建立無前綴及兩種前綴的 Prefab、AnimationClip、AnimatorController，核對略過／覆寫、重新匯入後的資產引用、原始 State／Spine 動畫名稱、事件索引、曲線綁定及 Loop 設定。

測試使用最小 Spine JSON（Idle、Win，無貼圖），Unity 與 Spine 為真實引擎／套件。QA 專案中的 IGS_GAME_EX 兩個元件僅用相同序列化欄位的替身，未驗證正式遊戲的事件播放行為或 GPU 畫面，也未修改正式專案。

## 重跑

只在可丟棄的測試專案執行。安裝 Spine、UGUI、此工具，以及它需要的 IGS_GAME_EX 元件，再將 `Editor/SpinePrefabBuilderPrefixTests.cs` 放入該專案的 Editor 資料夾。

```text
Unity.exe -batchmode -nographics -projectPath "測試專案絕對路徑" -executeMethod SpinePrefabBuilderPrefixTests.Run -logFile "測試記錄絕對路徑"
```

測試會自行結束 Unity；成功記錄為 `PREFIX_QA_PASS assertions=92`，失敗則回傳退出碼 1。
每次僅在新建的 `Assets/PrefixQA_<隨機值>` 下產生測試資產並保留供檢查；測試機種名設定會在結束時恢復。
