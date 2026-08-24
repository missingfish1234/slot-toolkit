from __future__ import annotations

import csv
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
ATLAS_EXTS = (".atlas", ".atlas.txt", ".atlas.bytes", ".txt")
DEFAULT_SPINE_EXE = r"C:\Program Files\Spine\Spine.exe"


def create_export_settings() -> str:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="spine_export_")
    settings = {
        "class": "export-json",
        "extension": ".json",
        "format": "JSON",
        "nonessential": True,
        "prettyPrint": False,
    }
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
        json.dump(settings, fh)
    return path


def strip_spine_ext(filename: str) -> str:
    lowered = filename.lower()
    for suffix in (".skel.bytes", ".skel", ".json"):
        if lowered.endswith(suffix):
            return filename[: -len(suffix)]
    return os.path.splitext(filename)[0]


def get_skel_version(filepath: str) -> str | None:
    try:
        with open(filepath, "rb") as fh:
            data = fh.read(2048)
        match = re.search(rb"(3\.\d+\.\d+|4\.\d+\.\d+)", data)
        return match.group(1).decode("ascii") if match else None
    except Exception:
        return None


def run_process_hidden(cmd: list[str], timeout_sec: int, cancel_event: threading.Event | None = None) -> tuple[int, str]:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    log_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".log", prefix="spineqc_process_") as log_file:
            log_path = log_file.name
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

        started = time.time()
        while True:
            if cancel_event and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                return -2, "使用者中止掃描"

            if proc.poll() is not None:
                break

            if time.time() - started > timeout_sec:
                proc.kill()
                return -1, f"Spine 匯出逾時 {timeout_sec} 秒"

            time.sleep(0.1)

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                output = fh.read().strip()
        except OSError:
            output = ""
        return proc.returncode or 0, output
    finally:
        if log_path:
            try:
                os.remove(log_path)
            except OSError:
                pass


def skel_to_json_hidden(
    skel_path: str,
    settings_path: str,
    spine_exe_path: str,
    cancel_event: threading.Event | None = None,
) -> tuple[str | None, str | None, str, str]:
    temp_dir = tempfile.mkdtemp(prefix="spine_qc_")
    skel_version = get_skel_version(skel_path)
    messages: list[str] = []
    input_path = skel_path

    if skel_path.lower().endswith(".skel.bytes"):
        input_path = os.path.join(temp_dir, "input.skel")
        try:
            shutil.copy2(skel_path, input_path)
        except OSError as exc:
            return None, skel_version, temp_dir, f"無法建立暫存 skel：{exc}"

    def run_spine(use_version: bool, timeout_sec: int) -> str | None:
        for item in os.listdir(temp_dir):
            if item.lower().endswith(".json"):
                try:
                    os.remove(os.path.join(temp_dir, item))
                except OSError:
                    pass

        cmd = [spine_exe_path]
        if use_version and skel_version:
            cmd.extend(["--update", skel_version])
        cmd.extend(["--input", input_path, "--output", temp_dir, "--export", settings_path])

        code, output = run_process_hidden(cmd, timeout_sec, cancel_event)
        if output.strip():
            messages.append(output.strip())
        if code != 0:
            messages.append(f"Spine 回傳碼: {code}")

        for item in os.listdir(temp_dir):
            if item.lower().endswith(".json"):
                return os.path.join(temp_dir, item)
        return None

    json_out = run_spine(use_version=True, timeout_sec=120)
    if not json_out and not (cancel_event and cancel_event.is_set()):
        json_out = run_spine(use_version=False, timeout_sec=30)

    return json_out, skel_version, temp_dir, "\n".join(messages)


def read_text_best_effort(path: str) -> str:
    encodings = ("utf-8-sig", "utf-8", "cp950", "mbcs", "utf-16", "utf-16-le", "latin1")
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="strict") as fh:
                return fh.read()
        except Exception:
            continue
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def atlas_candidates_for(base_file_path: str) -> list[str]:
    folder = os.path.abspath(os.path.dirname(base_file_path))
    base_name = strip_spine_ext(os.path.basename(base_file_path))
    candidates: list[str] = []

    exact_names = [
        f"{base_name}.atlas",
        f"{base_name}.atlas.txt",
        f"{base_name}.atlas.bytes",
        f"{base_name}.txt",
    ]
    for name in exact_names:
        path = os.path.abspath(os.path.join(folder, name))
        if os.path.exists(path):
            candidates.append(path)

    try:
        for name in os.listdir(folder):
            lowered = name.lower()
            path = os.path.abspath(os.path.join(folder, name))
            if not os.path.isfile(path):
                continue
            if lowered.endswith(ATLAS_EXTS) and path not in candidates:
                if lowered.startswith(base_name.lower()) or not candidates:
                    candidates.append(path)
    except OSError:
        pass

    return candidates


def parse_atlas_pages(atlas_path: str) -> list[str]:
    pages: list[str] = []
    try:
        text = read_text_best_effort(atlas_path)
    except Exception:
        return pages

    for raw_line in text.splitlines():
        line = raw_line.strip().strip('"')
        if not line or ":" in line:
            continue
        if line.lower().endswith(IMAGE_EXTS):
            pages.append(line.replace("\\", os.sep).replace("/", os.sep))

    return list(dict.fromkeys(pages))


def get_texture_dependencies(base_file_path: str) -> list[str]:
    folder = os.path.abspath(os.path.dirname(base_file_path))
    base_name = strip_spine_ext(os.path.basename(base_file_path))
    image_paths: list[str] = []

    for atlas_path in atlas_candidates_for(base_file_path):
        atlas_folder = os.path.dirname(atlas_path)
        for page in parse_atlas_pages(atlas_path):
            img_path = os.path.abspath(os.path.join(atlas_folder, page))
            if os.path.exists(img_path) and img_path not in image_paths:
                image_paths.append(img_path)

    if image_paths:
        return image_paths

    try:
        all_images = [
            os.path.abspath(os.path.join(folder, name))
            for name in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, name)) and name.lower().endswith(IMAGE_EXTS)
        ]
    except OSError:
        return []

    prefix_images = [
        path for path in all_images if os.path.basename(path).lower().startswith(base_name.lower())
    ]
    if prefix_images:
        return prefix_images
    if len(all_images) <= 3:
        return all_images
    return []


def get_image_size(filepath: str) -> str:
    try:
        with open(filepath, "rb") as fh:
            head = fh.read(24)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
                w, h = struct.unpack(">II", head[16:24])
                return f"{w}x{h}"

            if head.startswith(b"\xff\xd8"):
                fh.seek(2)
                while True:
                    marker = fh.read(1)
                    if not marker:
                        break
                    if marker != b"\xff":
                        continue
                    code = fh.read(1)
                    if code in (b"\xc0", b"\xc1", b"\xc2"):
                        fh.read(3)
                        h, w = struct.unpack(">HH", fh.read(4))
                        return f"{w}x{h}"
                    length_bytes = fh.read(2)
                    if len(length_bytes) < 2:
                        break
                    length = struct.unpack(">H", length_bytes)[0]
                    fh.seek(max(0, length - 2), os.SEEK_CUR)
    except Exception:
        pass
    return "未知"


def iter_skin_attachments(skins) -> list[dict]:
    attachments: list[dict] = []
    if isinstance(skins, list):
        for skin in skins:
            skin_attachments = skin.get("attachments", {}) if isinstance(skin, dict) else {}
            for slot_attachments in skin_attachments.values():
                if isinstance(slot_attachments, dict):
                    attachments.extend(
                        value for value in slot_attachments.values() if isinstance(value, dict)
                    )
    elif isinstance(skins, dict):
        for skin_value in skins.values():
            if not isinstance(skin_value, dict):
                continue
            slot_map = skin_value.get("attachments", skin_value)
            for slot_attachments in slot_map.values():
                if isinstance(slot_attachments, dict):
                    attachments.extend(
                        value for value in slot_attachments.values() if isinstance(value, dict)
                    )
    return attachments


def count_deforms(animations) -> int:
    count = 0
    if not isinstance(animations, dict):
        return count

    for anim_data in animations.values():
        if not isinstance(anim_data, dict):
            continue
        for deform_key in ("deform", "ffd"):
            deform_data = anim_data.get(deform_key, {})
            if not isinstance(deform_data, dict):
                continue
            for skin_data in deform_data.values():
                if not isinstance(skin_data, dict):
                    continue
                for slot_data in skin_data.values():
                    if isinstance(slot_data, dict):
                        count += len(slot_data)
    return count


def analyze_spine_json(json_path: str, original_path: str) -> dict | None:
    try:
        with open(json_path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)

        skeleton = data.get("skeleton", {}) if isinstance(data, dict) else {}
        skins = data.get("skins", [])
        attachments = iter_skin_attachments(skins)

        vertex_count = 0
        clipping_count = 0
        clipping_vertex_count = 0
        weighted_mesh_count = 0
        mesh_count = 0

        for attachment in attachments:
            attachment_type = attachment.get("type", "region")
            if attachment_type == "mesh":
                mesh_count += 1
                if attachment.get("uvs"):
                    vertex_count += len(attachment.get("uvs", [])) // 2
                else:
                    vertex_count += int(attachment.get("vertexCount", 0) or 0)
                if attachment.get("vertices") and attachment.get("bones"):
                    weighted_mesh_count += 1
            elif attachment_type == "clipping":
                clipping_count += 1
                vertex_count_value = int(attachment.get("vertexCount", 0) or 0)
                if not vertex_count_value and isinstance(attachment.get("vertices"), list):
                    vertex_count_value = len(attachment["vertices"]) // 2
                clipping_vertex_count += vertex_count_value

        animations = data.get("animations", {})
        constraints_count = (
            len(data.get("ik", []) or [])
            + len(data.get("transform", []) or [])
            + len(data.get("path", []) or [])
            + len(data.get("physics", []) or [])
        )

        skel_w = float(skeleton.get("width", 0) or 0)
        skel_h = float(skeleton.get("height", 0) or 0)
        area_sqrt = int(math.sqrt(skel_w * skel_h)) if skel_w > 0 and skel_h > 0 else "未設定"

        estimated_draw_calls = 1
        current_blend = "normal"
        for slot in data.get("slots", []) or []:
            if not isinstance(slot, dict):
                continue
            slot_blend = slot.get("blend", "normal")
            if slot_blend != current_blend:
                estimated_draw_calls += 1
                current_blend = slot_blend

        return {
            "version": skeleton.get("spine", "未知"),
            "bones": len(data.get("bones", []) or []),
            "slots": len(data.get("slots", []) or []),
            "skins": len(skins) if isinstance(skins, list) else len(skins.keys()) if isinstance(skins, dict) else 0,
            "anims": len(animations) if isinstance(animations, dict) else 0,
            "meshes": mesh_count,
            "weighted": weighted_mesh_count,
            "verts": vertex_count,
            "deforms": count_deforms(animations),
            "clips": clipping_count,
            "clip_verts": clipping_vertex_count,
            "constraints": constraints_count,
            "drawcalls": estimated_draw_calls,
            "area_sqrt": area_sqrt,
            "deps": get_texture_dependencies(original_path),
        }
    except Exception as exc:
        print(f"analyze_spine_json failed: {json_path} -> {exc}")
        return None


def format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / 1024:.0f} KB"


def numeric_value(value) -> float | None:
    try:
        text = str(value).replace("!", "").strip()
        if text in ("", "-", "未知", "未設定"):
            return None
        if "MB" in text:
            return float(text.replace("MB", "").replace("(共用)", "").strip()) * 1024
        if "KB" in text:
            return float(text.replace("KB", "").replace("(共用)", "").strip())
        return float(text)
    except Exception:
        return None


class SpineScannerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SPINE 資訊檢測工具")
        self.root.geometry("1480x780")
        self.root.minsize(1180, 680)

        self.bg_color = "#F0F4F8"
        self.card_color = "#FFFFFF"
        self.text_color = "#2C3E50"
        self.root.configure(bg=self.bg_color)

        self.path_var = tk.StringVar()
        self.spine_path_var = tk.StringVar(value=DEFAULT_SPINE_EXE)
        self.status_var = tk.StringVar(value="準備就緒")
        self.total_size_var = tk.StringVar(value="去重後總包圖真實容量: 0.00 MB (共 0 張圖)")
        self.progress_var = tk.DoubleVar(value=0)
        self.cancel_event = threading.Event()
        self.scan_thread: threading.Thread | None = None
        self.last_results: list[dict] = []

        self.threshold_vars = {
            "bones": tk.StringVar(value=""),
            "anims": tk.StringVar(value=""),
            "verts": tk.StringVar(value=""),
            "deforms": tk.StringVar(value=""),
            "clips": tk.StringVar(value=""),
            "drawcalls": tk.StringVar(value=""),
        }

        self.setup_style()
        self.setup_ui()

    def setup_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        font = ("Microsoft JhengHei UI", 10)
        bold_font = ("Microsoft JhengHei UI", 10, "bold")

        style.configure("Primary.TButton", font=bold_font, background="#3498DB", foreground="white", padding=6)
        style.map("Primary.TButton", background=[("active", "#2980B9")])
        style.configure("Success.TButton", font=bold_font, background="#2ECC71", foreground="white", padding=6)
        style.map("Success.TButton", background=[("active", "#27AE60")])
        style.configure("Danger.TButton", font=bold_font, background="#E74C3C", foreground="white", padding=6)
        style.map("Danger.TButton", background=[("active", "#C0392B")])
        style.configure("Tool.TButton", font=("Microsoft JhengHei UI", 9), background="#E0E6ED", foreground="#2C3E50", padding=4)
        style.map("Tool.TButton", background=[("active", "#BDC3C7")])

        style.configure("Card.TLabelframe", background=self.card_color, borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", font=bold_font, background=self.card_color, foreground="#7F8C8D")
        style.configure("TFrame", background=self.bg_color)
        style.configure("CardFrame.TFrame", background=self.card_color)
        style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=font)
        style.configure("Treeview", font=("Microsoft JhengHei UI", 9), rowheight=28, borderwidth=0, background=self.card_color)
        style.configure("Treeview.Heading", font=bold_font, background="#EAEDED", foreground=self.text_color, padding=5)
        style.map("Treeview", background=[("selected", "#D6EAF8")], foreground=[("selected", "#2C3E50")])

    def setup_ui(self) -> None:
        main = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=15)
        main.pack(fill=tk.BOTH, expand=True)

        setting_frame = ttk.LabelFrame(main, text=" 系統設定 ", style="Card.TLabelframe", padding=(15, 10))
        setting_frame.pack(fill=tk.X, pady=(0, 12))
        setting = tk.Frame(setting_frame, bg=self.card_color)
        setting.pack(fill=tk.X)
        tk.Label(setting, text="Spine 執行檔:", bg=self.card_color, fg=self.text_color, font=("Microsoft JhengHei UI", 10)).pack(side=tk.LEFT)
        tk.Entry(setting, textvariable=self.spine_path_var, width=72, relief="solid", bd=1).pack(side=tk.LEFT, padx=10, ipady=3)
        ttk.Button(setting, text="瀏覽", style="Tool.TButton", command=self.browse_spine_exe).pack(side=tk.LEFT)

        action_frame = ttk.LabelFrame(main, text=" 掃描目標 ", style="Card.TLabelframe", padding=(15, 12))
        action_frame.pack(fill=tk.X, pady=(0, 12))
        action = tk.Frame(action_frame, bg=self.card_color)
        action.pack(fill=tk.X)
        tk.Label(action, text="專案資料夾:", bg=self.card_color, fg=self.text_color, font=("Microsoft JhengHei UI", 10)).pack(side=tk.LEFT)
        tk.Entry(action, textvariable=self.path_var, width=72, relief="solid", bd=1).pack(side=tk.LEFT, padx=10, ipady=3)
        ttk.Button(action, text="瀏覽", style="Tool.TButton", command=self.browse_folder).pack(side=tk.LEFT)
        self.scan_btn = ttk.Button(action, text="開始掃描", style="Primary.TButton", command=self.start_scan_thread)
        self.scan_btn.pack(side=tk.LEFT, padx=(16, 8))
        self.stop_btn = ttk.Button(action, text="停止", style="Danger.TButton", command=self.stop_scan, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action, text="匯出 CSV", style="Success.TButton", command=self.export_csv).pack(side=tk.LEFT)

        standard_frame = ttk.LabelFrame(main, text=" 標準值設定 ", style="Card.TLabelframe", padding=(15, 10))
        standard_frame.pack(fill=tk.X, pady=(0, 12))
        std = tk.Frame(standard_frame, bg=self.card_color)
        std.pack(fill=tk.X)
        threshold_fields = [
            ("骨架上限", "bones"),
            ("動畫上限", "anims"),
            ("面數上限", "verts"),
            ("點變形上限", "deforms"),
            ("遮罩上限", "clips"),
            ("DrawCall 上限", "drawcalls"),
        ]
        for label, key in threshold_fields:
            wrap = tk.Frame(std, bg=self.card_color)
            wrap.pack(side=tk.LEFT, padx=(0, 12))
            tk.Label(wrap, text=label, bg=self.card_color, fg=self.text_color, font=("Microsoft JhengHei UI", 10)).pack(side=tk.LEFT)
            tk.Entry(wrap, textvariable=self.threshold_vars[key], width=8, relief="solid", bd=1, justify="center").pack(side=tk.LEFT, padx=(4, 0), ipady=2)
        tk.Label(
            standard_frame,
            text="留空代表不比對；超過標準值的欄位會加上 !，整列會以淡紅底標示。",
            bg=self.card_color,
            fg="#7F8C8D",
            font=("Microsoft JhengHei UI", 9),
        ).pack(anchor="w", pady=(8, 0))

        summary = tk.Frame(main, bg="#D4EFDF", pady=8, padx=15)
        summary.pack(fill=tk.X, pady=(0, 10))
        tk.Label(summary, textvariable=self.total_size_var, font=("Microsoft JhengHei UI", 10, "bold"), bg="#D4EFDF", fg="#196F3D").pack(side=tk.LEFT)
        tk.Label(summary, textvariable=self.status_var, font=("Microsoft JhengHei UI", 9), bg="#D4EFDF", fg="#145A32").pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(main, variable=self.progress_var, maximum=100)
        self.progress.pack(fill=tk.X, pady=(0, 10))

        table_frame = tk.Frame(main, bg=self.card_color, bd=1, relief="solid")
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = (
            "file", "status", "version", "bones", "slots", "skins", "anims", "meshes", "verts",
            "weighted", "deforms", "clips", "drawcalls", "area_sqrt", "tex_count", "tex_dims", "tex_size"
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", style="Treeview")
        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=y_scroll.set, xscroll=x_scroll.set)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        x_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        headers = [
            ("file", "檔案名稱", 190),
            ("status", "狀態", 80),
            ("version", "版本", 70),
            ("bones", "骨架", 60),
            ("slots", "Slot", 60),
            ("skins", "Skin", 60),
            ("anims", "動畫", 60),
            ("meshes", "Mesh", 60),
            ("verts", "面數", 70),
            ("weighted", "權重 Mesh", 80),
            ("deforms", "點變形", 70),
            ("clips", "遮罩", 60),
            ("drawcalls", "預估 DrawCall", 100),
            ("area_sqrt", "面積平方根", 90),
            ("tex_count", "包圖數", 70),
            ("tex_dims", "圖集尺寸", 260),
            ("tex_size", "檔案容量", 120),
        ]
        for col, text, width in headers:
            self.tree.heading(col, text=text, command=lambda c=col: self.sort_treeview(c, True))
            self.tree.column(col, width=width, anchor=tk.W if col in ("file", "tex_dims") else tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.tree.tag_configure("oddrow", background="#F9FBFD")
        self.tree.tag_configure("evenrow", background="#FFFFFF")
        self.tree.tag_configure("failrow", background="#FDEDEC", foreground="#C0392B")
        self.tree.tag_configure("exceedrow", background="#FFF5F5", foreground="#C62828")

    def browse_spine_exe(self) -> None:
        selected = filedialog.askopenfilename(
            title="選擇 Spine 執行檔",
            filetypes=[("執行檔", "*.exe"), ("所有檔案", "*.*")],
        )
        if selected:
            self.spine_path_var.set(selected)

    def browse_folder(self) -> None:
        selected = filedialog.askdirectory(title="選擇要掃描的專案資料夾")
        if selected:
            self.path_var.set(selected)

    def sort_treeview(self, col: str, reverse: bool) -> None:
        rows = [(self.tree.set(child, col), child) for child in self.tree.get_children("")]

        def sort_key(item):
            value = numeric_value(item[0])
            if value is not None:
                return (0, value)
            return (1, str(item[0]).lower())

        rows.sort(key=sort_key, reverse=reverse)
        for index, (_, child) in enumerate(rows):
            self.tree.move(child, "", index)
            tags = self.tree.item(child, "tags")
            if "failrow" not in tags and "exceedrow" not in tags:
                self.tree.item(child, tags=("evenrow" if index % 2 == 0 else "oddrow",))
        self.tree.heading(col, command=lambda: self.sort_treeview(col, not reverse))

    def threshold_value(self, key: str) -> int | None:
        value = numeric_value(self.threshold_vars[key].get())
        return int(value) if value is not None else None

    def apply_thresholds(self, stats: dict) -> tuple[dict, bool]:
        display = dict(stats)
        exceeded = False
        for key in ("bones", "anims", "verts", "deforms", "clips", "drawcalls"):
            limit = self.threshold_value(key)
            current = numeric_value(stats.get(key))
            if limit is not None and current is not None and current > limit:
                display[key] = f"! {stats[key]}"
                exceeded = True
        return display, exceeded

    def start_scan_thread(self) -> None:
        folder = self.path_var.get().strip()
        spine_exe = self.spine_path_var.get().strip()
        if not folder or not os.path.exists(folder):
            messagebox.showwarning("提醒", "請先選擇有效的專案資料夾。")
            return
        if not os.path.exists(spine_exe) or not spine_exe.lower().endswith(".exe"):
            messagebox.showerror("錯誤", f"找不到 Spine 執行檔，請重新選擇：\n{spine_exe}")
            return

        self.cancel_event.clear()
        self.last_results = []
        self.scan_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set("掃描中...")
        self.total_size_var.set("計算中...")
        self.progress_var.set(0)
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.scan_thread = threading.Thread(target=self.run_scan, args=(folder, spine_exe), daemon=True)
        self.scan_thread.start()

    def stop_scan(self) -> None:
        self.cancel_event.set()
        self.status_var.set("正在停止掃描...")
        self.stop_btn.configure(state=tk.DISABLED)

    def find_spine_files(self, folder: str) -> list[str]:
        targets: list[str] = []
        for root_dir, _, files in os.walk(folder):
            for filename in files:
                lowered = filename.lower()
                if lowered.endswith((".skel", ".skel.bytes")):
                    targets.append(os.path.join(root_dir, filename))
                elif lowered.endswith(".json") and not lowered.startswith("spine_export_"):
                    targets.append(os.path.join(root_dir, filename))
        return sorted(targets)

    def run_scan(self, folder: str, spine_exe: str) -> None:
        settings_path = create_export_settings()
        scan_results: list[dict] = []
        global_images: dict[str, int] = {}
        targets = self.find_spine_files(folder)
        total = len(targets)

        if total == 0:
            if os.path.exists(settings_path):
                try:
                    os.remove(settings_path)
                except OSError:
                    pass
            self.root.after(0, lambda: self.finish_scan([], {}, 0, 0, "找不到 .skel/.skel.bytes/.json 檔案"))
            return

        try:
            for index, full_path in enumerate(targets, start=1):
                if self.cancel_event.is_set():
                    break

                filename = os.path.basename(full_path)
                self.root.after(0, self.status_var.set, f"掃描 {index}/{total}: {filename}")
                self.root.after(0, self.progress_var.set, (index - 1) / total * 100)
                lowered = filename.lower()

                if lowered.endswith((".skel", ".skel.bytes")):
                    temp_json, real_version, temp_dir, message = skel_to_json_hidden(
                        full_path, settings_path, spine_exe, self.cancel_event
                    )
                    try:
                        stats = analyze_spine_json(temp_json, full_path) if temp_json else None
                        if stats and real_version:
                            stats["version"] = real_version
                    finally:
                        if temp_dir and os.path.exists(temp_dir):
                            shutil.rmtree(temp_dir, ignore_errors=True)

                    if stats:
                        self.process_stats(stats, filename, full_path, scan_results, global_images)
                    else:
                        self.process_failed(filename, real_version or "無法辨識", message, scan_results)
                else:
                    stats = analyze_spine_json(full_path, full_path)
                    if stats:
                        self.process_stats(stats, filename, full_path, scan_results, global_images)
                    else:
                        self.process_failed(filename, "未知", "JSON 解析失敗", scan_results)

                self.root.after(0, self.progress_var.set, index / total * 100)
        finally:
            if os.path.exists(settings_path):
                try:
                    os.remove(settings_path)
                except OSError:
                    pass

        image_usage: dict[str, int] = {}
        for result in scan_results:
            for img in result.get("deps", []):
                image_usage[img] = image_usage.get(img, 0) + 1

        total_unique_bytes = sum(global_images.values())
        message = "已停止" if self.cancel_event.is_set() else "完成"
        self.root.after(
            0,
            lambda: self.finish_scan(scan_results, image_usage, total_unique_bytes, len(global_images), message),
        )

    def process_stats(self, stats: dict, filename: str, full_path: str, scan_results: list[dict], global_images: dict[str, int]) -> None:
        unique_deps = list(dict.fromkeys(stats.get("deps", [])))
        local_bytes = 0
        dims: list[str] = []
        for image_path in unique_deps:
            if image_path not in global_images:
                global_images[image_path] = os.path.getsize(image_path) if os.path.exists(image_path) else 0
            local_bytes += global_images[image_path]
            dims.append(get_image_size(image_path))

        if unique_deps:
            tex_size = format_bytes(local_bytes)
            tex_dims = f"{', '.join(dims)} ({len(unique_deps)} 張)"
        else:
            tex_size = "-"
            tex_dims = "未找到圖集"

        display_stats, exceeded = self.apply_thresholds(stats)
        scan_results.append(
            {
                "is_success": True,
                "file": filename,
                "path": full_path,
                "stats": display_stats,
                "raw_stats": stats,
                "tex_count": len(unique_deps),
                "tex_dims": tex_dims,
                "tex_size": tex_size,
                "deps": unique_deps,
                "exceeded": exceeded,
                "message": "",
            }
        )

    def process_failed(self, filename: str, version: str, message: str, scan_results: list[dict]) -> None:
        scan_results.append(
            {
                "is_success": False,
                "file": filename,
                "path": "",
                "stats": {
                    "version": version,
                    "bones": "-",
                    "slots": "-",
                    "skins": "-",
                    "anims": "-",
                    "meshes": "-",
                    "verts": "-",
                    "weighted": "-",
                    "deforms": "-",
                    "clips": "-",
                    "drawcalls": "-",
                    "area_sqrt": "-",
                },
                "raw_stats": {},
                "tex_count": "-",
                "tex_dims": message or "Spine 轉檔或 JSON 解析失敗",
                "tex_size": "-",
                "deps": [],
                "exceeded": False,
                "message": message,
            }
        )

    def finish_scan(self, scan_results: list[dict], image_usage: dict[str, int], total_bytes: int, total_img_count: int, message: str) -> None:
        self.last_results = scan_results
        self.tree.delete(*self.tree.get_children())
        exceeded_count = 0
        failed_count = 0

        for index, result in enumerate(scan_results):
            stats = result["stats"]
            if result["is_success"]:
                tex_size = result["tex_size"]
                tex_dims = result["tex_dims"]
                shared = any(image_usage.get(img, 0) > 1 for img in result.get("deps", []))
                if shared and tex_size != "-":
                    tex_size = f"{tex_size} (共用)"
                    tex_dims = f"{tex_dims} (共用)"

                exceeded_count += 1 if result.get("exceeded") else 0
                row_tag = "exceedrow" if result.get("exceeded") else ("evenrow" if index % 2 == 0 else "oddrow")
                values = (
                    result["file"],
                    "成功(超標)" if result.get("exceeded") else "成功",
                    stats["version"],
                    stats["bones"],
                    stats["slots"],
                    stats["skins"],
                    stats["anims"],
                    stats["meshes"],
                    stats["verts"],
                    stats["weighted"],
                    stats["deforms"],
                    stats["clips"],
                    stats["drawcalls"],
                    stats["area_sqrt"],
                    result["tex_count"],
                    tex_dims,
                    tex_size,
                )
            else:
                failed_count += 1
                row_tag = "failrow"
                values = (
                    result["file"],
                    "失敗",
                    stats["version"],
                    stats["bones"],
                    stats["slots"],
                    stats["skins"],
                    stats["anims"],
                    stats["meshes"],
                    stats["verts"],
                    stats["weighted"],
                    stats["deforms"],
                    stats["clips"],
                    stats["drawcalls"],
                    stats["area_sqrt"],
                    result["tex_count"],
                    result["tex_dims"],
                    result["tex_size"],
                )

            self.tree.insert("", tk.END, values=values, tags=(row_tag,))

        self.progress_var.set(100 if scan_results else 0)
        self.total_size_var.set(
            f"去重後總包圖真實容量: {total_bytes / (1024 * 1024):.2f} MB (共 {total_img_count} 張圖)"
        )
        self.status_var.set(f"{message}：共 {len(scan_results)} 個檔案，失敗 {failed_count}，超標 {exceeded_count}")
        self.scan_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def export_csv(self) -> None:
        if not self.tree.get_children():
            messagebox.showinfo("提示", "目前沒有資料可以匯出，請先掃描。")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 逗號分隔檔", "*.csv"), ("所有檔案", "*.*")],
            title="匯出報告",
            initialfile="Spine資訊檢測報告.csv",
        )
        if not save_path:
            return

        try:
            with open(save_path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                headers = [self.tree.heading(col)["text"] for col in self.tree["columns"]]
                writer.writerow(headers)
                for item in self.tree.get_children():
                    writer.writerow(list(self.tree.item(item)["values"]))
            messagebox.showinfo("成功", f"報告已匯出：\n{save_path}")
        except Exception as exc:
            messagebox.showerror("錯誤", f"匯出失敗：\n{exc}")


if __name__ == "__main__":
    root = tk.Tk()
    app = SpineScannerApp(root)
    root.mainloop()
