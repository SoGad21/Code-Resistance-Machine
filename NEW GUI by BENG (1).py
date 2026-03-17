import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import time
import csv
import os
import sys
import subprocess
import json
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from threading import Thread

# --- ตั้งค่า Theme ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# ฟอนต์
FONT_HEADER = ("Prompt", 20, "bold")
FONT_LABEL = ("Prompt", 12)
FONT_VALUE = ("Prompt", 48, "bold")
FONT_UNIT = ("Prompt", 16)

# สี
COLOR_BG = "#1a1a1a"
COLOR_CARD = "#2b2b2b"
COLOR_ACCENT = "#3498db"
COLOR_SUCCESS = "#27ae60" # สีเขียว (Force)
COLOR_DANGER = "#c0392b"
COLOR_TEXT = "#ecf0f1"
COLOR_COF = "#e74c3c"     # สีส้มแดง (COF)

class IndustrialTesterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Shoe Friction Tester - Engineering Edition")
        self.after(1500, lambda: self.state('zoomed')) 
        
        # ตัวแปรระบบ
        self.ser = None
        self.is_running = False
        self.data_time = []
        self.data_force = []
        self.data_cof = [] 
        self.start_timestamp = 0
        self.current_load_n = 1.0 
        
        # --- [เพิ่มใหม่] ตัวแปรเก็บค่า Settings พื้นฐาน ---
        self.setting_motor_speed = 220      
        self.setting_test_duration = 3.5    
        self.setting_cal_factor = 2.94
        
        self.base_folder = os.path.join(os.path.expanduser("~"), "Desktop", "FrictionTest_Database")
        if not os.path.exists(self.base_folder): os.makedirs(self.base_folder)

        self.config_file = os.path.join(self.base_folder, "system_config.json")
        self.load_settings()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.create_header()
        self.create_main_workspace()

        self.serial_thread = Thread(target=self.serial_loop, daemon=True)
        self.serial_thread.start()

    def create_header(self):
        self.header = ctk.CTkFrame(self, height=60, corner_radius=0, fg_color="#000000")
        self.header.grid(row=0, column=0, sticky="ew")
        
        title_lbl = ctk.CTkLabel(self.header, text="FRICTION LAB | ENGINEERING WORKSTATION", 
                                 font=("Prompt", 18, "bold"), text_color=COLOR_TEXT)
        title_lbl.pack(side="left", padx=20, pady=15)

        self.status_indicator = ctk.CTkButton(self.header, text="DISCONNECTED", 
                                              fg_color="#555555", hover=False, width=200, corner_radius=5)
        self.status_indicator.pack(side="right", padx=20, pady=10)

    def create_main_workspace(self):
        # 1. แก้ไขให้เป็น frame โค้งมนคลุมพื้นที่ด้านล่าง Header ทั้งหมด
        self.main_container = ctk.CTkFrame(self, corner_radius=10, fg_color=COLOR_BG)
        self.main_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        # 2. สร้างแถบแท็บ (Tab Bar) สำหรับวางปุ่มเลียนแบบ
        self.tab_bar = ctk.CTkFrame(self.main_container, height=50, fg_color="#1a1a1a", corner_radius=0)
        self.tab_bar.grid(row=0, column=0, sticky="ew")
        
        # (ลบคำสั่ง grid_columnconfigure เดิมทิ้งไป เพื่อไม่ให้มันดึงไปตรงกลาง)

        # สีสำหรับปุ่มแท็บ (ปรับเพื่อเน้นความโค้งมน)
        color_tab_selected = COLOR_ACCENT
        color_tab_unselected = "#262626"

        # 3. สร้างปุ่มแท็บเลียนแบบ (ใช้ .pack(side="left") เพื่อจัดให้ชิดซ้ายเรียงกัน)
        # ปุ่ม 📊 LIVE TEST
        self.btn_tab_live = ctk.CTkButton(self.tab_bar, text="📊 LIVE TEST", 
                                          font=("Prompt", 14, "bold"), text_color="#ecf0f1",
                                          fg_color=color_tab_selected, hover_color=COLOR_ACCENT,
                                          height=40, corner_radius=20, 
                                          command=lambda: self.select_tab("live"))
        # เปลี่ยนมาใช้ pack และเพิ่มระยะห่างจากขอบซ้าย (padx=20)
        self.btn_tab_live.pack(side="left", padx=(20, 5), pady=5)

        # ปุ่ม ⚙️ SYSTEM SETTINGS
        self.btn_tab_settings = ctk.CTkButton(self.tab_bar, text="⚙️ SYSTEM SETTINGS", 
                                              font=("Prompt", 14, "bold"), text_color="#ecf0f1",
                                              fg_color=color_tab_unselected, hover_color=COLOR_ACCENT,
                                              height=40, corner_radius=20, 
                                              command=lambda: self.select_tab("settings"))
        # ใช้ pack วางต่อจากปุ่มแรก
        self.btn_tab_settings.pack(side="left", padx=(5, 10), pady=5)

        # 4. สร้างพื้นที่เนื้อหาโค้งมน (Content Frames) ที่วางซ้อนกัน
        self.content_area = ctk.CTkFrame(self.main_container, fg_color=COLOR_BG, corner_radius=10)
        self.content_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(10, 0))
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(0, weight=1)

        # frame เนื้อหา 📊 LIVE TEST
        self.frame_live = ctk.CTkFrame(self.content_area, corner_radius=10, fg_color=COLOR_BG)
        # สร้างเนื้อหา Live Test ใน frame เฉพาะ
        self.build_live_test_content(self.frame_live)

        # frame เนื้อหา ⚙️ SYSTEM SETTINGS
        self.frame_settings = ctk.CTkFrame(self.content_area, corner_radius=10, fg_color=COLOR_BG)
        # สร้างเนื้อหา Settings ใน frame เฉพาะ
        self.build_settings_content(self.frame_settings)

        # เริ่มต้นแสดงแท็บแรก
        self.select_tab("live")

        

    def create_sidebar_group(self, title, row_idx):
        container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        container.pack(fill="x", padx=15, pady=15)
        ctk.CTkLabel(container, text=title, font=("Prompt", 10, "bold"), text_color="gray").pack(anchor="w")
        self.sidebar_group = ctk.CTkFrame(container, fg_color="#333333", corner_radius=5)
        self.sidebar_group.pack(fill="x", pady=5)

    def setup_graph(self):
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.fig.patch.set_facecolor(COLOR_CARD)
        
        self.ax = self.fig.add_subplot(111)
        self.ax2 = self.ax.twinx()
        
        self.ax.set_facecolor('#1e1e1e')
        
        # --- [จุดที่แก้] ล็อคสเกลแกน Y ให้คงที่ ---
        self.ax.set_ylim(0, 200)    # แกนแรง: 0 ถึง 600 นิวตัน
        self.ax2.set_ylim(0, 1.2)   # แกน COF: 0 ถึง 1.2
        # ------------------------------------

        # (ส่วนตั้งค่าสีและ Label เหมือนเดิม...)
        for spine in self.ax.spines.values(): spine.set_color('#555555')
        self.ax2.spines['top'].set_color('#555555')
        self.ax2.spines['bottom'].set_color('#555555')
        self.ax2.spines['left'].set_color('#555555')
        self.ax2.spines['right'].set_color('#555555')

        self.ax.set_xlabel("TIME (s)", fontname="Prompt", fontsize=10, color='#aaaaaa')
        self.ax.set_ylabel("FORCE (N)", fontname="Prompt", fontsize=10, color=COLOR_SUCCESS)
        self.ax2.set_ylabel("COEFFICIENT (µ)", fontname="Prompt", fontsize=10, color=COLOR_COF)

        self.ax.tick_params(axis='y', colors=COLOR_SUCCESS, labelsize=9)
        self.ax.tick_params(axis='x', colors='#aaaaaa', labelsize=9)
        self.ax2.tick_params(axis='y', colors=COLOR_COF, labelsize=9)

        self.ax.grid(True, color='#333333', linestyle='-', linewidth=0.5)

        self.line_force, = self.ax.plot([], [], color=COLOR_SUCCESS, linewidth=1.5, label="Force")
        self.line_cof, = self.ax2.plot([], [], color=COLOR_COF, linewidth=1.5, linestyle='--', label="COF")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_container)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=2, pady=2)

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        if ports:
            self.port_combo.configure(values=ports)
            self.port_combo.set(ports[0])
        else:
            self.port_combo.configure(values=["No Ports"])

    def toggle_connection(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.btn_connect.configure(text="CONNECT", fg_color=COLOR_ACCENT)
            self.status_indicator.configure(text="DISCONNECTED", fg_color="#555555")
            self.btn_start.configure(state="disabled")
        else:
            try:
                port = self.port_combo.get()
                self.ser = serial.Serial(port, 57600, timeout=1)
                time.sleep(2)
                self.btn_connect.configure(text="DISCONNECT", fg_color="#7f8c8d")
                self.status_indicator.configure(text=f"ONLINE : {port}", fg_color=COLOR_SUCCESS)
                self.btn_start.configure(state="normal")
            except Exception as e:
                tk.messagebox.showerror("Connection Error", str(e))

    def serial_loop(self):
        while True:
            if self.ser and self.ser.is_open and self.ser.in_waiting:
                try:
                    line = self.ser.readline().decode('utf-8').strip()
                    
                    if line.startswith("PREVIEW:"):
                        val = abs(float(line.split(":")[1])) * 0.00981
                        cof = val / self.current_load_n if self.current_load_n > 0 else 0
                        self.after(0, lambda v=val, c=cof: self.update_readout(v, c))
                        
                    elif line.startswith("DATA:"):
                        val = abs(float(line.split(":")[1])) * 0.00981
                        cof = val / self.current_load_n if self.current_load_n > 0 else 0
                        
                        if self.start_timestamp == 0: self.start_timestamp = time.time()
                        current_t = time.time() - self.start_timestamp
                        
                        self.data_time.append(current_t)
                        self.data_force.append(val)
                        self.data_cof.append(cof) # เก็บค่า COF
                        
                        self.after(0, self.update_plot)
                        self.after(0, lambda v=val, c=cof: self.update_readout(v, c))
                        
                    elif line == "STATUS:FINISHED":
                        self.after(0, self.finish_test)
                except: pass
            time.sleep(0.01)

    def update_readout(self, force, cof):
        self.lbl_force.configure(text=f"{force:.2f}")
        self.lbl_cof.configure(text=f"{cof:.3f}")

    def update_plot(self):
        # อัพเดตข้อมูล
        self.line_force.set_data(self.data_time, self.data_force)
        self.line_cof.set_data(self.data_time, self.data_cof)
        
        # ปรับเฉพาะแกน X (เวลา) ให้เลื่อนตามข้อมูล
        self.ax.set_xlim(left=0, right=max(10, self.data_time[-1] + 1 if self.data_time else 10))
        self.ax2.set_xlim(left=0, right=max(10, self.data_time[-1] + 1 if self.data_time else 10))
        
        self.canvas.draw()

    def start_test(self):
        brand_name = self.entry_brand.get().strip()
        if not brand_name:
            tk.messagebox.showwarning("System Alert", "Please input 'Shoe Model' before testing.")
            return
            
        try:
            mass_kg = float(self.entry_load.get())
            if mass_kg <= 0: raise ValueError
            self.current_load_n = mass_kg * 9.81
        except ValueError:
            tk.messagebox.showerror("Error", "Invalid Normal Load! Please enter a valid number (kg).")
            return

        # 1. ล้างข้อมูลเก่า
        self.data_time = []
        self.data_force = []
        self.data_cof = [] # ล้าง COF ด้วย
        self.start_timestamp = 0

        # รีเซ็ตตัวเลขแผงผลลัพธ์ขวามือให้เป็นขีดๆ
        self.lbl_res_max_force.configure(text="--.--", text_color="#ecf0f1")
        self.lbl_res_static_cof.configure(text="--.--", text_color="#ecf0f1")
        self.lbl_res_avg_cof.configure(text="--.--", text_color="#ecf0f1")
        
        # 2. รีเซ็ตกราฟ (ต้องเคลียร์ทั้ง 2 แกน)
        self.ax.cla()
        self.ax2.cla()

        self.ax2.yaxis.tick_right()              # บังคับตัวเลขให้ไปอยู่ขวา
        self.ax2.yaxis.set_label_position("right") # บังคับชื่อแกนให้ไปอยู่ขวา

        # --- [เพิ่มใหม่] ตั้งค่าล็อคสเกลอีกครั้งหลังจากเคลียร์ ---
        self.ax.set_xlim(0, 5)     # <--- เริ่มต้นแกนเวลาที่ 5 วินาที
        self.ax2.set_xlim(0, 5)
        self.ax.set_ylim(0, 200)
        self.ax2.set_ylim(0, 1.2)
        # -----------------------------------------------
        
        # Setup พื้นฐานใหม่หลังจากเคลียร์
        self.ax.set_facecolor('#1e1e1e')
        self.ax.grid(True, color='#333333', linestyle='-', linewidth=0.5)
        self.ax.set_title(f"LIVE TEST: {brand_name}", color='#aaaaaa', fontsize=10)
        
        self.ax.set_ylabel("FORCE (N)", color=COLOR_SUCCESS)
        self.ax2.set_ylabel("COEFFICIENT (µ)", color=COLOR_COF)
        self.ax.tick_params(axis='y', colors=COLOR_SUCCESS)
        self.ax2.tick_params(axis='y', colors=COLOR_COF)
        self.ax.tick_params(axis='x', colors='#aaaaaa')
        
        # สร้างเส้นเปล่ารอข้อมูลใหม่
        self.line_force, = self.ax.plot([], [], color=COLOR_SUCCESS, linewidth=1.5, label="Force")
        self.line_cof, = self.ax2.plot([], [], color=COLOR_COF, linewidth=1.5, linestyle='--', label="COF")
        
        self.canvas.draw() 

        # 3. ส่งคำสั่ง
        if self.ser: 
            self.ser.reset_input_buffer()
            self.ser.write(b'S')
            
        self.is_running = True
        self.btn_start.configure(state="disabled", text="TESTING IN PROGRESS...", fg_color="#f39c12")
        self.entry_brand.configure(state="disabled")
        self.entry_load.configure(state="disabled")
        self.status_indicator.configure(text="STATUS : RUNNING", fg_color="#f39c12")

    def stop_test(self):
        if self.ser: self.ser.write(b'X')
        self.is_running = False
        self.btn_start.configure(state="normal", text="START TEST", fg_color=COLOR_SUCCESS)
        self.entry_brand.configure(state="normal")
        self.entry_load.configure(state="normal")
        self.status_indicator.configure(text="STATUS : STOPPED", fg_color=COLOR_DANGER)

    # --- ฟังก์ชันเปิดหน้าต่าง Manual Control ---
    def open_manual_control_window(self):
        # เช็คว่าเปิดค้างอยู่แล้วหรือไม่ ถ้าเปิดอยู่ให้ดึงมาไว้หน้าสุด
        if hasattr(self, 'manual_window') and self.manual_window.winfo_exists():
            self.manual_window.focus()
            return

        # สร้างหน้าต่าง Pop-up เล็กๆ
        self.manual_window = ctk.CTkToplevel(self)
        self.manual_window.title("Manual Motor Override")
        self.manual_window.geometry("320x220")
        self.manual_window.attributes("-topmost", True) # ให้อยู่บนสุดเสมอ
        self.manual_window.configure(fg_color=COLOR_BG)

        lbl = ctk.CTkLabel(self.manual_window, text="⚠️ MANUAL OVERRIDE", font=("Prompt", 16, "bold"), text_color="#b60000")
        lbl.pack(pady=(15, 10))

        # ปุ่ม Forward (กดค้าง)
        btn_fwd = ctk.CTkButton(self.manual_window, text="FORWARD ⏩", 
                                font=("Prompt", 14, "bold"), fg_color="#8e44ad", hover_color="#9b59b6", height=45)
        btn_fwd.pack(fill="x", padx=20, pady=5)
        btn_fwd.bind("<ButtonPress-1>", self.manual_forward)
        btn_fwd.bind("<ButtonRelease-1>", self.manual_stop)

        # ปุ่ม Reverse (กดค้าง)
        btn_rev = ctk.CTkButton(self.manual_window, text="⏪ REVERSE", 
                                font=("Prompt", 14, "bold"), fg_color="#8e44ad", hover_color="#9b59b6", height=45)
        btn_rev.pack(fill="x", padx=20, pady=5)
        btn_rev.bind("<ButtonPress-1>", self.manual_reverse)
        btn_rev.bind("<ButtonRelease-1>", self.manual_stop)

        ctk.CTkLabel(self.manual_window, text="*Hold button to move, release to stop", font=("Prompt", 10), text_color="gray").pack(pady=5)

    # --- ฟังก์ชันสั่งงานมอเตอร์ (ใช้ร่วมกับ Pop-up) ---
    def manual_forward(self, event):
        if not self.is_running and self.ser and self.ser.is_open:
            self.ser.write(b'F') 
            self.status_indicator.configure(text="STATUS : MANUAL FORWARD", fg_color="#8e44ad")

    def manual_reverse(self, event):
        if not self.is_running and self.ser and self.ser.is_open:
            self.ser.write(b'B') 
            self.status_indicator.configure(text="STATUS : MANUAL REVERSE", fg_color="#8e44ad")

    def manual_stop(self, event):
        if not self.is_running and self.ser and self.ser.is_open:
            self.ser.write(b'X') 
            self.status_indicator.configure(text="STATUS : STOPPED", fg_color=COLOR_DANGER)

    def send_tare(self):
        if self.ser: self.ser.write(b'T')

    def finish_test(self):
        self.is_running = False
        self.btn_start.configure(state="normal", text="START TEST", fg_color=COLOR_SUCCESS)
        self.entry_brand.configure(state="normal")
        self.entry_load.configure(state="normal")
        
        # รับค่าและอัปเดตแผงผลลัพธ์
        max_f, static_cof,avg_cof = self.save_all_data()
        self.lbl_res_max_force.configure(text=f"{max_f:.2f}", text_color=COLOR_SUCCESS)
        self.lbl_res_static_cof.configure(text=f"{static_cof:.3f}", text_color="#f39c12")
        self.lbl_res_avg_cof.configure(text=f"{avg_cof:.3f}", text_color=COLOR_COF)
        
        self.status_indicator.configure(text="COMPLETED & SAVED", fg_color=COLOR_ACCENT)

    def save_all_data(self):
        # [จุดแก้ที่ 1] เปลี่ยนจากส่งกลับ 2 ค่า เป็น 3 ค่า
        if not self.data_time: return 0, 0, 0 
        
        brand_name = self.entry_brand.get().strip().replace(" ", "_")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        folder_name = f"{timestamp}_{brand_name}"
        full_path = os.path.join(self.base_folder, folder_name)
        if not os.path.exists(full_path): os.makedirs(full_path)

        with open(os.path.join(full_path, "raw_data.csv"), 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Time (s)", "Force (N)", "COF"]) # เพิ่มคอลัมน์ COF
            for t, f_val, cof_val in zip(self.data_time, self.data_force, self.data_cof):
                writer.writerow([t, f_val, cof_val])

        # --- [แก้ไขใหม่] คำนวณค่าต่างๆ ก่อนเซฟรูปลงไฟล์ ---
        
        # กรองข้อมูลช่วง 1.5 วินาทีแรกทิ้งไปก่อน เพื่อหลบยอดกระตุก (False Peak)
        valid_forces = [f for t, f in zip(self.data_time, self.data_force) if t > 0.1]
        
        max_f = max(valid_forces) if valid_forces else (max(self.data_force) if self.data_force else 0)
        
        if self.data_force:
            # 1. หาตำแหน่งของจุด Peak (ของจริง)
            max_index = self.data_force.index(max_f)
            
            # 2. หั่นเอาเฉพาะข้อมูล Force "หลังจาก" จุด Peak ไปจนจบ
            kinetic_forces = self.data_force[max_index + 1:]
            
            # 3. หาค่าเฉลี่ยเฉพาะช่วง Kinetic
            if len(kinetic_forces) > 0:
                avg_f = sum(kinetic_forces) / len(kinetic_forces)
            else:
                avg_f = 0
        else:
            max_index = 0
            avg_f = 0
            
        static_cof = max_f / self.current_load_n if self.current_load_n > 0 else 0
        avg_cof = avg_f / self.current_load_n if self.current_load_n > 0 else 0

        # วาดวงกลมสีแดงและกล่องข้อความลงบนกราฟ
        if self.data_force:
            target_time = self.data_time[max_index]
            target_force = self.data_force[max_index]
            
            # พลอตวงกลมสีแดงตรงจุด Max Force
            self.ax.plot(target_time, target_force, 'ro', markersize=15, alpha=0.4)
            
            # สร้างข้อความสรุปผล
            label_text = f"MAX FORCE: {max_f:.2f} N\n" \
                         f"STATIC COF: {static_cof:.3f}\n" \
                         f"KINETIC COF: {avg_cof:.3f}"
            
            # วางกล่องข้อความเยื้องจากจุด Max ไปทางขวาบน
            self.ax.text(target_time + 0.3, target_force, label_text, 
                         fontsize=10, fontweight='bold', color='#e74c3c',
                         bbox=dict(facecolor='#2b2b2b', edgecolor='#e74c3c', boxstyle='round,pad=0.6', alpha=0.9))
            
            # อัปเดตภาพกราฟก่อนสั่งเซฟ
            self.canvas.draw()
        # ---------------------------------------------

        # เซฟกราฟ (ซึ่งตอนนี้มีรอยสแตมป์ค่าผลลัพธ์สีแดงติดไปด้วยแล้ว)
        self.fig.savefig(os.path.join(full_path, "graph_plot.png"), facecolor=COLOR_CARD)

        with open(os.path.join(full_path, "report.txt"), 'w') as f:
            f.write(f"TEST REPORT: {brand_name}\n")
            f.write(f"Date: {timestamp}\n")
            f.write(f"Normal Load: {self.current_load_n/9.81:.2f} kg ({self.current_load_n:.2f} N)\n")
            f.write("-" * 30 + "\n")
            f.write(f"Max Force: {max_f:.4f} N\n")
            f.write(f"Avg Force: {avg_f:.4f} N\n")
            f.write(f"Static COF (u_s): {static_cof:.4f}\n") # พิมพ์ค่า Static ลง Report
            f.write(f"Kinetic COF (u_k): {avg_cof:.4f}\n")
             
        print(f"Data saved: {full_path}")
        
        # [จุดแก้ที่ 2] ส่งค่ากลับ 3 ค่าให้หน้า UI
        return max_f, static_cof, avg_cof

    def open_data_folder(self):
        if os.path.exists(self.base_folder):
            if sys.platform == 'win32':
                os.startfile(self.base_folder)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.base_folder])
            else:
                subprocess.Popen(['xdg-open', self.base_folder])
        else:
            tk.messagebox.showerror("Error", "Data folder not found!")

    def update_plot(self):
        # อัพเดตข้อมูล
        self.line_force.set_data(self.data_time, self.data_force)
        self.line_cof.set_data(self.data_time, self.data_cof)
        
        # --- 1. ขยายเพดานแกน X (เวลา) อัตโนมัติ ---
        if self.data_time:
            current_time = self.data_time[-1]
            current_x_limit = self.ax.get_xlim()[1] # อ่านค่าขอบขวาสุดของกราฟปัจจุบัน
            
            # ถ้าเส้นกราฟวิ่งไปถึง 85% ของขอบขวา
            if current_time >= current_x_limit * 0.85:
                # ให้ขยายแกนเวลาเพิ่มไปอีก 5 วินาที (จาก 5->10, 10->15)
                new_x_limit = current_x_limit + 5
                self.ax.set_xlim(0, new_x_limit)
                self.ax2.set_xlim(0, new_x_limit) # ต้องขยายแกน COF ไปพร้อมกัน
                
        # --- 2. ขยายเพดานแกน Y (แรงกระทำ) อัตโนมัติ ---
        if self.data_force:
            current_max_force = max(self.data_force)
            current_y_limit = self.ax.get_ylim()[1] 
            
            # ถ้าแรงพุ่งขึ้นไปเกิน 85% ของขอบบน
            if current_max_force >= current_y_limit * 0.85:
                # ให้ขยายเพดานกราฟเพิ่มขึ้นไปอีก 100 นิวตัน
                self.ax.set_ylim(0, current_y_limit + 100) 

        self.canvas.draw()

    def show_summary_popup(self, max_f, avg_cof):
        # สร้างหน้าต่าง Pop-up
        popup = ctk.CTkToplevel(self)
        popup.title("Test Summary")
        popup.geometry("400x450") # ปรับขนาดให้มีพื้นที่เหลือ
        popup.attributes("-topmost", True)
        popup.configure(fg_color=COLOR_BG)
        
        # หัวข้อ
        lbl_title = ctk.CTkLabel(popup, text="✅ TEST COMPLETED", font=("Prompt", 20, "bold"), text_color=COLOR_SUCCESS)
        lbl_title.pack(pady=(20, 10))
        
        # กรอบแสดงผลการทดสอบ
        result_frame = ctk.CTkFrame(popup, fg_color=COLOR_CARD, corner_radius=10)
        result_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # 1. แสดงค่า Max Force ตัวใหญ่
        ctk.CTkLabel(result_frame, text="MAXIMUM FORCE", font=("Prompt", 14), text_color="gray").pack(pady=(20, 0))
        ctk.CTkLabel(result_frame, text=f"{max_f:.2f} N", font=("Prompt", 48, "bold"), text_color=COLOR_SUCCESS).pack(pady=(0, 15))
        
        # 2. แสดงค่า Average Kinetic COF
        ctk.CTkLabel(result_frame, text="AVERAGE KINETIC COF", font=("Prompt", 14), text_color="gray").pack(pady=(10, 0))
        ctk.CTkLabel(result_frame, text=f"{avg_cof:.3f}", font=("Prompt", 36, "bold"), text_color=COLOR_COF).pack(pady=(0, 15))
        
        # 3. พื้นที่ว่างเผื่ออนาคต (Reserved Space)
        future_frame = ctk.CTkFrame(result_frame, fg_color="transparent", height=50)
        future_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(future_frame, text="[ Reserved for future parameters ]", font=("Prompt", 12, "italic"), text_color="#555555").pack()
        
        # ปุ่ม OK สำหรับปิดหน้าต่างและเตรียมเทสรอบต่อไป
        btn_ok = ctk.CTkButton(popup, text="OK", font=("Prompt", 16, "bold"), height=50, 
                               command=popup.destroy, fg_color=COLOR_ACCENT, hover_color="#2980b9")
        btn_ok.pack(fill="x", padx=40, pady=(10, 20))

    # =======================================================
    #                 SYSTEM SETTINGS WINDOW
    # =======================================================
    def open_settings_window(self):
        # เช็คว่าเปิดค้างอยู่หรือไม่
        if hasattr(self, 'settings_window') and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return

        self.settings_window = ctk.CTkToplevel(self)
        self.settings_window.title("Advanced System Settings")
        self.settings_window.geometry("450x380")
        self.settings_window.attributes("-topmost", True)
        self.settings_window.configure(fg_color=COLOR_BG)

        # 1. สร้าง Tabview (แถบเมนูสไตล์ Google)
        self.tabview = ctk.CTkTabview(self.settings_window, width=400, height=250, 
                                      fg_color=COLOR_CARD, segmented_button_selected_color=COLOR_ACCENT)
        self.tabview.pack(padx=20, pady=15, fill="both", expand=True)

        # 2. เพิ่มชื่อ Tab
        self.tabview.add("⚙️ Motor & Test")
        self.tabview.add("⚖️ Calibration")

        # --- TAB 1: Motor & Test ---
        tab_motor = self.tabview.tab("⚙️ Motor & Test")
        
        # 1.1 Motor Speed (ใช้ Slider เลื่อน)
        ctk.CTkLabel(tab_motor, text="Motor Speed (PWM: 0 - 255):", font=FONT_LABEL, text_color="gray").pack(anchor="w", padx=20, pady=(15,0))
        
        self.slider_speed = ctk.CTkSlider(tab_motor, from_=0, to=255, number_of_steps=255, button_color=COLOR_ACCENT)
        self.slider_speed.set(self.setting_motor_speed)
        self.slider_speed.pack(fill="x", padx=20, pady=5)
        
        self.lbl_speed_val = ctk.CTkLabel(tab_motor, text=str(self.setting_motor_speed), font=("Prompt", 16, "bold"), text_color="#ecf0f1")
        self.lbl_speed_val.pack()
        self.slider_speed.configure(command=lambda val: self.lbl_speed_val.configure(text=str(int(val)))) # อัปเดตตัวเลขตอนเลื่อน

        # 1.2 Test Duration (ใช้ช่องกรอก)
        ctk.CTkLabel(tab_motor, text="Test Duration (Seconds):", font=FONT_LABEL, text_color="gray").pack(anchor="w", padx=20, pady=(15,0))
        self.entry_duration = ctk.CTkEntry(tab_motor, font=FONT_LABEL, justify="center")
        self.entry_duration.insert(0, str(self.setting_test_duration))
        self.entry_duration.pack(fill="x", padx=20, pady=5)

        # --- TAB 2: Calibration ---
        tab_cal = self.tabview.tab("⚖️ Calibration")
        
        # 2.1 Load Cell Cal Factor
        ctk.CTkLabel(tab_cal, text="Load Cell Calibration Factor:", font=FONT_LABEL, text_color="gray").pack(anchor="w", padx=20, pady=(20,0))
        self.entry_cal_factor = ctk.CTkEntry(tab_cal, font=FONT_LABEL, justify="center")
        self.entry_cal_factor.insert(0, str(self.setting_cal_factor))
        self.entry_cal_factor.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(tab_cal, text="*ค่านี้จะถูกส่งไปเขียนทับในบอร์ด Arduino ทันที", font=("Prompt", 10), text_color="#e74c3c").pack(anchor="w", padx=20)

        # --- ปุ่ม SAVE ---
        btn_save = ctk.CTkButton(self.settings_window, text="💾 SAVE & APPLY SETTINGS", 
                                 font=("Prompt", 14, "bold"), fg_color=COLOR_SUCCESS, hover_color="#229954", height=45,
                                 command=self.save_settings)
        btn_save.pack(fill="x", padx=20, pady=(0, 20))

    def build_settings_content(self, container_frame):
        # 1. คอนเทนเนอร์หลัก (มีพื้นหลัง COLOR_CARD และความโค้ง)
        container = ctk.CTkFrame(container_frame, fg_color=COLOR_CARD, corner_radius=15)
        container.pack(anchor="nw", fill="x", expand=True, padx=50, pady=50) 
        
        # --- 2. สร้างแถบ Header แนวนอน ---
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        # [จุดที่แก้] เพิ่ม padx=40 และดันขอบบนให้เว้นที่ว่าง pady=(40, 40)
        header_frame.pack(fill="x", padx=40, pady=(40, 40))
        
        # หัวข้อชิดซ้าย
        ctk.CTkLabel(header_frame, text="⚙️ ADVANCED SYSTEM SETTINGS", font=("Prompt", 32, "bold"), text_color=COLOR_ACCENT).pack(side="left")
        
        # ปุ่ม Save ดันไปชิดขวาบน
        btn_save = ctk.CTkButton(header_frame, text="💾 SAVE & APPLY SETTINGS", width=250,
                                 font=("Prompt", 16, "bold"), fg_color=COLOR_SUCCESS, hover_color="#229954", height=45,
                                 command=self.save_settings)
        btn_save.pack(side="right")

        # --- 3. ส่วนเนื้อหาการตั้งค่า ---
        LABEL_FONT = ("Prompt", 18)           
        VALUE_FONT = ("Prompt", 20, "bold")   
        
        # 1. Motor Speed
        frame_motor = ctk.CTkFrame(container, fg_color="transparent")
        # [จุดที่แก้] เพิ่ม padx=40 ไม่ให้ข้อความชิดขอบซ้ายเกินไป
        frame_motor.pack(fill="x", padx=40, pady=20) 
        ctk.CTkLabel(frame_motor, text="Motor Speed (PWM: 0 - 255):", font=LABEL_FONT, text_color="gray").pack(side="left")
        
        self.lbl_speed_val = ctk.CTkLabel(frame_motor, text=str(self.setting_motor_speed), font=VALUE_FONT, text_color="#ecf0f1")
        self.lbl_speed_val.pack(side="right")
        
        self.slider_speed = ctk.CTkSlider(container, from_=0, to=255, number_of_steps=255, button_color=COLOR_ACCENT, height=20)
        self.slider_speed.set(self.setting_motor_speed)
        # [จุดที่แก้] เพิ่ม padx=40 ให้สไลเดอร์หดเข้ามาจากขอบ
        self.slider_speed.pack(fill="x", padx=40, pady=(0, 20))
        self.slider_speed.configure(command=lambda val: self.lbl_speed_val.configure(text=str(int(val))))
        
        # 2. Test Duration
        frame_dur = ctk.CTkFrame(container, fg_color="transparent")
        frame_dur.pack(fill="x", padx=40, pady=20) # [จุดที่แก้] เพิ่ม padx=40
        ctk.CTkLabel(frame_dur, text="Test Duration (Seconds):", font=LABEL_FONT, text_color="gray").pack(side="left")
        
        self.entry_duration = ctk.CTkEntry(frame_dur, font=VALUE_FONT, justify="center", width=200, height=45)
        self.entry_duration.insert(0, str(self.setting_test_duration))
        self.entry_duration.pack(side="right")

        # 3. Calibration
        frame_cal = ctk.CTkFrame(container, fg_color="transparent")
        frame_cal.pack(fill="x", padx=40, pady=20) # [จุดที่แก้] เพิ่ม padx=40
        ctk.CTkLabel(frame_cal, text="Load Cell Calibration Factor:", font=LABEL_FONT, text_color="gray").pack(side="left")
        
        self.entry_cal_factor = ctk.CTkEntry(frame_cal, font=VALUE_FONT, justify="center", width=200, height=45)
        self.entry_cal_factor.insert(0, str(self.setting_cal_factor))
        self.entry_cal_factor.pack(side="right")
        
        # หมายเหตุด้านล่าง
        # [จุดที่แก้] เพิ่ม padx=40 และดันขอบล่างให้มีพื้นที่ว่าง pady=(40, 40)
        ctk.CTkLabel(container, text="* ค่าการตั้งค่าจะถูกส่งไปยังบอร์ด Arduino เมื่อเริ่มทดสอบรอบถัดไป", font=("Prompt", 14), text_color="#e74c3c").pack(anchor="w", padx=40, pady=(40, 40))

    def select_tab(self, tab_name):
        # สีสำหรับปุ่มแท็บ
        color_tab_selected = COLOR_ACCENT
        color_tab_unselected = "#262626"

        if tab_name == "live":
            # แสดง frame Live Test, ซ่อน frame Settings
            self.frame_live.grid(row=0, column=0, sticky="nsew")
            self.frame_settings.grid_forget()
            
            # เปลี่ยนสีปุ่มที่เลือก/ไม่เลือก
            self.btn_tab_live.configure(fg_color=color_tab_selected)
            self.btn_tab_settings.configure(fg_color=color_tab_unselected)
            
        elif tab_name == "settings":
            # แสดง frame Settings, ซ่อน frame Live Test
            self.frame_settings.grid(row=0, column=0, sticky="nsew")
            self.frame_live.grid_forget()
            
            # เปลี่ยนสีปุ่มที่เลือก/ไม่เลือก
            self.btn_tab_settings.configure(fg_color=color_tab_selected)
            self.btn_tab_live.configure(fg_color=color_tab_unselected)

    def build_live_test_content(self, container_frame):
        # จัด Layout หลักของหน้า Live Test
        container_frame.grid_columnconfigure(1, weight=1)
        container_frame.grid_rowconfigure(0, weight=1)

        # LEFT SIDEBAR (SCROLLABLE)
        self.sidebar = ctk.CTkScrollableFrame(container_frame, width=320, corner_radius=0, fg_color=COLOR_CARD)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
 
        # --- Group 1: Config ---
        # แก้ไขให้สร้างใน container_frame เฉพาะ
        self.create_sidebar_group("TEST CONFIGURATION", 0)
        self.entry_brand = ctk.CTkEntry(self.sidebar_group, placeholder_text="Enter Shoe Model...", font=FONT_LABEL, height=40)
        self.entry_brand.pack(fill="x", pady=(10, 5))
        
        ctk.CTkLabel(self.sidebar_group, text="Normal Load (kg):", font=("Prompt", 12), text_color="gray", anchor="w").pack(fill="x", padx=2)
        self.entry_load = ctk.CTkEntry(self.sidebar_group, placeholder_text="e.g. 50", font=FONT_LABEL, height=40)
        self.entry_load.pack(fill="x", pady=(0, 10))
        self.entry_load.insert(0, "50") 

        # --- Group 2: Hardware ---
        # แก้ไขให้สร้างใน container_frame เฉพาะ
        self.create_sidebar_group("HARDWARE CONNECTION", 1)
        self.port_combo = ctk.CTkComboBox(self.sidebar_group, values=["Scanning..."], font=FONT_LABEL)
        self.port_combo.pack(fill="x", pady=5)
        
        btn_row = ctk.CTkFrame(self.sidebar_group, fg_color="transparent")
        btn_row.pack(fill="x", pady=5)
        ctk.CTkButton(btn_row, text="↻", width=40, command=self.refresh_ports, fg_color="#555555").pack(side="left", padx=(0,5))
        self.btn_connect = ctk.CTkButton(btn_row, text="CONNECT", command=self.toggle_connection, fg_color=COLOR_ACCENT, font=("Prompt", 12, "bold"))
        self.btn_connect.pack(side="left", fill="x", expand=True)
        self.refresh_ports()

        # --- Group 3: Operation ---
        # แก้ไขให้สร้างใน container_frame เฉพาะ
        self.create_sidebar_group("OPERATION CONTROL", 2)
        self.btn_start = ctk.CTkButton(self.sidebar_group, text="START TEST", command=self.start_test, 
                                       font=("Prompt", 16, "bold"), fg_color=COLOR_SUCCESS, height=60, corner_radius=5, state="disabled")
        self.btn_start.pack(fill="x", pady=(10, 5))
        
        self.btn_stop = ctk.CTkButton(self.sidebar_group, text="EMERGENCY STOP", command=self.stop_test, 
                                      font=("Prompt", 14, "bold"), fg_color=COLOR_DANGER, height=40, corner_radius=5)
        self.btn_stop.pack(fill="x", pady=5)

        self.btn_tare = ctk.CTkButton(self.sidebar_group, text="TARE (ZERO)", command=self.send_tare, 
                                      fg_color="#555555", height=30)
        self.btn_tare.pack(fill="x", pady=(20,5))

        self.btn_manual_settings = ctk.CTkButton(self.sidebar_group, text="⚙️ MANUAL CONTROL", 
                                                 command=self.open_manual_control_window, 
                                                 fg_color="#34495e", hover_color="#2c3e50", height=30)
        self.btn_manual_settings.pack(fill="x", pady=(5, 10))
    
        # --- Group 4: Data Archive ---
        # แก้ไขให้สร้างใน container_frame เฉพาะ
        self.create_sidebar_group("DATA ARCHIVE", 3)
        self.btn_open_folder = ctk.CTkButton(self.sidebar_group, text="📂 OPEN DATA FOLDER", 
                                             command=self.open_data_folder, 
                                             font=("Prompt", 12, "bold"), text_color="#ffffff",
                                             fg_color="#555555", hover_color="#333333", height=40)
        self.btn_open_folder.pack(fill="x", pady=10)

        # RIGHT AREA (MONITOR)
        self.monitor_area = ctk.CTkFrame(container_frame, fg_color=COLOR_BG, corner_radius=0)
        self.monitor_area.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.monitor_area.grid_rowconfigure(1, weight=1)
        self.monitor_area.grid_columnconfigure(0, weight=1)

        # Readout Panel
        self.readout_panel = ctk.CTkFrame(self.monitor_area, height=150, fg_color=COLOR_CARD, corner_radius=5)
        self.readout_panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.readout_panel.grid_columnconfigure(0, weight=1)
        self.readout_panel.grid_columnconfigure(1, weight=1)
        
        # ช่องซ้าย: Force
        frame_force = ctk.CTkFrame(self.readout_panel, fg_color="transparent")
        frame_force.grid(row=0, column=0, pady=10)
        ctk.CTkLabel(frame_force, text="FRICTION FORCE", font=("Prompt", 14), text_color="gray").pack()
        self.lbl_force = ctk.CTkLabel(frame_force, text="0.00", font=FONT_VALUE, text_color=COLOR_SUCCESS)
        self.lbl_force.pack()
        ctk.CTkLabel(frame_force, text="NEWTON (N)", font=FONT_UNIT, text_color="gray").pack()

        # ช่องขวา: COF
        frame_cof = ctk.CTkFrame(self.readout_panel, fg_color="transparent")
        frame_cof.grid(row=0, column=1, pady=10)
        ctk.CTkLabel(frame_cof, text="COEFFICIENT (µ)", font=("Prompt", 14), text_color="gray").pack()
        self.lbl_cof = ctk.CTkLabel(frame_cof, text="0.00", font=FONT_VALUE, text_color=COLOR_COF)
        self.lbl_cof.pack()
        ctk.CTkLabel(frame_cof, text="UNITLESS", font=FONT_UNIT, text_color="gray").pack()

        self.graph_container = ctk.CTkFrame(self.monitor_area, fg_color=COLOR_CARD, corner_radius=5)
        self.graph_container.grid(row=1, column=0, sticky="nsew")
        
        self.setup_graph()

        # --- RIGHT SIDEBAR (RESULTS DASHBOARD) ---
        container_frame.grid_columnconfigure(2, weight=0) 
        
        self.results_sidebar = ctk.CTkFrame(container_frame, width=250, corner_radius=0, fg_color=COLOR_CARD)
        self.results_sidebar.grid(row=0, column=2, sticky="nsew", padx=(0, 2), pady=2)
        
        # หัวข้อ
        ctk.CTkLabel(self.results_sidebar, text="📊 TEST SUMMARY", font=("Prompt", 16, "bold"), text_color=COLOR_ACCENT).pack(pady=(20, 10))
        ctk.CTkFrame(self.results_sidebar, height=2, fg_color="#555555").pack(fill="x", padx=20, pady=5)

        # 1. ค่า Max Force
        ctk.CTkLabel(self.results_sidebar, text="MAXIMUM FORCE", font=("Prompt", 12), text_color="gray").pack(pady=(15, 0))
        self.lbl_res_max_force = ctk.CTkLabel(self.results_sidebar, text="--.--", font=("Prompt", 40, "bold"), text_color="#ecf0f1")
        self.lbl_res_max_force.pack()
        ctk.CTkLabel(self.results_sidebar, text="NEWTON (N)", font=("Prompt", 12), text_color="gray").pack(pady=(0, 10))

        # ค่า Static COF
        ctk.CTkLabel(self.results_sidebar, text="STATIC COF", font=("Prompt", 12), text_color="gray").pack(pady=(15, 0))
        self.lbl_res_static_cof = ctk.CTkLabel(self.results_sidebar, text="--.--", font=("Prompt", 40, "bold"), text_color="#ecf0f1")
        self.lbl_res_static_cof.pack()
        ctk.CTkLabel(self.results_sidebar, text="UNITLESS (µ)", font=("Prompt", 12), text_color="gray").pack(pady=(0, 10))

        # 2. ค่า Avg Kinetic COF
        ctk.CTkLabel(self.results_sidebar, text="KINETIC COF", font=("Prompt", 12), text_color="gray").pack(pady=(15, 0))
        self.lbl_res_avg_cof = ctk.CTkLabel(self.results_sidebar, text="--.--", font=("Prompt", 40, "bold"), text_color="#ecf0f1")
        self.lbl_res_avg_cof.pack()
        ctk.CTkLabel(self.results_sidebar, text="UNITLESS (µ)", font=("Prompt", 12), text_color="gray").pack(pady=(0, 10))
        
        # 3. พื้นที่ว่างด้านล่าง 
        self.future_params_frame = ctk.CTkFrame(self.results_sidebar, fg_color="transparent")
        self.future_params_frame.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(self.future_params_frame, text="[ Reserved for future parameters ]", font=("Prompt", 10, "italic"), text_color="#555555").pack(side="bottom", pady=20)

    def save_settings(self):
        # --- [เพิ่มใหม่] บังคับให้ต้องเชื่อมต่อบอร์ดก่อนเซฟค่า ---
        if not self.ser or not self.ser.is_open:
            tk.messagebox.showwarning("Connection Required", "กรุณาเชื่อมต่อเครื่องทดสอบ (กดปุ่ม CONNECT)")
            return
        # ---------------------------------------------------

        try:
            new_speed = int(self.slider_speed.get())
            new_duration = float(self.entry_duration.get())
            new_cal = float(self.entry_cal_factor.get())

            # --- ดักจับห้ามตั้งเวลาน้อยกว่าหรือเท่ากับ 1.5 วินาที ---
            if new_duration <= 1.5:
                tk.messagebox.showwarning("System Alert", "Test Duration ต้องมากกว่า 1.5 วินาที!\n\n(เนื่องจากระบบมีการหน่วงเวลา 1.5 วินาทีแรกเพื่อกรองแรงกระตุกช่วงเริ่มต้น)")
                return  # สั่งหยุดการทำงานทันที (ไม่บันทึกค่าและไม่ส่งไป Arduino)
                
            if new_speed < 0 or new_speed > 255:
                raise ValueError
            
            # บันทึกค่าลงตัวแปร
            self.setting_motor_speed = new_speed
            self.setting_test_duration = new_duration
            self.setting_cal_factor = new_cal
            
            # --- [เพิ่มใหม่] เซฟค่าล่าสุดลงไฟล์ system_config.json ทันที ---
            config_data = {
                "motor_speed": self.setting_motor_speed,
                "test_duration": self.setting_test_duration,
                "cal_factor": self.setting_cal_factor
            }
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=4)
            except Exception as e:
                print(f"Error saving config: {e}")
            # -------------------------------------------------------
            
            # --- ส่งคำสั่งผ่าน USB ไปยัง Arduino ---
            if self.ser and self.ser.is_open:
                # 1. ส่งความเร็ว (P นำหน้า)
                self.ser.write(f"P{new_speed}\n".encode('utf-8'))
                time.sleep(0.05) # หน่วงเวลาให้ Arduino รับข้อมูลทัน
                
                # 2. ส่งระยะเวลา (D นำหน้า) ต้องแปลงเป็นมิลลิวินาที
                duration_ms = int(new_duration * 1000)
                self.ser.write(f"D{duration_ms}\n".encode('utf-8'))
                time.sleep(0.05)
                
                # 3. ส่งค่า Calibrate (C นำหน้า)
                self.ser.write(f"C{new_cal}\n".encode('utf-8'))
                time.sleep(0.05)
            # -----------------------------------------------
            
            tk.messagebox.showinfo("Success", "บันทึกและอัปเดตค่าไปยังเครื่องทดสอบเรียบร้อยแล้ว!")
            
            # เด้งกลับไปหน้าต่าง LIVE TEST อัตโนมัติ 
            self.select_tab("live")

        except ValueError:
            tk.messagebox.showerror("Error", "กรุณากรอกตัวเลขให้ถูกต้อง!")

    def load_settings(self):
        # ถ้ามีไฟล์ config อยู่แล้ว ให้ดึงค่ามาทับตัวแปรเริ่มต้น
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.setting_motor_speed = config.get("motor_speed", 220)
                    self.setting_test_duration = config.get("test_duration", 3.5)
                    self.setting_cal_factor = config.get("cal_factor", 2.94)
            except Exception as e:
                print(f"Error loading config: {e}")        

if __name__ == "__main__":
    app = IndustrialTesterApp()
    app.mainloop()