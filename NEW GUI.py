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
        self.after(500, lambda: self.state('zoomed')) 
        
        # ตัวแปรระบบ
        self.ser = None
        self.is_running = False
        self.data_time = []
        self.data_force = []
        self.data_cof = [] # [ใหม่] เพิ่มตัวแปรเก็บค่า COF
        self.start_timestamp = 0
        self.current_load_n = 1.0 
        
        self.base_folder = os.path.join(os.path.expanduser("~"), "Desktop", "FrictionTest_Database")
        if not os.path.exists(self.base_folder): os.makedirs(self.base_folder)

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
        self.main_frame = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=0)
        self.main_frame.grid(row=1, column=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(1, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # LEFT SIDEBAR
        self.sidebar = ctk.CTkFrame(self.main_frame, width=300, corner_radius=0, fg_color=COLOR_CARD)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        # --- Group 1: Config ---
        self.create_sidebar_group("TEST CONFIGURATION", 0)
        self.entry_brand = ctk.CTkEntry(self.sidebar_group, placeholder_text="Enter Shoe Model...", font=FONT_LABEL, height=40)
        self.entry_brand.pack(fill="x", pady=(10, 5))
        
        ctk.CTkLabel(self.sidebar_group, text="Normal Load (kg):", font=("Prompt", 12), text_color="gray", anchor="w").pack(fill="x", padx=2)
        self.entry_load = ctk.CTkEntry(self.sidebar_group, placeholder_text="e.g. 50", font=FONT_LABEL, height=40)
        self.entry_load.pack(fill="x", pady=(0, 10))
        self.entry_load.insert(0, "50") 

        # --- Group 2: Hardware ---
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
        
        # --- Group 4: Data Archive ---
        self.create_sidebar_group("DATA ARCHIVE", 3)
        self.btn_open_folder = ctk.CTkButton(self.sidebar_group, text="📂 OPEN DATA FOLDER", 
                                             command=self.open_data_folder, 
                                             font=("Prompt", 12, "bold"),
                                             fg_color="#7f8c8d", hover_color="#95a5a6",
                                             height=40)
        self.btn_open_folder.pack(fill="x", pady=10)

        # RIGHT AREA
        self.monitor_area = ctk.CTkFrame(self.main_frame, fg_color=COLOR_BG, corner_radius=0)
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
        # [ใหม่] สร้างแกนที่ 2 (แกนขวา)
        self.ax2 = self.ax.twinx()
        
        # ปรับแต่งสีพื้นหลัง
        self.ax.set_facecolor('#1e1e1e')
        
        # ปรับแต่งเส้นขอบ
        for spine in self.ax.spines.values(): spine.set_color('#555555')
        self.ax2.spines['top'].set_color('#555555')
        self.ax2.spines['bottom'].set_color('#555555')
        self.ax2.spines['left'].set_color('#555555')
        self.ax2.spines['right'].set_color('#555555')

        # ปรับแต่ง Label และสีแกน
        self.ax.set_xlabel("TIME (s)", fontname="Prompt", fontsize=10, color='#aaaaaa')
        self.ax.set_ylabel("FORCE (N)", fontname="Prompt", fontsize=10, color=COLOR_SUCCESS) # สีเขียว
        self.ax2.set_ylabel("COEFFICIENT (µ)", fontname="Prompt", fontsize=10, color=COLOR_COF) # สีแดง

        # ปรับสีตัวเลขบนแกน
        self.ax.tick_params(axis='y', colors=COLOR_SUCCESS, labelsize=9)
        self.ax.tick_params(axis='x', colors='#aaaaaa', labelsize=9)
        self.ax2.tick_params(axis='y', colors=COLOR_COF, labelsize=9)

        self.ax.grid(True, color='#333333', linestyle='-', linewidth=0.5)

        # สร้างเส้นกราฟ 2 เส้น
        self.line_force, = self.ax.plot([], [], color=COLOR_SUCCESS, linewidth=1.5, label="Force")
        self.line_cof, = self.ax2.plot([], [], color=COLOR_COF, linewidth=1.5, linestyle='--', label="COF") # เส้นปะ

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
                        val = float(line.split(":")[1]) * 0.00981
                        cof = val / self.current_load_n if self.current_load_n > 0 else 0
                        self.after(0, lambda v=val, c=cof: self.update_readout(v, c))
                        
                    elif line.startswith("DATA:"):
                        val = float(line.split(":")[1]) * 0.00981
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
        # อัพเดตข้อมูลทั้ง 2 เส้น
        self.line_force.set_data(self.data_time, self.data_force)
        self.line_cof.set_data(self.data_time, self.data_cof)
        
        # ปรับสเกลแกนซ้าย (Force)
        self.ax.relim()
        self.ax.autoscale_view()
        
        # ปรับสเกลแกนขวา (COF)
        self.ax2.relim()
        self.ax2.autoscale_view()
        
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
        
        # 2. รีเซ็ตกราฟ (ต้องเคลียร์ทั้ง 2 แกน)
        self.ax.cla()
        self.ax2.cla()
        
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

    def send_tare(self):
        if self.ser: self.ser.write(b'T')

    def finish_test(self):
        self.is_running = False
        self.btn_start.configure(state="normal", text="START TEST", fg_color=COLOR_SUCCESS)
        self.entry_brand.configure(state="normal")
        self.entry_load.configure(state="normal")
        
        self.save_all_data()
        self.status_indicator.configure(text="COMPLETED & SAVED", fg_color=COLOR_ACCENT)

    def save_all_data(self):
        if not self.data_time: return
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

        self.fig.savefig(os.path.join(full_path, "graph_plot.png"), facecolor=COLOR_CARD)

        max_f = max(self.data_force) if self.data_force else 0
        avg_f = sum(self.data_force) / len(self.data_force) if self.data_force else 0
        avg_cof = avg_f / self.current_load_n if self.current_load_n > 0 else 0
        
        with open(os.path.join(full_path, "report.txt"), 'w') as f:
            f.write(f"TEST REPORT: {brand_name}\n")
            f.write(f"Date: {timestamp}\n")
            f.write(f"Normal Load: {self.current_load_n/9.81:.2f} kg ({self.current_load_n:.2f} N)\n")
            f.write("-" * 30 + "\n")
            f.write(f"Max Force: {max_f:.4f} N\n")
            f.write(f"Avg Force: {avg_f:.4f} N\n")
            f.write(f"Avg COF (u): {avg_cof:.4f}\n")
            
        print(f"Data saved: {full_path}")

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

if __name__ == "__main__":
    app = IndustrialTesterApp()
    app.mainloop()