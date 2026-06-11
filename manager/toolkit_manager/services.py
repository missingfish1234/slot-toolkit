from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import AppConfig, INDEX_FILE_NAME, InstalledTool, ToolIndex, ToolInfo


ProgressCallback = Callable[[str, int], None]


class ConfigStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = base_dir / "config.json"

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            example = self.base_dir / "config.example.json"
            if not example.exists() and getattr(sys, "_MEIPASS", None):
                example = Path(sys._MEIPASS) / "config.example.json"  # type: ignore[attr-defined]
            if example.exists():
                shutil.copyfile(example, self.config_path)
            else:
                self.save(AppConfig())
        data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        return AppConfig.from_dict(data)

    def save(self, config: AppConfig) -> None:
        self.config_path.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class StateStore:
    def __init__(self, app_dir: Path) -> None:
        self.app_dir = app_dir
        self.state_path = app_dir / "state.json"
        self.app_dir.mkdir(parents=True, exist_ok=True)

    def load_installed(self) -> dict[str, InstalledTool]:
        if not self.state_path.exists():
            return {}
        data = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        return {
            item["id"]: InstalledTool.from_dict(item)
            for item in data.get("installed", [])
            if item.get("id")
        }

    def save_installed(self, installed: dict[str, InstalledTool]) -> None:
        self.state_path.write_text(
            json.dumps(
                {"installed": [item.to_dict() for item in installed.values()]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


class GitHubClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def is_configured(self) -> bool:
        return bool(self.config.github_owner and self.config.github_repo)

    def raw_url(self, path: str) -> str:
        return (
            f"https://raw.githubusercontent.com/"
            f"{self.config.github_owner}/{self.config.github_repo}/"
            f"{self.config.github_branch}/{path.strip('/')}"
        )

    def api_contents_url(self, path: str) -> str:
        return (
            f"https://api.github.com/repos/"
            f"{self.config.github_owner}/{self.config.github_repo}/contents/"
            f"{path.strip('/')}?ref={self.config.github_branch}"
        )

    def fetch_index(self) -> ToolIndex:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        data = request_json(self.raw_url(INDEX_FILE_NAME))
        return ToolIndex.from_dict(data)

    def download_tool(self, tool: ToolInfo, destination: Path, progress: ProgressCallback | None = None) -> None:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = destination.with_name(destination.name + ".download")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)

        files = self._list_files(tool.path)
        total = max(len(files), 1)
        for index, file_info in enumerate(files, start=1):
            rel_path = file_info["path"][len(tool.path):].strip("/")
            target = temp_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            download_url = file_info.get("download_url")
            if not download_url:
                continue
            download_file(download_url, target)
            if progress:
                progress(f"下載 {rel_path}", int(index / total * 100))

        ensure_safe_child(destination.parent, destination)
        if destination.exists():
            shutil.rmtree(destination)
        temp_dir.rename(destination)

    def _list_files(self, path: str) -> list[dict]:
        items = request_json(self.api_contents_url(path))
        if isinstance(items, dict) and items.get("type") == "file":
            return [items]
        files: list[dict] = []
        for item in items:
            if item.get("type") == "file":
                files.append(item)
            elif item.get("type") == "dir":
                files.extend(self._list_files(item["path"]))
        return files


class ToolLibrary:
    def __init__(self, config: AppConfig, state: StateStore) -> None:
        self.config = config
        self.state = state
        self.installed = state.load_installed()

    def status_for(self, tool: ToolInfo) -> str:
        local = self.installed.get(tool.id)
        if not local:
            return "未安裝"
        if not Path(local.path).exists():
            return "本機工具遺失"
        if compare_versions(local.version, tool.version) < 0:
            return "可更新"
        return "已是最新版"

    def install_path_for(self, tool: ToolInfo) -> Path:
        return self.config.install_path / tool.id

    def mark_installed(self, tool: ToolInfo, path: Path) -> None:
        self.installed[tool.id] = InstalledTool(
            id=tool.id,
            version=tool.version,
            installed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            path=str(path),
        )
        self.state.save_installed(self.installed)

    def launch(self, tool: ToolInfo) -> None:
        local = self.installed.get(tool.id)
        if not local:
            raise RuntimeError("工具尚未安裝。")
        base = Path(local.path)
        entry = base / tool.entry if tool.entry else base
        if not entry.exists():
            raise RuntimeError(f"找不到啟動檔：{entry}")
        open_path(entry)

    def open_folder(self, tool: ToolInfo) -> None:
        local = self.installed.get(tool.id)
        path = Path(local.path) if local else self.install_path_for(tool)
        path.mkdir(parents=True, exist_ok=True)
        open_path(path)


def app_data_dir() -> Path:
    root = os.environ.get("APPDATA")
    if root:
        return Path(root) / "ToolkitManager"
    return Path.home() / ".toolkit-manager"


def request_json(url: str) -> dict | list:
    request = urllib.request.Request(url, headers={"User-Agent": "ToolkitManager/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub 讀取失敗：HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub 連線失敗：{exc.reason}") from exc


def download_file(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ToolkitManager/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())


def compare_versions(left: str, right: str) -> int:
    def parts(value: str) -> list[int]:
        result = []
        for chunk in value.replace("-", ".").split("."):
            digits = "".join(char for char in chunk if char.isdigit())
            result.append(int(digits or 0))
        return result

    a = parts(left)
    b = parts(right)
    width = max(len(a), len(b))
    a += [0] * (width - len(a))
    b += [0] * (width - len(b))
    return (a > b) - (a < b)


def ensure_safe_child(root: Path, child: Path) -> None:
    root = root.resolve()
    child = child.resolve()
    if root != child and root not in child.parents:
        raise RuntimeError(f"不安全的路徑：{child}")


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
