import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import os
import sys
import scheduler_bot
from PIL import Image, ImageTk
import pystray

CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "TAMUCheckSeats")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
monitor_thread = None
monitor_running = False

class TextRedirector:
    def __init__(self, text_widget, tag="stdout"):
        self.text_widget = text_widget
        self.tag = tag

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)

    def flush(self):
        pass

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config({
            "username": "",
            "password": "",
            "discord_token": "",
            "channel_name": "",
            "term_name": "",
            "reg_time": "",
            "discord_account_id": "",
            "class_names": [],
            "headless": False,
            "auto_register": False
        })
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

class ConfigTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.channel_var = tk.StringVar()
        self.term_var = tk.StringVar()
        self.reg_var = tk.StringVar()
        self.id_var = tk.StringVar()
        self.headless_var = tk.BooleanVar()
        self.auto_register_var = tk.BooleanVar()
        self.class_vars = []

        self.build_ui()
        self.load_config_into_fields()

    def build_ui(self):
        tk.Label(self, text="Username").grid(row=0, column=0, sticky="w")
        tk.Entry(self, textvariable=self.username_var).grid(row=0, column=1)

        tk.Label(self, text="Password").grid(row=1, column=0, sticky="w")
        tk.Entry(self, textvariable=self.password_var, show="*").grid(row=1, column=1)

        tk.Label(self, text="Discord Token").grid(row=2, column=0, sticky="w")
        tk.Entry(self, textvariable=self.token_var, show="*").grid(row=2, column=1)

        tk.Label(self, text="Channel Name").grid(row=3, column=0, sticky="w")
        tk.Entry(self, textvariable=self.channel_var).grid(row=3, column=1)

        tk.Label(self, text="Term Name").grid(row=4, column=0, sticky="w")
        tk.Entry(self, textvariable=self.term_var).grid(row=4, column=1)

        tk.Label(self, text="Registration Time (Epoch)").grid(row=5, column=0, sticky="w")
        tk.Entry(self, textvariable=self.reg_var).grid(row=5, column=1)

        tk.Label(self, text="Discord Account ID").grid(row=6, column=0, sticky="w")
        tk.Entry(self, textvariable=self.id_var).grid(row=6, column=1)

        tk.Checkbutton(self, text="Run Headless", variable=self.headless_var).grid(row=7, column=0, columnspan=2, sticky="w")
        tk.Checkbutton(self, text="Auto Register for Shopping Carts Courses", variable=self.auto_register_var).grid(row=8, column=0, columnspan=2, sticky="w")

        self.class_frame = tk.LabelFrame(self, text="Class Names")
        self.class_frame.grid(row=9, column=0, columnspan=2, pady=10, sticky="we")

        self.add_class_field_btn = tk.Button(self, text="Add Class", command=self.add_class_field)
        self.add_class_field_btn.grid(row=10, column=0, pady=5)

        tk.Button(self, text="Save Config", command=self.save_fields_to_config).grid(row=10, column=1, pady=5)

    def add_class_field(self, value=""):
        var = tk.StringVar(value=value)
        row = len(self.class_vars)
        entry = tk.Entry(self.class_frame, textvariable=var, width=30)
        entry.grid(row=row, column=0, padx=5, pady=2, sticky="w")

        btn = tk.Button(self.class_frame, text="Remove", command=lambda: self.remove_class_field(var, entry, btn))
        btn.grid(row=row, column=1, padx=5, pady=2)

        self.class_vars.append(var)

    def remove_class_field(self, var, entry, btn):
        idx = self.class_vars.index(var)
        entry.destroy()
        btn.destroy()
        self.class_vars.pop(idx)

    def load_config_into_fields(self):
        data = load_config()
        self.username_var.set(data.get("username", ""))
        self.password_var.set(data.get("password", ""))
        self.token_var.set(data.get("discord_token", ""))
        self.channel_var.set(data.get("channel_name", ""))
        self.term_var.set(data.get("term_name", ""))
        self.reg_var.set(data.get("reg_time", ""))
        self.id_var.set(data.get("discord_account_id", ""))
        self.headless_var.set(data.get("headless", False))
        self.auto_register_var.set(data.get("auto_register", False))

        for var in self.class_vars:
            del var
        self.class_vars = []
        for cls in data.get("class_names", []):
            self.add_class_field(cls)

    def save_fields_to_config(self):
        data = {
            "username": self.username_var.get(),
            "password": self.password_var.get(),
            "discord_token": self.token_var.get(),
            "channel_name": self.channel_var.get(),
            "term_name": self.term_var.get(),
            "reg_time": self.reg_var.get(),
            "discord_account_id": self.id_var.get(),
            "class_names": [v.get() for v in self.class_vars if v.get().strip()],
            "headless": self.headless_var.get(),
            "auto_register": self.auto_register_var.get()
        }
        save_config(data)
        messagebox.showinfo("Saved", "Configuration saved!")

class MonitorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.log_box = tk.Text(self, height=20, wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)

        sys.stdout = TextRedirector(self.log_box, "stdout")
        sys.stderr = TextRedirector(self.log_box, "stderr")

        btn_frame = tk.Frame(self)
        btn_frame.pack()

        tk.Button(btn_frame, text="Start Monitor", command=self.start_monitor).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Stop Monitor", command=self.stop_monitor).pack(side="left", padx=5)

    def start_monitor(self):
        global monitor_thread, monitor_running
        if monitor_running:
            return
        monitor_running = True

        scheduler_bot.stop_event.clear()

        monitor_thread = threading.Thread(target=scheduler_bot.start_monitoring, daemon=True)
        monitor_thread.start()

        self.log("Monitoring started.")

    def stop_monitor(self):
        global monitor_running
        if monitor_running:
            monitor_running = False
            scheduler_bot.stop_event.set()
            try:
                if scheduler_bot.driver:
                    scheduler_bot.driver.quit()
                    self.log("ChromeDriver forcibly closed.")
            except Exception as e:
                self.log(f"Error closing driver: {e}")

            self.log("Monitoring stopped.")

    def log(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)

def main():
    root = tk.Tk()
    root.title("CollegeScheduler Monitor")

    icon_path = os.path.join(os.path.dirname(__file__), "scheduler_logo.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(default=icon_path)
        icon_image = Image.open(icon_path)
    else:
        icon_image = Image.new("RGB", (64, 64), "white")  # Fallback

    notebook = ttk.Notebook(root)
    monitor_tab = MonitorTab(notebook)
    config_tab = ConfigTab(notebook)

    notebook.add(monitor_tab, text="Monitor")
    notebook.add(config_tab, text="Config")
    notebook.pack(fill="both", expand=True)

    root.geometry("700x550")

    # Hide to tray function
    def hide_window():
        root.withdraw()
        show_tray_icon()

    # Show window again
    def show_window(icon, item):
        icon.stop()
        root.after(0, root.deiconify)

    # Quit from tray
    def quit_app(icon, item):
        icon.stop()
        root.destroy()

    # Show tray icon
    def show_tray_icon():
        menu = pystray.Menu(
            pystray.MenuItem("Show", show_window),
            pystray.MenuItem("Quit", quit_app)
        )
        tray_icon = pystray.Icon("CollegeScheduler Monitor", icon_image, "CollegeScheduler", menu)
        threading.Thread(target=tray_icon.run, daemon=True).start()

    # On minimize, hide window
    root.protocol("WM_DELETE_WINDOW", hide_window)
    root.bind("<Unmap>", lambda e: hide_window() if root.state() == "iconic" else None)

    root.mainloop()

if __name__ == "__main__":
    main()
