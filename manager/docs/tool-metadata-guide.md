# 工具描述撰寫規範

每個工具資料夾可以放一個 `tool.json`，管理者模式掃描時會優先讀取它。

## 檔案位置

範例：

```text
SPINE相關工具/
  SPINE合圖工具/
    tool.json
    spine_atlas_merge.html
```

## 基本範本

```json
{
  "id": "spine-atlas-merge",
  "name": "SPINE合圖工具",
  "category": "SPINE相關工具",
  "description": "將多組 Spine atlas 與貼圖整合成單一輸出，適合整理角色動畫資源與降低手動合圖時間。",
  "version": "1.0.0",
  "entry": "spine_atlas_merge.html",
  "tags": ["SPINE", "合圖", "atlas", "貼圖"],
  "updatedAt": "2026-06-11",
  "changelog": [
    "建立初版工具",
    "支援 atlas 與貼圖檔案拖放"
  ]
}
```

## description 寫法

建議一到兩句，讓同事一眼知道：

- 這個工具解決什麼問題
- 適合什麼使用情境
- 主要輸入/輸出是什麼

好範例：

```text
檢查 Spine 匯出檔案的版本、atlas、貼圖與 JSON 結構，協助美術與工程快速找出缺檔或格式錯誤。
```

不建議：

```text
好用工具。
```

```text
測試用。
```

## entry 寫法

`entry` 是同事按「開啟」時執行的檔案。

常見範例：

```json
"entry": "tool.exe"
```

```json
"entry": "index.html"
```

```json
"entry": "啟動本地伺服器.bat"
```

如果是 Shader、素材包、文件包，不需要開啟主程式，可以留空：

```json
"entry": ""
```

## version 寫法

建議使用三段式版本：

```text
1.0.0
1.1.0
1.1.1
```

規則：

- 大功能改版：`1.0.0 -> 1.1.0`
- 修 bug：`1.1.0 -> 1.1.1`
- 破壞性大改：`1.x.x -> 2.0.0`

## tags 寫法

放同事會搜尋的關鍵字，不要太多，3 到 6 個即可。

範例：

```json
"tags": ["SPINE", "檢查", "atlas", "JSON", "貼圖"]
```

## 更新流程

1. 在工具資料夾新增或修改 `tool.json`。
2. 開啟工具包管理器。
3. 進入「管理者模式」。
4. 掃描工具包根目錄。
5. 儲存 `tools-index.json`。
6. Commit 並 push 到 GitHub。
