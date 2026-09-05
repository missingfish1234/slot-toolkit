# Photoshop PSD Export Pipeline 1.2.19

執行 Install_PSDExportPipeline_1.2.19.cmd 安裝，或用 Creative Cloud 開啟 PSDExportPipeline_1.2.19.ccx。需 Photoshop 23.0+ 與 Creative Cloud Desktop。成功後重開 Photoshop，在 Plugins 開啟 PSD Export Pipeline。安裝失敗會回傳非0退出碼並顯示日誌。舊 EXE、1.2.18 CCX 與安裝器保留供回復；工具清單入口已指向新安裝器。

輸入目前 PSD 的圖層，輸出 PNG、metadata、Spine JSON／atlas，以及 Unity6.0／6.3 或 Cocos3.8.8 Prefab 素材包。實際引擎版本相容性須在目標引擎確認。

新版選擇的是「輸出根目錄」：A.psd 寫入 A_Export，B.psd 寫入 B_Export，內部 images／metadata／spine／engine 結構保持原有形式。舊版直接輸出的根目錄內容不會自動搬移或刪除。

每次先產生獨立 _psd_stage_ 暫存，自檢缺檔及 PNG 完整性通過後才換入。既有輸出中不在工具產物清單的檔案會合併保留；若與新產物同名，會停止發布並保留舊版。每次替換保留完整 _psd_backup_ 備份，工具不自動刪除備份。發布失敗會嘗試還原舊版；失敗暫存與復原資訊亦保留，確認不需後可手動清理。

原有沒有 .psd-export-manifest.json 或來源識別的同名 A_Export 資料夾不會被接管。清單會記錄 PSD 完整路徑／雲端識別；不同路徑的同名 PSD 在匯出開始及發布前都會檢查並拒絕覆蓋，請使用不同輸出根或更改 PSD 名稱。未儲存 PSD 以本次插件工作階段與文件 ID 識別；重開插件或另存後會視為不同來源，需選新輸出根。請勿手動修改清單以繞過保護。

維護來源在 source，打包執行 `powershell -NoProfile -File build.ps1`。腳本先跑交易回歸／語法檢查，按固定排序與時間戳產生 CCX；已有同版本包時拒絕覆寫，須先驗證或升版。

`node tests/transaction.test.js` 使用記憶體 UXP 檔案接口，覆蓋兩PSD隔離、舊流程輸出保留、自訂檔、備份、驗證失敗、改名失敗還原、同名異來源拒絕、發布前來源再檢查與未儲存文件隔離。這不代替 Photoshop 真實圖層渲染、Adobe 安裝及 Unity／Cocos 匯入驗收。
