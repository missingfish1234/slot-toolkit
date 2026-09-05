"""Literal, scoped Git operations; never include unrelated staged changes."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git_run(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args], cwd=root,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", "GIT_LITERAL_PATHSPECS": "1"},
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or "Git 執行失敗。")
    return result


def git_output(root: Path, args: list[str]) -> str:
    return git_run(root, args).stdout


def parse_status(status: str) -> list[tuple[str, tuple[str, ...]]]:
    records = status.split("\0")
    result = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2] != " ":
            raise ValueError("Git 狀態不是 porcelain -z 格式。")
        code, path = record[:2], record[3:]
        paths = (path,)
        if "R" in code or "C" in code:
            if index >= len(records) or not records[index]:
                raise ValueError("Git 重新命名狀態不完整。")
            paths += (records[index],)
            index += 1
        result.append((code, paths))
    return result


def git_tool_update_paths(root: Path, status: str) -> list[str]:
    ignored = {"manager", "design", "dist", "build", "docs", "tests", "scripts"}
    allowed = {"tools-index.json"} | {p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".") and p.name not in ignored}
    paths = []
    for _, record_paths in parse_status(status):
        # A rename crossing out of the tool area needs an explicit CLI review.
        if all(path.split("/", 1)[0] in allowed for path in record_paths):
            paths.extend(record_paths)
    return list(dict.fromkeys(paths))


def git_status_lines_for_paths(status: str, paths: list[str]) -> list[str]:
    allowed = set(paths)
    return [f"{code} {' ← '.join(items)}" for code, items in parse_status(status) if all(p in allowed for p in items)]


def commit_tool_paths(root: Path, paths: list[str], message: str) -> None:
    if not paths or not message.strip():
        raise ValueError("提交路徑和訊息不可空白。")
    indexed = set(git_output(root, ["ls-files", "-z"]).split("\0"))
    stage_paths = [path for path in paths if (root / path).exists() or path in indexed]
    if stage_paths:
        git_run(root, ["add", "-A", "--", *stage_paths])
    git_run(root, ["commit", "--only", "-m", message, "--", *paths])
