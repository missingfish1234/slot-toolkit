# 工具包可靠性更新與驗證（2026-09-05）

本次範圍是既有 28 項工具與管理器；將原本藏在 SPINE 串接工具內的 Cocos Timeline 獨立登錄後，共 29 項。每項均補齊用途、版本、更新日誌及使用／安裝說明。保留原有工具分類、舊套件和使用者樣本，不重排實體素材資料夾。

## 本次修改

| 範圍 | 改善重點 | 驗證方式 |
|---|---|---|
| 管理器 1.2.1 | 安裝前檢查入口／ID／版本；保留設定、使用者新增檔及完整舊版；乾淨 runtime 防舊 DLL 殘留、校驗下載、逐工具 ZIP、離線索引；Git 限定路徑及背景推送 | 31 項 Python／Qt 回歸、Windows PowerShell 更新器實跑、打包 EXE 自測；下載包逐一解壓與入口核對 |
| 數字拆分、包圖、對位 | 字碼別名往返、重複字及尺寸防錯、透明邊界快取、底部 1 px 裁切、預覽比例、中文 ZIP、離線 JSZip | 原函式回歸；真 Chromium 產生 PNG/FNT/ZIP；原始 21 張 PNG 在 1／0.67／0.75 比例下，各經 Cocos 3.8.6 原始排版核心 120 次換字 |
| Cocos 滾分 QA 1.2.1 | 終值等待 Scene 確認、請求與測試批次隔離、同格式寬度分組、字型切換樣本清理；主版本產生相容副本 | core／panel／scene／timing 回歸；核心數字格式／字型測試 |
| Photoshop 插件 1.2.19 | 每 PSD 獨立輸出目錄、暫存完成才換入、保留前版與額外檔案；來源識別阻擋同名不同路徑 PSD 覆蓋；可維護來源及新版安裝器 | 交易式輸出隔離、同名來源／工作階段／發布前競態測試、27 個來源與 CCX 成員核對；未更動正式 PSD |
| 影片、圖片及網頁測試工具 | 停止／取消、輸出防撞名、工作目錄所有權、程序樹清理、Alpha 中性值、Spine 專案往返、單一滾分排程、大轉盤預設圖同步、H3 快啟動 | Python 資料安全案例、JavaScript 回歸、真 Chromium WebM 錄製／取消／抽幀、Windows PowerShell 啟動器測試 |
| SPINE 四工具及 Timeline 0.13.2 | 轉檔獨立工作區與舊版備份、完整 atlas/圖片還原、compact atlas／名稱碰撞防錯、加權 mesh 判定及純 JSON 掃描；Timeline 非同步載入生命週期 | Python／JS／Timeline 回歸、QC 打包 EXE 自測、Cocos 真實型別定義檢查 |
| Unity／Cocos Shader 與滾分工具 | 材質所有權／還原、預览變更才更新、滾分節點與 Sprite 重用、原本型別編譯錯誤、UV／Editor 分離；可選效能品質開關保留預設外觀 | Unity 6000.3.20f1 + Spine 4.2 隔離專案真編譯；10,000 次更新資源穩定、清理及遮罩矩陣檢查；6 個 Shader 匯入 |

## 驗證界線

- 「通過」指列出的測試與環境未發現未解決的失敗，不代表所有引擎、素材、GPU、字型、Photoshop 版本都已驗收。
- Cocos 數字測試執行安裝版本的原始 TextProcessing / FontAtlas 程式；數值物件及 CanvasPool 使用宿主替身。已驗證 NONE 同格式寬度穩定、字形 atlas 矩形更換及 SHRINK 生效，**不是正式 Scene/GPU 畫面測試**。
- Unity 使用獨立暫存專案、batchmode / null graphics。已驗證編譯、資源數量與 Shader 匯入，**未做 GPU 畫質、URP/HDRP 移植或手機效能基準**。
- PS 的文件匯出資料保護以隔離檔案系統／API 替身驗證，未批次操作正式 PSD。Spine 轉檔與圖片放大器的防錯測試不等同於所有版本的授權 CLI、GPU 放大品質驗收。
- 新版本不會自動替換正在開啟的 Cocos／Unity／Photoshop 專案插件副本。引擎內需要依工具安裝說明更新，再用專案副本確認。
- 舊版與樣本仍保留。管理器的新更新流程不自動刪除 `*.backup-*`；若已確認新版和個人設定正常，可自行封存。

## 發布機制

`manager/scripts/package_tools.py` 只從指定 Git commit 產生獨立 ZIP，不把未追蹤素材、建置暫存及歷史備份混入。每包必須通過 tool.json ID／版本與入口檢查，總索引記錄不可變來源 commit、下載 URL 與 SHA-256。

管理器建置固定 Python 套件版本、隔離 DLL 搜尋 PATH，避免把其他軟體的 ICU 誤包為 Qt 依賴。測試與真正的 `ToolkitManager.exe --smoke-test` 任一失敗時，停止產生發布包。

`manager/scripts/verify_manager_upgrade.py` 額外在隔離舊安裝注入已移除的 ICU／根 DLL，使用新版更新器實際換版，再啟動更新後的 EXE；1.2.1 已通過。個人 Tools 內的執行檔、設定及整份舊版備份均保留，新 runtime 的 174 項發布檔（除個人設定）與來源校驗一致。

舊管理器（1.1.x）的第一次跨版更新仍使用舊更新程式；建議從 Release ZIP 解壓到新資料夾試開，確認後再搬入原 `config.json`，不要刪除舊版目錄。
