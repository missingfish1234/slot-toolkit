"""Atomic JSON persistence with recoverable corruption handling."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any, Callable


def atomic_json(path: Path, data: Any, *, backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if backup and path.is_file():
            # Never replace a valid recovery copy with an already broken JSON file.
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
            except (ValueError, UnicodeError):
                pass
            else:
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def recover_json(path: Path, default: Any, valid: Callable[[Any], bool] | None = None) -> Any:
    if not path.exists() and not path.with_suffix(path.suffix + ".bak").is_file():
        return default
    valid = valid or (lambda value: isinstance(value, dict))
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if not valid(data):
                raise ValueError("Unexpected JSON structure")
        except (ValueError, UnicodeError):
            continue
        if candidate != path:
            quarantine_json(path)
            atomic_json(path, data, backup=False)
            warnings.warn(f"已從備份恢復：{path.name}", RuntimeWarning, stacklevel=2)
        return data
    quarantine_json(path)
    atomic_json(path, default, backup=False)
    warnings.warn(f"{path.name} 格式損壞，原檔已保留為 .corrupt，已載入預設資料。", RuntimeWarning, stacklevel=2)
    return default


def quarantine_json(path: Path) -> None:
    if path.exists():
        suffix = f".corrupt-{time.time_ns()}"
        path.rename(path.with_name(path.name + suffix))
