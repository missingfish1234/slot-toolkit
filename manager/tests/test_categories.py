from __future__ import annotations

from pathlib import Path

from toolkit_manager.indexer import category_from_folder
from toolkit_manager.models import category_display_name, category_filters, category_matches

root = Path("C:/toolkit")
assert category_from_folder(root, root / "PS內插件" / "Photoshop工具") == "PS內插件"
assert category_from_folder(root, root / "測試工具" / "影片處理工具" / "影片工具") == "測試工具 / 影片處理工具"
assert category_from_folder(root, root / "Sharder" / "COCOS" / "掃光") == "Sharder / COCOS"
assert category_from_folder(root, root / "COCOS內插件" / "CocosCreator38Extension") == "COCOS內插件"

categories = {
    "PS內插件",
    "COCOS內插件",
    "測試工具 / 影片處理工具",
    "Sharder / COCOS",
    "Sharder / Unity",
}
filters = category_filters(categories)
assert "測試工具" in filters
assert "測試工具 / 影片處理工具" in filters
assert "PS內插件" in filters
assert "COCOS內插件" in filters
assert category_matches("Sharder / COCOS", "Sharder")
assert not category_matches("Sharder / Unity", "Sharder / COCOS")
assert category_display_name("Sharder / COCOS") == "   ↳ COCOS"

print("toolkit category tests passed")
