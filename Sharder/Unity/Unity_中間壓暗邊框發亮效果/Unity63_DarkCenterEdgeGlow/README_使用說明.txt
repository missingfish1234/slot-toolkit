Unity 6.3 / Built-in：Dark Center Edge Glow Distortion
=========================================================

用途
----
針對「透明底文字／圖騰 PNG」製作：
1. 圖形中心壓暗
2. 內外輪廓發光
3. 外圍光暈
4. Noise UV 擾動
5. 橫向電流波紋
6. 邊緣亮度不規則閃爍
7. 支援 UGUI Mask / RectMask2D

安裝
----
1. 把整個資料夾放進 Unity 專案 Assets。
2. 選取 Noise_Seamless_256.png：
   - Texture Type：Default
   - Wrap Mode：Repeat
   - Filter Mode：Bilinear
   - Compression：None 或 High Quality
   - sRGB：關閉（建議）
3. 建立 Material，Shader 選：
   Ark/UI/Dark Center Edge Glow Distortion
4. 把材質指定給 Canvas 下的 Image 或 RawImage。
5. MainTex 通常由 Image 自動提供；Noise Texture 指定 Noise_Seamless_256.png。

重要：圖片留白
--------------
外光暈只能畫在 UI 四邊形範圍內。
來源 PNG 的文字／圖騰四周請預留透明空間：
- 一般建議：16～32 px
- Glow Width 很大時：32～64 px
若使用 Sprite Atlas，請保留足夠 Padding / Extrude，避免採樣到相鄰圖片。

建議起始參數：藍色電光
----------------------
Center Color：接近黑藍
Keep Source RGB：0～0.1
Edge Glow Color：HDR 青藍；亮度可拉到 3～8
Bright Edge Width：2～4
Edge Sharpness：2～4
Bright Edge Intensity：1.5～3
Outer Glow Width：7～14
Outer Glow Intensity：0.8～2
Noise Scale：6～10
Noise Distortion Strength：0.002～0.006
Horizontal Wave Strength：0.0005～0.003
Edge Flicker Amount：0.15～0.4

建議起始參數：紫色靈氣
----------------------
Center Color：深紫黑
Edge Glow Color：HDR 紫紅或紫藍
Bright Edge Width：2～5
Outer Glow Width：10～18
Glow Intensity：1.2～2.5
Noise Distortion Strength：0.003～0.008
Edge Flicker Amount：0.25～0.55

真正的 Bloom
------------
Shader 本身會畫出外光暈；若要像參考圖那樣大範圍過曝，Camera 必須允許 HDR，
並在 Built-in Render Pipeline 安裝／啟用 Post Processing 的 Bloom。
沒有 Bloom 時仍會顯示亮邊與外圈，但不會產生跨像素的鏡頭泛光。

效能
----
此高品質版本每個像素會進行多次 MainTex 採樣，適合 Logo、標題、報獎文字等少量大型 UI。
不建議同時套在大量小圖騰或整個轉輪上。

常見問題
--------
1. 外光被裁掉：
   PNG 周圍透明留白不足，或 RectMask2D 正在裁切。

2. 邊緣出現其他圖案：
   Sprite Atlas padding 不足，採樣到相鄰 Sprite。

3. 擾動不動：
   Noise Texture 未指定、Wrap Mode 不是 Repeat，或 Noise Speed X/Y 都是 0。

4. 中間仍太亮：
   Center Color 調暗，Keep Source RGB 降到 0，Center Opacity 不需要降低。

5. 顏色沒有參考圖那麼亮：
   提高 HDR Edge Glow Color、Edge Intensity、Glow Intensity，並開啟 Bloom。
