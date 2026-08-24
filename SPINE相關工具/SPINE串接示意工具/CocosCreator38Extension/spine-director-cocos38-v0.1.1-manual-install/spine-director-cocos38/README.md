# Spine Director for Cocos Creator 3.8

支援：

- Cocos Creator `3.8.x`
- Spine `3.8`
- `.skel/.json + .atlas + .png`

不支援 Spine 4.x；若需原生平台，請避免使用 Spine `3.8.75`。

## 建議安裝方式

1. 在 Creator 3.8 開啟目標專案。
2. 開啟「擴充功能管理員」。
3. 選擇匯入擴充功能資料夾，指定本資料夾 `spine-director-cocos38`。
4. 重新整理擴充功能清單並啟用。
5. 從「面板 → Spine Director 3.8」開啟工具。

若匯入 ZIP 顯示 `Decompression failed`，請改用：

- `spine-director-cocos38-v0.1.1-compat.zip`（相容封裝）；或
- 解壓縮手動安裝包後，雙擊 `Install-Cocos38Extension.cmd`。

也可以把本資料夾直接複製到 Cocos 專案的
`extensions/spine-director-cocos38`，再回 Creator 重新整理。

## 使用

1. 開啟工具並匯入 Spine 3.8 的 `.skel/.json`、`.atlas` 與貼圖。
2. 在時間軸完成編排。
3. 按「輸出至 Cocos 專案」。
4. 等 Creator 完成 TypeScript 編譯與資源匯入。
5. 開啟目標場景。
6. 按「建立播放器節點」，工具會在第一個 Canvas 下建立播放器。

輸出內容：

- `assets/resources/spine-director/<專案名稱>/`：Spine 資源與 `director.json`
- `assets/spine-director/runtime/SpineDirectorPlayer.ts`：共用播放器
- `assets/spine-director/SpineDirectorEntry_<專案名稱>.ts`：專案入口元件

## 已支援的時間軸資料

- 多個 Spine Track
- Loop、Mix Duration
- 位置、旋轉、縮放、透明度與 easing
- 物理下落與落地事件
- 圖片軌道
- 專案背景色

## 離線使用

PixiJS、Pixi Spine 3.8 與時間軸套件已放在 `static/vendor`，
工具不依賴 CDN。
