from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import AppConfig, INDEX_FILE_NAME, InstalledTool, ManagerRelease, ToolIndex, ToolInfo
from .storage import atomic_json, recover_json


ProgressCallback = Callable[[str, int], None]


class ConfigStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = base_dir / "config.json"

    def load(self) -> AppConfig:
        if not self.config_path.exists() and not self.config_path.with_suffix(".json.bak").is_file():
            example = self.base_dir / "config.example.json"
            if not example.exists() and getattr(sys, "_MEIPASS", None):
                example = Path(sys._MEIPASS) / "config.example.json"  # type: ignore[attr-defined]
            if example.exists():
                shutil.copyfile(example, self.config_path)
            else:
                self.save(AppConfig())
        data = recover_json(self.config_path, AppConfig().to_dict())
        return AppConfig.from_dict(data)

    def save(self, config: AppConfig) -> None:
        atomic_json(self.config_path, config.to_dict())


class StateStore:
    def __init__(self, app_dir: Path) -> None:
        self.app_dir = app_dir
        self.state_path = app_dir / "state.json"
        self.app_dir.mkdir(parents=True, exist_ok=True)

    def load_installed(self) -> dict[str, InstalledTool]:
        if not self.state_path.exists() and not self.state_path.with_suffix(".json.bak").is_file():
            return {}
        data = recover_json(self.state_path, {"installed": []}, lambda value: isinstance(value, dict) and isinstance(value.get("installed"), list) and all(isinstance(item, dict) and isinstance(item.get("id", ""), str) for item in value["installed"]))
        return {
            item["id"]: InstalledTool.from_dict(item)
            for item in data.get("installed", [])
            if item.get("id")
        }

    def save_installed(self, installed: dict[str, InstalledTool]) -> None:
        atomic_json(self.state_path, {"installed": [item.to_dict() for item in installed.values()]})


class GitHubClient:
    def __init__(self, config: AppConfig, *, cache_dir: Path | None = None) -> None:
        self.config = config
        self._auth_token: str | None = None
        self.cache_dir = cache_dir or app_data_dir() / "cache"
        self.source_revision = ""
        self.index_fingerprint = ""

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
        if re.fullmatch(r"[a-fA-F0-9]{40}", self.source_revision):
            return f"https://codeload.github.com/{self.config.github_owner}/{self.config.github_repo}/zip/{self.source_revision}"
        encoded_branch = urllib.parse.quote(self.config.github_branch, safe="/")
        return (
            f"https://codeload.github.com/"
            f"{self.config.github_owner}/{self.config.github_repo}/zip/refs/heads/"
            f"{encoded_branch}"
        )

    @property
    def auth_token(self) -> str:
        if self._auth_token is None:
            self._auth_token = resolve_github_token(self.config)
        return self._auth_token

    def fetch_index(self) -> ToolIndex:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        data = request_json(self.raw_url(INDEX_FILE_NAME), self.auth_token)
        if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
            raise RuntimeError("GitHub 工具索引格式錯誤。")
        index = ToolIndex.from_dict(data)
        self.source_revision = index.source_revision
        self.index_fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        return index

    def latest_release_url(self) -> str:
        return f"https://api.github.com/repos/{self.config.github_owner}/{self.config.github_repo}/releases/latest"

    def fetch_latest_manager_release(self) -> ManagerRelease | None:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        data = request_json(self.latest_release_url(), self.auth_token)
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
            sha256=str(asset.get("digest") or "").removeprefix("sha256:"),
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
        zip_path = target / Path(release.asset_name).name
        download_file(release.asset_url, zip_path, progress, "下載管理器更新包", token=self.auth_token)
        if release.sha256 and file_digest(zip_path) != release.sha256.lower():
            raise RuntimeError("管理器更新包校驗不符，未套用更新。")
        return zip_path

    def download_tool(self, tool: ToolInfo, destination: Path, progress: ProgressCallback | None = None) -> None:
        if not self.is_configured:
            raise RuntimeError("尚未設定 GitHub owner/repo。")
        destination = destination.resolve()
        ensure_safe_child(self.config.install_path, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{destination.name}.download-", dir=destination.parent))
        backup_dir: Path | None = None
        try:
            zip_path = self.cached_package(tool, progress)
            if progress:
                progress("解壓工具檔案", 45)
            extracted = extract_tool_from_archive(zip_path, "" if tool.download_url else tool.path, temp_dir, progress)
            if extracted == 0:
                raise RuntimeError(f"GitHub 壓縮包中找不到工具路徑：{tool.path}")
            validate_tool_payload(tool, temp_dir)
            managed = {path.relative_to(temp_dir).as_posix(): file_digest(path) for path in temp_dir.rglob("*") if path.is_file()}
            if destination.exists():
                preserve_user_files(destination, temp_dir, tool)
            atomic_json(temp_dir / ".toolkit-managed.json", {"id": tool.id, "version": tool.version, "files": managed}, backup=False)
            if progress:
                progress("套用工具檔案", 96)
            ensure_safe_child(destination.parent, destination)
            if destination.exists():
                backup_dir = unique_backup_path(destination)
                destination.rename(backup_dir)
            temp_dir.rename(destination)
            if progress:
                progress("下載完成；舊版備份已保留" if backup_dir else "下載完成", 100)
        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if backup_dir and backup_dir.exists() and not destination.exists():
                backup_dir.rename(destination)
            raise

    def cached_package(self, tool: ToolInfo, progress: ProgressCallback | None = None) -> Path:
        if tool.download_url:
            if not re.fullmatch(r"[a-fA-F0-9]{64}", tool.sha256):
                raise RuntimeError("工具更新包缺少有效 SHA-256，請重新整理索引。")
            url = tool.download_url
            if urllib.parse.urlsplit(url).scheme != "https":
                raise RuntimeError("工具更新包必須使用 HTTPS。")
            key = tool.sha256.lower()
        else:
            url = self.archive_url()
            fingerprint = self.index_fingerprint or json.dumps([tool.id, tool.version, tool.updated_at])
            key = hashlib.sha256((url + fingerprint).encode()).hexdigest()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached = self.cache_dir / f"{key}.zip"
        if cached.is_file():
            valid = file_digest(cached) == tool.sha256.lower() if tool.download_url else zipfile.is_zipfile(cached)
            if valid:
                if progress:
                    progress("使用已驗證的下載快取", 40)
                return cached
        download_file(url, cached, progress, "下載工具更新包" if tool.download_url else "下載共用工具包快取", 5, 40, self.auth_token)
        if tool.download_url and file_digest(cached) != tool.sha256.lower():
            cached.unlink(missing_ok=True)
            raise RuntimeError("工具更新包 SHA-256 不符，現有工具未被替換。")
        if not zipfile.is_zipfile(cached):
            cached.unlink(missing_ok=True)
            raise RuntimeError("下載內容不是有效 ZIP，現有工具未被替換。")
        return cached

    def _list_files(self, path: str) -> list[dict]:
        items = request_json(self.api_contents_url(path), self.auth_token)
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
        path = self.config.install_path / tool.id
        if not tool.id or Path(tool.id).name != tool.id or any(c in tool.id for c in ("/", "\\", ":")):
            raise RuntimeError("工具識別碼不能包含路徑。")
        ensure_safe_child(self.config.install_path, path)
        return path

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
        if tool.entry:
            ensure_safe_child(base, entry)
        if not entry.exists():
            raise RuntimeError(f"找不到啟動檔：{entry}")
        if entry.suffix.lower() in {".bat", ".cmd"}:
            subprocess.Popen(["cmd", "/c", str(entry)], cwd=str(base))
        elif entry.suffix.lower() == ".py":
            executable = shutil.which("py") or shutil.which("python")
            if not executable:
                raise RuntimeError("此工具需要 Python，請先安裝 Python 或使用工具附的啟動器。")
            args = [executable, "-3", str(entry)] if Path(executable).stem.lower() == "py" else [executable, str(entry)]
            subprocess.Popen(args, cwd=str(base))
        else:
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


def resolve_github_token(config: AppConfig) -> str:
    configured = config.github_token.strip()
    if configured:
        return configured
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return gh_auth_token()


def gh_auth_token() -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def github_headers(token: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": "ToolkitManager/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_json(url: str, token: str = "") -> dict | list:
    url = encode_url(url)
    request = urllib.request.Request(url, headers=github_headers(token))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(github_http_error_message(exc, "GitHub 讀取失敗")) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub 連線失敗：{exc.reason}") from exc


def download_file(
    url: str,
    target: Path,
    progress: ProgressCallback | None = None,
    label: str = "下載檔案",
    start_percent: int = 0,
    end_percent: int = 100,
    token: str = "",
) -> None:
    url = encode_url(url)
    request = urllib.request.Request(url, headers=github_headers(token))
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".part", dir=target.parent)
    temporary = Path(name)
    os.close(fd)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            last_percent = -1
            with temporary.open("wb") as output:
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
            if total and done != total:
                raise RuntimeError(f"下載未完成：預期 {total} bytes，收到 {done} bytes。")
            os.replace(temporary, target)
            if progress:
                progress(label, end_percent)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(github_http_error_message(exc, "GitHub 下載失敗")) from exc
    finally:
        temporary.unlink(missing_ok=True)


def github_http_error_message(exc: urllib.error.HTTPError, prefix: str) -> str:
    detail = ""
    try:
        data = json.loads(exc.read().decode("utf-8"))
        detail = str(data.get("message") or "").strip()
    except Exception:
        detail = str(exc.reason or "").strip()
    message = f"{prefix}：HTTP {exc.code}"
    if detail:
        message += f" - {detail}"
    remaining = exc.headers.get("X-RateLimit-Remaining")
    reset = exc.headers.get("X-RateLimit-Reset")
    if exc.code == 403 and remaining == "0":
        message += "\nGitHub API 額度已用完，請在設定填入 GitHub Token，或稍後再試。"
        if reset:
            message += f"\nRate limit reset：{reset}"
    return message


def select_manager_asset(assets: list[dict]) -> dict | None:
    zip_assets = [
        asset for asset in assets
        if str(asset.get("name", "")).lower().endswith(".zip")
        and asset.get("browser_download_url")
    ]
    for asset in zip_assets:
        if "toolkitmanager" in str(asset.get("name", "")).lower():
            return asset
    return None


def extract_tool_from_archive(
    zip_path: Path,
    tool_path: str,
    destination: Path,
    progress: ProgressCallback | None = None,
) -> int:
    normalized_tool_path = tool_path.replace("\\", "/").strip("/")
    extracted = 0
    with zipfile.ZipFile(zip_path) as archive:
        def relative_name(filename: str) -> str:
            return archive_inner_path(filename, normalized_tool_path) if normalized_tool_path else filename.replace("\\", "/")

        members = [
            info for info in archive.infolist()
            if not info.is_dir() and relative_name(info.filename)
        ]
        total = max(len(members), 1)
        last_percent = -1
        for index, info in enumerate(members, start=1):
            rel_path = relative_name(info.filename)
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
    if root == child or root not in child.parents:
        raise RuntimeError(f"不安全的路徑：{child}")


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_tool_payload(tool: ToolInfo, payload: Path) -> None:
    metadata = payload / "tool.json"
    try:
        data = json.loads(metadata.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("工具更新包的 tool.json 遺失或損壞，未替換現有工具。") from exc
    if not isinstance(data, dict) or data.get("id") != tool.id or str(data.get("version")) != tool.version:
        raise RuntimeError("更新包的工具識別碼／版本與索引不同，請重新整理後再試。")
    if tool.entry:
        entry = payload / tool.entry
        ensure_safe_child(payload, entry)
        if not entry.is_file():
            raise RuntimeError(f"更新包缺少入口 {tool.entry}，現有工具未被替換。")
    if (payload / ".toolkit-managed.json").exists():
        raise RuntimeError("更新包含保留的安裝狀態檔。")


def preserve_user_files(previous: Path, payload: Path, tool: ToolInfo) -> None:
    """Carry user additions/settings forward; keep a full old install for recovery.

    Unmodified obsolete distribution files may be omitted using the previous receipt.
    A legacy install has no receipt, so conservatively preserve every extra file.
    Colliding program edits remain recoverable in the retained full backup.
    """
    try:
        receipt = json.loads((previous / ".toolkit-managed.json").read_text(encoding="utf-8"))
        managed = receipt.get("files", {}) if receipt.get("id") == tool.id else {}
    except (OSError, ValueError, AttributeError):
        managed = {}
    if not isinstance(managed, dict):
        managed = {}
    preserve = []
    for pattern in tool.preserve_paths:
        relative = pattern.replace("\\", "/").strip("/")
        ensure_safe_child(previous, previous / relative)
        preserve.append(relative.casefold())
    for directory, dirs, files in os.walk(previous, followlinks=False):
        for name in dirs + files:
            child = Path(directory) / name
            if child.is_symlink() or getattr(child, "is_junction", lambda: False)():
                raise RuntimeError(f"舊工具內含連結目錄／檔案，請先將使用者資料移至獨立位置：{child}")
        for name in files:
            source = Path(directory) / name
            relative = source.relative_to(previous).as_posix()
            if relative == ".toolkit-managed.json":
                continue
            destination = payload / relative
            ensure_safe_child(payload, destination)
            key = relative.casefold()
            keep_setting = any(key == item or key.startswith(item + "/") for item in preserve)
            unmodified_distribution = relative in managed and file_digest(source) == managed[relative]
            if keep_setting or (not destination.exists() and not unmodified_distribution):
                if destination.is_dir():
                    raise RuntimeError(f"新版資料夾與舊設定檔衝突：{relative}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])
