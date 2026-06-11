# 我的工具包

這個倉庫用來集中管理內部工具，並提供 Windows 桌面版「工具包管理器」讓同事檢視、下載與更新工具。

## 目前內容

- `tools-index.json`：工具管理器讀取的工具清單。
- `manager/`：工具包管理器原始碼與打包腳本。
- `Sharder/`：Shader 與效果相關工具。
- `SPINE相關工具/`：Spine 相關工具。
- `數字圖片工具/`：數字圖與圖片處理工具。
- `測試工具/`：各類測試工具。
- `design/`：UI 設計稿與設計規格。

## 管理者更新工具流程

1. 將新工具資料夾放進對應分類。
2. 需要工具名稱、用途描述、版本、入口檔時，在工具資料夾新增 `tool.json`。
3. 參考 `manager/docs/tool-metadata-guide.md` 撰寫工具描述。
4. 執行 `manager/run.py`，打開「管理者模式」。
5. 掃描工具包根目錄。
6. 儲存 `tools-index.json`。
7. Commit 並 push 到 GitHub。

## 同事使用流程

1. 下載 `ToolkitManager.exe`。
2. 第一次打開後，到「設定」填入 GitHub：
   - GitHub Owner
   - GitHub Repo
   - Branch，一般為 `main`
3. 按「重新整理」讀取工具清單。
4. 點選工具後即可下載、更新、開啟或打開資料夾。

## 打包工具管理器

```powershell
cd manager
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

輸出位置：

```text
manager/dist/ToolkitManager/ToolkitManager.exe
```

建議將打包結果上傳到 GitHub Release，讓同事下載 Release 裡的 EXE，不要把 `manager/dist/` 直接 commit 到 repo。

## 注意

- 目前 repo 需要設為 Public，管理器不需要 GitHub Token。
- GitHub 未登入 API 有流量限制，日常內部使用通常夠用。
- 有些資源型工具沒有啟動檔，下載後主要使用「資料夾」開啟。
