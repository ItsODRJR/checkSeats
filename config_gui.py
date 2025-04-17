# monitor_ui.py
import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image
import sys
import requests
import pystray
import scheduler_bot

# --- CONFIG PATHS & GLOBAL COOKIE ---
CONFIG_DIR  = os.path.join(os.environ["LOCALAPPDATA"], "TAMUClassSwap")
CONFIG_PATH = os.path.join(CONFIG_DIR,    "config.json")
COOKIE      = ""

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config({})
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

cfg = load_config()
COOKIE = cfg.get("cookie", "")

# ---------------------------------------------------
# COURSE GROUP FRAME now with a single CRN entry
# ---------------------------------------------------
class CourseGroupFrame(tk.Frame):
    def __init__(self, parent, remove_cb, fetch_by_crn_cb):
        super().__init__(parent, borderwidth=1, relief="groove", padx=5, pady=5)
        self.remove_cb       = remove_cb
        self.fetch_by_crn_cb = fetch_by_crn_cb
        self.crn_var         = tk.StringVar()
        self.course_title_var= tk.StringVar()

        # Row 0: CRN entry + Remove button
        tk.Label(self, text="CRN:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        e = tk.Entry(self, textvariable=self.crn_var, width=15)
        e.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        e.bind("<FocusOut>", self.on_crn_focus_out)
        tk.Button(self, text="Remove", command=self.remove_self).grid(row=0, column=2, padx=5, pady=5)

        # Row 1: read‑only course title
        tk.Label(self, text="Course:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        tk.Label(self, textvariable=self.course_title_var, width=40, anchor="w", relief="sunken")\
            .grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="w")

    def on_crn_focus_out(self, event):
        crn = self.crn_var.get().strip()
        if not crn:
            self.course_title_var.set("")
            return

        # show searching state
        self.course_title_var.set("searching…")
        self.update_idletasks()

        title = self.fetch_by_crn_cb(crn)
        if title:
            self.course_title_var.set(title)
        else:
            self.course_title_var.set("n/a")

    def remove_self(self):
        if self.remove_cb:
            self.remove_cb(self)

    def get_crn(self):
        return self.crn_var.get().strip()

# ---------------------------------------------------
# CONFIG TAB, adding fetch_by_crn()
# ---------------------------------------------------
class ConfigTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        # connection & Discord settings
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.cookie_var   = tk.StringVar()
        self.token_var    = tk.StringVar()
        self.channel_var  = tk.StringVar()
        self.id_var       = tk.StringVar()

        # term + mode
        self.term_var = tk.StringVar()
        self.type_var = tk.StringVar(value="watch")

        # swap fields
        self.sf_var = tk.StringVar()
        self.st_var = tk.StringVar()
        self.tc_var = tk.StringVar()

        # course‑groups
        self.course_groups = []
        self._term_map     = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(15, weight=1)

        self.build_ui()
        self.load_config_into_fields()
        self.update_type_fields()

    def fetch_terms(self):
        cookie = self.cookie_var.get() or COOKIE
        try:
            resp = requests.get(
                "https://howdy.tamu.edu/api/all-terms",
                headers={"Cookie": cookie},
                timeout=10
            )
            resp.raise_for_status()
            terms = resp.json()
            self._term_map = {
                t["STVTERM_DESC"]: t["STVTERM_CODE"]
                for t in terms
                if "STVTERM_DESC" in t and "STVTERM_CODE" in t
            }
            return list(self._term_map.keys())
        except Exception as e:
            print(f"[ConfigTab] Failed to fetch terms: {e}")
            return []

    def fetch_by_crn(self, crn):
        cookie    = self.cookie_var.get() or COOKIE
        term_desc = self.term_var.get()
        term_code = self._term_map.get(term_desc)
        if not term_code:
            return None

        payload = {
            "startRow":     0,
            "endRow":       0,
            "termCode":     term_code,
            "publicSearch": "Y",
            "crn":          crn
        }
        try:
            print(f"[ConfigTab] Looking up CRN {crn} for term {term_desc} ({term_code})")
            resp = requests.post(
                "https://howdy.tamu.edu/api/course-sections",
                json=payload,
                headers={"Cookie": cookie},
                timeout=10
            )
            resp.raise_for_status()
            data     = resp.json()
            sections = data if isinstance(data, list) else data.get("courseSections", [])
            for s in sections:
                if str(s.get("SWV_CLASS_SEARCH_CRN","")) == crn:
                    sub   = s["SWV_CLASS_SEARCH_SUBJECT"]
                    num   = s["SWV_CLASS_SEARCH_COURSE"]
                    title = s["SWV_CLASS_SEARCH_TITLE"]
                    return f"{sub} {num} – {title}"
        except Exception as e:
            print(f"[ConfigTab] CRN lookup error for {crn}: {e}")
        return None

    def refresh_terms_and_courses(self):
        terms = self.fetch_terms()
        self.term_dropdown["values"] = terms

    def on_term_select(self, _evt):
        for cg in self.course_groups:
            cg.course_title_var.set("")

    def build_ui(self):
        # --- REQUIRED SETTINGS ---
        tk.Label(self, text="Required Settings", font=("Helvetica",14,"bold"))\
            .grid(row=0, column=0, columnspan=3, pady=(10,5))
        tk.Label(self, text="CollegeScheduler Username")\
            .grid(row=1, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(self, textvariable=self.username_var, width=40)\
            .grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Label(self, text="CollegeScheduler Password")\
            .grid(row=2, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(self, textvariable=self.password_var, show="*", width=40)\
            .grid(row=2, column=1, sticky="w", padx=5, pady=5)

        tk.Label(self, text="CollegeScheduler Cookie")\
            .grid(row=3, column=0, sticky="e", padx=5, pady=5)
        ce = tk.Entry(self, textvariable=self.cookie_var, show="*", width=40)
        ce.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        ce.bind("<FocusOut>", lambda e: self.refresh_terms_and_courses())

        tk.Label(self, text="Discord Token")\
            .grid(row=4, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(self, textvariable=self.token_var, show="*", width=40)\
            .grid(row=4, column=1, sticky="w", padx=5, pady=5)

        tk.Label(self, text="Discord Channel Name")\
            .grid(row=5, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(self, textvariable=self.channel_var, width=40)\
            .grid(row=5, column=1, sticky="w", padx=5, pady=5)

        tk.Label(self, text="Discord Account ID")\
            .grid(row=6, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(self, textvariable=self.id_var, width=40)\
            .grid(row=6, column=1, sticky="w", padx=5, pady=5)

        tk.Label(self, text="Term Name")\
            .grid(row=7, column=0, sticky="e", padx=5, pady=5)
        self.term_dropdown = ttk.Combobox(
            self, textvariable=self.term_var,
            values=self.fetch_terms(), state="readonly", width=37
        )
        self.term_dropdown.grid(row=7, column=1, sticky="w", padx=5, pady=5)
        self.term_dropdown.bind("<<ComboboxSelected>>", self.on_term_select)

        # --- SELECT MODE ---
        tk.Label(self, text="Select Mode", font=("Helvetica",14,"bold"))\
            .grid(row=8, column=0, columnspan=3, pady=(10,5))
        mf = tk.Frame(self)
        mf.grid(row=9, column=0, columnspan=3)
        tk.Label(mf, text="Type:").pack(side="left", padx=(0,10))
        tk.Radiobutton(mf, text="Watch", variable=self.type_var,
                       value="watch", command=self.update_type_fields).pack(side="left")
        tk.Radiobutton(mf, text="Swap",  variable=self.type_var,
                       value="swap",  command=self.update_type_fields).pack(side="left")

        # --- WATCH: CRN groups ---
        self.course_groups_container = tk.Frame(self)
        self.course_groups_container.grid(row=10, column=0, columnspan=3, sticky="we")
        tk.Button(self, text="Add CRN", command=self.add_course_group)\
            .grid(row=11, column=0, columnspan=3, pady=5)

        # --- SWAP ---
        self.swap_frame = tk.Frame(self)
        tk.Label(self.swap_frame, text="Swap From").grid(row=0, column=0, sticky="e", padx=5, pady=2)
        tk.Entry(self.swap_frame, textvariable=self.sf_var, width=40)\
            .grid(row=0, column=1, sticky="w", padx=5, pady=2)
        tk.Label(self.swap_frame, text="Swap To").grid(row=1, column=0, sticky="e", padx=5, pady=2)
        tk.Entry(self.swap_frame, textvariable=self.st_var, width=40)\
            .grid(row=1, column=1, sticky="w", padx=5, pady=2)
        self.swap_frame.grid(row=10, column=0, columnspan=3, sticky="we")

        # --- SAVE BUTTON ---
        bf = tk.Frame(self)
        bf.grid(row=15, column=0, columnspan=3, sticky="we", padx=5, pady=5)
        tk.Button(bf, text="Save Config", command=self.save_fields_to_config)\
            .pack(side="right")
        tk.Label(bf, text="Make sure to save config!", fg="gray")\
            .pack(side="left")

    def add_course_group(self):
        cg = CourseGroupFrame(
            self.course_groups_container,
            remove_cb=self.remove_course_group,
            fetch_by_crn_cb=self.fetch_by_crn
        )
        cg.pack(fill="x", pady=5, padx=5)
        self.course_groups.append(cg)

    def remove_course_group(self, cg):
        cg.destroy()
        self.course_groups.remove(cg)

    def update_type_fields(self):
        if self.type_var.get() == "watch":
            self.swap_frame.grid_remove()
            self.course_groups_container.grid()
        else:
            self.course_groups_container.grid_remove()
            self.swap_frame.grid()

    def load_config_into_fields(self):
        global COOKIE
        data = load_config()
        # load basics
        self.username_var.set(data.get("username",""))
        self.password_var.set(data.get("password",""))
        self.cookie_var.set(data.get("cookie",""))
        COOKIE = data.get("cookie","")
        self.token_var.set(data.get("discord_token",""))
        self.channel_var.set(data.get("channel_name",""))
        self.id_var.set(data.get("discord_account_id",""))
        self.term_var.set(data.get("term_name",""))
        self.type_var.set(data.get("type","watch"))
        self.sf_var.set(data.get("swap_from",""))
        self.st_var.set(data.get("swap_to",""))

        # clear existing groups
        for cg in self.course_groups:
            cg.destroy()
        self.course_groups = []

        # re-create from saved CRNs
        for crn_entry in data.get("crns_to_watch", []):
            cg = CourseGroupFrame(
                self.course_groups_container,
                remove_cb=self.remove_course_group,
                fetch_by_crn_cb=self.fetch_by_crn
            )
            cg.crn_var.set(crn_entry)
            cg.pack(fill="x", pady=5, padx=5)
            cg.on_crn_focus_out(None)
            self.course_groups.append(cg)

    def save_fields_to_config(self):
        cfg = {
            "username":            self.username_var.get(),
            "password":            self.password_var.get(),
            "cookie":              self.cookie_var.get(),
            "discord_token":       self.token_var.get(),
            "channel_name":        self.channel_var.get(),
            "discord_account_id":  self.id_var.get(),
            "term_name":           self.term_var.get(),
            "type":                self.type_var.get(),
            "swap_from":           self.sf_var.get(),
            "swap_to":             self.st_var.get(),
            "crns_to_watch":       [cg.get_crn() for cg in self.course_groups]
        }
        save_config(cfg)
        messagebox.showinfo("Saved","Configuration saved!")
        global COOKIE
        COOKIE = self.cookie_var.get()
        self.update_type_fields()

# ---------------------------------------------------
# MonitorTab + main() remain unchanged
# ---------------------------------------------------
class MonitorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.log_box = tk.Text(self, height=20, wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)
        sys.stdout = TextRedirector(self.log_box)
        btn_frame = tk.Frame(self)
        btn_frame.pack()
        tk.Button(btn_frame, text="Start Monitor", command=self.start_monitor).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Stop Monitor",  command=self.stop_monitor).pack(side="left", padx=5)

    def start_monitor(self):
        threading.Thread(target=scheduler_bot.start_monitoring, daemon=True).start()
        self.log("Monitoring started.")

    def stop_monitor(self):
        scheduler_bot.stop_monitoring()
        self.log("Monitoring stop requested.")

    def log(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)

class TextRedirector:
    def __init__(self, widget):
        self.widget = widget
    def write(self, msg):
        self.widget.insert(tk.END, msg)
        self.widget.see(tk.END)
    def flush(self):
        pass

def main():
    root = tk.Tk()
    root.title("CollegeScheduler Monitor")

    icon_path = os.path.join(os.path.dirname(__file__), "scheduler_logo.ico")
    if os.path.exists(icon_path):
        root.iconbitmap(default=icon_path)
        icon_image = Image.open(icon_path)
    else:
        icon_image = Image.new("RGB", (64, 64), "white")

    notebook   = ttk.Notebook(root)
    monitor    = MonitorTab(notebook)
    config     = ConfigTab(notebook)
    notebook.add(monitor, text="Monitor")
    notebook.add(config,  text="Config")
    notebook.pack(fill="both", expand=True)

    def hide_window():
        root.withdraw()
        show_tray_icon()
    def show_window(icon, item):
        icon.stop()
        root.after(0, root.deiconify)
    def quit_app(icon, item):
        icon.stop()
        root.destroy()
    def show_tray_icon():
        menu = pystray.Menu(
            pystray.MenuItem("Show", show_window),
            pystray.MenuItem("Quit", quit_app)
        )
        tray = pystray.Icon("CollegeScheduler", icon_image, "CollegeScheduler", menu)
        threading.Thread(target=tray.run, daemon=True).start()

    root.protocol("WM_DELETE_WINDOW", hide_window)
    root.bind("<Unmap>", lambda e: hide_window() if root.state()=="iconic" else None)
    root.geometry("800x600")
    root.mainloop()

if __name__=="__main__":
    main()