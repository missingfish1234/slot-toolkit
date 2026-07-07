@echo off
setlocal
cd /d "%~dp0"

set "INPUT=%~1"
if "%INPUT%"=="" set "INPUT=%~dp0.."

set "OUTPUT=%~2"
if "%OUTPUT%"=="" set "OUTPUT=%INPUT%\IMAGE2_4x_realesr_animevideov3"

python "%~dp0spine_alpha_upscale_tool.py" ^
  --input "%INPUT%" ^
  --output "%OUTPUT%" ^
  --work "%OUTPUT%_work" ^
  --scale 4 ^
  --model realesr-animevideov3 ^
  --exe "%~dp0tools\realesrgan-ncnn-vulkan.exe" ^
  --model-dir "%~dp0tools\models" ^
  --keep-work

pause
