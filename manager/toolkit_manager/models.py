from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


APP_NAME = "小魚骨頭工作包管理器"
APP_VERSION = "1.1.4"
INDEX_FILE_NAME = "tools-index.json"


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
        return cls(
            github_owner=str(data.get("github_owner") or defaults.github_owner),
            github_repo=str(data.get("github_repo") or defaults.github_repo),
            github_branch=str(data.get("github_branch") or defaults.github_branch),
            github_token=str(data.get("github_token", defaults.github_token)),
            install_root=str(data.get("install_root", defaults.install_root)),
            admin_tools_root=str(data.get("admin_tools_root", defaults.admin_tools_root)),
            admin_password=str(data.get("admin_password", defaults.admin_password)),
            auto_check_on_start=bool(data.get("auto_check_on_start", defaults.auto_check_on_start)),
            auto_check_minutes=int(data.get("auto_check_minutes", defaults.auto_check_minutes)),
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolInfo":
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
        }


@dataclass(slots=True)
class ToolIndex:
    updated_at: str
    tools: list[ToolInfo]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolIndex":
        return cls(
            updated_at=str(data.get("updatedAt") or data.get("updated_at") or ""),
            tools=[ToolInfo.from_dict(item) for item in data.get("tools", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "updatedAt": self.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tools": [tool.to_dict() for tool in self.tools],
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
