# -*- coding: utf-8 -*-
"""
影片最後一幀輸出工具 - 自動安裝依賴版

功能：
1. 選擇單一影片，輸出最後一個畫面為圖片
2. 選擇資料夾，批次輸出每支影片的最後一幀
3. 支援 mp4 / mov / avi / mkv / webm / m4v

如果缺少 opencv-python / pillow，工具會自動嘗試安裝。
"""

import sys
import subprocess
import importlib


def ensure_package(import_name: str, pip_name: str):
    try:
        return importlib.import_module(import_name)
    except ModuleNotFoundError:
        print(f"缺少套件 {pip_name}，正在自動安裝...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return importlib.import_module(import_name)


cv2 = ensure_package("cv2", "opencv-python")
PIL_Image_Module = ensure_package("PIL.Image", "pillow")
Image = PIL_Image_Module

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def safe_filename(name: str) -> str:
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "_")
    return name.strip()


def extract_last_frame(video_path: str, output_dir: str, output_format: str = "png", jpg_quality: int = 95) -> str:
    video_path = str(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"無法開啟影片：{video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if frame_count <= 0:
        cap.release()
        raise RuntimeError(f"無法讀取影片總幀數：{video_path}")

    frame = None

    # 從最後一幀往前嘗試，避免部分影片最後幀索引讀不到
    start_index = frame_count - 1
    end_index = max(frame_count - 120, -1)

    for index in range(start_index, end_index, -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, current_frame = cap.read()
        if ret and current_frame is not None:
            frame = current_frame
            break

    cap.release()

    if frame is None:
        raise RuntimeError(f"讀取最後畫面失敗：{video_path}")

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(frame_rgb)

    stem = safe_filename(Path(video_path).stem)
    output_format = output_format.lower().replace(".", "")

    if output_format not in {"png", "jpg", "jpeg"}:
        output_format = "png"

    ext = "jpg" if output_format in {"jpg", "jpeg"} else "png"
    output_path = output_dir / f"{stem}_last_frame.{ext}"

    if ext == "jpg":
        img.save(output_path, quality=jpg_quality)
    else:
        img.save(output_path)

    return str(output_path)


class LastFrameTool(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("影片最後一幀輸出工具")
        self.geometry("650x390")
        self.resizable(False, False)

        self.video_path_var = tk.StringVar()
        self.folder_path_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.format_var = tk.StringVar(value="png")
        self.status_var = tk.StringVar(value="請選擇影片或資料夾。")

        self.build_ui()

    def build_ui(self):
        title = tk.Label(self, text="影片最後一幀輸出工具", font=("Microsoft JhengHei UI", 16, "bold"))
        title.pack(pady=(14, 8))

        frame = tk.Frame(self)
        frame.pack(fill="x", padx=12, pady=6)

        tk.Label(frame, text="單一影片：", width=12, anchor="e").grid(row=0, column=0, sticky="e", pady=5)
        tk.Entry(frame, textvariable=self.video_path_var, width=58).grid(row=0, column=1, padx=6)
        tk.Button(frame, text="選擇影片", command=self.select_video).grid(row=0, column=2)

        tk.Label(frame, text="批次資料夾：", width=12, anchor="e").grid(row=1, column=0, sticky="e", pady=5)
        tk.Entry(frame, textvariable=self.folder_path_var, width=58).grid(row=1, column=1, padx=6)
        tk.Button(frame, text="選擇資料夾", command=self.select_folder).grid(row=1, column=2)

        tk.Label(frame, text="輸出位置：", width=12, anchor="e").grid(row=2, column=0, sticky="e", pady=5)
        tk.Entry(frame, textvariable=self.output_dir_var, width=58).grid(row=2, column=1, padx=6)
        tk.Button(frame, text="選擇位置", command=self.select_output_dir).grid(row=2, column=2)

        option_frame = tk.Frame(self)
        option_frame.pack(fill="x", padx=12, pady=6)

        tk.Label(option_frame, text="輸出格式：").pack(side="left", padx=(112, 6))
        ttk.Combobox(
            option_frame,
            textvariable=self.format_var,
            values=["png", "jpg"],
            state="readonly",
            width=8
        ).pack(side="left")

        button_frame = tk.Frame(self)
        button_frame.pack(pady=12)

        tk.Button(
            button_frame,
            text="輸出單一影片最後畫面",
            width=25,
            height=2,
            command=self.export_single
        ).grid(row=0, column=0, padx=8)

        tk.Button(
            button_frame,
            text="批次輸出資料夾影片",
            width=25,
            height=2,
            command=self.export_batch
        ).grid(row=0, column=1, padx=8)

        self.progress = ttk.Progressbar(self, orient="horizontal", length=585, mode="determinate")
        self.progress.pack(pady=8)

        status = tk.Label(
            self,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            wraplength=590,
            fg="#333333"
        )
        status.pack(fill="x", padx=28, pady=6)

        note = tk.Label(
            self,
            text="提示：如果不選輸出位置，會自動輸出到影片同層或資料夾內的 last_frames。",
            fg="#666666"
        )
        note.pack(pady=(6, 0))

    def select_video(self):
        path = filedialog.askopenfilename(
            title="選擇影片",
            filetypes=[
                ("Video Files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.video_path_var.set(path)
            if not self.output_dir_var.get():
                self.output_dir_var.set(str(Path(path).parent / "last_frames"))

    def select_folder(self):
        path = filedialog.askdirectory(title="選擇影片資料夾")
        if path:
            self.folder_path_var.set(path)
            if not self.output_dir_var.get():
                self.output_dir_var.set(str(Path(path) / "last_frames"))

    def select_output_dir(self):
        path = filedialog.askdirectory(title="選擇輸出位置")
        if path:
            self.output_dir_var.set(path)

    def export_single(self):
        video_path = self.video_path_var.get().strip()

        if not video_path:
            messagebox.showwarning("提醒", "請先選擇一支影片。")
            return

        if not Path(video_path).exists():
            messagebox.showerror("錯誤", "影片路徑不存在。")
            return

        output_dir = self.output_dir_var.get().strip() or str(Path(video_path).parent / "last_frames")

        try:
            self.progress["maximum"] = 100
            self.progress["value"] = 0
            self.status_var.set("正在輸出最後一幀...")
            self.update_idletasks()

            output_path = extract_last_frame(video_path, output_dir, self.format_var.get())

            self.progress["value"] = 100
            self.status_var.set(f"完成：{output_path}")
            messagebox.showinfo("完成", f"已輸出：\n{output_path}")

        except Exception as e:
            self.status_var.set("輸出失敗。")
            messagebox.showerror("錯誤", str(e))

    def export_batch(self):
        folder_path = self.folder_path_var.get().strip()

        if not folder_path:
            messagebox.showwarning("提醒", "請先選擇影片資料夾。")
            return

        folder = Path(folder_path)

        if not folder.exists():
            messagebox.showerror("錯誤", "資料夾路徑不存在。")
            return

        videos = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]

        if not videos:
            messagebox.showwarning("提醒", "此資料夾沒有找到支援的影片格式。")
            return

        output_dir = self.output_dir_var.get().strip() or str(folder / "last_frames")

        success = 0
        failed = []

        self.progress["maximum"] = len(videos)
        self.progress["value"] = 0

        for i, video in enumerate(videos, 1):
            try:
                self.status_var.set(f"正在處理 {i}/{len(videos)}：{video.name}")
                self.update_idletasks()

                extract_last_frame(str(video), output_dir, self.format_var.get())
                success += 1

            except Exception as e:
                failed.append(f"{video.name}：{e}")

            self.progress["value"] = i
            self.update_idletasks()

        msg = f"批次完成：成功 {success} 支，失敗 {len(failed)} 支。\n輸出位置：{output_dir}"

        if failed:
            msg += "\n\n失敗清單：\n" + "\n".join(failed[:10])
            if len(failed) > 10:
                msg += f"\n...另有 {len(failed) - 10} 筆"

        self.status_var.set(msg)
        messagebox.showinfo("完成", msg)


if __name__ == "__main__":
    app = LastFrameTool()
    app.mainloop()
