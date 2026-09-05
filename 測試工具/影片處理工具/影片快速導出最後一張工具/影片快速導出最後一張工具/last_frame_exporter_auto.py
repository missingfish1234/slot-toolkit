# -*- coding: utf-8 -*-
"""
影片最後一幀輸出工具 - 背景處理與輸出保護版

功能：
1. 選擇單一影片，輸出最後一個畫面為圖片
2. 選擇資料夾，批次輸出每支影片的最後一幀
3. 支援 mp4 / mov / avi / mkv / webm / m4v

缺少依賴請執行 fix_package.bat；正常啟動不會修改 Python 套件。
"""

import sys
import subprocess
import importlib
import threading
import queue


def ensure_package(import_name: str, pip_name: str):
    try:
        return importlib.import_module(import_name)
    except ModuleNotFoundError:
        raise RuntimeError(f'缺少 {pip_name}；請先執行 fix_package.bat 安裝本工具專用環境。')


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


def extract_last_frame(video_path: str, output_dir: str, output_format: str = "png", jpg_quality: int = 95, cancel=None) -> str:
    video_path = str(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"無法開啟影片：{video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if frame_count <= 0:
        cap.release()
        raise RuntimeError(f"無法讀取影片總幀數：{video_path}")

    frame = None

    # 從最後一幀往前嘗試，避免部分影片最後幀索引讀不到
    start_index = frame_count - 1
    end_index = max(frame_count - 120, -1)

    try:
        for index in range(start_index, end_index, -1):
            if cancel and cancel.is_set(): raise InterruptedError('已取消')
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ret, current_frame = cap.read()
            if ret and current_frame is not None:
                frame = current_frame
                break
    finally:
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

    if cancel and cancel.is_set(): raise InterruptedError('已取消')
    index = 1
    while True:
        try:
            stream = output_path.open('xb')
            break
        except FileExistsError:
            index += 1
            output_path = output_dir / f'{stem}_last_frame_{index}.{ext}'
    try:
        with stream:
            img.save(stream, format='JPEG' if ext == 'jpg' else 'PNG', **({'quality':jpg_quality} if ext == 'jpg' else {}))
    except Exception:
        output_path.unlink(missing_ok=True)
        raise

    return str(output_path)


class LastFrameTool(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("影片最後一幀輸出工具")
        self.geometry("750x420")
        self.resizable(False, False)

        self.video_path_var = tk.StringVar()
        self.folder_path_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.format_var = tk.StringVar(value="png")
        self.status_var = tk.StringVar(value="請選擇影片或資料夾。")
        self.cancel_event = threading.Event()
        self.events = queue.Queue()
        self.busy = False

        self.build_ui()
        self.after(100, self.poll_events)
        self.protocol('WM_DELETE_WINDOW', self.close_tool)

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

        self.single_button = tk.Button(
            button_frame,
            text="輸出單一影片最後畫面",
            width=25,
            height=2,
            command=self.export_single
        )
        self.single_button.grid(row=0, column=0, padx=8)

        self.batch_button = tk.Button(
            button_frame,
            text="批次輸出資料夾影片",
            width=25,
            height=2,
            command=self.export_batch
        )
        self.batch_button.grid(row=0, column=1, padx=8)
        self.cancel_button = tk.Button(button_frame, text='取消', command=self.cancel_event.set, state='disabled')
        self.cancel_button.grid(row=0,column=2)

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

    def start_job(self, videos, output_dir):
        if self.busy: return
        self.busy = True
        self.cancel_event.clear()
        self.single_button.configure(state='disabled')
        self.batch_button.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.progress['maximum'] = len(videos)
        self.progress['value'] = 0
        output_format = self.format_var.get()
        def worker():
            success, failed = 0, []
            try:
                for i, video in enumerate(videos, 1):
                    if self.cancel_event.is_set(): break
                    self.events.put(('status', f'正在處理 {i}/{len(videos)}：{video.name}'))
                    try:
                        extract_last_frame(str(video), output_dir, output_format, cancel=self.cancel_event)
                        success += 1
                    except InterruptedError:
                        break
                    except Exception as exc:
                        failed.append(f'{video.name}：{exc}')
                    self.events.put(('progress', i))
            finally:
                self.events.put(('done', (success, failed, output_dir, self.cancel_event.is_set())))
        threading.Thread(target=worker, daemon=True).start()

    def export_single(self):
        path = Path(self.video_path_var.get().strip())
        if not path.is_file():
            messagebox.showwarning('提醒', '請選擇有效影片。')
            return
        self.start_job([path], self.output_dir_var.get().strip() or str(path.parent / 'last_frames'))

    def export_batch(self):
        folder = Path(self.folder_path_var.get().strip())
        if not self.folder_path_var.get().strip() or not folder.is_dir():
            messagebox.showwarning('提醒', '請選擇影片資料夾。')
            return
        videos = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
        if not videos:
            messagebox.showinfo('提醒', '此資料夾沒有支援的影片。')
            return
        self.start_job(videos, self.output_dir_var.get().strip() or str(folder / 'last_frames'))

    def poll_events(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'status': self.status_var.set(value)
            elif kind == 'progress': self.progress['value'] = value
            elif kind == 'done':
                self.busy = False
                self.single_button.configure(state='normal')
                self.batch_button.configure(state='normal')
                self.cancel_button.configure(state='disabled')
                success, failed, folder, cancelled = value
                status = '已取消' if cancelled else '處理完成'
                summary = f'{status}：成功 {success} 支，失敗 {len(failed)} 支。輸出：{folder}'
                self.status_var.set(summary)
                if failed: messagebox.showwarning(status, summary + '\n' + '\n'.join(failed[:10]))
        self.after(100, self.poll_events)

    def close_tool(self):
        if self.busy:
            self.cancel_event.set()
            self.status_var.set('正在取消；目前幀解碼完成後即可關閉。')
            self.after(100, self.close_when_idle)
        else:
            self.destroy()

    def close_when_idle(self):
        if self.busy: self.after(100, self.close_when_idle)
        else: self.destroy()


if __name__ == "__main__":
    app = LastFrameTool()
    app.mainloop()
