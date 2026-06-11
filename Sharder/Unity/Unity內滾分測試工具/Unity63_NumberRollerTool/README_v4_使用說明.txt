Unity63 Number Roller Tool v4
============================

主要新增：
1. Robust Number Roller v4
   Component 選單：Slot Tools / Number Roller / Robust Number Roller v4

2. 支援 UGUI_IMAGE Text Font / MakeFont 包圖字典
   - Glyph Source 選 UGUIImageTextFontPrefab
   - uguiImageTextFontObject 拖入你的數字字型 prefab 或掛有 FontDictionary / m_SpriteAry 的 Component
   - 按「從 UGUI_IMAGE 字典抽出到 Direct Sprites」最穩，會自動把 0~9、逗號、小數點、B/E/K/M/P/T/X/Y/Z 抽出
   - 抽出後 Glyph Source 會切成 DirectSprites

3. 支援一分一分快速滾上去
   建議設定：
   - Display Mode = ImageOdometer
   - Count Mode = StepPerTick
   - Points Per Tick = 1
   - Tick Interval = 0.005 ~ 0.02
   - Odometer Follows Current Value = 開
   這樣輪帶會根據目前分數逐位滾動，不會一下整排轉到目標。

4. 速度模式說明
   - DurationSmooth：固定時間從起始補間到目標，適合一般文字滾分
   - UnitsPerSecond：依每秒分數速度前進，例如每秒 6000 分
   - StepPerTick：固定每 tick 增加 pointsPerTick，最適合「一分一分」的老虎機分數感

5. 你的範例 prefab 結構
   你提供的 FuXiangKaoChao4_LineBetNum.prefab / Onmyoji_FG_BonusNum.prefab 內有：
   - FontDictionary._Keys
   - FontDictionary._Values
   - m_SpriteAry
   所以 v4 會嘗試讀這些欄位。

建議第一次測試：
- Canvas 下建立 Empty UI Object
- 掛 Robust Number Roller v4
- Display Mode = ImageOdometer
- Glyph Source = UGUIImageTextFontPrefab
- uguiImageTextFontObject = 拖入你的數字 prefab 或 Component
- 按「從 UGUI_IMAGE 字典抽出到 Direct Sprites」
- 按「重建顯示」
- Play Mode 後按「播放滾分」
