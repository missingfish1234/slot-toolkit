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

1. 打開管理者模式。
2. 選擇工具包根目錄。
3. 掃描工具。
4. 儲存 `tools-index.json`。
5. 將工具資料夾與 `tools-index.json` 上傳到 GitHub。

## 打包 EXE

```powershell
cd manager
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```
