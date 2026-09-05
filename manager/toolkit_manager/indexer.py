from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import CATEGORY_SEPARATOR, INDEX_FILE_NAME, ToolIndex, ToolInfo, slugify
from .storage import atomic_json


IGNORED_DIRS = {
    ".git",
    ".github",
    ".venv",
    "__pycache__",
    "manager",
    "design",
    "dist",
    "build",
    "docs",
    "tests",
    "scripts",
    "node_modules",
    "vendor",
    "backups",
    "Old",
    "舊版",
    "舊版本",
}

ENTRY_PRIORITY = [
    "*.exe",
    "*.bat",
    "*.cmd",
    "*.html",
    "*.py",
    "*.ps1",
]


def scan_tools(root: Path) -> ToolIndex:
    root = root.resolve()
    tools: list[ToolInfo] = []

    for category_dir in sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        if category_dir.name in IGNORED_DIRS or category_dir.name.startswith(".") or category_dir.is_symlink() or getattr(category_dir, "is_junction", lambda: False)():
            continue

        for tool_dir in collect_tool_dirs(category_dir):
            tools.append(build_tool_info(root, tool_dir, category_dir.name))

    ids = [tool.id for tool in tools]
    if len(ids) != len(set(ids)):
        raise ValueError("工具識別碼重複，請先修正 tool.json，原始資料尚未儲存。")
    return ToolIndex(
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        tools=tools,
    )


def collect_tool_dirs(category_dir: Path) -> list[Path]:
    result: list[Path] = []

    def visit(path: Path) -> None:
        children = sorted(
            [p for p in path.iterdir() if p.is_dir() and p.name not in IGNORED_DIRS and not p.is_symlink() and not getattr(p, "is_junction", lambda: False)() and not p.name.startswith(".")],
            key=lambda p: p.name.lower(),
        )
        direct_files = [
            p for p in path.iterdir()
            if p.is_file() and p.name not in {"tool.json", "tools-index.json"}
        ]

        if (path / "tool.json").is_file():
            result.append(path)
            # A nested extension is a separate tool only when explicitly registered.
            for child in children:
                visit_registered(child)
            return

        runnable = any(p.suffix.lower() in {".exe", ".bat", ".cmd", ".html", ".py", ".ps1", ".effect", ".shader", ".cs", ".ccx"} for p in direct_files)
        if runnable:
            result.append(path)
            for child in children:
                visit_registered(child)
            return

        for child in children:
            visit(child)

    def visit_registered(path: Path) -> None:
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            return
        if (path / "tool.json").is_file():
            visit(path)
            return
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and child.name not in IGNORED_DIRS and not child.name.startswith("."):
                visit_registered(child)

    visit(category_dir)
    if result == [category_dir]:
        return result
    return [path for path in result if path != category_dir]


def build_tool_info(root: Path, tool_dir: Path, category: str) -> ToolInfo:
    meta_path = tool_dir / "tool.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or not data.get("id") or not data.get("name") or not data.get("version"):
                raise ValueError("tool.json 必須有 id、name、version。")
            tool = ToolInfo.from_dict(data)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"工具資料格式錯誤，已保留原檔，請先修正：{meta_path}\n{exc}") from exc
    else:
        tool = infer_tool_info(root, tool_dir, category)

    tool.path = tool_dir.relative_to(root).as_posix()
    tool.category = category_from_folder(root, tool_dir, category)
    category_tags = [tool.category, *tool.category.split(CATEGORY_SEPARATOR)]
    tool.tags = list(dict.fromkeys([*category_tags, *tool.tags, tool.name]))
    if not tool.entry:
        entry = find_entry_file(tool_dir)
        tool.entry = entry.relative_to(tool_dir).as_posix() if entry else ""
    if not tool.updated_at:
        tool.updated_at = datetime.fromtimestamp(tool_dir.stat().st_mtime).strftime("%Y-%m-%d")
    if tool.entry and not (tool_dir / tool.entry).is_file():
        raise ValueError(f"工具入口不存在：{tool_dir / tool.entry}")
    if tool.entry and tool_dir.resolve() not in (tool_dir / tool.entry).resolve().parents:
        raise ValueError(f"工具入口超出工具目錄：{tool.entry}")
    tool.size = format_size(folder_size(tool_dir))
    if not tool.kind:
        tool.kind = infer_kind(tool)
    return tool


def category_from_folder(root: Path, tool_dir: Path, fallback: str = "未分類") -> str:
    """Use the first two folder levels above a tool as its visible category path."""
    relative = tool_dir.resolve().relative_to(root.resolve())
    parents = list(relative.parts[:-1])
    if not parents:
        return fallback
    return CATEGORY_SEPARATOR.join(parents[:2])


def infer_tool_info(root: Path, tool_dir: Path, category: str) -> ToolInfo:
    name = tool_dir.name
    rel_path = tool_dir.relative_to(root).as_posix()
    return ToolInfo(
        id=slugify(rel_path),
        name=name,
        category=category,
        description="",
        version="1.0.0",
        path=rel_path,
        entry="",
        icon="",
        tags=[category, name],
        updated_at=datetime.fromtimestamp(tool_dir.stat().st_mtime).strftime("%Y-%m-%d"),
        size=format_size(folder_size(tool_dir)),
        changelog=[],
    )


def find_entry_file(tool_dir: Path) -> Path | None:
    for pattern in ENTRY_PRIORITY:
        matches = sorted((p for p in tool_dir.glob(pattern) if not p.name.lower().startswith(("fix_", "build_", "test_", "setup"))), key=lambda p: p.name.lower())
        if matches:
            return matches[0]
    for pattern in ENTRY_PRIORITY:
        matches = sorted((p for p in tool_dir.rglob(pattern) if not any(part in IGNORED_DIRS for part in p.relative_to(tool_dir).parts[:-1]) and not p.name.lower().startswith(("fix_", "build_", "test_", "setup"))), key=lambda p: (len(p.parts), p.name.lower()))
        if matches:
            return matches[0]
    return None


def folder_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def format_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def save_index(index: ToolIndex, output_path: Path) -> None:
    atomic_json(output_path, index.to_dict(), backup=False)


def save_tool_metadata(root: Path, tool: ToolInfo) -> Path:
    root = root.resolve()
    metadata_path = root / tool.path / "tool.json"
    if root not in metadata_path.resolve().parents:
        raise ValueError(f"工具資料路徑超出工具包：{metadata_path}")
    atomic_json(metadata_path, tool.to_dict(), backup=False)
    return metadata_path


def save_all_tool_metadata(root: Path, index: ToolIndex) -> None:
    root = root.resolve()
    for tool in index.tools:
        save_tool_metadata(root, tool)


def infer_kind(tool: ToolInfo) -> str:
    if tool.category.startswith("PS內插件"):
        return "Photoshop 插件"
    if tool.category.startswith("COCOS內插件"):
        return "Cocos Creator 插件"
    if not tool.entry:
        return "引擎資源"
    suffix = Path(tool.entry).suffix.lower()
    return {".html": "網頁工具", ".py": "Python 工具", ".exe": "桌面工具", ".zip": "安裝套件"}.get(suffix, "啟動器")
