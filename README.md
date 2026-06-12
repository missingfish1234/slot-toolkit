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
2. 執行 `manager/run.py`，打開「管理者模式」。
3. 輸入管理者密碼，預設為 `12345678`。
4. 按「掃描並更新文件」，程式會自動建立或更新每個工具資料夾的 `tool.json`，並更新根目錄 `tools-index.json`。
5. 在管理者模式右側欄位編輯工具名稱、用途描述、版本、入口檔、標籤與更新日誌。
6. 按「儲存目前工具」或「儲存全部並更新總索引」。
7. 參考 `manager/docs/tool-metadata-guide.md` 撰寫清楚的工具描述。
8. Commit 並 push 到 GitHub。

## 同事使用流程

1. 下載 `ToolkitManager.exe`。
2. 第一次打開後，到「設定」填入 GitHub：
   - GitHub Owner
   - GitHub Repo
   - Branch，一般為 `main`
3. 按「重新整理」讀取工具清單。
4. 點選工具後即可下載、更新、開啟或打開資料夾。

## 管理器本體更新

管理器會讀取 GitHub Release 最新版本。如果 Release tag 高於目前版本，會提示同事下載並更新管理器本體。

發布新版管理器流程：

1. 修改程式後確認 `manager/toolkit_manager/models.py` 內的 `APP_VERSION` 已升版。
2. 執行打包腳本。
3. 到 GitHub 建立新的 Release，Tag 例如 `v1.1.0`。
4. 上傳 `manager/dist/ToolkitManager.zip` 到該 Release。
5. 同事打開管理器後會自動檢查；也可手動按「管理器更新」。

## 打包工具管理器

```powershell
cd manager
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

輸出位置：

```text
manager/dist/ToolkitManager/ToolkitManager.exe
manager/dist/ToolkitManager.zip
```

請將 `ToolkitManager.zip` 上傳到 GitHub Release，讓管理器本體更新功能下載使用；不要把 `manager/dist/` 直接 commit 到 repo。

## 注意

- 目前 repo 需要設為 Public，管理器不需要 GitHub Token。
- GitHub 未登入 API 有流量限制，日常內部使用通常夠用。
- 有些資源型工具沒有啟動檔，下載後主要使用「資料夾」開啟。
- 管理者密碼可在「設定」調整；預設密碼是 `12345678`。
