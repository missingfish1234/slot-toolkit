# 工具包管理器

Windows 桌面工具，用來從 GitHub 公開倉庫檢視、下載、更新與開啟工具。

## 開發執行

```powershell
cd manager
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

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
