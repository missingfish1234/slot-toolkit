"""Isolated Spine CLI execution and recoverable publication; no GUI dependencies."""
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


class ConversionCancelled(Exception):
    pass


def validate_roots(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_dir():
        raise ValueError("輸入資料夾不存在。")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("輸入與輸出必須是分開的資料夾，不能相同或互相包含。")
    return source, output


def run_spine(cmd, cancel_event, timeout=300):
    if cancel_event.is_set():
        raise ConversionCancelled("已取消")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
        started = time.monotonic()
        try:
            while proc.poll() is None:
                if cancel_event.wait(0.15):
                    raise ConversionCancelled("已取消；本次尚未完成的成果不會取代舊檔。")
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Spine 執行超過 {timeout} 秒，已停止本次轉檔。")
        finally:
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=flags, timeout=15, check=False)
                else:
                    proc.kill()
                proc.wait(timeout=15)
        log.seek(0)
        output = log.read().decode("utf-8", errors="replace")
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, cmd, output=output)
        return output


def normalize_atlas_names(folder, project_name, is_up):
    """Only use this run's isolated output; never delete an existing destination."""
    folder = Path(folder)
    suffix = ".atlas.txt" if is_up else ".atlas"
    candidates = sorted(folder.glob("*" + suffix))
    expected = folder / (project_name + suffix)
    if expected.exists():
        return
    if len(candidates) != 1:
        raise ValueError("無法唯一辨識本次 Atlas；保留原成果，請檢查 Spine 匯出設定。")
    candidates[0].rename(expected)


def validate_output(folder):
    folder = Path(folder).resolve()
    skeletons = [p for p in folder.iterdir() if p.name.endswith((".skel", ".skel.bytes"))]
    atlases = [p for p in folder.iterdir() if p.name.endswith((".atlas", ".atlas.txt"))]
    if not skeletons or not atlases or any(p.stat().st_size == 0 for p in skeletons + atlases):
        raise ValueError("本次缺少有效的 skeleton／atlas，未替換舊成果。")
    for atlas in atlases:
        pages = []
        expect_page = True
        for line in atlas.read_text(encoding="utf-8-sig").splitlines():
            name = line.strip()
            if not name:
                expect_page = True
                continue
            # Atlas pages are separated by blank lines. A region may itself be
            # named "icon.png" and must not be mistaken for a texture page.
            if expect_page:
                pages.append((folder / name).resolve())
                expect_page = False
        if not pages or any(folder not in p.parents or not p.is_file() or p.stat().st_size == 0 for p in pages):
            raise ValueError(f"{atlas.name} 缺少引用的貼圖；未替換舊成果。")


def _require_ordinary_tree(root):
    root = Path(root)
    is_junction = getattr(os.path, "isjunction", lambda _: False)
    for current, dirs, files in os.walk(root, followlinks=False):
        for entry in [Path(current)] + [Path(current) / name for name in dirs + files]:
            if entry.is_symlink() or is_junction(entry):
                raise ValueError("成果資料夾包含符號連結／接合點；請移到一般資料夾後重試，未替換舊成果。")


def publish_output(staged, destination, backup_root):
    """Merge only produced paths; keep user additions and a complete rollback copy."""
    staged, destination = Path(staged), Path(destination)
    _require_ordinary_tree(staged)
    if destination.exists(): _require_ordinary_tree(destination)
    staged, destination = staged.resolve(), destination.resolve()
    if staged == destination or staged in destination.parents or destination in staged.parents:
        raise ValueError("暫存與目的目錄不可互相包含。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    merged = Path(tempfile.mkdtemp(prefix=".spine-publish-", dir=destination.parent))
    backup = None
    try:
        if destination.exists():
            if destination.is_symlink() or not destination.is_dir():
                raise ValueError("目的路徑不是一般資料夾。")
            shutil.copytree(destination, merged, dirs_exist_ok=True)
        shutil.copytree(staged, merged, dirs_exist_ok=True)
        if destination.exists():
            backup_root = Path(backup_root)
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / (destination.name + "-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
            destination.rename(backup)
        try:
            merged.rename(destination)
        except Exception:
            if backup and not destination.exists():
                backup.rename(destination)
            raise
        return backup
    finally:
        if merged.exists():
            shutil.rmtree(merged)
