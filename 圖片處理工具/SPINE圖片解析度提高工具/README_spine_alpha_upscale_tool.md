# SPINE圖片解析度提高工具

針對 SPINE / 遊戲透明 PNG 拆件進行 Real-ESRGAN 放大，並保留原始 alpha 輪廓。

這個工具會：

1. 讀取來源資料夾內的 PNG。
2. 裁切可見範圍並補乾淨 RGB 底色，降低透明區域造成的雜訊。
3. 逐張呼叫 Real-ESRGAN，避免整包批次推論造成 Vulkan 黑圖或彩色條紋。
4. 將原圖 alpha 依倍率放大後套回輸出圖。
5. 檢查輸出品質，若偵測到黑化、嚴重偏色或條紋，會自動回退成乾淨的傳統放大。
6. 輸出 `_validation_report.csv` 與 `_preview_contact_sheet.png` 方便檢查。

## 快速使用

一般使用請直接雙擊：

```bat
啟動SPINE圖片解析度提高工具.cmd
```

圖形介面可設定：

- 來源 PNG 資料夾
- 輸出資料夾
- 放大倍率
- Real-ESRGAN 模型
- Tile Size
- 預覽圖數量
- 是否保留中介檔

## 命令列

```bat
python spine_alpha_upscale_tool.py ^
  --input "D:\path\to\images" ^
  --output "D:\path\to\images_4x" ^
  --scale 4 ^
  --model realesr-animevideov3
```

支援模型：

- `realesr-animevideov3`
- `realesrgan-x4plus-anime`
- `realesrgan-x4plus`

支援倍率：

- `2`
- `3`
- `4`

## 資料夾內容

- `spine_alpha_upscale_tool.py`：主要工具
- `啟動SPINE圖片解析度提高工具.cmd`：圖形介面啟動檔
- `run_upscale_folder_4x.cmd`：命令列快速放大啟動檔
- `tools/realesrgan-ncnn-vulkan.exe`：Real-ESRGAN 執行檔
- `tools/models/`：Real-ESRGAN 模型

## 注意事項

- 需要 Windows 與 Python。
- Python 需要安裝 Pillow。
- `tools` 資料夾必須和 `spine_alpha_upscale_tool.py` 放在同一層。
- 若報告中的 `fallback_used` 為 `True`，代表該圖的 AI 輸出被判定異常，已自動改用乾淨放大保護結果。
