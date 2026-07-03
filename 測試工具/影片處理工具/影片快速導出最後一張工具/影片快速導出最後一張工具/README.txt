# 影片最後一幀輸出工具 - 自動安裝依賴版

## 啟動方式
雙擊：
run_tool.bat

第一次啟動時，如果電腦沒有安裝 opencv-python 或 pillow，工具會自動安裝。

## 如果還是出現 cv2 錯誤
請雙擊：
fix_package.bat

或手動在 CMD 輸入：

py -3 -m pip install opencv-python pillow

如果你電腦沒有 py 指令，改用：

python -m pip install opencv-python pillow

## 功能
- 單一影片輸出最後一幀
- 資料夾批次輸出每支影片最後一幀
- 支援 mp4 / mov / avi / mkv / webm / m4v
- 可輸出 PNG 或 JPG

## 輸出檔名
原影片名稱_last_frame.png

例如：
demo.mp4
會輸出：
demo_last_frame.png
