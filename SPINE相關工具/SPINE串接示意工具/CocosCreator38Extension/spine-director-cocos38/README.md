# Cocos Timeline / Spine Director 0.13.0

適用：

- Cocos Creator `3.8.x`
- Spine runtime `3.8`
- Cocos Scene 內的一般節點、`sp.Skeleton`、`ParticleSystem2D`、
  `ParticleSystem` 與 `Animation`

不支援 Spine 4.x。

## 安裝

將 `spine-director-cocos38` 複製到目標專案：

```text
<Cocos 專案>/extensions/spine-director-cocos38
```

回到 Creator 重新整理擴充功能並啟用，再從
「面板 → Spine Director 3.8」開啟。

若擴充功能管理員解壓縮失敗，可執行上層資料夾的
`Install-Cocos38Extension.cmd`。

## Unity Timeline 式工作方式

1. 使用 Cocos 原本的 Assets，把 Spine、粒子、Sprite 或 Prefab 拖進 Scene。
2. 從 Hierarchy 將節點拖進 Timeline。外掛使用 Cocos 3.8 原生的
   `cc.Node` 拖放協定，不會再把它當成一般網頁拖放。
3. 若目前的面板配置攔截拖曳，可先在 Hierarchy 點選節點，再按
   空白 Timeline 中的「將目前選取加入 Timeline」。
4. Timeline 會依元件自動建立 Transform、Spine Animation、
   Particle System 2D/3D 與 Cocos Animation 子軌。
5. 雙擊空白子軌，或按子軌右側 `＋`：
   - Transform：記錄 Key。
   - Spine/Cocos Animation：直接選擇動作。
   - Particle：建立粒子片段。
6. 拖曳片段本體可調整開始時間，拖曳左右邊緣可 Trim 長度。
7. 按紅色 `●` 進入 Record 模式，在 Scene 或 Inspector 移動節點會
   自動在目前播放頭記錄 Transform。
8. 右側 Inspector 可精確修改時間、長度、動畫與 Loop。
9. 播放或拖曳時間時，結果會直接顯示在 Cocos Scene；按停止可還原。

## 片段編輯工具

- 不同 Spine/Cocos 動畫會依動畫清單分配不同顏色，同名動畫維持同色。
- `🧲 磁吸` 預設開啟：片段會吸附播放頭、時間軸起訖與同軌片段邊界。
- `⇥ 推擠` 預設開啟：新增、移動、Trim 或更換動畫長度時，
  會連鎖推動後續片段，必要時自動延長 Timeline。
- 關閉「推擠」後可讓片段重疊；關閉「磁吸」後仍維持 FPS 對格。
- 在 Timeline 上滾動滑鼠滾輪，會以游標所在時間為中心縮放刻度。
- 縮放範圍為 `10%` 到 `3200%`；低於 `100%` 時可在較小面板內
  同時看到更長的時間刻度範圍。
- 按住滑鼠中鍵拖曳，可水平移動時間及垂直捲動軌道。
- 選取 Transform Key 或動畫／粒子片段後，可按 `Delete` 或
  `Backspace` 刪除。
- 時間尺會依縮放倍率自動調整秒／小數秒刻度；工具列的倍率按鈕可
  一鍵回到 `Fit 100%`。

這個流程不會複製素材，也不會再建立 `[SpineDirector]` 預覽節點。

## 儲存與開啟

「自動長度」預設開啟，Timeline 長度會取所有動畫片段終點與
Transform 關鍵幀的最晚時間。勾選 Loop 時會在這個時間點回到 0 秒。
取消「自動長度」後才會使用工具列手動輸入的長度。

「儲存」會依 Timeline 名稱建立獨立資料夾：

```text
assets/Game/Animation/Timeline/
├─ runtime/CocosTimelinePlayer.ts
├─ <名稱 A>/
│  ├─ resources/<名稱 A>.timeline.json
│  └─ TimelinePlayer_<名稱 A>.ts
└─ <名稱 B>/
   ├─ resources/<名稱 B>.timeline.json
   └─ TimelinePlayer_<名稱 B>.ts
```

`resources` 這一層不能省略，因為正式建置後播放器會透過
`resources.load()` 載入 Timeline JSON。

第一個加入 Timeline 的 Scene 物件若位於 Prefab 階層內，工具會嘗試使用
它的父節點名稱取代預設 `MainTimeline`。請在儲存前確認工具列的 Timeline
名稱與 Prefab 名稱一致，例如 `SugarRushBoom`，即可直接從資料夾辨識對應關係。
要製作第二份動畫，先按工具列的「新增 Timeline」建立空白內容，再加入另一個
Prefab 內的物件並確認名稱，不必覆寫第一份 Timeline。

要開啟既有 Timeline，先在 Assets 選取一個 `.timeline.json`，
再按面板的「開啟」。

遊戲使用時，把 `TimelinePlayer_<名稱>` 元件加到 Scene 任一管理節點，
即可使用 `play()`、`pause()`、`stop()` 與 `seek(seconds)`。播放器會優先
以 Hierarchy 路徑綁定既有 Scene 節點，並以 UUID 作為備援。

`TimelinePlayer_<名稱>` 是每一份 Timeline 的入口元件；
`runtime/CocosTimelinePlayer.ts` 是所有 Timeline 共用的播放器，不需要手動掛載；
`.timeline.json` 是動作、片段與節點綁定資料，也不需要手動拖到 Inspector。

若同名 Timeline 曾由 0.9.x 或 0.10.x 輸出到舊位置，再次按「儲存」時會
移除舊位置的同名 JSON 與入口元件，避免 Cocos 出現重複的 `ccclass`。

## 預覽差異

- Transform、Spine 3.8 與 Cocos Animation 可依播放頭精確取樣。
- 只要物件具有 Spine Animation 片段，片段外會停用 `sp.Skeleton` 顯示，
  進入片段時才重新啟用；停止預覽後會還原元件原本的 enabled 狀態。
- 只有 Transform 關鍵幀、沒有 Spine Animation 片段的物件不會被自動隱藏。
- ParticleSystem2D 在停止播放時會由編輯器重新模擬到目前時間。
- Cocos 3.8 的 3D ParticleSystem 沒有公開的 seek API；拖曳播放頭時
  會重啟並暫停粒子，正常播放時則由 Cocos 引擎連續模擬。

舊版 Pixi 編輯器仍保留在 `static/SpinePlayTest-Cocos38.html`，
但不再是主要面板。
