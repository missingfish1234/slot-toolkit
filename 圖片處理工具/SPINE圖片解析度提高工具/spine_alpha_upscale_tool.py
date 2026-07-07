from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import threading
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


def scaled_alpha(src: Image.Image, scale: int) -> Image.Image:
    return src.getchannel("A").resize((src.width * scale, src.height * scale), Image.Resampling.LANCZOS)


def source_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.glob("*.png") if p.is_file() and not p.name.startswith("_"))


def prepare_inputs(files: list[Path], work_input: Path) -> None:
    work_input.mkdir(parents=True, exist_ok=True)
    for src_path in files:
        src = Image.open(src_path).convert("RGBA")
        make_rgb_input(src).save(work_input / src_path.name, "PNG", optimize=True)


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
    cmd = [
        str(exe),
        "-i",
        str(work_input),
        "-o",
        str(raw_output),
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


def apply_alpha_and_validate(files: list[Path], raw_output: Path, output_dir: Path, scale: int) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for src_path in files:
        raw_path = raw_output / src_path.name
        final_path = output_dir / src_path.name
        src = Image.open(src_path).convert("RGBA")
        expected_size = (src.width * scale, src.height * scale)
        alpha = scaled_alpha(src, scale)

        raw_exists = raw_path.exists()
        if raw_exists:
            raw = Image.open(raw_path).convert("RGB")
            if raw.size != expected_size:
                raw = raw.resize(expected_size, Image.Resampling.LANCZOS)
            out = raw.convert("RGBA")
            out.putalpha(alpha)
            out.save(final_path, "PNG", optimize=True)

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
                "raw_exists": raw_exists,
                "output_exists": output_exists,
                "width": src.width,
                "height": src.height,
                "output_width": output_width,
                "output_height": output_height,
                "expected_width": expected_size[0],
                "expected_height": expected_size[1],
                "alpha_matches_scaled_original": alpha_ok,
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
                "raw_exists",
                "output_exists",
                "width",
                "height",
                "output_width",
                "output_height",
                "expected_width",
                "expected_height",
                "alpha_matches_scaled_original",
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


def make_preview(files: list[Path], output_dir: Path, preview_path: Path, preview_count: int) -> None:
    selected = [p for p in files if (output_dir / p.name).exists()][:preview_count]
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
        new = Image.open(output_dir / src_path.name).convert("RGBA")
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
    parser.add_argument("--tile-size", type=int, default=None, help="Optional Real-ESRGAN tile size.")
    parser.add_argument("--preview-count", type=int, default=24, help="Number of files to include in preview sheet.")
    parser.add_argument("--skip-upscale", action="store_true", help="Skip Real-ESRGAN and only reapply alpha to raw outputs.")
    parser.add_argument("--keep-work", action="store_true", help="Keep intermediate RGB and raw Real-ESRGAN folders.")
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
        if not Path(input_var.get()).exists():
            errors.append("來源資料夾不存在。")
        if not output_var.get().strip():
            errors.append("請設定輸出資料夾。")
        try:
            int(preview_var.get())
        except ValueError:
            errors.append("預覽張數必須是整數。")
        if tile_var.get().strip():
            try:
                int(tile_var.get())
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
        return command

    def set_running(value: bool) -> None:
        running["value"] = value
        start_button.configure(state="disabled" if value else "normal")
        stop_button.configure(state="normal" if value else "disabled")
        if value:
            progress.start(12)
        else:
            progress.stop()

    def run_worker() -> None:
        command = build_command()
        append_log("執行命令：\n" + " ".join(f'"{part}"' if " " in part else part for part in command) + "\n\n")
        try:
            process["value"] = subprocess.Popen(
                command,
                cwd=str(here),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process["value"].stdout is not None
            for line in process["value"].stdout:
                root.after(0, append_log, line)
            code = process["value"].wait()
        except Exception as exc:
            root.after(0, append_log, f"\n執行失敗：{exc}\n")
            code = 1
        finally:
            process["value"] = None
            root.after(0, set_running, False)
            root.after(0, append_log, "\n完成。\n" if code == 0 else f"\n處理結束，錯誤碼：{code}\n")
            if code == 0:
                root.after(0, lambda: messagebox.showinfo("完成", "圖片解析度提高完成。"))

    def start() -> None:
        if running["value"]:
            return
        ok, errors = validate()
        if not ok:
            messagebox.showwarning("設定有誤", "\n".join(errors))
            return
        log_text.delete("1.0", "end")
        set_running(True)
        threading.Thread(target=run_worker, daemon=True).start()

    def stop() -> None:
        proc = process["value"]
        if proc and proc.poll() is None:
            proc.terminate()
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
    ttk.Button(buttons, text="關閉", command=root.destroy).grid(row=0, column=4, padx=(8, 0))

    root.mainloop()
    return 0


def main() -> int:
    args = parse_args()
    if args.gui:
        return launch_gui(args)

    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    work_dir = Path(args.work).resolve()
    work_input = work_dir / "input_rgb"
    raw_output = work_dir / "raw_realesr"
    report_path = output_dir / "_validation_report.csv"
    preview_path = output_dir / "_preview_contact_sheet.png"
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

    prepare_inputs(files, work_input)
    if not args.skip_upscale:
        run_realesrgan(exe, model_dir, work_input, raw_output, args.model, args.scale, args.tile_size)

    rows = apply_alpha_and_validate(files, raw_output, output_dir, args.scale)
    write_report(rows, report_path)
    make_preview(files, output_dir, preview_path, args.preview_count)

    bad = [
        row
        for row in rows
        if not row["raw_exists"]
        or not row["output_exists"]
        or row["output_width"] != row["expected_width"]
        or row["output_height"] != row["expected_height"]
        or not row["alpha_matches_scaled_original"]
    ]
    print(f"Finished: {len(rows)} files")
    print(f"Validation failures: {len(bad)}")
    print(f"Report: {report_path}")
    print(f"Preview: {preview_path}")

    if not args.keep_work and not bad:
        shutil.rmtree(work_dir, ignore_errors=True)
        print(f"Removed work folder: {work_dir}")
    elif args.keep_work:
        print(f"Kept work folder: {work_dir}")

    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
