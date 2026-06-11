# Spine 功能問題解決方案

## ✅ 本地檔案已下載完成

**已下載的檔案：**
- `spine-player.js` (606KB) - Spine Player JavaScript 程式庫
- `spine-player.css` (27KB) - Spine Player 樣式表

---

## 🔴 常見問題：資源檔案無法載入

### 錯誤訊息
```
Spine Player 初始化失敗: Assets could not be loaded.
Couldn't load JSON BeachIdol_MG_Symbol_001.json: status 400
Couldn't load texture atlas BeachIdol_MG_Symbol_001.atlas: status 400
```

### 問題原因
當在本地檔案系統（file://）運行 HTML 時，瀏覽器 CORS 安全限制阻止載入資源檔案。

---

## ✅ 快速解決方案（推薦）

### 方案 1：使用本地 HTTP 伺服器（100% 成功率）

**最簡單的方法：**
1. 找到資料夾內的 `啟動本地伺服器.bat` 檔案
2. 雙擊執行
3. 在瀏覽器中開啟：`http://localhost:8000/slot_test.html`
4. ✅ Spine 動畫功能完全正常！

**原理：** HTTP 伺服器繞過了本地檔案系統的 CORS 限制

---

## 📋 詳細說明

### 為什麼需要 HTTP 伺服器？

| 運行方式 | 協議 | CORS | Spine 資源 | 其他功能 |
|---------|------|------|---------|--------|
| 直接開啟 HTML | `file://` | ❌ 受限 | ❌ 失敗 | ⚠️ 受限 |
| HTTP 伺服器 | `http://` | ✅ 允許 | ✅ 成功 | ✅ 正常 |

### 資源檔案路徑說明

Spine 資源檔案應該與 HTML 在相同或指定的相對路徑：

```
轉輪測試工具/
├── slot_test.html           ← 主 HTML 檔案
├── spine-player.js         ← Spine Player 函式庫
├── spine-player.css        ← Spine Player 樣式
├── 沙灘甜心測試資料/
│   ├── 沙灘甜心轉輪測試.json
│   └── JASON檔/
│       ├── BeachIdol_MG_Symbol_001.json    ← Spine 資源
│       └── BeachIdol_MG_Symbol_001.atlas   ← Spine 資源
└── ... 其他檔案
```

---

## 🔧 進階設定

### 自訂 Spine 資源路徑

如果 Spine 資源在特定資料夾，可以修改 HTML 中的路徑配置：

```javascript
// 在上傳 Spine 資源時指定路徑
{
    "jsonName": "沙灘甜心測試資料/JASON檔/BeachIdol_MG_Symbol_001.json",
    "atlasName": "沙灘甜心測試資料/JASON檔/BeachIdol_MG_Symbol_001.atlas",
    "rawDataURIs": [/* ... */]
}
```

---

## ✅ 其他解決方案

### 方案 2：瀏覽器設定（不推薦）
- 安裝 "Allow CORS" 瀏覽器擴充功能
- 限制性強，不穩定

### 方案 3：上傳到網路伺服器
- 在線測試
- 成本較高

---

## 💡 最佳實踐

1. **開發調試** → 使用本地 HTTP 伺服器
2. **團隊測試** → 上傳到測試伺服器
3. **線上發佈** → 部署到生產環境

---

## 🎯 確認 Spine 正常運作

執行以下測試：

1. 啟動本地伺服器
2. 開啟 `http://localhost:8000/slot_test.html`
3. 上傳含有 Spine 資源的測試資料
4. 查看瀏覽器控制台（F12）
5. 應該看到信息：
   ```
   ✅ 本地 Spine Player 載入成功
   ✅ Spine 動畫播放中...
   ```

未出現錯誤信息 = Spine 功能正常 ✅

---

## 📞 需要幫助？

如有問題，請檢查：
1. HTTP 伺服器是否正常運行
2. Spine 資源檔案是否存在
3. 瀏覽器控制台的錯誤訊息