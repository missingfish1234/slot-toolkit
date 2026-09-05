# 小魚骨頭工作包管理器

Windows 桌面工具，用來從 GitHub 公開倉庫檢視、下載、更新與開啟工具。

## 1.2.0 更新

- 每個工具可以使用独立 ZIP 與 SHA-256 校驗；旧索引仍可共用一次下載的倉庫快取。
- 更新先驗證 tool.json 的 ID、版本與啟動入口，再替換安裝；失敗不動原工具。
- `user-data/`、`outputs/`、`presets/`、`config.json`、`settings.json` 預設保留，可用 `preservePaths` 增補。使用者新增的額外檔也會保留；改過的程式與新版衝突時以新版程式為準，但完整舊版仍在同層 `工具ID.backup-*`，不自動刪除。
- 管理器本體會等待舊程序離開，驗證完整性、保留設定與整套舊版，再交易式換入。更新失敗記錄在 `%APPDATA%/ToolkitManager/updates/apply-*/request.json.status.json`。
- 已同步索引按 GitHub 倉庫及分支個別快取，離線重開仍可使用；損壞 JSON 保留 `.corrupt-*` 原檔並優先從 `.bak` 恢復。
- 掃描不再把分類 README 或 vendor/tests 當成工具；明確登錄的巢狀插件可独立列出，損壞 metadata、重複 ID 和缺少入口會停止儲存。
- Git 推送改背景執行、NUL 格式處理中文與空白檔名，僅提交本次工具路徑，不夾帶其他已暫存變更。跨分類範圍的重新命名請用 Git 命令列確認。
- 顯示工具類型；Shader／引擎資源沒有可執行入口是正常的，請開啟資料夾閱讀各工具說明。

備份保留會占用磁碟空間；確認新版與個人資料正常後，可自行封存舊版備份。管理者密碼只防誤操作，不是 GitHub 權限控管；GitHub Token 不應分享或上傳。

## 驗證

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

測試使用獨立暫存目錄，不更動正式工具。包含資料保留、損壞下載、SHA、路徑防錯、Git 範圍、掃描、離線快取、Qt 生命週期，以及真正執行 PowerShell 更新器。建置依賴固定於 `requirements-build.txt`，測試失敗不會產生新版包。

## 開發執行

```powershell
cd manager
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python run.py
```

`run.py` 會自動切換到專案內的 `.venv`；也可以直接執行
`.\.venv\Scripts\python.exe run.py`。

## 設定 GitHub

第一次啟動後會建立 `config.json`。填入：

```json
{
  "github_owner": "你的GitHub帳號或組織",
  "github_repo": "你的repo名稱",
  "github_branch": "main"
}
```

GitHub repo 根目錄需要有 `tools-index.json`。

## 管理者流程

1. 打開管理者模式，預設密碼是 `12345678`。
2. 選擇工具包根目錄。
3. 掃描並更新文件。
4. 視需要編輯工具描述、版本、入口檔與標籤。
5. 儲存全部並更新總索引。
6. 將工具資料夾與 `tools-index.json` 上傳到 GitHub。

## 管理器本體更新

本體更新使用 GitHub Release：

1. 修改 `manager/toolkit_manager/models.py` 的 `APP_VERSION`。
2. 執行打包腳本產生 `dist/ToolkitManager.zip`。
3. 建立 GitHub Release，Tag 例如 `v1.1.0`。
4. 上傳 `ToolkitManager.zip`。

同事端啟動後會自動檢查新版，也可手動按「管理器更新」。

## 打包 EXE

```powershell
cd manager
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

輸出：

```text
dist/ToolkitManager/ToolkitManager.exe
dist/ToolkitManager.zip
```
