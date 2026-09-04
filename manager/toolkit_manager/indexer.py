from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import CATEGORY_SEPARATOR, INDEX_FILE_NAME, ToolIndex, ToolInfo, slugify


IGNORED_DIRS = {
    ".git",
    ".github",
    ".venv",
    "__pycache__",
    "manager",
    "design",
    "dist",
    "build",
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
        if category_dir.name in IGNORED_DIRS:
            continue

        for tool_dir in collect_tool_dirs(category_dir):
            tools.append(build_tool_info(root, tool_dir, category_dir.name))

    return ToolIndex(
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        tools=tools,
    )


def collect_tool_dirs(category_dir: Path) -> list[Path]:
    result: list[Path] = []

    def visit(path: Path) -> None:
        children = sorted(
            [p for p in path.iterdir() if p.is_dir() and p.name not in IGNORED_DIRS],
            key=lambda p: p.name.lower(),
        )
        direct_files = [
            p for p in path.iterdir()
            if p.is_file() and p.name not in {"tool.json", "tools-index.json"}
        ]

        if direct_files:
            result.append(path)
            return

        for child in children:
            visit(child)

    visit(category_dir)
    if result == [category_dir]:
        return result
    return [path for path in result if path != category_dir]


def build_tool_info(root: Path, tool_dir: Path, category: str) -> ToolInfo:
    meta_path = tool_dir / "tool.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8-sig"))
            tool = ToolInfo.from_dict(data)
        except Exception:
            tool = infer_tool_info(root, tool_dir, category)
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
    if not tool.size:
        tool.size = format_size(folder_size(tool_dir))
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
        matches = sorted(tool_dir.glob(pattern), key=lambda p: p.name.lower())
        if matches:
            return matches[0]
    for pattern in ENTRY_PRIORITY:
        matches = sorted(tool_dir.rglob(pattern), key=lambda p: (len(p.parts), p.name.lower()))
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
    output_path.write_text(
        json.dumps(index.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_tool_metadata(root: Path, tool: ToolInfo) -> Path:
    metadata_path = root.resolve() / tool.path / "tool.json"
    metadata_path.write_text(
        json.dumps(tool.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return metadata_path


def save_all_tool_metadata(root: Path, index: ToolIndex) -> None:
    root = root.resolve()
    for tool in index.tools:
        save_tool_metadata(root, tool)
