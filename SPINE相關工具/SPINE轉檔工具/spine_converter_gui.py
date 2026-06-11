import os
import subprocess
import json
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

class SpineConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Spine 雙向管線轉檔工具 (終極黃金管線 - 緊湊介面版)")
        # 視窗高度大幅縮減至 680
        self.root.geometry("760x680")
        
        # --- UI 顏色與字型設定 (Dark Theme) ---
        self.bg_base = "#1E1E1E"
        self.bg_panel = "#252526"
        self.bg_entry = "#3E3E42"
        self.fg_main = "#E0E0E0"
        self.fg_accent = "#4DAAFB"
        self.fg_sub = "#A0A0A0"
        self.btn_bg = "#333337"
        self.btn_fg = "#E0E0E0"
        self.btn_run_bg = "#0E639C"
        self.btn_run_fg = "#FFFFFF"

        self.font_title = ("Microsoft JhengHei UI", 11, "bold") # 稍微調小標題
        self.font_main = ("Microsoft JhengHei UI", 10, "bold")
        self.font_sub = ("Microsoft JhengHei UI", 9)
        self.font_log = ("Consolas", 9)

        self.root.configure(bg=self.bg_base)
        self.default_spine_path = r"C:\Program Files\Spine\Spine.exe"
        
        self.create_widgets()

    def style_frame(self, parent, text):
        # 縮減 LabelFrame 的內外留白
        frame = tk.LabelFrame(parent, text=text, padx=10, pady=5, 
                              bg=self.bg_panel, fg=self.fg_accent, 
                              font=self.font_title, bd=1, relief="solid", highlightbackground="#333333")
        frame.pack(fill="x", padx=15, pady=4)
        return frame

    def style_button(self, parent, text, command):
        btn = tk.Button(parent, text=text, command=command, 
                        bg=self.btn_bg, fg=self.btn_fg, font=self.font_sub,
                        relief="flat", activebackground="#404040", activeforeground="#FFFFFF",
                        cursor="hand2", padx=8, pady=0)
        return btn

    def style_entry(self, parent, text_var, width=60):
        entry = tk.Entry(parent, textvariable=text_var, width=width, 
                         bg=self.bg_entry, fg=self.fg_main, font=self.font_sub,
                         insertbackground=self.fg_main, relief="flat")
        return entry

    def create_widgets(self):
        # ==================== 作業模式選擇區 ====================
        frame_mode = self.style_frame(self.root, " 作業模式選擇 (黃金安全管線) ")

        self.var_mode = tk.StringVar(value="upgrade")
        # 大幅縮減選項間的 pady
        rb_up = tk.Radiobutton(frame_mode, text="⬆️ 升級 (3.8 轉 4.0) ─ 引擎直出遊戲包，無損升級製作檔 (安全)", 
                               variable=self.var_mode, value="upgrade",
                               bg=self.bg_panel, fg=self.fg_main, font=self.font_main, 
                               selectcolor=self.bg_base, activebackground=self.bg_panel, activeforeground=self.fg_accent)
        rb_up.pack(anchor="w", pady=1)

        rb_same = tk.Radiobutton(frame_mode, text="🔄 同版 (3.8 維持 3.8) ─ 引擎直出遊戲包，物理複製製作檔 (100% 完美動畫)", 
                                 variable=self.var_mode, value="same_v3",
                                 bg=self.bg_panel, fg="#B5CEA8", font=self.font_main, 
                                 selectcolor=self.bg_base, activebackground=self.bg_panel, activeforeground=self.fg_accent)
        rb_same.pack(anchor="w", pady=1)

        rb_down = tk.Radiobutton(frame_mode, text="⬇️ 降級 (4.0 轉 3.8) ─ 透過 JSON 降級 (⚠️ 官方引擎限制：遺失路徑與變形)", 
                                 variable=self.var_mode, value="downgrade",
                                 bg=self.bg_panel, fg="#F44747", font=self.font_main, 
                                 selectcolor=self.bg_base, activebackground=self.bg_panel, activeforeground=self.fg_accent)
        rb_down.pack(anchor="w", pady=1)

        # ==================== 路徑設定區 ====================
        frame_paths = self.style_frame(self.root, " 專案路徑設定 ")

        tk.Label(frame_paths, text="Spine 執行檔:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=0, column=0, sticky="w", pady=3)
        self.var_spine_exe = tk.StringVar(value=self.default_spine_path)
        self.style_entry(frame_paths, self.var_spine_exe).grid(row=0, column=1, padx=5, ipady=2)
        self.style_button(frame_paths, "瀏覽...", self.browse_spine_exe).grid(row=0, column=2)

        tk.Label(frame_paths, text="輸入資料夾:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=1, column=0, sticky="w", pady=3)
        self.var_input_dir = tk.StringVar()
        self.style_entry(frame_paths, self.var_input_dir).grid(row=1, column=1, padx=5, ipady=2)
        self.style_button(frame_paths, "瀏覽...", self.browse_input_dir).grid(row=1, column=2)

        tk.Label(frame_paths, text="輸出資料夾:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=2, column=0, sticky="w", pady=3)
        self.var_output_dir = tk.StringVar()
        self.style_entry(frame_paths, self.var_output_dir).grid(row=2, column=1, padx=5, ipady=2)
        self.style_button(frame_paths, "瀏覽...", self.browse_output_dir).grid(row=2, column=2)

        # ==================== 參數設定區 ====================
        frame_params = self.style_frame(self.root, " 版本與遊戲包縮放設定 (引擎處理) ")

        tk.Label(frame_params, text="Spine 4.0 版號:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=0, column=0, sticky="w", pady=2)
        self.var_ver_4 = tk.StringVar(value="4.0.56")
        self.style_entry(frame_params, self.var_ver_4, width=15).grid(row=0, column=1, sticky="w", padx=5, ipady=2)

        tk.Label(frame_params, text="Spine 3.8 版號:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=0, column=2, sticky="w", padx=(20, 0), pady=2)
        self.var_ver_3 = tk.StringVar(value="3.8.99")
        self.style_entry(frame_params, self.var_ver_3, width=15).grid(row=0, column=3, sticky="w", padx=5, ipady=2)

        tk.Label(frame_params, text="遊戲包 (.skel) 倍率:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=1, column=0, sticky="w", pady=(6, 2))
        self.var_skel_scale = tk.DoubleVar(value=1.5)
        self.style_entry(frame_params, self.var_skel_scale, width=15).grid(row=1, column=1, sticky="w", padx=5, ipady=2, pady=(6, 2))

        tk.Label(frame_params, text="圖片打包倍率:", bg=self.bg_panel, fg=self.fg_sub, font=self.font_sub).grid(row=1, column=2, sticky="w", padx=(20, 0), pady=(6, 2))
        self.var_atlas_scale = tk.DoubleVar(value=1.0)
        self.style_entry(frame_params, self.var_atlas_scale, width=15).grid(row=1, column=3, sticky="w", padx=5, ipady=2, pady=(6, 2))

        # ==================== 管線轉移選項區 ====================
        frame_adv = self.style_frame(self.root, " 專案檔保護與備份 ")

        self.var_copy_images = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_adv, text="同步複製原圖資料夾 (完美保留相對路徑，開啟不缺圖)", variable=self.var_copy_images,
                       bg=self.bg_panel, fg=self.fg_main, font=self.font_sub, selectcolor=self.bg_base, activebackground=self.bg_panel, activeforeground=self.fg_main).pack(anchor="w", pady=1)

        self.var_save_project = tk.BooleanVar(value=True)
        tk.Checkbutton(frame_adv, text="保留對應版本的 .spine 製作檔 (✔ 嚴格鎖定 1.0 比例，保護所有約束與動畫)", variable=self.var_save_project,
                       bg=self.bg_panel, fg=self.fg_main, font=self.font_sub, selectcolor=self.bg_base, activebackground=self.bg_panel, activeforeground=self.fg_main).pack(anchor="w", pady=1)

        # ==================== 執行按鈕 ====================
        self.btn_run = tk.Button(self.root, text="開始執行管線", command=self.start_processing, 
                                 bg=self.btn_run_bg, fg=self.btn_run_fg, font=("Microsoft JhengHei UI", 12, "bold"),
                                 relief="flat", activebackground="#1177BB", activeforeground="#FFFFFF", cursor="hand2", pady=5)
        self.btn_run.pack(fill="x", padx=15, pady=8)

        # ==================== 日誌輸出區 ====================
        tk.Label(self.root, text="處理進度日誌:", bg=self.bg_base, fg=self.fg_sub, font=self.font_sub).pack(anchor="w", padx=20, pady=(0, 2))
        self.log_area = scrolledtext.ScrolledText(self.root, height=10, state='disabled', 
                                                  bg=self.bg_panel, fg="#4EC9B0", font=self.font_log, bd=0, padx=10, pady=5)
        self.log_area.pack(fill="both", expand=True, padx=15, pady=(0, 10))

    def browse_spine_exe(self):
        filepath = filedialog.askopenfilename(title="選擇 Spine.exe", filetypes=[("Executable", "*.exe")])
        if filepath: self.var_spine_exe.set(filepath)

    def browse_input_dir(self):
        dirpath = filedialog.askdirectory(title="選擇輸入根目錄")
        if dirpath: self.var_input_dir.set(dirpath)

    def browse_output_dir(self):
        dirpath = filedialog.askdirectory(title="選擇輸出根目錄")
        if dirpath: self.var_output_dir.set(dirpath)

    def log(self, message):
        self.log_area.config(state='normal')
        if not hasattr(self, "log_tags_configured"):
            self.log_area.tag_config("error", foreground="#F44747")
            self.log_area.tag_config("success", foreground="#B5CEA8")
            self.log_area.tag_config("warn", foreground="#D7BA7D")
            self.log_area.tag_config("highlight", foreground="#4DAAFB")
            self.log_area.tag_config("normal", foreground="#D4D4D4")
            self.log_tags_configured = True

        tag = "normal"
        if "❌" in message: tag = "error"
        elif "✅" in message or "🎉" in message: tag = "success"
        elif "⚠️" in message: tag = "warn"
        elif "✨" in message or "🔧" in message or "🔄" in message: tag = "highlight"

        self.log_area.insert(tk.END, message + "\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.root.update_idletasks()

    def start_processing(self):
        if not os.path.exists(self.var_spine_exe.get()) or not self.var_input_dir.get() or not self.var_output_dir.get():
            messagebox.showerror("錯誤", "請確認路徑皆已填寫正確。")
            return

        self.btn_run.config(state="disabled", text="處理中，請稍候...", bg="#555555")
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        
        mode = self.var_mode.get()
        mode_str = "升級 (3.8 -> 4.0)" if mode == "upgrade" else "降級 (4.0 -> 3.8)" if mode == "downgrade" else "同版本 (3.8 -> 3.8)"
        self.log(f"🚀 開始執行黃金管線... [當前模式: {mode_str}]")
        threading.Thread(target=self.run_conversion, daemon=True).start()

    def create_dynamic_binary_settings(self, is_up, target_scale, atlas_scale, temp_dir, project_name):
        settings = {
            "class": "export-binary", "format": "Binary", "scale": target_scale,
            "extension": ".skel.bytes" if is_up else ".skel",
            "packAtlas": {
                "atlasName": project_name,
                "scale": [atlas_scale], "maxWidth": 2048, "maxHeight": 2048,
                "pot": is_up, "square": is_up, 
                "atlasExtension": ".atlas.txt" if is_up else ".atlas",
                "premultiplyAlpha": is_up, 
                "bleed": not is_up, "duplicatePadding": not is_up,
                "filterMin": "Linear", "filterMag": "Linear", "format": "RGBA8888", "ignoreBlankImages": True
            }
        }
        path = os.path.join(temp_dir, f"bin_settings_{project_name}.json")
        with open(path, "w", encoding="utf-8") as f: json.dump(settings, f, indent=4)
        return path

    def create_json_settings(self, version, temp_dir):
        settings = {"class": "export-json", "extension": ".json", "format": "JSON", "nonessential": True}
        if version: settings["version"] = version
        path = os.path.join(temp_dir, f"export_json_down.json")
        with open(path, "w", encoding="utf-8") as f: json.dump(settings, f, indent=4)
        return path

    def fix_atlas_naming(self, output_dir, project_name, is_up):
        atlas_ext = ".atlas.txt" if is_up else ".atlas"
        atlas_files = [f for f in os.listdir(output_dir) if f.endswith(atlas_ext)]
        
        for atlas_file in atlas_files:
            if atlas_file == f"{project_name}{atlas_ext}": continue 
            
            old_atlas_path = os.path.join(output_dir, atlas_file)
            new_atlas_path = os.path.join(output_dir, f"{project_name}{atlas_ext}")
            
            try:
                with open(old_atlas_path, 'r', encoding='utf-8') as f: lines = f.readlines()
                if not lines: continue
                
                png_idx = next((i for i, line in enumerate(lines) if line.strip().endswith('.png')), -1)
                        
                if png_idx != -1:
                    old_img_name = lines[png_idx].strip()
                    new_img_name = f"{project_name}.png"
                    lines[png_idx] = new_img_name + "\n"
                    
                    old_img_path = os.path.join(output_dir, old_img_name)
                    new_img_path = os.path.join(output_dir, new_img_name)
                    if os.path.exists(old_img_path) and old_img_path != new_img_path:
                        if os.path.exists(new_img_path): os.remove(new_img_path)
                        os.rename(old_img_path, new_img_path)
                        
                with open(old_atlas_path, 'w', encoding='utf-8') as f: f.writelines(lines)
                    
                if os.path.exists(new_atlas_path): os.remove(new_atlas_path)
                os.rename(old_atlas_path, new_atlas_path)
                self.log(f"  ├─ 🔧 強制修復圖集檔名為: {project_name}{atlas_ext}")
            except Exception:
                pass

    def modify_json_image_path(self, json_path, new_image_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f: data = json.load(f)
            if 'skeleton' in data: data['skeleton']['images'] = new_image_path.replace("\\", "/")
            with open(json_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
        except Exception: pass

    def run_conversion(self):
        spine_exe = self.var_spine_exe.get()
        input_dir = self.var_input_dir.get()
        output_dir = self.var_output_dir.get()
        mode = self.var_mode.get()
        
        v4 = self.var_ver_4.get()
        v3 = self.var_ver_3.get()
        skel_scale = self.var_skel_scale.get()
        atlas_scale = self.var_atlas_scale.get()

        temp_dir = os.path.join(output_dir, ".spine_temp_worker")
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)

        spine_files_info = []
        for root, dirs, files in os.walk(input_dir):
            for file in files:
                if file.endswith('.spine'):
                    spine_files_info.append({
                        "filename": file, "input_path": os.path.abspath(os.path.join(root, file)),
                        "rel_path": os.path.relpath(root, input_dir), "root": root
                    })

        if not spine_files_info:
            self.log("⚠️ 輸入資料夾中沒有找到 .spine 檔案。")
            self.finish_processing(temp_dir)
            return

        self.log(f"📁 共找到 {len(spine_files_info)} 個專案，開始管線轉換...\n" + "="*50)

        for file_info in spine_files_info:
            filename = file_info["filename"]
            input_path = file_info["input_path"]
            rel_path = file_info["rel_path"]
            src_root = file_info["root"]
            project_name = os.path.splitext(filename)[0]

            project_output = os.path.abspath(os.path.join(output_dir, rel_path, project_name)) if rel_path != '.' else os.path.abspath(os.path.join(output_dir, project_name))
            display_path = os.path.join(rel_path, filename) if rel_path != '.' else filename
            if not os.path.exists(project_output): os.makedirs(project_output)

            self.log(f"📍 目標: {display_path}")

            target_images_folder = os.path.join(project_output, "images")
            if self.var_copy_images.get():
                for dir_name in os.listdir(src_root):
                    src_dir = os.path.join(src_root, dir_name)
                    if os.path.isdir(src_dir) and dir_name.lower() in ['images', 'image', 'textures', 'texture', 'tex']:
                        try:
                            shutil.copytree(src_dir, os.path.join(project_output, dir_name), dirs_exist_ok=True)
                            self.log(f"  ├─ 📁 複製原圖資料夾: {dir_name}/")
                        except Exception: pass

            try:
                target_spine_path = os.path.join(project_output, filename)
                is_up = (mode == "upgrade")

                bin_set = self.create_dynamic_binary_settings(is_up, skel_scale, atlas_scale, temp_dir, project_name)

                if mode == "upgrade":
                    subprocess.run([spine_exe, "-u", v4, "-i", input_path, "-o", project_output, "-e", bin_set], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
                    self.log(f"  ├─ ✅ 匯出 {v4} 遊戲包 (由引擎精準縮放 {skel_scale}x，保護約束與網格)")
                    self.fix_atlas_naming(project_output, project_name, True)
                    
                    if self.var_save_project.get():
                        if os.path.exists(target_spine_path): os.remove(target_spine_path)
                        subprocess.run([spine_exe, "-u", v4, "-i", input_path, "-o", target_spine_path, "-r"], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
                        self.log(f"  ├─ ✨ 儲存 {v4} 製作檔 (維持 1.0 原始比例，100% 完美動畫無損)")

                elif mode == "same_v3":
                    subprocess.run([spine_exe, "-u", v3, "-i", input_path, "-o", project_output, "-e", bin_set], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
                    self.log(f"  ├─ ✅ 匯出 {v3} 同版本遊戲包 (由引擎精準縮放 {skel_scale}x)")
                    self.fix_atlas_naming(project_output, project_name, False)

                    if self.var_save_project.get():
                        shutil.copy2(input_path, target_spine_path)
                        self.log(f"  ├─ 🔄 物理複製 {v3} 製作檔 (絕無 JSON 破壞，100% 完美)")

                elif mode == "downgrade":
                    temp_json_out = os.path.join(temp_dir, project_name)
                    os.makedirs(temp_json_out, exist_ok=True)
                    json_set_downgrade = self.create_json_settings("3.8", temp_dir)
                    
                    subprocess.run([spine_exe, "-u", v4, "-i", input_path, "-o", temp_json_out, "-e", json_set_downgrade], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
                    json_files = [f for f in os.listdir(temp_json_out) if f.endswith('.json')]
                    if not json_files: raise Exception("Spine 未成功產出 3.8 JSON")
                    temp_json_path = os.path.join(temp_json_out, json_files[0])

                    abs_img_path = os.path.join(project_output, "images")
                    self.modify_json_image_path(temp_json_path, abs_img_path)
                    
                    subprocess.run([spine_exe, "-u", v3, "-i", temp_json_path, "-o", project_output, "-e", bin_set], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
                    self.log(f"  ├─ ✅ 匯出 {v3} 遊戲包 (縮放 {skel_scale}x)")
                    self.fix_atlas_naming(project_output, project_name, False)

                    if self.var_save_project.get():
                        self.modify_json_image_path(temp_json_path, "./images/")
                        if os.path.exists(target_spine_path): os.remove(target_spine_path)
                        subprocess.run([spine_exe, "-u", v3, "-i", temp_json_path, "-o", target_spine_path, "-r"], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
                        self.log(f"  ├─ ⚠️ 儲存降級製作檔 (官方引擎限制，會遺失路徑約束與變形動畫)")

            except subprocess.CalledProcessError as e:
                self.log("  ├─ ❌ 處理失敗")
                if e.output:
                    for line in e.output.splitlines()[-5:]:
                        if line.strip(): self.log(f"      > {line.strip()}")
            except Exception as e:
                self.log(f"  ├─ ❌ 系統錯誤: {e}")

            self.log("-" * 50)

        self.log("\n🎉 所有任務執行完畢！")
        self.finish_processing(temp_dir)

    def finish_processing(self, temp_dir):
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        self.btn_run.config(state="normal", text="開始執行管線", bg=self.btn_run_bg)
        messagebox.showinfo("完成", "批次處理已全部結束。")

if __name__ == "__main__":
    root = tk.Tk()
    app = SpineConverterApp(root)
    root.mainloop()