import os
import json
import subprocess
import threading
import tkinter as tk
import csv
import math
import struct
import tempfile
import shutil
import re
import time
from tkinter import filedialog, messagebox, ttk

def create_export_settings():
    temp_settings_fd, temp_settings_path = tempfile.mkstemp(suffix=".json", prefix="spine_export_")
    settings_content = {
        "class": "export-json",
        "extension": ".json",
        "format": "JSON",
        "nonessential": True,
        "prettyPrint": False
    }
    with os.fdopen(temp_settings_fd, 'w', encoding='utf-8') as f:
        json.dump(settings_content, f)
    return temp_settings_path

def get_skel_version(filepath):
    """暴力掃描二進位，精準抓出版本號"""
    try:
        with open(filepath, 'rb') as f:
            data = f.read(256)
            match = re.search(rb'(3\.\d+\.\d+|4\.\d+\.\d+)', data)
            if match:
                return match.group(1).decode('ascii')
    except Exception:
        pass
    return None

def skel_to_json_hidden(skel_path, settings_path, spine_exe_path):
    temp_dir = tempfile.mkdtemp()
    skel_version = get_skel_version(skel_path)
    
    def run_spine(use_version, max_wait_sec):
        # 確保資料夾乾淨
        for f in os.listdir(temp_dir):
            if f.endswith(".json"):
                try: os.remove(os.path.join(temp_dir, f))
                except: pass

        cmd = [spine_exe_path]
        if use_version and skel_version:
            cmd.extend(["--update", skel_version])
        
        # 修正：直接使用原始 skel_path 作為輸入，確保 Spine 抓得到同層的 atlas/png
        cmd.extend([
            "--input", skel_path,
            "--output", temp_dir,
            "--export", settings_path
        ])
        
        try:
            # 修正：使用 Popen 後加上 wait() 阻塞等待，確保 Spine 轉檔程序「完全結束」
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # 讓主執行緒等待 Spine 處理，設定 Timeout 防止卡死
            proc.wait(timeout=max_wait_sec) 
            
            # 執行結束後再安心尋找 json 檔案
            for f in os.listdir(temp_dir):
                if f.endswith(".json"):
                    return os.path.join(temp_dir, f)
                    
        except subprocess.TimeoutExpired:
            proc.kill() # 如果超時，強制砍掉這個 Spine 背景處理序
        except Exception:
            pass
            
        return None

    # 第一階段：強制使用偵測到的版本，給予充足時間讓 Spine 下載核心！
    json_out = run_spine(use_version=True, max_wait_sec=120)
    
    # 第二階段：若失敗，退回預設盲測
    if not json_out:
        json_out = run_spine(use_version=False, max_wait_sec=15)
        
    return json_out, skel_version, temp_dir

def get_texture_dependencies(base_file_path):
    dir_name = os.path.dirname(base_file_path)
    filename = os.path.basename(base_file_path)
    
    filename_lower = filename.lower()
    if filename_lower.endswith(".skel.bytes"):
        base_name = filename[:-11]  
    elif filename_lower.endswith(".skel"):
        base_name = filename[:-5]   
    elif filename_lower.endswith(".json"):
        base_name = filename[:-5]   
    else:
        base_name = os.path.splitext(filename)[0]

    atlas_paths = [
        os.path.join(dir_name, base_name + ".atlas"),
        os.path.join(dir_name, base_name + ".atlas.txt")
    ]
    
    image_paths = []
    valid_atlas = None
    for ap in atlas_paths:
        if os.path.exists(ap):
            valid_atlas = ap
            break
            
    if valid_atlas:
        try:
            with open(valid_atlas, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.lower().endswith(".png") or line.lower().endswith(".jpg"):
                        img_path = os.path.abspath(os.path.join(dir_name, line))
                        if os.path.exists(img_path) and img_path not in image_paths:
                            image_paths.append(img_path)
        except Exception:
            pass
            
    if not image_paths:
        fallback_img = os.path.abspath(os.path.join(dir_name, base_name + ".png"))
        if os.path.exists(fallback_img):
            image_paths.append(fallback_img)
            
    return image_paths

def get_image_size(filepath):
    try:
        with open(filepath, 'rb') as f:
            head = f.read(24)
            if head.startswith(b'\x89PNG\r\n\x1a\n'):
                if head[12:16] == b'IHDR':
                    w, h = struct.unpack('>II', head[16:24])
                    return f"{w}x{h}"
            elif head.startswith(b'\xff\xd8'):
                f.seek(0)
                byte = f.read(2)
                while byte:
                    marker = f.read(1)
                    if marker == b'\xff':
                        continue
                    if marker in [b'\xc0', b'\xc1', b'\xc2']:
                        f.read(3)
                        h, w = struct.unpack('>HH', f.read(4))
                        return f"{w}x{h}"
                    else:
                        length_bytes = f.read(2)
                        if len(length_bytes) < 2: break
                        length = struct.unpack('>H', length_bytes)[0]
                        f.read(length - 2)
                    byte = f.read(1)
    except Exception:
        pass
    return "未知"

def analyze_spine_json(json_path, original_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        bones_count = len(data.get("bones", []))
        animations_count = len(data.get("animations", {}))
        constraints_count = len(data.get("ik", [])) + len(data.get("transform", [])) + len(data.get("path", []))
        
        skel_w = data.get("skeleton", {}).get("width", 0)
        skel_h = data.get("skeleton", {}).get("height", 0)
        if skel_w == 0 or skel_h == 0:
            area_sqrt = "未設定"
        else:
            area_sqrt = int(math.sqrt(skel_w * skel_h))

        vertex_count = 0
        clipping_count = 0
        clipping_vertex_count = 0
        
        skins = data.get("skins", [])
        if isinstance(skins, list): 
            for skin in skins:
                attachments = skin.get("attachments", {})
                for slot_name, slot_attachments in attachments.items():
                    for attachment_name, attachment_data in slot_attachments.items():
                        if attachment_data.get("type") == "mesh":
                            uvs = attachment_data.get("uvs", [])
                            vertex_count += len(uvs) // 2
                        elif attachment_data.get("type") == "clipping":
                            clipping_count += 1
                            v_count = attachment_data.get("vertexCount", 0)
                            if v_count == 0 and "vertices" in attachment_data:
                                v_count = len(attachment_data["vertices"]) // 2
                            clipping_vertex_count += v_count

        deform_count = 0
        for anim_name, anim_data in data.get("animations", {}).items():
            for skin_name, skin_deforms in anim_data.get("deform", {}).items():
                for slot_name, slot_deforms in skin_deforms.items():
                    deform_count += len(slot_deforms)

        estimated_draw_calls = 1
        current_blend = "normal"
        for slot in data.get("slots", []):
            slot_blend = slot.get("blend", "normal")
            if slot_blend != current_blend:
                estimated_draw_calls += 1
                current_blend = slot_blend
                
        deps = get_texture_dependencies(original_path)

        return {
            "version": data.get("skeleton", {}).get("spine", "未知"),
            "bones": bones_count,
            "anims": animations_count,
            "verts": vertex_count,
            "deforms": deform_count,
            "clips": clipping_count,
            "clip_verts": clipping_vertex_count,
            "constraints": constraints_count,
            "drawcalls": estimated_draw_calls,
            "area_sqrt": area_sqrt,
            "deps": deps 
        }
    except Exception:
        return None

class SpineScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SPINE 效能檢測與 QC 工具")
        self.root.geometry("1400x650") 
        
        self.bg_color = "#F0F4F8"
        self.card_color = "#FFFFFF"
        self.text_color = "#2C3E50"
        self.root.configure(bg=self.bg_color)
        
        self.path_var = tk.StringVar()
        self.spine_path_var = tk.StringVar()
        self.spine_path_var.set(r"C:\Program Files\Spine\Spine.exe")
        
        self.setup_style()
        self.setup_ui()
        
    def setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("Primary.TButton", font=("微軟正黑體", 10, "bold"), background="#3498DB", foreground="white", padding=6)
        style.map("Primary.TButton", background=[("active", "#2980B9")])
        style.configure("Success.TButton", font=("微軟正黑體", 10, "bold"), background="#2ECC71", foreground="white", padding=6)
        style.map("Success.TButton", background=[("active", "#27AE60")])
        style.configure("Tool.TButton", font=("微軟正黑體", 9), background="#E0E6ED", foreground="#2C3E50", padding=4)
        style.map("Tool.TButton", background=[("active", "#BDC3C7")])
        
        style.configure("Card.TLabelframe", background=self.card_color, borderwidth=1, relief="solid")
        style.configure("Card.TLabelframe.Label", font=("微軟正黑體", 10, "bold"), background=self.card_color, foreground="#7F8C8D")
        style.configure("TFrame", background=self.bg_color)
        style.configure("CardFrame.TFrame", background=self.card_color)
        style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=("微軟正黑體", 10))
        
        style.configure("Treeview", font=("微軟正黑體", 9), rowheight=28, borderwidth=0, background=self.card_color)
        style.configure("Treeview.Heading", font=("微軟正黑體", 10, "bold"), background="#EAEDED", foreground=self.text_color, padding=5)
        style.map("Treeview", background=[("selected", "#D6EAF8")], foreground=[("selected", "#2C3E50")])

    def sort_treeview(self, col, reverse):
        """讓 Treeview 支援點擊標題進行排序，並聰明判斷數值與容量大小"""
        # 取得所有列的資料與 ID
        data_list = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]
        
        # 針對數值與容量欄位進行特殊轉換，避免單純的字串排序 (例如避免 9 > 12)
        def convert_for_sort(val):
            if val in ("-", "未知", "未設定", "") or "失敗" in str(val):
                return -1.0 # 錯誤或無資料的項目沉到底部
            try:
                # 處理容量轉換 (統一轉成數值比較)
                if "MB" in str(val):
                    return float(str(val).replace(" MB", "").replace(" (共用)", "")) * 1024
                elif "KB" in str(val):
                    return float(str(val).replace(" KB", "").replace(" (共用)", ""))
                # 一般數值 (如 DrawCall, 面數)
                return float(val)
            except ValueError:
                return str(val).lower() # 無法轉成數字就用原本的字串排
                
        # 執行排序
        data_list.sort(key=lambda item: convert_for_sort(item[0]), reverse=reverse)
        
        # 重新排列 Treeview 並更新底色 (斑馬紋)
        for index, (val, child) in enumerate(data_list):
            self.tree.move(child, '', index)
            # 保留失敗的紅底色，只重算正常行的斑馬紋
            current_tags = self.tree.item(child, 'tags')
            if 'failrow' not in current_tags:
                self.tree.item(child, tags=('evenrow' if index % 2 == 0 else 'oddrow',))
                
        # 切換下次點擊的反向排序
        self.tree.heading(col, command=lambda: self.sort_treeview(col, not reverse))

    def setup_ui(self):
        main_container = tk.Frame(self.root, bg=self.bg_color, padx=15, pady=15)
        main_container.pack(fill=tk.BOTH, expand=True)

        setting_frame = ttk.LabelFrame(main_container, text=" ⚙️ 系統設定 ", style="Card.TLabelframe", padding=(15, 10))
        setting_frame.pack(fill=tk.X, pady=(0, 15))
        
        inner_setting = tk.Frame(setting_frame, bg=self.card_color)
        inner_setting.pack(fill=tk.X)
        tk.Label(inner_setting, text="Spine 執行檔:", bg=self.card_color, fg=self.text_color, font=("微軟正黑體", 10)).pack(side=tk.LEFT)
        tk.Entry(inner_setting, textvariable=self.spine_path_var, width=60, relief="solid", bd=1).pack(side=tk.LEFT, padx=10, ipady=3)
        ttk.Button(inner_setting, text="指定路徑", style="Tool.TButton", command=self.browse_spine_exe).pack(side=tk.LEFT)

        action_frame = ttk.LabelFrame(main_container, text=" 📂 掃描目標 ", style="Card.TLabelframe", padding=(15, 15))
        action_frame.pack(fill=tk.X, pady=(0, 15))
        
        inner_action = tk.Frame(action_frame, bg=self.card_color)
        inner_action.pack(fill=tk.X)
        tk.Label(inner_action, text="專案資料夾:", bg=self.card_color, fg=self.text_color, font=("微軟正黑體", 10)).pack(side=tk.LEFT)
        tk.Entry(inner_action, textvariable=self.path_var, width=60, relief="solid", bd=1).pack(side=tk.LEFT, padx=10, ipady=3)
        ttk.Button(inner_action, text="瀏覽...", style="Tool.TButton", command=self.browse_folder).pack(side=tk.LEFT)
        
        self.scan_btn = ttk.Button(inner_action, text="🚀 開始掃描", style="Primary.TButton", command=self.start_scan_thread)
        self.scan_btn.pack(side=tk.LEFT, padx=(20, 10))
        self.export_btn = ttk.Button(inner_action, text="📥 匯出 CSV", style="Success.TButton", command=self.export_csv)
        self.export_btn.pack(side=tk.LEFT)

        summary_frame = tk.Frame(main_container, bg="#D4EFDF", pady=8, padx=15, relief="flat")
        summary_frame.pack(fill=tk.X, pady=(0, 10))
        self.total_size_var = tk.StringVar()
        self.total_size_var.set("📊 去重後總包圖真實容量: 0.00 MB (共 0 張圖)")
        tk.Label(summary_frame, textvariable=self.total_size_var, font=("微軟正黑體", 10, "bold"), bg="#D4EFDF", fg="#196F3D").pack(side=tk.LEFT)
        
        self.status_var = tk.StringVar()
        self.status_var.set("準備就緒。")
        tk.Label(summary_frame, textvariable=self.status_var, font=("微軟正黑體", 9), bg="#D4EFDF", fg="#145A32").pack(side=tk.RIGHT)

        table_frame = tk.Frame(main_container, bg=self.card_color, bd=1, relief="solid")
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("file", "version", "bones", "anims", "verts", "deforms", "clips", "drawcalls", "area_sqrt", "tex_count", "tex_dims", "tex_size")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", style="Treeview")
        
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        headers = [
            ("file", "檔案名稱", 160), ("version", "版本", 50), ("bones", "骨架", 40),
            ("anims", "動畫數量", 80), ("verts", "面數", 50), ("deforms", "點變形", 50), ("clips", "遮罩", 40),
            ("drawcalls", "預估 DrawCall", 90), ("area_sqrt", "面積平方根", 80),
            ("tex_count", "包圖數", 50), ("tex_dims", "圖集尺寸", 200), ("tex_size", "檔案容量", 100)
        ]
        
        for col, text, width in headers:
            # 綁定點擊排序功能
            self.tree.heading(col, text=text, command=lambda c=col: self.sort_treeview(c, True))
            anchor = tk.W if col in ("file", "tex_dims") else tk.CENTER
            self.tree.column(col, width=width, anchor=anchor)
            
        self.tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.tree.tag_configure('oddrow', background="#F9FBFD")
        self.tree.tag_configure('evenrow', background="#FFFFFF")
        self.tree.tag_configure('failrow', background="#FDEDEC", foreground="#C0392B")

    def browse_spine_exe(self):
        exe_selected = filedialog.askopenfilename(
            title="選擇 Spine 執行檔",
            filetypes=[("執行檔", "*.exe"), ("所有檔案", "*.*")]
        )
        if exe_selected:
            self.spine_path_var.set(exe_selected)

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.path_var.set(folder_selected)

    def export_csv(self):
        if not self.tree.get_children():
            messagebox.showinfo("提示", "目前沒有資料可以匯出，請先進行掃描！")
            return
            
        save_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 逗號分隔檔", "*.csv"), ("所有檔案", "*.*")],
            title="儲存報表",
            initialfile="Spine效能檢測報告.csv"
        )
        if not save_path:
            return  
            
        try:
            with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # 取得標題，並在最前面加上「檢測狀態」欄位
                headers = ["檢測狀態"] + [self.tree.heading(col)["text"] for col in self.tree["columns"]]
                writer.writerow(headers)
                
                for item in self.tree.get_children():
                    values = list(self.tree.item(item)['values'])
                    tags = self.tree.item(item, 'tags')
                    
                    # 透過 tag 判斷這行是成功還是失敗
                    status = "失敗" if 'failrow' in tags else "成功"
                    
                    # 將狀態加在第一欄寫入
                    writer.writerow([status] + values)
                    
            messagebox.showinfo("成功", f"報告已成功匯出至：\n{save_path}")
        except Exception as e:
            messagebox.showerror("錯誤", f"匯出失敗：\n{e}")

    def start_scan_thread(self):
        folder = self.path_var.get()
        spine_exe = self.spine_path_var.get()

        if not folder or not os.path.exists(folder):
            messagebox.showwarning("警告", "請選擇正確的目標資料夾路徑！")
            return
        if not os.path.exists(spine_exe) or not spine_exe.lower().endswith(".exe"):
            messagebox.showerror("錯誤", f"找不到 Spine 執行檔，請確認:\n{spine_exe}")
            return

        self.scan_btn.config(state=tk.DISABLED)
        self.status_var.set("掃描中，請稍候...")
        self.total_size_var.set("📊 計算中...")
        
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        threading.Thread(target=self.run_scan, args=(folder, spine_exe), daemon=True).start()

    def run_scan(self, folder, spine_exe):
        settings_path = create_export_settings()
        scan_results = []
        global_images = {} 
        
        for root_dir, _, files in os.walk(folder):
            for file in files:
                file_lower = file.lower()
                
                if file_lower.endswith(".skel") or file_lower.endswith(".skel.bytes"):
                    full_path = os.path.join(root_dir, file)
                    # 加入貼心提示，讓你知道如果是第一次掃到 4.0.64 正在下載
                    self.root.after(0, self.status_var.set, f"正在解析: {file} (若需下載核心可能較久)...")
                    
                    temp_json, real_version, temp_dir = skel_to_json_hidden(full_path, settings_path, spine_exe)
                    
                    stats = None
                    if temp_json:
                        stats = analyze_spine_json(temp_json, full_path)
                        if stats and real_version:
                            stats["version"] = real_version
                            
                    if temp_dir and os.path.exists(temp_dir):
                        try: shutil.rmtree(temp_dir, ignore_errors=True)
                        except: pass
                        
                    if stats:
                        self._process_stats(stats, file, scan_results, global_images)
                    else:
                        self._process_failed(file, real_version, scan_results)
                
                elif file_lower.endswith(".json") and not file_lower.startswith("spine_export_"):
                    full_path = os.path.join(root_dir, file)
                    self.root.after(0, self.status_var.set, f"正在解析: {file}...")
                    stats = analyze_spine_json(full_path, full_path)
                    
                    if stats:
                        self._process_stats(stats, file, scan_results, global_images)
                    else:
                        self._process_failed(file, "未知", scan_results)
        
        if os.path.exists(settings_path):
            try: os.remove(settings_path)
            except: pass
            
        image_usage_count = {}
        for res in scan_results:
            for img in res["deps"]:
                image_usage_count[img] = image_usage_count.get(img, 0) + 1
                
        total_unique_bytes = sum(global_images.values())
        self.root.after(0, lambda: self._render_final_results(scan_results, image_usage_count, total_unique_bytes, len(global_images)))

    def _process_stats(self, stats, file, scan_results, global_images):
        local_bytes = 0
        unique_deps = list(set(stats["deps"]))
        tex_count = len(unique_deps)
        
        dims_list = []
        for img in unique_deps:
            if img not in global_images:
                global_images[img] = os.path.getsize(img) if os.path.exists(img) else 0
            local_bytes += global_images[img]
            dim_str = get_image_size(img)
            dims_list.append(dim_str)
            
        if tex_count == 0:
            tex_str = "無圖集"
            dims_str = "-"
        else:
            kb = local_bytes / 1024
            tex_str = f"{kb/1024:.2f} MB" if kb > 1024 else f"{kb:.0f} KB"
            dims_str = f"{', '.join(dims_list)} ({tex_count}張)"
            
        scan_results.append({
            "is_success": True,
            "file": file,
            "stats": stats,
            "tex_count": tex_count,
            "dims_str": dims_str,
            "local_tex_str": tex_str,
            "deps": unique_deps
        })

    def _process_failed(self, file, skel_version, scan_results):
        scan_results.append({
            "is_success": False,
            "file": file,
            "stats": {
                "version": skel_version if skel_version else "無法辨識",
                "bones": "-", "anims": "-", "verts": "-",
                "deforms": "-", "clips": "-", "drawcalls": "-", "area_sqrt": "-"
            },
            "tex_count": "-",
            "dims_str": "Spine 轉檔失敗，請確認檔案或核心",
            "local_tex_str": "-",
            "deps": []
        })

    def _render_final_results(self, scan_results, image_usage_count, total_bytes, total_img_count):
        for index, res in enumerate(scan_results):
            s = res["stats"]
            
            if res["is_success"]:
                tex_str = res["local_tex_str"]
                dims_str = res["dims_str"]
                
                is_shared = False
                for img in res["deps"]:
                    if image_usage_count.get(img, 0) > 1:
                        is_shared = True
                        break
                        
                if is_shared and tex_str != "無圖集":
                    tex_str += " (共用)"
                    dims_str += " (共用)" 
                    
                row_tag = 'evenrow' if index % 2 == 0 else 'oddrow'
                self.tree.insert("", tk.END, values=(
                    res["file"], s["version"], s["bones"], s["anims"], s["verts"], 
                    s["deforms"], s["clips"], s["drawcalls"], s["area_sqrt"], 
                    res["tex_count"], dims_str, tex_str
                ), tags=(row_tag,))
            else:
                self.tree.insert("", tk.END, values=(
                    res["file"], s["version"], s["bones"], s["anims"], s["verts"], 
                    s["deforms"], s["clips"], s["drawcalls"], s["area_sqrt"], 
                    res["tex_count"], res["dims_str"], res["local_tex_str"]
                ), tags=('failrow',))
            
        total_mb = total_bytes / (1024 * 1024)
        self.total_size_var.set(f"📊 去重後總包圖真實容量: {total_mb:.2f} MB (共 {total_img_count} 張圖)")
        self.status_var.set(f"完成！共處理 {len(scan_results)} 個檔案")
        self.scan_btn.config(state=tk.NORMAL)

if __name__ == "__main__":
    root = tk.Tk()
    app = SpineScannerApp(root)
    root.mainloop()