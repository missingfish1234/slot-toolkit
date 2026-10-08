# SPINE 粒子系統（Particle Studio）

此工具用瀏覽器離線編排 Spine 粒子特效。雙擊 `啟動粒子工作室.cmd`，或直接開啟 `dist/Particle-Studio.html`；不需要啟動伺服器或連線。從工作包管理器按「開啟」時也會直接開啟後者。

操作請先看 [使用指南](使用指南.md)，各參數與轉換流程詳見 [完整說明](使用說明.txt)。轉換現有 `.spine` 工程時需另裝對應版本的 Spine 編輯器；本工具不附帶該程式。

可編輯來源是根目錄的 `index.html`、`styles.css` 和 JavaScript 檔。安裝 Node.js 後執行 `node scripts/build.js`，即可重新產生單檔離線版 `dist/Particle-Studio.html`。下載包則以已驗證的 v1.9.0 單檔版為主；本機開發用的測試、分析及交付草稿不包含在下載包內。
