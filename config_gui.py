import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import sys
import requests
import pystray
import scheduler_bot

CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "TAMUClassSwap")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
COOKIE = ""

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config({})
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

data = load_config()
COOKIE = data.get("cookie", "")

# ---------------------------------------------------
# Compound widget for a course group:
#   Allows selection of a course and addition of multiple CRN entries.
# ---------------------------------------------------
class CourseGroupFrame(tk.Frame):
    def __init__(self, parent, remove_callback):
        """
        remove_callback: function to call (passing self) when this course group is to be removed.
        """
        super().__init__(parent, borderwidth=1, relief="groove", padx=5, pady=5)
        self.remove_callback = remove_callback
        self.course_var = tk.StringVar()
        self.crn_vars = []  # list of StringVar for CRNs

        # Row 0: Course selection and remove button.
        tk.Label(self, text="Course:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.course_dropdown = ttk.Combobox(self, textvariable=self.course_var, width=30)
        self.course_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        remove_btn = tk.Button(self, text="Remove Course", command=self.remove_self)
        remove_btn.grid(row=0, column=2, padx=5, pady=5)

        # Row 1: Frame to hold CRN entry widgets.
        self.crn_frame = tk.Frame(self)
        self.crn_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="we")
        # Row 2: "Add CRN" button for this course group.
        self.add_crn_btn = tk.Button(self, text="Add CRN", command=self.add_crn_field)
        self.add_crn_btn.grid(row=2, column=0, columnspan=3, padx=5, pady=5)

    def add_crn_field(self, value=""):
        var = tk.StringVar(value=value)
        row = len(self.crn_vars)
        entry = tk.Entry(self.crn_frame, textvariable=var, width=20)
        entry.grid(row=row, column=0, padx=5, pady=2, sticky="w")
        remove_btn = tk.Button(
            self.crn_frame,
            text="Remove",
            command=lambda: self.remove_crn_field(var, entry, remove_btn)
        )
        remove_btn.grid(row=row, column=1, padx=5, pady=2)
        self.crn_vars.append(var)

    def remove_crn_field(self, var, entry, btn):
        idx = self.crn_vars.index(var)
        entry.destroy()
        btn.destroy()
        self.crn_vars.pop(idx)

    def remove_self(self):
        if self.remove_callback:
            self.remove_callback(self)

    def get_crns(self):
        return [v.get() for v in self.crn_vars if v.get().strip()]

    def load_data(self, course_data):
        """
        Load a dictionary with keys: "course" and "crns".
        """
        self.course_var.set(course_data.get("course", ""))
        for crn in course_data.get("crns", []):
            self.add_crn_field(crn)

# ---------------------------------------------------
# ConfigTab now supports multiple courses (each with its own CRN list),
# plus new fields for username and password.
# ---------------------------------------------------
class ConfigTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        # Variables for required settings.
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.cookie_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.channel_var = tk.StringVar()
        self.id_var = tk.StringVar()
        self.term_var = tk.StringVar()
        self.type_var = tk.StringVar(value="watch")  # Default to "watch"
        self.sf_var = tk.StringVar()  # swap_from
        self.st_var = tk.StringVar()  # swap_to

        # A list to hold CourseGroupFrame instances.
        self.course_groups = []

        # Configure grid for anchoring bottom buttons/footer.
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(15, weight=1)

        self.build_ui()
        self.load_config_into_fields()
        self.update_type_fields()

    def fetch_terms(self):
        cookie = self.cookie_var.get() or COOKIE
        try:
            response = requests.get("https://tamu.collegescheduler.com/api/terms", headers={"Cookie": cookie})
            response.raise_for_status()
            return [term["title"] for term in response.json()]
        except Exception as e:
            print("Failed to fetch terms. Please check if your cookies are valid!")
            return []

    def fetch_courses(self, term_title):
        cookie = self.cookie_var.get() or COOKIE
        try:
            url = f"https://tamu.collegescheduler.com/api/terms/{term_title}/courses"
            response = requests.get(url, headers={"Cookie": cookie})
            response.raise_for_status()
            courses = response.json()
            return [
                f"{c['subjectShort']} {c['number']} - {c['title']}"
                for c in sorted(courses, key=lambda x: x['subjectShort'])
            ]
        except Exception as e:
            print("Failed to fetch courses. Please check if your cookies are valid!")
            return []

    def on_term_select(self, event):
        term = self.term_var.get()
        courses_list = self.fetch_courses(term)
        # Update all course group dropdowns.
        for cg in self.course_groups:
            cg.course_dropdown["values"] = courses_list

    def refresh_terms_and_courses(self):
        """Called when the user leaves the cookie field; refresh terms and course dropdowns."""
        new_terms = self.fetch_terms()
        self.term_dropdown['values'] = new_terms
        print("Terms refreshed:", new_terms)
        current_term = self.term_var.get()
        if current_term in new_terms:
            new_courses = self.fetch_courses(current_term)
            for cg in self.course_groups:
                cg.course_dropdown['values'] = new_courses

    def build_ui(self):
        # --- HEADER: Required Settings ---
        header_label = tk.Label(self, text="Required Settings", font=("Helvetica", 14, "bold"))
        header_label.grid(row=0, column=0, columnspan=3, pady=(10, 5))

        # CollegeScheduler Username.
        tk.Label(self, text="CollegeScheduler Username").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(self, textvariable=self.username_var, width=40).grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # CollegeScheduler Password.
        tk.Label(self, text="CollegeScheduler Password").grid(row=2, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(self, textvariable=self.password_var, show="*", width=40).grid(row=2, column=1, padx=5, pady=5, sticky="w")

        # CollegeScheduler Cookie with focus-out binding.
        tk.Label(self, text="CollegeScheduler Cookie").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        cookie_entry = tk.Entry(self, textvariable=self.cookie_var, show="*", width=40)
        cookie_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        cookie_entry.bind("<FocusOut>", lambda e: self.refresh_terms_and_courses())
        # (No Refresh Cookie button; automatic refresh in monitor.py)

        # Discord Token.
        tk.Label(self, text="Discord Token").grid(row=4, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(self, textvariable=self.token_var, show="*", width=40).grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Discord Channel Name.
        tk.Label(self, text="Discord Channel Name").grid(row=5, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(self, textvariable=self.channel_var, width=40).grid(row=5, column=1, padx=5, pady=5, sticky="w")

        # Discord Account ID.
        tk.Label(self, text="Discord Account ID").grid(row=6, column=0, padx=5, pady=5, sticky="e")
        tk.Entry(self, textvariable=self.id_var, width=40).grid(row=6, column=1, padx=5, pady=5, sticky="w")

        # Term Name.
        tk.Label(self, text="Term Name").grid(row=7, column=0, padx=5, pady=5, sticky="e")
        self.term_dropdown = ttk.Combobox(self, textvariable=self.term_var,
                                          values=self.fetch_terms(), state="readonly", width=37)
        self.term_dropdown.grid(row=7, column=1, padx=5, pady=5, sticky="w")
        self.term_dropdown.bind("<<ComboboxSelected>>", self.on_term_select)

        # --- HEADER: Select Mode ---
        mode_label = tk.Label(self, text="Select Mode", font=("Helvetica", 14, "bold"))
        mode_label.grid(row=8, column=0, columnspan=3, pady=(10, 5))

        # Radio Buttons for Watch vs. Swap.
        self.type_frame = tk.Frame(self)
        self.type_frame.grid(row=9, column=0, columnspan=3)
        tk.Label(self.type_frame, text="Type:").pack(side="left", padx=(0, 10))
        self.watch_radio = tk.Radiobutton(self.type_frame, text="Watch", variable=self.type_var,
                                          value="watch", command=self.update_type_fields)
        self.watch_radio.pack(side="left")
        self.swap_radio = tk.Radiobutton(self.type_frame, text="Swap", variable=self.type_var,
                                         value="swap", command=self.update_type_fields)
        self.swap_radio.pack(side="left")

        # --- WATCH MODE: Courses with CRNs -------------
        self.course_groups_container = tk.Frame(self)
        self.course_groups_container.grid(row=10, column=0, columnspan=3, sticky="we")
        self.add_course_btn = tk.Button(self, text="Add Course", command=self.add_course_group)
        self.add_course_btn.grid(row=11, column=0, columnspan=3, pady=5)

        # --- SWAP MODE: Swap From/To -------------
        self.swap_frame = tk.Frame(self)
        tk.Label(self.swap_frame, text="Swap From").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        tk.Entry(self.swap_frame, textvariable=self.sf_var, width=40).grid(row=0, column=1, padx=5, pady=2, sticky="w")
        tk.Label(self.swap_frame, text="Swap To").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        tk.Entry(self.swap_frame, textvariable=self.st_var, width=40).grid(row=1, column=1, padx=5, pady=2, sticky="w")
        self.swap_frame.grid(row=10, column=0, columnspan=3, sticky="we")

        # --- Bottom Buttons and Footer ---
        bottom_frame = tk.Frame(self)
        bottom_frame.grid(row=15, column=0, columnspan=3, sticky="we", padx=5, pady=5)
        self.save_button = tk.Button(bottom_frame, text="Save Config", command=self.save_fields_to_config)
        self.save_button.pack(side="right")
        self.footer_label = tk.Label(bottom_frame, text="Make sure to save config!", fg="gray")
        self.footer_label.pack(side="left")

    def add_course_group(self):
        """Add a new CourseGroupFrame to the container."""
        cg = CourseGroupFrame(self.course_groups_container, remove_callback=self.remove_course_group)
        cg.course_dropdown["values"] = self.fetch_courses(self.term_var.get())
        cg.pack(fill="x", pady=5, padx=5)
        self.course_groups.append(cg)

    def remove_course_group(self, course_group):
        """Remove the given course group."""
        course_group.destroy()
        self.course_groups.remove(course_group)

    def update_type_fields(self):
        """
        Show the course groups (and Add Course button) if 'watch' is selected,
        otherwise show the swap frame.
        """
        if self.type_var.get() == "watch":
            self.swap_frame.grid_remove()
            self.course_groups_container.grid(row=10, column=0, columnspan=3, sticky="we")
            self.add_course_btn.grid(row=11, column=0, columnspan=3, pady=5)
        else:
            self.course_groups_container.grid_remove()
            self.add_course_btn.grid_remove()
            self.swap_frame.grid(row=10, column=0, columnspan=3, sticky="we")

    def load_config_into_fields(self):
        global COOKIE
        data = load_config()
        self.username_var.set(data.get("username", ""))
        self.password_var.set(data.get("password", ""))
        self.token_var.set(data.get("discord_token", ""))
        self.channel_var.set(data.get("channel_name", ""))
        self.id_var.set(data.get("discord_account_id", ""))
        self.term_var.set(data.get("term_name", ""))
        self.type_var.set(data.get("type", "watch"))
        self.sf_var.set(data.get("swap_from", ""))
        self.st_var.set(data.get("swap_to", ""))
        self.cookie_var.set(data.get("cookie", ""))
        COOKIE = data.get("cookie", "")

        # Remove any previously existing course groups.
        for cg in self.course_groups:
            cg.destroy()
        self.course_groups = []

        # Load courses if available; expected structure is a list of dicts with keys "course" and "crns"
        courses_data = data.get("courses", [])
        if courses_data:
            for course_data in courses_data:
                cg = CourseGroupFrame(self.course_groups_container, remove_callback=self.remove_course_group)
                cg.course_dropdown["values"] = self.fetch_courses(self.term_var.get())
                cg.load_data(course_data)
                cg.pack(fill="x", pady=5, padx=5)
                self.course_groups.append(cg)

    def save_fields_to_config(self):
        # Gather courses data from all course groups.
        courses_data = []
        for cg in self.course_groups:
            course_entry = {
                "course": cg.course_var.get(),
                "crns": cg.get_crns()
            }
            courses_data.append(course_entry)

        data = {
            "username": self.username_var.get(),
            "password": self.password_var.get(),
            "discord_token": self.token_var.get(),
            "channel_name": self.channel_var.get(),
            "discord_account_id": self.id_var.get(),
            "term_name": self.term_var.get(),
            "type": self.type_var.get(),
            "swap_from": self.sf_var.get(),
            "swap_to": self.st_var.get(),
            "cookie": self.cookie_var.get(),
            "courses": courses_data
        }
        save_config(data)
        messagebox.showinfo("Saved", "Configuration saved!")
        global COOKIE
        COOKIE = self.cookie_var.get()
        self.update_type_fields()

class MonitorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.log_box = tk.Text(self, height=20, wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)
        sys.stdout = TextRedirector(self.log_box, "stdout")
        btn_frame = tk.Frame(self)
        btn_frame.pack()
        tk.Button(btn_frame, text="Start Monitor", command=self.start_monitor).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Stop Monitor", command=self.stop_monitor).pack(side="left", padx=5)

    def start_monitor(self):
        threading.Thread(target=scheduler_bot.start_monitoring, daemon=True).start()
        self.log("Monitoring started.")

    def stop_monitor(self):
        scheduler_bot.stop_monitoring()
        self.log("Monitoring stop requested and should soon stop.")

    def log(self, msg):
        self.log_box.insert(tk.END, msg + "\n")
        self.log_box.see(tk.END)

class TextRedirector:
    def __init__(self, text_widget, tag="stdout"):
        self.text_widget = text_widget
        self.tag = tag
    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)
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
        icon_image = Image.new("RGB", (64, 64), "white")  # Fallback

    notebook = ttk.Notebook(root)
    monitor_tab = MonitorTab(notebook)
    config_tab = ConfigTab(notebook)
    notebook.add(monitor_tab, text="Monitor")
    notebook.add(config_tab, text="Config")
    notebook.pack(fill="both", expand=True)

    # Hide-to-tray functions.
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
        tray_icon = pystray.Icon("CollegeScheduler Monitor", icon_image, "CollegeScheduler", menu)
        threading.Thread(target=tray_icon.run, daemon=True).start()

    root.protocol("WM_DELETE_WINDOW", hide_window)
    root.bind("<Unmap>", lambda e: hide_window() if root.state() == "iconic" else None)
    root.geometry("800x600")
    root.mainloop()

if __name__ == "__main__":
    main()