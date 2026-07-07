# Spine Alpha Upscale Tool

Portable Real-ESRGAN upscaling tool for transparent Spine/game PNG parts.

The tool preserves the original alpha silhouette by:

1. Preparing clean RGB input from each transparent PNG.
2. Running Real-ESRGAN.
3. Reapplying the source alpha channel scaled to the same ratio.
4. Writing a validation CSV and preview contact sheet.

## Folder Contents

- `spine_alpha_upscale_tool.py` - main CLI tool
- `run_upscale_folder_4x.cmd` - Windows shortcut for 4x `realesr-animevideov3`
- `tools/realesrgan-ncnn-vulkan.exe` - Real-ESRGAN executable
- `tools/models/` - bundled Real-ESRGAN models

## Quick Run

Recommended for artists / general users:

```bat
啟動SPINE圖片解析度提高工具.cmd
```

The graphical interface lets you choose:

- source PNG folder
- output folder
- upscale ratio
- Real-ESRGAN model
- preview count
- whether to keep intermediate files

To upscale the parent folder of this tool folder:

```bat
run_upscale_folder_4x.cmd
```

To upscale a specific folder:

```bat
run_upscale_folder_4x.cmd "D:\path\to\images"
```

To choose both input and output folders:

```bat
run_upscale_folder_4x.cmd "D:\path\to\images" "D:\path\to\images_4x"
```

## CLI

```bat
python spine_alpha_upscale_tool.py ^
  --input "D:\path\to\images" ^
  --output "D:\path\to\images_4x" ^
  --scale 4 ^
  --model realesr-animevideov3
```

Supported models:

- `realesr-animevideov3`
- `realesrgan-x4plus-anime`
- `realesrgan-x4plus`

Supported scales:

- `2`
- `3`
- `4`

## Requirements

- Windows
- Python with Pillow installed
- The bundled `tools` folder must stay next to `spine_alpha_upscale_tool.py`

## Outputs

The output folder contains:

- Upscaled PNG files
- `_validation_report.csv`
- `_preview_contact_sheet.png`

Source PNG files are not overwritten.
