# Cocos Timeline / Spine 3.8 v0.13.2

支援 Creator 3.8.x；Spine 來源須相容 3.8。將 ZIP 內 spine-director-cocos38 資料夾放入專案 extensions，於擴充管理器啟用；面板選單為 Spine Director 3.8。先備份專案並關閉舊面板，再更新插件。請保留原有 .meta，不覆蓋正式遊戲素材。

在面板加入 Scene 節點、錄製 Transform Key／新增 Spine 或粒子 Clip，可輸出 Timeline JSON 與 Runtime。0.13.2 保留原有 0.13.1 錄製行為；新增載入中停用／刪除／換 Scene 的回應隔離。

完整操作見 spine-director-cocos38/README.md。開發者執行 build_package.ps1 先跑 Scene mock、18 項錄製回歸與 Runtime lifecycle，再打包並輸出 SHA256。測試需 Node.js 與 TypeScript（可設 COCOS_TYPESCRIPT 指向 Creator 內附 TypeScript 模組）。套件內 tests 亦可執行 npm test；安裝 Creator 插件本身不需 npm build。

驗證不會修改正式 Scene。引擎版本、專案其他控制腳本與實際粒子表演仍需在專案確認；不要把 mock 通過解讀成所有專案的視覺驗收。
