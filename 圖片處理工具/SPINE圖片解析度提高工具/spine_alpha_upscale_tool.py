from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import threading
import hashlib
import json
import os
import tempfile
import uuid
import queue
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat


DEFAULT_MODEL = "realesr-animevideov3"
SUPPORTED_MODELS = (
    "realesr-animevideov3",
    "realesrgan-x4plus-anime",
    "realesrgan-x4plus",
)
MODEL_LABELS = {
    "realesr-animevideov3": "動畫素材推薦：realesr-animevideov3",
    "realesrgan-x4plus-anime": "插畫線條推薦：realesrgan-x4plus-anime",
    "realesrgan-x4plus": "通用圖片：realesrgan-x4plus",
}

WORK_OWNER = 'spine-alpha-upscale-v1'

def validate_paths(input_dir: Path, output_dir: Path, work_base: Path) -> None:
    input_dir, output_dir, work_base = (p.resolve() for p in (input_dir, output_dir, work_base))
    if not input_dir.is_dir():
        raise ValueError('來源必須是資料夾。')
    if output_dir == input_dir or output_dir in input_dir.parents:
        raise ValueError('輸出不可等於來源或包含來源資料夾。')
    if work_base == input_dir or work_base in input_dir.parents or work_base == output_dir or work_base in output_dir.parents or output_dir in work_base.parents:
        raise ValueError('工作資料夾不可與來源相同／包含來源，亦不可與輸出重疊。')

def input_signature(files, scale, model):
    return {'owner': WORK_OWNER, 'scale': scale, 'model': model,
            'inputs': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}

def create_work_directory(base: Path, signature: dict, resume=False) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    pointer = base / '.last-upscale-task.json'
    if resume:
        if not pointer.is_file():
            raise ValueError('找不到可恢復的工作；請先正常放大並勾選保留中介檔。')
        task = (base / json.loads(pointer.read_text(encoding='utf-8'))['directory']).resolve()
        if task.parent != base.resolve() or not task.name.startswith('.spine-upscale-'):
            raise ValueError('工作路徑不屬於此工具。')
        marker = task / '.task.json'
        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')) != signature:
            raise ValueError('中介檔與目前來源／模型／倍率不同，請重新放大。')
        return task
    task = Path(tempfile.mkdtemp(prefix='.spine-upscale-', dir=base)).resolve()
    (task / '.task.json').write_text(json.dumps(signature), encoding='utf-8')
    pointer.write_text(json.dumps({'directory': task.name}), encoding='utf-8')
    return task

def cleanup_work_directory(task: Path, base: Path, signature: dict) -> None:
    task, base = task.resolve(), base.resolve()
    marker = task / '.task.json'
    if task.parent != base or not task.name.startswith('.spine-upscale-') or not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')) != signature:
        raise ValueError('拒絕清除非本次工具工作目錄。')
    shutil.rmtree(task)

def output_path_for(path: Path, collision='rename') -> Path | None:
    if not path.exists() or collision == 'overwrite': return path
    if collision == 'skip': return None
    index = 2
    while path.with_name(f'{path.stem}_{index}{path.suffix}').exists(): index += 1
    return path.with_name(f'{path.stem}_{index}{path.suffix}')

def publish_png(image, path: Path, collision='rename') -> Path | None:
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        image.save(temporary, 'PNG', optimize=True)
        if collision == 'overwrite':
            os.replace(temporary, path)
            return path
        candidate = path
        while True:
            try:
                # Linking a complete same-directory file is atomic and refuses
                # existing destinations, including a concurrent export's file.
                os.link(temporary, candidate)
                return candidate
            except FileExistsError:
                if collision == 'skip': return None
                candidate = output_path_for(path, 'rename')
            except OSError:
                # FAT/network destinations may not support hard links. Still
                # reserve a new name exclusively, never replace someone else's.
                try:
                    destination = candidate.open('xb')
                except FileExistsError:
                    if collision == 'skip': return None
                    candidate = output_path_for(path, 'rename')
                    continue
                try:
                    with destination, temporary.open('rb') as source:
                        shutil.copyfileobj(source, destination)
                    return candidate
                except Exception:
                    candidate.unlink(missing_ok=True)
                    raise
    finally:
        if temporary.exists(): temporary.unlink()

def terminate_process_tree(proc) -> None:
    if proc is None or proc.poll() is not None: return
    if sys.platform.startswith('win'):
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    else:
        import signal
        os.killpg(proc.pid, signal.SIGTERM)


def clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def visible_average(rgb: Image.Image, alpha: Image.Image) -> tuple[int, int, int]:
    mask = alpha.point(lambda p: 255 if p > 16 else 0)
    stat = ImageStat.Stat(rgb, mask)
    if not stat.count or stat.count[0] == 0:
        return (128, 128, 128)
    return tuple(clamp(c) for c in stat.mean[:3])


def make_rgb_input(src: Image.Image) -> Image.Image:
    rgba = src.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    avg = visible_average(rgb, alpha)
    filled = Image.new("RGB", rgb.size, avg)
    filled.paste(rgb, mask=alpha)
    return filled


def visible_bbox(src: Image.Image, padding: int = 8) -> tuple[int, int, int, int] | None:
    alpha = src.getchannel("A")
    mask = alpha.point(lambda p: 255 if p > 2 else 0)
    box = mask.getbbox()
    if box is None:
        return None
    left, top, right, bottom = box
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(src.width, right + padding),
        min(src.height, bottom + padding),
    )


def crop_box_text(box: tuple[int, int, int, int] | None) -> str:
    return "" if box is None else ",".join(str(v) for v in box)


def scaled_alpha(src: Image.Image, scale: int) -> Image.Image:
    return src.getchannel("A").resize((src.width * scale, src.height * scale), Image.Resampling.LANCZOS)


def source_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.glob("*.png") if p.is_file() and not p.name.startswith("_"))


def prepare_inputs(files: list[Path], work_input: Path) -> dict[str, tuple[int, int, int, int] | None]:
    work_input.mkdir(parents=True, exist_ok=True)
    crop_boxes: dict[str, tuple[int, int, int, int] | None] = {}
    for src_path in files:
        src = Image.open(src_path).convert("RGBA")
        box = visible_bbox(src)
        crop_boxes[src_path.name] = box
        model_src = src.crop(box) if box else src
        make_rgb_input(model_src).save(work_input / src_path.name, "PNG", optimize=True)
    return crop_boxes


def run_realesrgan(
    exe: Path,
    model_dir: Path,
    work_input: Path,
    raw_output: Path,
    model: str,
    scale: int,
    tile_size: int | None,
) -> None:
    raw_output.mkdir(parents=True, exist_ok=True)
    prepared_files = source_files(work_input)
    for index, input_path in enumerate(prepared_files, start=1):
        output_path = raw_output / input_path.name
        print(f"Upscaling {index}/{len(prepared_files)}: {input_path.name}", flush=True)
        cmd = [
            str(exe),
            "-i",
            str(input_path),
            "-o",
            str(output_path),
            "-m",
            str(model_dir),
            "-n",
            model,
            "-s",
            str(scale),
            "-f",
            "png",
        ]
        if tile_size is not None:
            cmd.extend(["-t", str(tile_size)])
        subprocess.run(cmd, cwd=str(exe.parent), check=True)


def resized_source(src: Image.Image, expected_size: tuple[int, int]) -> Image.Image:
    return src.resize(expected_size, Image.Resampling.LANCZOS)


def visual_issue(src: Image.Image, candidate: Image.Image, expected_size: tuple[int, int]) -> str:
    baseline = resized_source(src, expected_size)
    alpha = baseline.getchannel("A")
    mask = alpha.point(lambda p: 255 if p > 16 else 0)
    visible_pixels = ImageStat.Stat(mask).sum[0] / 255
    if visible_pixels <= 0:
        return ""

    base_rgb = baseline.convert("RGB")
    cand_rgb = candidate.convert("RGB")
    base_stat = ImageStat.Stat(base_rgb, mask)
    cand_stat = ImageStat.Stat(cand_rgb, mask)
    base_mean = base_stat.mean[:3]
    cand_mean = cand_stat.mean[:3]
    diff = ImageChops.difference(base_rgb, cand_rgb)
    diff_mean = ImageStat.Stat(diff, mask).mean[:3]

    base_luma = base_mean[0] * 0.2126 + base_mean[1] * 0.7152 + base_mean[2] * 0.0722
    cand_luma = cand_mean[0] * 0.2126 + cand_mean[1] * 0.7152 + cand_mean[2] * 0.0722
    avg_diff = sum(diff_mean) / 3
    base_min = sum(channel[0] for channel in base_stat.extrema[:3]) / 3
    cand_min = sum(channel[0] for channel in cand_stat.extrema[:3]) / 3
    base_std = sum(base_stat.stddev[:3]) / 3
    cand_std = sum(cand_stat.stddev[:3]) / 3

    if base_luma > 45 and cand_luma < base_luma * 0.35 and avg_diff > 45:
        return "darkened"
    if avg_diff > 60:
        return "large_color_shift"
    if base_luma > 100 and avg_diff > 35 and cand_min < max(8, base_min * 0.35):
        return "stripe_noise"
    if avg_diff > 35 and cand_std > max(base_std * 1.6, base_std + 35):
        return "noise_spike"
    if max(diff_mean) > 145 and avg_diff > 70:
        return "channel_shift"
    return ""


def compose_raw_rgb(
    src: Image.Image,
    raw: Image.Image,
    crop_box: tuple[int, int, int, int] | None,
    expected_size: tuple[int, int],
    scale: int,
) -> Image.Image:
    if raw.size == expected_size or crop_box is None:
        return raw.resize(expected_size, Image.Resampling.LANCZOS) if raw.size != expected_size else raw

    left, top, right, bottom = crop_box
    crop_size = ((right - left) * scale, (bottom - top) * scale)
    if raw.size != crop_size:
        raw = raw.resize(crop_size, Image.Resampling.LANCZOS)

    base = resized_source(src, expected_size).convert("RGB")
    base.paste(raw, (left * scale, top * scale))
    return base


def apply_alpha_and_validate(
    files: list[Path],
    raw_output: Path,
    output_dir: Path,
    scale: int,
    crop_boxes: dict[str, tuple[int, int, int, int] | None],
    collision: str = 'rename',
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for src_path in files:
        raw_path = raw_output / src_path.name
        final_path = output_path_for(output_dir / src_path.name, collision)
        if final_path is None:
            rows.append({'file': src_path.name, 'output_file': src_path.name, 'skipped': True})
            continue
        src = Image.open(src_path).convert("RGBA")
        expected_size = (src.width * scale, src.height * scale)
        alpha = scaled_alpha(src, scale)
        crop_box = crop_boxes.get(src_path.name)
        fallback_used = False
        quality_issue = ""

        raw_exists = raw_path.exists()
        if raw_exists:
            raw = Image.open(raw_path).convert("RGB")
            composed = compose_raw_rgb(src, raw, crop_box, expected_size, scale)
            out = composed.convert("RGBA")
            out.putalpha(alpha)
            quality_issue = visual_issue(src, out, expected_size)
            if quality_issue:
                out = resized_source(src, expected_size)
                fallback_used = True
            final_path = publish_png(out, final_path, collision)
            if final_path is None:
                rows.append({'file':src_path.name,'output_file':src_path.name,'skipped':True})
                continue

        output_exists = final_path.exists()
        if output_exists:
            check = Image.open(final_path).convert("RGBA")
            alpha_ok = ImageChops.difference(alpha, check.getchannel("A")).getbbox() is None
            output_width = check.width
            output_height = check.height
        else:
            alpha_ok = False
            output_width = ""
            output_height = ""

        rows.append(
            {
                "file": src_path.name,
                "output_file": final_path.name,
                "skipped": False,
                "raw_exists": raw_exists,
                "output_exists": output_exists,
                "width": src.width,
                "height": src.height,
                "output_width": output_width,
                "output_height": output_height,
                "expected_width": expected_size[0],
                "expected_height": expected_size[1],
                "alpha_matches_scaled_original": alpha_ok,
                "crop_box": crop_box_text(crop_box),
                "fallback_used": fallback_used,
                "quality_issue": quality_issue,
            }
        )
    return rows


def write_report(rows: list[dict[str, object]], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "file",
                "output_file",
                "skipped",
                "raw_exists",
                "output_exists",
                "width",
                "height",
                "output_width",
                "output_height",
                "expected_width",
                "expected_height",
                "alpha_matches_scaled_original",
                "crop_box",
                "fallback_used",
                "quality_issue",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def paste_on_checker(canvas: Image.Image, img: Image.Image, xy: tuple[int, int], cell: int = 10) -> None:
    w, h = img.size
    checker = Image.new("RGBA", (w, h), (238, 238, 238, 255))
    pixels = checker.load()
    for y in range(h):
        for x in range(w):
            if ((x // cell) + (y // cell)) % 2:
                pixels[x, y] = (204, 204, 204, 255)
    checker.alpha_composite(img)
    canvas.alpha_composite(checker, xy)


def make_preview(files: list[Path], output_dir: Path, preview_path: Path, preview_count: int, output_names=None) -> None:
    output_names = output_names or {}
    selected = [p for p in files if (output_dir / output_names.get(p.name, p.name)).exists()][:preview_count]
    if not selected:
        return

    thumb = 136
    header_h = 22
    gap = 14
    cols = min(4, len(selected))
    row_h = thumb * 2 + header_h + gap
    sheet_w = cols * (thumb + gap) - gap
    sheet_h = ((len(selected) + cols - 1) // cols) * row_h
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (32, 34, 38, 255))
    draw = ImageDraw.Draw(sheet)

    for idx, src_path in enumerate(selected):
        col = idx % cols
        row = idx // cols
        x = col * (thumb + gap)
        y = row * row_h
        draw.text((x + 4, y + 3), src_path.name[:24], fill=(235, 235, 235, 255))

        old = Image.open(src_path).convert("RGBA")
        new = Image.open(output_dir / output_names.get(src_path.name, src_path.name)).convert("RGBA")
        old.thumbnail((thumb, thumb), Image.Resampling.LANCZOS)
        new.thumbnail((thumb, thumb), Image.Resampling.LANCZOS)
        paste_on_checker(sheet, old, (x + (thumb - old.width) // 2, y + header_h + (thumb - old.height) // 2))
        paste_on_checker(
            sheet,
            new,
            (x + (thumb - new.width) // 2, y + header_h + thumb + (thumb - new.height) // 2),
        )

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(preview_path, "PNG", optimize=True)


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Upscale transparent Spine/game PNG parts with Real-ESRGAN while preserving original alpha shape.",
    )
    parser.add_argument("--gui", action="store_true", help="Launch the Windows graphical interface.")
    parser.add_argument("--input", default=".", help="Folder containing source PNG files. Default: current folder.")
    parser.add_argument("--output", default="IMAGE2_4x_realesr_animevideov3", help="Final output folder.")
    parser.add_argument("--work", default="IMAGE2_4x_realesr_animevideov3_work", help="Intermediate work folder.")
    parser.add_argument("--scale", type=int, default=4, choices=[2, 3, 4], help="Upscale ratio. Default: 4.")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=SUPPORTED_MODELS, help="Real-ESRGAN model name.")
    parser.add_argument(
        "--exe",
        default=str(here / "tools" / "realesrgan-ncnn-vulkan.exe"),
        help="Path to realesrgan-ncnn-vulkan.exe.",
    )
    parser.add_argument(
        "--model-dir",
        default=str(here / "tools" / "models"),
        help="Path to Real-ESRGAN ncnn model folder.",
    )
    parser.add_argument("--tile-size", type=int, default=128, help="Optional Real-ESRGAN tile size. Default: 128.")
    parser.add_argument("--preview-count", type=int, default=24, help="Number of files to include in preview sheet.")
    parser.add_argument("--skip-upscale", action="store_true", help="Skip Real-ESRGAN and only reapply alpha to raw outputs.")
    parser.add_argument("--keep-work", action="store_true", help="Keep intermediate RGB and raw Real-ESRGAN folders.")
    parser.add_argument('--collision', choices=['rename', 'skip', 'overwrite'], default='rename', help='Existing PNG policy; default preserves the old file with a new numbered name.')
    return parser.parse_args()


def launch_gui(args: argparse.Namespace) -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    here = Path(__file__).resolve().parent

    def default_input() -> str:
        value = Path(args.input)
        if str(value) == ".":
            return str(here.parent)
        return str(value.resolve())

    def default_output(input_path: str) -> str:
        return str(Path(input_path) / f"IMAGE2_{scale_var.get()}x_{model_var.get()}")

    root = tk.Tk()
    root.title("SPINE 圖片解析度提高工具")
    root.geometry("880x680")
    root.minsize(820, 620)
    root.configure(bg="#101417")

    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#101417")
    style.configure("Panel.TFrame", background="#151b1f", borderwidth=1, relief="solid")
    style.configure("TLabel", background="#101417", foreground="#eaf4ea", font=("Microsoft JhengHei UI", 10))
    style.configure("Muted.TLabel", background="#101417", foreground="#9fb0a3", font=("Microsoft JhengHei UI", 9))
    style.configure("Panel.TLabel", background="#151b1f", foreground="#eaf4ea", font=("Microsoft JhengHei UI", 10))
    style.configure("Title.TLabel", background="#101417", foreground="#f4fff0", font=("Microsoft JhengHei UI", 18, "bold"))
    style.configure("Section.TLabel", background="#151b1f", foreground="#cfff50", font=("Microsoft JhengHei UI", 11, "bold"))
    style.configure("TButton", font=("Microsoft JhengHei UI", 10, "bold"), padding=(12, 8))
    style.configure("Primary.TButton", background="#91e600", foreground="#10140c")
    style.map("Primary.TButton", background=[("active", "#b8ff19")])
    style.configure("TEntry", fieldbackground="#0f1417", foreground="#f4fff0", insertcolor="#f4fff0")
    style.configure("TCombobox", fieldbackground="#0f1417", foreground="#f4fff0")
    style.configure("TCheckbutton", background="#151b1f", foreground="#eaf4ea")

    scale_var = tk.IntVar(value=args.scale)
    input_var = tk.StringVar(value=default_input())
    output_var = tk.StringVar()
    model_var = tk.StringVar(value=args.model)
    tile_var = tk.StringVar(value="" if args.tile_size is None else str(args.tile_size))
    preview_var = tk.StringVar(value=str(args.preview_count))
    keep_work_var = tk.BooleanVar(value=args.keep_work)
    skip_upscale_var = tk.BooleanVar(value=args.skip_upscale)
    running = {"value": False}
    process = {"value": None}
    cancelled = threading.Event()
    ui_events = queue.Queue()
    def post_ui(function, *values):
        ui_events.put((function, values))
    def drain_ui():
        while not ui_events.empty():
            function, values = ui_events.get_nowait()
            function(*values)
        root.after(100, drain_ui)
    root.after(100, drain_ui)
    collision_var = tk.StringVar(value=args.collision)

    output_var.set(default_output(input_var.get()))

    root.columnconfigure(0, weight=1)
    root.rowconfigure(3, weight=1)

    header = ttk.Frame(root, padding=(22, 18, 22, 12))
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="SPINE 圖片解析度提高工具", style="Title.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(
        header,
        text="保留原始透明輪廓，使用 Real-ESRGAN 提高 PNG 素材解析度，適合 Spine/game 拆件素材。",
        style="Muted.TLabel",
    ).grid(row=1, column=0, sticky="w", pady=(6, 0))

    path_panel = ttk.Frame(root, style="Panel.TFrame", padding=16)
    path_panel.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 14))
    path_panel.columnconfigure(1, weight=1)

    def choose_input() -> None:
        selected = filedialog.askdirectory(title="選擇來源 PNG 資料夾", initialdir=input_var.get())
        if selected:
            input_var.set(selected)
            output_var.set(default_output(selected))
            update_summary()

    def choose_output() -> None:
        selected = filedialog.askdirectory(title="選擇輸出資料夾", initialdir=output_var.get() or input_var.get())
        if selected:
            output_var.set(selected)

    ttk.Label(path_panel, text="來源資料夾", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
    ttk.Entry(path_panel, textvariable=input_var).grid(row=0, column=1, sticky="ew", pady=5)
    ttk.Button(path_panel, text="選擇", command=choose_input).grid(row=0, column=2, padx=(10, 0), pady=5)
    ttk.Label(path_panel, text="輸出資料夾", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=5)
    ttk.Entry(path_panel, textvariable=output_var).grid(row=1, column=1, sticky="ew", pady=5)
    ttk.Button(path_panel, text="選擇", command=choose_output).grid(row=1, column=2, padx=(10, 0), pady=5)

    options = ttk.Frame(root, style="Panel.TFrame", padding=16)
    options.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 14))
    for col in range(6):
        options.columnconfigure(col, weight=1)

    ttk.Label(options, text="處理設定", style="Section.TLabel").grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 10))
    ttk.Label(options, text="倍率", style="Panel.TLabel").grid(row=1, column=0, sticky="w")
    ttk.Combobox(options, textvariable=scale_var, values=[2, 3, 4], state="readonly", width=8).grid(row=1, column=1, sticky="w", padx=(6, 20))
    ttk.Label(options, text="模型", style="Panel.TLabel").grid(row=1, column=2, sticky="w")
    model_combo = ttk.Combobox(options, textvariable=model_var, values=list(SUPPORTED_MODELS), state="readonly", width=28)
    model_combo.grid(row=1, column=3, columnspan=3, sticky="ew", padx=(6, 0))
    ttk.Label(options, text="Tile Size", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(12, 0))
    ttk.Entry(options, textvariable=tile_var, width=10).grid(row=2, column=1, sticky="w", padx=(6, 20), pady=(12, 0))
    ttk.Label(options, text="預覽張數", style="Panel.TLabel").grid(row=2, column=2, sticky="w", pady=(12, 0))
    ttk.Entry(options, textvariable=preview_var, width=10).grid(row=2, column=3, sticky="w", padx=(6, 20), pady=(12, 0))
    ttk.Checkbutton(options, text="保留中繼資料夾", variable=keep_work_var).grid(row=2, column=4, sticky="w", pady=(12, 0))
    ttk.Checkbutton(options, text="只套 alpha，不重新放大", variable=skip_upscale_var).grid(row=2, column=5, sticky="w", pady=(12, 0))
    ttk.Label(options, text='同名輸出', style='Panel.TLabel').grid(row=3, column=0, sticky='w', pady=(10,0))
    ttk.Combobox(options, textvariable=collision_var, values=['rename','skip','overwrite'], state='readonly', width=12).grid(row=3,column=1,sticky='w',pady=(10,0))
    ttk.Label(options, text='rename：保留並編號；skip：略過；overwrite：覆寫輸出', style='Panel.TLabel').grid(row=3,column=2,columnspan=4,sticky='w',pady=(10,0))

    log_panel = ttk.Frame(root, style="Panel.TFrame", padding=16)
    log_panel.grid(row=3, column=0, sticky="nsew", padx=22, pady=(0, 14))
    log_panel.columnconfigure(0, weight=1)
    log_panel.rowconfigure(2, weight=1)
    summary_var = tk.StringVar()
    ttk.Label(log_panel, text="執行狀態", style="Section.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(log_panel, textvariable=summary_var, style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 10))
    log_text = tk.Text(
        log_panel,
        bg="#0f1417",
        fg="#dce8dc",
        insertbackground="#dce8dc",
        relief="flat",
        height=12,
        wrap="word",
        font=("Consolas", 10),
    )
    log_text.grid(row=2, column=0, sticky="nsew")
    log_scroll = ttk.Scrollbar(log_panel, orient="vertical", command=log_text.yview)
    log_scroll.grid(row=2, column=1, sticky="ns")
    log_text.configure(yscrollcommand=log_scroll.set)

    progress = ttk.Progressbar(root, mode="indeterminate")
    progress.grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 10))

    buttons = ttk.Frame(root, padding=(22, 0, 22, 18))
    buttons.grid(row=5, column=0, sticky="ew")
    buttons.columnconfigure(0, weight=1)

    def append_log(text: str) -> None:
        log_text.insert("end", text)
        log_text.see("end")

    def update_summary(*_args) -> None:
        folder = Path(input_var.get())
        png_count = len(source_files(folder)) if folder.exists() else 0
        model_label = MODEL_LABELS.get(model_var.get(), model_var.get())
        summary_var.set(f"來源 PNG：{png_count} 張｜倍率：{scale_var.get()}x｜模型：{model_label}")

    for variable in (input_var, model_var, scale_var):
        variable.trace_add("write", update_summary)
    update_summary()

    def validate() -> tuple[bool, list[str]]:
        errors = []
        try:
            validate_paths(Path(input_var.get()), Path(output_var.get()), Path(output_var.get() + '_work'))
        except ValueError as exc:
            errors.append(str(exc))
        if not Path(input_var.get()).exists():
            errors.append("來源資料夾不存在。")
        if not output_var.get().strip():
            errors.append("請設定輸出資料夾。")
        try:
            int(preview_var.get())
            if not 0 <= int(preview_var.get()) <= 100: raise ValueError()
        except ValueError:
            errors.append("預覽張數必須是整數。")
        if tile_var.get().strip():
            try:
                int(tile_var.get())
                if int(tile_var.get()) < 0: raise ValueError()
            except ValueError:
                errors.append("Tile Size 必須是整數或空白。")
        if not (here / "tools" / "realesrgan-ncnn-vulkan.exe").exists():
            errors.append("找不到 tools/realesrgan-ncnn-vulkan.exe。")
        return not errors, errors

    def build_command() -> list[str]:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--input",
            input_var.get(),
            "--output",
            output_var.get(),
            "--work",
            f"{output_var.get()}_work",
            "--scale",
            str(scale_var.get()),
            "--model",
            model_var.get(),
            "--exe",
            str(here / "tools" / "realesrgan-ncnn-vulkan.exe"),
            "--model-dir",
            str(here / "tools" / "models"),
            "--preview-count",
            preview_var.get(),
        ]
        if tile_var.get().strip():
            command.extend(["--tile-size", tile_var.get().strip()])
        if keep_work_var.get():
            command.append("--keep-work")
        if skip_upscale_var.get():
            command.append("--skip-upscale")
        command.extend(['--collision', collision_var.get()])
        return command

    def set_running(value: bool) -> None:
        running["value"] = value
        start_button.configure(state="disabled" if value else "normal")
        stop_button.configure(state="normal" if value else "disabled")
        if value:
            progress.start(12)
        else:
            progress.stop()

    def run_worker(command) -> None:
        try:
            if cancelled.is_set(): raise RuntimeError('已取消')
            process["value"] = subprocess.Popen(
                command,
                cwd=str(here),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=not sys.platform.startswith('win'),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            )
            if cancelled.is_set(): terminate_process_tree(process['value'])
            assert process["value"].stdout is not None
            for line in process["value"].stdout:
                post_ui(append_log, line)
            code = process["value"].wait()
        except Exception as exc:
            post_ui(append_log, f"\n執行失敗：{exc}\n")
            code = 1
        finally:
            process["value"] = None
            post_ui(set_running, False)
            post_ui(append_log, "\n完成。\n" if code == 0 else f"\n處理結束，錯誤碼：{code}\n")
            if code == 0:
                post_ui(lambda: messagebox.showinfo("完成", "圖片解析度提高完成。"))

    def start() -> None:
        if running["value"]:
            return
        ok, errors = validate()
        if not ok:
            messagebox.showwarning("設定有誤", "\n".join(errors))
            return
        log_text.delete("1.0", "end")
        command = build_command()
        append_log('執行命令：\n' + ' '.join(command) + '\n')
        cancelled.clear()
        set_running(True)
        threading.Thread(target=run_worker, args=(command,), daemon=True).start()

    def stop() -> None:
        cancelled.set()
        proc = process["value"]
        if proc and proc.poll() is None:
            terminate_process_tree(proc)
            append_log("\n已要求停止處理。\n")

    def open_output() -> None:
        path = Path(output_var.get())
        if path.exists():
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        else:
            messagebox.showinfo("尚未產生", "輸出資料夾尚不存在。")

    start_button = ttk.Button(buttons, text="開始提高解析度", style="Primary.TButton", command=start)
    start_button.grid(row=0, column=1, padx=(8, 0))
    stop_button = ttk.Button(buttons, text="停止", state="disabled", command=stop)
    stop_button.grid(row=0, column=2, padx=(8, 0))
    ttk.Button(buttons, text="開啟輸出資料夾", command=open_output).grid(row=0, column=3, padx=(8, 0))
    def close():
        if running['value']:
            if not messagebox.askyesno('停止並關閉', '目前仍在處理，要停止本次作業並關閉？'): return
            stop()
        root.destroy()
    ttk.Button(buttons, text="關閉", command=close).grid(row=0, column=4, padx=(8, 0))
    root.protocol('WM_DELETE_WINDOW', close)

    root.mainloop()
    return 0


def main() -> int:
    args = parse_args()
    if args.gui:
        return launch_gui(args)

    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    work_base = Path(args.work).resolve()
    try:
        validate_paths(input_dir, output_dir, work_base)
        if not 0 <= args.preview_count <= 100 or args.tile_size < 0: raise ValueError('預覽張數限 0–100，Tile Size 不可小於 0。')
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    files = source_files(input_dir)
    if not files:
        print('No source PNG files found.', file=sys.stderr)
        return 1
    signature = input_signature(files, args.scale, args.model)
    work_dir = create_work_directory(work_base, signature, args.skip_upscale)
    work_input = work_dir / "input_rgb"
    raw_output = work_dir / "raw_realesr"
    report_path = output_path_for(output_dir / "_validation_report.csv")
    preview_path = output_path_for(output_dir / "_preview_contact_sheet.png")
    exe = Path(args.exe).resolve()
    model_dir = Path(args.model_dir).resolve()

    if not input_dir.exists():
        print(f"Input folder not found: {input_dir}", file=sys.stderr)
        return 2
    if not exe.exists():
        print(f"Real-ESRGAN executable not found: {exe}", file=sys.stderr)
        return 2
    if not model_dir.exists():
        print(f"Real-ESRGAN model folder not found: {model_dir}", file=sys.stderr)
        return 2

    files = source_files(input_dir)
    if not files:
        print(f"No PNG files found in: {input_dir}", file=sys.stderr)
        return 1

    print(f"Source PNGs: {len(files)}")
    print(f"Model: {args.model}")
    print(f"Scale: {args.scale}x")
    print(f"Output: {output_dir}")

    crop_boxes = prepare_inputs(files, work_input)
    if not args.skip_upscale:
        run_realesrgan(exe, model_dir, work_input, raw_output, args.model, args.scale, args.tile_size)

    rows = apply_alpha_and_validate(files, raw_output, output_dir, args.scale, crop_boxes, args.collision)
    write_report(rows, report_path)
    make_preview(files, output_dir, preview_path, args.preview_count, {r['file']:r['output_file'] for r in rows})
    fallback_count = sum(1 for row in rows if row.get("fallback_used"))

    bad = [
        row
        for row in rows
        if not row.get('skipped') and (not row["raw_exists"]
        or not row["output_exists"]
        or row["output_width"] != row["expected_width"]
        or row["output_height"] != row["expected_height"]
        or not row["alpha_matches_scaled_original"])
    ]
    print(f"Finished: {len(rows)} files")
    print(f"Validation failures: {len(bad)}")
    print(f"Safety fallbacks: {fallback_count}")
    print(f"Report: {report_path}")
    print(f"Preview: {preview_path}")

    if not args.keep_work and not bad:
        cleanup_work_directory(work_dir, work_base, signature)
        print(f"Removed work folder: {work_dir}")
    elif args.keep_work:
        print(f"Kept work folder: {work_dir}")

    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
