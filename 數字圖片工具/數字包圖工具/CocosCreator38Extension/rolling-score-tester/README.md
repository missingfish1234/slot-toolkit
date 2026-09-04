# 滾分 QA 測試工具（Cocos Creator 3.8）

## v1.2.0

- 每次變更字串時先標記 Label render data dirty，再立即重建 assembler。
- 呼叫 Cocos 3.8 `cce.Engine.repaintInEditMode()`，修正 Inspector 字串有更新但 Scene 畫面停在舊數字。
- 保留 v1.1.0 的 15 FPS Scene 確認節流與寬度／SHRINK 診斷。

直接在 Cocos Scene 裡對 `cc.Label` 做滾分與 BMFont 壓力測試，並記錄：

- 設定字級 `fontSize` 與實際字級 `actualFontSize`
- `SHRINK` 發生時間與最小縮放比例
- 相同字數案例的渲染寬度漂移
- Label 邊界、`spacingX`、`lineHeight`、節點 Scale

## 安裝

將整個 `rolling-score-tester` 資料夾複製到：

```text
<Cocos 專案>/extensions/rolling-score-tester
```

回到 Creator 重新整理／啟用擴充功能，再從「面板 → 滾分 QA 測試工具」開啟。

## 使用

1. 在 Hierarchy 選取含 `Label` 的節點（也可選父節點）。
2. 按「綁定目前選取」，若找到多個 Label 可在下拉選單切換。
3. 設定起訖值、時間、FPS、格式與 easing，按「開始滾分」。
4. 按「字距／縮放壓力測試」檢查 `44444`、`41414`、`11111`、`99999`、千分位與極長數值。
5. 按「複製 JSON 報告」貼給美術或程式比對。

停止、重設或關閉面板時會還原測試前的 Label 字串。測試期間若 Scene 顯示為未儲存，確認還原後再決定是否儲存。

> v1.1.0 起，Scene 寫入上限為 15 FPS，且開始計時前會先等待 Cocos 確認起始值。即時監測顯示的是 Scene 實際回傳字串，不再顯示超前主畫面的面板預估值。建議把面板停駐在 Cocos 主視窗；浮動視窗仍可使用，但 Windows/Electron 可能降低背景主視窗的重繪頻率。

## 判讀

- `actualFontSize < fontSize`：Cocos 的 `SHRINK` 確實介入。
- `actualFontSize` 不變但視覺字距跳動：通常是 BMFont 的 `xadvance / xoffset / glyph width` 光學配置問題。
- 只有長字串縮小：通常是 Label 固定邊界不足，屬於預期的 `SHRINK` 行為。
