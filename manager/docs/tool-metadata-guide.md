# 工具描述撰寫規範

每個工具資料夾會有一個 `tool.json`，管理者模式掃描時會自動建立或更新它，並同步更新根目錄的 `tools-index.json`。

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

1. 將新工具資料夾放進對應分類。
2. 開啟工具包管理器。
3. 進入「管理者模式」，預設密碼為 `12345678`。
4. 按「掃描並更新文件」建立或更新各工具資料夾的 `tool.json`。
5. 在右側欄位修改工具名稱、用途描述、版本、入口檔、標籤與更新日誌。
6. 按「儲存目前工具」或「儲存全部並更新總索引」。
7. Commit 並 push 到 GitHub。
