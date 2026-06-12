from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import AppConfig, INDEX_FILE_NAME, InstalledTool, ManagerRelease, ToolIndex, ToolInfo


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
        encoded_path = urllib.parse.quote(path.strip("/"), safe="/")
        encoded_branch = urllib.parse.quote(self.config.github_branch, safe="")
        return (
            f"https://raw.githubusercontent.com/"
            f"{self.config.github_owner}/{self.config.github_repo}/"
            f"{encoded_branch}/{encoded_path}"
        )

    def api_contents_url(self, path: str) -> str:
        encoded_path = urllib.parse.quote(path.strip("/"), safe="/")
        encoded_branch = urllib.parse.quote(self.config.github_branch, safe="")
        return (
            f"https://api.github.com/repos/"
            f"{self.config.github_owner}/{self.config.github_repo}/contents/"
            f"{encoded_path}?ref={encoded_branch}"
        )

    def archive_url(self) -> str:
        encoded_branch = urllib.parse.quote(self.config.github_branch, safe="/")
        return (
            f"https://codeload.github.com/"
            f"{self.config.github_owner}/{self.config.github_repo}/zip/refs/heads/"
            f"{encoded_branch}"
        )

    def fetch_index(self) -> ToolIndex:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        data = request_json(self.raw_url(INDEX_FILE_NAME))
        return ToolIndex.from_dict(data)

    def latest_release_url(self) -> str:
        return f"https://api.github.com/repos/{self.config.github_owner}/{self.config.github_repo}/releases/latest"

    def fetch_latest_manager_release(self) -> ManagerRelease | None:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        data = request_json(self.latest_release_url())
        if not isinstance(data, dict):
            return None
        asset = select_manager_asset(data.get("assets", []))
        if not asset:
            return None
        tag_name = str(data.get("tag_name", "")).strip()
        return ManagerRelease(
            tag_name=tag_name,
            version=tag_name.lstrip("vV"),
            name=str(data.get("name") or tag_name),
            body=str(data.get("body") or ""),
            asset_name=str(asset.get("name") or ""),
            asset_url=str(asset.get("browser_download_url") or ""),
        )

    def download_manager_release(
        self,
        release: ManagerRelease,
        target: Path,
        progress: ProgressCallback | None = None,
    ) -> Path:
        if not release.asset_url:
            raise RuntimeError("Release 找不到可下載的更新包。")
        target.mkdir(parents=True, exist_ok=True)
        zip_path = target / release.asset_name
        if zip_path.exists():
            zip_path.unlink()
        download_file(release.asset_url, zip_path, progress, "下載管理器更新包")
        return zip_path

    def download_tool(self, tool: ToolInfo, destination: Path, progress: ProgressCallback | None = None) -> None:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = destination.with_name(destination.name + ".download")
        zip_path = destination.with_name(destination.name + ".zipdownload")
        backup_dir: Path | None = None
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        if zip_path.exists():
            zip_path.unlink()
        temp_dir.mkdir(parents=True)

        try:
            if progress:
                progress("下載 GitHub 壓縮包", 5)
            download_file(self.archive_url(), zip_path, progress, "下載 GitHub 壓縮包", 5, 40)

            if progress:
                progress("解壓工具檔案", 45)
            extracted = extract_tool_from_archive(zip_path, tool.path, temp_dir, progress)
            if extracted == 0:
                raise RuntimeError(f"GitHub 壓縮包中找不到工具路徑：{tool.path}")

            if progress:
                progress("套用工具檔案", 96)
            ensure_safe_child(destination.parent, destination)
            if destination.exists():
                backup_dir = unique_backup_path(destination)
                destination.rename(backup_dir)
            temp_dir.rename(destination)
            if backup_dir:
                cleanup_path_async(backup_dir)
            if progress:
                progress("下載完成", 100)
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if backup_dir and backup_dir.exists() and not destination.exists():
                backup_dir.rename(destination)
            raise
        finally:
            if zip_path.exists():
                zip_path.unlink()

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
    url = encode_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "ToolkitManager/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub 讀取失敗：HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub 連線失敗：{exc.reason}") from exc


def download_file(
    url: str,
    target: Path,
    progress: ProgressCallback | None = None,
    label: str = "下載檔案",
    start_percent: int = 0,
    end_percent: int = 100,
) -> None:
    url = encode_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "ToolkitManager/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        last_percent = -1
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as output:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                done += len(chunk)
                if progress and total:
                    span = max(0, end_percent - start_percent)
                    percent = min(end_percent, start_percent + int(done / total * span))
                    if percent != last_percent:
                        progress(label, percent)
                        last_percent = percent
        if progress:
            progress(label, end_percent)


def select_manager_asset(assets: list[dict]) -> dict | None:
    zip_assets = [
        asset for asset in assets
        if str(asset.get("name", "")).lower().endswith(".zip")
        and asset.get("browser_download_url")
    ]
    for asset in zip_assets:
        if "toolkitmanager" in str(asset.get("name", "")).lower():
            return asset
    return zip_assets[0] if zip_assets else None


def extract_tool_from_archive(
    zip_path: Path,
    tool_path: str,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> int:
    normalized_tool_path = tool_path.replace("\\", "/").strip("/")
    extracted = 0
    with zipfile.ZipFile(zip_path) as archive:
        members = [
            info for info in archive.infolist()
            if not info.is_dir() and archive_inner_path(info.filename, normalized_tool_path)
        ]
        total = max(len(members), 1)
        last_percent = -1
        for index, info in enumerate(members, start=1):
            rel_path = archive_inner_path(info.filename, normalized_tool_path)
            if not rel_path:
                continue
            target = destination / Path(rel_path)
            ensure_safe_child(destination, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted += 1
            if progress:
                percent = 45 + int(index / total * 45)
                if percent != last_percent:
                    progress("解壓工具檔案", percent)
                    last_percent = percent
    return extracted


def unique_backup_path(destination: Path) -> Path:
    stamp = f"{int(time.time())}-{os.getpid()}"
    backup = destination.with_name(f"{destination.name}.backup-{stamp}")
    counter = 1
    while backup.exists():
        backup = destination.with_name(f"{destination.name}.backup-{stamp}-{counter}")
        counter += 1
    return backup


def cleanup_path_async(path: Path) -> None:
    def cleanup() -> None:
        shutil.rmtree(path, ignore_errors=True)

    thread = threading.Thread(target=cleanup, name="ToolkitManagerCleanup", daemon=True)
    thread.start()


def archive_inner_path(filename: str, tool_path: str) -> str:
    normalized = filename.replace("\\", "/").strip("/")
    parts = normalized.split("/", 1)
    if len(parts) != 2:
        return ""
    inner = parts[1]
    if inner == tool_path:
        return ""
    prefix = tool_path + "/"
    if not inner.startswith(prefix):
        return ""
    return inner[len(prefix):]


def encode_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


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
