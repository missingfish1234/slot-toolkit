from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


APP_NAME = "小魚骨頭工作包管理器"
APP_VERSION = "1.2.0"
INDEX_FILE_NAME = "tools-index.json"
CATEGORY_SEPARATOR = " / "
CATEGORY_ROOT_ORDER = [
    "測試工具",
    "圖片處理工具",
    "數字圖片工具",
    "SPINE相關工具",
    "Sharder",
    "PS內插件",
    "COCOS內插件",
]


def category_parts(category: str) -> list[str]:
    return [part.strip() for part in category.split("/") if part.strip()]


def category_ancestors(category: str) -> list[str]:
    parts = category_parts(category)
    return [CATEGORY_SEPARATOR.join(parts[:index]) for index in range(1, len(parts) + 1)]


def category_filters(categories: list[str] | set[str]) -> list[str]:
    filters: set[str] = set()
    for category in categories:
        filters.update(category_ancestors(category))
    return sorted(filters, key=category_sort_key)


def category_matches(tool_category: str, selected_category: str) -> bool:
    tool_parts = category_parts(tool_category)
    selected_parts = category_parts(selected_category)
    return bool(selected_parts) and tool_parts[:len(selected_parts)] == selected_parts


def category_sort_key(category: str) -> tuple[int, tuple[str, ...]]:
    parts = category_parts(category)
    root = parts[0] if parts else ""
    try:
        root_order = CATEGORY_ROOT_ORDER.index(root)
    except ValueError:
        root_order = len(CATEGORY_ROOT_ORDER)
    return root_order, tuple(part.casefold() for part in parts)


def category_display_name(category: str) -> str:
    parts = category_parts(category)
    return parts[0] if len(parts) <= 1 else f"   ↳ {parts[-1]}"


@dataclass(slots=True)
class AppConfig:
    github_owner: str = "missingfish1234"
    github_repo: str = "slot-toolkit"
    github_branch: str = "main"
    github_token: str = ""
    install_root: str = "%USERPROFILE%\\Documents\\ToolkitManager\\Tools"
    admin_tools_root: str = ".."
    admin_password: str = "12345678"
    auto_check_on_start: bool = True
    auto_check_minutes: int = 30

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        defaults = cls()
        try:
            minutes = max(1, min(1440, int(data.get("auto_check_minutes", defaults.auto_check_minutes))))
        except (ValueError, TypeError):
            minutes = defaults.auto_check_minutes
        return cls(
            github_owner=str(data.get("github_owner") or defaults.github_owner),
            github_repo=str(data.get("github_repo") or defaults.github_repo),
            github_branch=str(data.get("github_branch") or defaults.github_branch),
            github_token=str(data.get("github_token", defaults.github_token)),
            install_root=str(data.get("install_root", defaults.install_root)),
            admin_tools_root=str(data.get("admin_tools_root", defaults.admin_tools_root)),
            admin_password=str(data.get("admin_password", defaults.admin_password)),
            auto_check_on_start=bool(data.get("auto_check_on_start", defaults.auto_check_on_start)),
            auto_check_minutes=minutes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "github_owner": self.github_owner,
            "github_repo": self.github_repo,
            "github_branch": self.github_branch,
            "github_token": self.github_token,
            "install_root": self.install_root,
            "admin_tools_root": self.admin_tools_root,
            "admin_password": self.admin_password,
            "auto_check_on_start": self.auto_check_on_start,
            "auto_check_minutes": self.auto_check_minutes,
        }

    @property
    def install_path(self) -> Path:
        return Path(expand_env(self.install_root)).resolve()


@dataclass(slots=True)
class ToolInfo:
    id: str
    name: str
    category: str
    description: str = ""
    version: str = "1.0.0"
    path: str = ""
    entry: str = ""
    icon: str = ""
    tags: list[str] = field(default_factory=list)
    updated_at: str = ""
    size: str = ""
    changelog: list[str] = field(default_factory=list)
    download_url: str = ""
    sha256: str = ""
    kind: str = ""
    preserve_paths: list[str] = field(default_factory=lambda: ["user-data", "outputs", "presets", "config.json", "settings.json"])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolInfo":
        if not isinstance(data, dict):
            raise ValueError("工具項目必須是物件。")
        for key in ("tags", "changelog", "preservePaths"):
            if key in data and not isinstance(data[key], list):
                raise ValueError(f"{key} 必須是陣列。")
        return cls(
            id=str(data.get("id") or slugify(str(data.get("name", "tool")))),
            name=str(data.get("name", "")),
            category=str(data.get("category", "未分類")),
            description=str(data.get("description", "")),
            version=str(data.get("version", "1.0.0")),
            path=normalize_slash(str(data.get("path", ""))),
            entry=normalize_slash(str(data.get("entry", ""))),
            icon=normalize_slash(str(data.get("icon", ""))),
            tags=[str(item) for item in data.get("tags", [])],
            updated_at=str(data.get("updatedAt") or data.get("updated_at") or ""),
            size=str(data.get("size", "")),
            changelog=[str(item) for item in data.get("changelog", [])],
            download_url=str(data.get("downloadUrl", "")),
            sha256=str(data.get("sha256", "")),
            kind=str(data.get("kind", "")),
            preserve_paths=[normalize_slash(str(item)) for item in data.get("preservePaths", ["user-data", "outputs", "presets", "config.json", "settings.json"])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "version": self.version,
            "path": self.path,
            "entry": self.entry,
            "icon": self.icon,
            "tags": self.tags,
            "updatedAt": self.updated_at,
            "size": self.size,
            "changelog": self.changelog,
            "downloadUrl": self.download_url,
            "sha256": self.sha256,
            "kind": self.kind,
            "preservePaths": self.preserve_paths,
        }


@dataclass(slots=True)
class ToolIndex:
    updated_at: str
    tools: list[ToolInfo]
    source_revision: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolIndex":
        if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
            raise ValueError("工具索引必須包含 tools 陣列。")
        ids = [item.get("id") for item in data["tools"] if isinstance(item, dict)]
        if len(ids) != len(data["tools"]) or any(not isinstance(value, str) or not value for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("工具索引包含無效或重複的識別碼。")
        return cls(
            updated_at=str(data.get("updatedAt") or data.get("updated_at") or ""),
            tools=[ToolInfo.from_dict(item) for item in data.get("tools", [])],
            source_revision=str(data.get("sourceRevision", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "updatedAt": self.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tools": [tool.to_dict() for tool in self.tools],
            "sourceRevision": self.source_revision,
        }


@dataclass(slots=True)
class InstalledTool:
    id: str
    version: str
    installed_at: str
    path: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InstalledTool":
        return cls(
            id=str(data.get("id", "")),
            version=str(data.get("version", "")),
            installed_at=str(data.get("installedAt") or data.get("installed_at") or ""),
            path=str(data.get("path", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "installedAt": self.installed_at,
            "path": self.path,
        }


@dataclass(slots=True)
class ManagerRelease:
    tag_name: str
    version: str
    name: str
    body: str
    asset_name: str
    asset_url: str
    sha256: str = ""


def normalize_slash(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def expand_env(value: str) -> str:
    import os

    return os.path.expandvars(value)


def slugify(value: str) -> str:
    safe = []
    for char in value.strip().lower():
        if char.isascii() and char.isalnum():
            safe.append(char)
        elif char in (" ", "-", "_", ".", "/"):
            safe.append("-")
        elif not char.isspace():
            safe.append(f"{ord(char):x}")
    slug = "".join(safe).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "tool"
