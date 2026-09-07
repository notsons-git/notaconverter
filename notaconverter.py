import os
import re
import json
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

# Hide the Windows console when launched as a .py file.
def _hide_console():
    if os.name == "nt":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass

_hide_console()

try:
    from PIL import Image, ImageTk, ImageSequence
except ImportError:
    raise SystemExit("Please install Pillow")

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_AVAILABLE = False

APP_NAME = "NotAconverter"
CONFIG_PATH = Path.home() / ".notaconverter.json"
MAX_BYTES_HARD = 256 * 1024
MAX_SIDE_HARD = 512
MAX_DURATION_HARD = 3.0

BG = "#080b10"
PANEL = "#10151d"
PANEL_2 = "#141a23"
PANEL_3 = "#19212d"
PANEL_4 = "#202a38"
PREVIEW_BG = "#0b0f16"
TEXT = "#f3f5fa"
MUTED = "#8c98ab"
MUTED_2 = "#647086"
ACCENT = "#7557ff"
ACCENT_HOVER = "#896fff"
SUCCESS = "#49d492"
ERROR = "#ff6274"
WARNING = "#ffbd58"
DISABLED = "#4a5362"


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip(" .")
    return name or "sticker"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("980x720")
        self.root.minsize(760, 430)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.files = []
        self.selected_index = -1
        self.last_result = None
        self.worker = None
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.session_folder_override = ""
        self.progress_value = 0
        self.settings_window = None
        self._config_save_job = None

        self.preview_photo = None
        self.preview_path = None
        self.preview_image = None
        self.preview_gif = None
        self.preview_gif_index = 0
        self.preview_gif_frames = []
        self.preview_gif_after = None

        cfg = self._load_config()
        self.output_mode = tk.StringVar(value=cfg.get("output_mode", "first_file"))
        self.custom_folder = tk.StringVar(value=cfg.get("custom_folder", ""))
        self.max_side = tk.IntVar(value=min(int(cfg.get("max_side", 512)), MAX_SIDE_HARD))
        self.max_duration = tk.DoubleVar(value=min(float(cfg.get("max_duration", 3.0)), MAX_DURATION_HARD))
        self.fps = tk.IntVar(value=min(max(int(cfg.get("fps", 30)), 15), 60))
        self.max_size = tk.IntVar(value=min(max(int(cfg.get("max_size", 256)), 64), 256))
        self.keep_names = tk.BooleanVar(value=cfg.get("keep_names", True))
        self.overwrite = tk.BooleanVar(value=cfg.get("overwrite", True))
        self.open_after = tk.BooleanVar(value=cfg.get("open_after", False))

        self.ffmpeg_available = bool(shutil.which("ffmpeg"))
        self.ffprobe_available = bool(shutil.which("ffprobe"))
        self.dnd_available = DND_AVAILABLE

        self._build_ui()
        self._setup_dnd()
        self._update_dependency_label()
        self._update_folder_ui()
        self._update_export_state()
        self.root.after(60, self._poll_events)

    # ---------------- Config ----------------
    def _load_config(self):
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_config(self):
        data = {
            "output_mode": self.output_mode.get(),
            "custom_folder": self.custom_folder.get(),
            "max_side": int(self.max_side.get()),
            "max_duration": float(self.max_duration.get()),
            "fps": int(self.fps.get()),
            "max_size": int(self.max_size.get()),
            "keep_names": bool(self.keep_names.get()),
            "overwrite": bool(self.overwrite.get()),
            "open_after": bool(self.open_after.get()),
        }
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _queue_save_config(self):
        if self._config_save_job is not None:
            try:
                self.root.after_cancel(self._config_save_job)
            except Exception:
                pass
        self._config_save_job = self.root.after(250, self._save_config)

    # ---------------- UI helpers ----------------
    def _button(self, parent, text, command, accent=False, compact=False):
        b = tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if accent else PANEL_3,
            fg=TEXT,
            activebackground=ACCENT_HOVER if accent else PANEL_4,
            activeforeground=TEXT,
            disabledforeground="#6c7688",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI Semibold", 9 if compact else 10),
            cursor="hand2",
            padx=11 if compact else 14,
            pady=7 if compact else 10,
        )
        b._accent = accent
        b._enabled_bg = ACCENT if accent else PANEL_3
        b._hover_bg = ACCENT_HOVER if accent else PANEL_4

        def enter(_):
            if str(b["state"]) != "disabled":
                b.configure(bg=b._hover_bg)

        def leave(_):
            if str(b["state"]) != "disabled":
                b.configure(bg=b._enabled_bg)

        b.bind("<Enter>", enter)
        b.bind("<Leave>", leave)
        return b

    def _label(self, parent, text, size=10, color=TEXT, bold=False, bg=None, **kwargs):
        return tk.Label(
            parent,
            text=text,
            bg=bg if bg is not None else parent.cget("bg"),
            fg=color,
            font=("Segoe UI Semibold" if bold else "Segoe UI", size),
            bd=0,
            highlightthickness=0,
            **kwargs,
        )

    def _card(self, parent):
        return tk.Frame(parent, bg=PANEL_2, bd=0, highlightthickness=0)

    def _bind_mousewheel(self, widget, canvas):
        def wheel(event):
            try:
                if not canvas.winfo_exists():
                    return
                delta = int(-event.delta / 120) if event.delta else 0
                if delta:
                    canvas.yview_scroll(delta, "units")
            except tk.TclError:
                pass
        widget.bind("<MouseWheel>", wheel, add="+")

    def _recursive_bind_mousewheel(self, parent, canvas):
        self._bind_mousewheel(parent, canvas)
        for child in parent.winfo_children():
            self._recursive_bind_mousewheel(child, canvas)

    # ---------------- Main UI ----------------
    def _build_ui(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(18, 12))

        title_line = tk.Frame(header, bg=BG)
        title_line.pack(fill="x")
        self._label(title_line, APP_NAME, 25, TEXT, True, bg=BG).pack(side="left")
        self._label(title_line, "PNG / GIF → Telegram WebM", 11, MUTED, bg=BG).pack(side="left", padx=(12, 0), pady=(7, 0))

        self.settings_btn = self._button(title_line, "SETTINGS  ⚙", self.open_settings, compact=True)
        self.settings_btn.pack(side="right", pady=2)

        self.dependency_label = self._label(header, "", 8, ERROR, True, bg=BG, anchor="w", justify="left")
        self.dependency_label.pack(fill="x", pady=(5, 0))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)

        self.left = tk.Frame(body, bg=PANEL, bd=0, highlightthickness=0)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.right = tk.Frame(body, bg=PANEL, bd=0, highlightthickness=0)
        self.right.grid(row=0, column=1, sticky="nsew")

        self._build_left()
        self._build_right()

    def _build_left(self):
        head = tk.Frame(self.left, bg=PANEL)
        head.pack(fill="x", padx=18, pady=(15, 10))
        self._label(head, "Files", 12, TEXT, True, bg=PANEL).pack(side="left")
        self.file_count = self._label(head, "0", 9, MUTED, bg=PANEL_3, padx=8, pady=3)
        self.file_count.pack(side="left", padx=(8, 0))

        # File list sits directly under the header; drag & drop works on the whole window.
        list_host = tk.Frame(self.left, bg=PANEL)
        list_host.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        list_host.grid_rowconfigure(0, weight=1)
        list_host.grid_columnconfigure(0, weight=1)

        self.file_canvas = tk.Canvas(list_host, bg=PANEL, bd=0, highlightthickness=0)
        self.file_canvas.grid(row=0, column=0, sticky="nsew")
        # No visible scrollbar: scrolling is done with the mouse wheel and drag gesture.
        self.file_inner = tk.Frame(self.file_canvas, bg=PANEL)
        self.file_window = self.file_canvas.create_window((0, 0), window=self.file_inner, anchor="nw")
        self.file_inner.bind("<Configure>", self._sync_file_scroll)
        self.file_canvas.bind("<Configure>", self._sync_file_scroll)
        self._recursive_bind_mousewheel(list_host, self.file_canvas)

        actions = tk.Frame(self.left, bg=PANEL)
        actions.pack(fill="x", padx=16, pady=(0, 14))
        self._button(actions, "+  Add files", self.select_files, compact=True).pack(side="left")
        self._button(actions, "Clear", self.clear_files, compact=True).pack(side="left", padx=(8, 0))
        self._button(actions, "Open output", self.open_output, compact=True).pack(side="right")

    def _sync_file_scroll(self, _event=None):
        try:
            self.file_canvas.itemconfigure(self.file_window, width=self.file_canvas.winfo_width())
            self.file_canvas.configure(scrollregion=self.file_canvas.bbox("all"))
        except tk.TclError:
            pass

    def _build_right(self):
        self.right.grid_rowconfigure(0, weight=1)
        self.right.grid_rowconfigure(1, weight=0)
        self.right.grid_rowconfigure(2, weight=0)
        self.right.grid_rowconfigure(3, weight=0)
        self.right.grid_rowconfigure(4, weight=0)
        self.right.grid_columnconfigure(0, weight=1, minsize=260)

        # Preview block: fixed header row + flexible preview area.
        preview_card = self._card(self.right)
        preview_card.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 10))
        preview_card.grid_columnconfigure(0, weight=1)
        preview_card.grid_rowconfigure(1, weight=1)

        preview_title = self._label(
            preview_card, "Preview", 12, TEXT, True, bg=PANEL_2, anchor="w"
        )
        preview_title.grid(row=0, column=0, sticky="ew", padx=12, pady=(11, 8))

        self.preview_area = tk.Label(
            preview_card, text="Select a file", bg=PREVIEW_BG, fg=MUTED,
            font=("Segoe UI", 10), bd=0, highlightthickness=0
        )
        self.preview_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        self.preview_area.bind("<Configure>", self._resize_preview)

        self.preview_meta = self._label(
            preview_card, "PNG / GIF preview", 8, MUTED_2,
            bg=PANEL_2, anchor="w", justify="left"
        )
        self.preview_meta.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        # Folder block: title + current folder on one row + explanation below.
        folder_card = self._card(self.right)
        folder_card.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 9))
        folder_card.grid_columnconfigure(0, weight=1)

        folder_title = self._label(
            folder_card, "Export folder", 12, TEXT, True, bg=PANEL_2, anchor="w"
        )
        folder_title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 7))

        folder_row = tk.Frame(folder_card, bg=PANEL_2)
        folder_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 3))
        folder_row.grid_columnconfigure(0, weight=1)

        self.folder_display = self._label(
            folder_row, "—", 9, TEXT, True, bg=PANEL_2, anchor="w"
        )
        self.folder_display.grid(row=0, column=0, sticky="ew")

        self._button(
            folder_row, "Change folder", self.change_current_folder, compact=True
        ).grid(row=0, column=1, sticky="e", padx=(10, 0))

        self.folder_reason = self._label(
            folder_card, "", 8, MUTED_2, bg=PANEL_2,
            anchor="w", justify="left"
        )
        self.folder_reason.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))

        self.status_line = self._label(
            self.right, "Ready", 9, MUTED, bg=PANEL,
            anchor="w", justify="left"
        )
        self.status_line.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 5))

        self.export_btn = self._button(
            self.right, "EXPORT  →", self.start_conversion, accent=True
        )
        self.export_btn.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 7), ipady=6)

        self.progress = tk.Canvas(
            self.right, height=4, bg=PANEL_3,
            bd=0, highlightthickness=0
        )
        self.progress.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.progress.bind("<Configure>", lambda _e: self._draw_progress())


    # ---------------- Dependency status ----------------
    def _update_dependency_label(self):
        missing = []
        if not self.ffmpeg_available:
            missing.append("Please install FFmpeg")
        if not self.ffprobe_available:
            missing.append("Please install FFprobe")
        if not self.dnd_available:
            missing.append("Please install tkinterdnd2")
        self.dependency_label.config(text="  •  ".join(missing) if missing else "")

    # ---------------- Settings ----------------
    def open_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("NotAconverter — Settings")
        win.geometry("480x620")
        win.minsize(420, 500)
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()  # Main window is not interactive while settings is open.
        win.focus_force()
        win.lift()
        try:
            win.attributes("-topmost", True)
            win.after(150, lambda: win.attributes("-topmost", False) if win.winfo_exists() else None)
        except tk.TclError:
            pass

        def close_settings():
            try:
                win.grab_release()
            except tk.TclError:
                pass
            self._queue_save_config()
            self.settings_window = None
            win.destroy()
            self.root.lift()
            self.root.focus_force()
            self._update_folder_ui()
            self._update_export_state()

        win.protocol("WM_DELETE_WINDOW", close_settings)

        self._label(win, "Settings", 19, TEXT, True, bg=BG).pack(anchor="w", padx=24, pady=(20, 2))
        self._label(win, "Defaults used for future exports", 9, MUTED, bg=BG).pack(anchor="w", padx=24, pady=(0, 14))

        holder = tk.Frame(win, bg=BG)
        holder.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(holder, bg=BG, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        inner = tk.Frame(canvas, bg=BG)
        wid = canvas.create_window((0, 0), window=inner, anchor="nw")

        def sync(_=None):
            try:
                canvas.itemconfigure(wid, width=canvas.winfo_width())
                canvas.configure(scrollregion=canvas.bbox("all"))
            except tk.TclError:
                pass

        inner.bind("<Configure>", sync)
        canvas.bind("<Configure>", sync)
        self._recursive_bind_mousewheel(holder, canvas)

        card = self._card(inner)
        card.pack(fill="x", pady=6)
        self._label(card, "Output folder", 10, TEXT, True, bg=PANEL_2).pack(anchor="w", padx=14, pady=(12, 8))
        self._radio(card, "Automatic — same folder as first selected file", self.output_mode, "first_file", self._on_settings_change)
        self._radio(card, "Use a custom default folder", self.output_mode, "custom", self._on_settings_change)
        row = tk.Frame(card, bg=PANEL_2)
        row.pack(fill="x", padx=12, pady=(5, 12))
        self.settings_folder_entry = tk.Entry(
            row, textvariable=self.custom_folder, bg=PANEL_3, fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0, highlightthickness=0,
            font=("Segoe UI", 9)
        )
        self.settings_folder_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.settings_folder_entry.bind("<KeyRelease>", lambda _e: self._on_settings_change())
        self._button(row, "Browse", self.browse_default_folder, compact=True).pack(side="right", padx=(8, 0))

        card = self._card(inner)
        card.pack(fill="x", pady=6)
        self._label(card, "Telegram output", 10, TEXT, True, bg=PANEL_2).pack(anchor="w", padx=14, pady=(12, 9))
        self._slider(card, "Max side", self.max_side, 64, 512, 2, " px")
        self._slider(card, "Max duration", self.max_duration, 0.5, 3.0, 0.1, " s")
        self._slider(card, "Max file size", self.max_size, 64, 256, 1, " KiB")
        self._slider(card, "FPS", self.fps, 15, 60, 1, " fps")
        self._label(card, "Quality is automatically optimized for the selected size limit.",
                    8, MUTED_2, bg=PANEL_2, wraplength=400, justify="left").pack(fill="x", padx=14, pady=(4, 12))

        card = self._card(inner)
        card.pack(fill="x", pady=6)
        self._label(card, "Output behavior", 10, TEXT, True, bg=PANEL_2).pack(anchor="w", padx=14, pady=(12, 8))
        self._check(card, "Keep original file names", self.keep_names)
        self._check(card, "Overwrite existing WebM files", self.overwrite)
        self._check(card, "Open output folder when finished", self.open_after)
        self._label(card, "All changes are saved automatically.", 8, MUTED_2, bg=PANEL_2).pack(anchor="w", padx=14, pady=(4, 12))

        sync()

    def _radio(self, parent, text, variable, value, command=None):
        rb = tk.Radiobutton(
            parent, text=text, variable=variable, value=value, command=command,
            bg=PANEL_2, fg=TEXT, selectcolor=PANEL_3,
            activebackground=PANEL_2, activeforeground=TEXT,
            highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9), anchor="w"
        )
        rb.pack(fill="x", padx=9, pady=1)
        return rb

    def _check(self, parent, text, variable):
        cb = tk.Checkbutton(
            parent, text=text, variable=variable,
            bg=PANEL_2, fg=TEXT, selectcolor=PANEL_3,
            activebackground=PANEL_2, activeforeground=TEXT,
            highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9), anchor="w",
            command=self._on_settings_change
        )
        cb.pack(fill="x", padx=9, pady=1)
        return cb

    def _slider(self, parent, label, variable, lo, hi, step=1, suffix=""):
        box = tk.Frame(parent, bg=PANEL_2)
        box.pack(fill="x", padx=12, pady=(3, 2))
        row = tk.Frame(box, bg=PANEL_2)
        row.pack(fill="x")
        self._label(row, label, 8, MUTED, bg=PANEL_2).pack(side="left")
        value_label = self._label(row, "", 8, TEXT, True, bg=PANEL_2)
        value_label.pack(side="right")

        def update(v):
            num = round(float(v) / step) * step
            num = int(num) if isinstance(variable, tk.IntVar) else round(num, 1)
            variable.set(num)
            value_label.config(text=f"{num:g}{suffix}")
            self._on_settings_change()

        scale = tk.Scale(
            box, from_=lo, to=hi, resolution=step, orient="horizontal",
            variable=variable, command=update, showvalue=False,
            bg=PANEL_2, fg=MUTED, troughcolor=PANEL_3,
            activebackground=ACCENT, highlightthickness=0, bd=0,
            sliderrelief="flat", relief="flat", borderwidth=0
        )
        scale.pack(fill="x", pady=(0, 4))
        update(variable.get())
        return scale

    def _on_settings_change(self):
        self._queue_save_config()
        self._update_folder_ui()

    def browse_default_folder(self):
        folder = filedialog.askdirectory(parent=self.settings_window, title="Choose default export folder")
        if folder:
            self.custom_folder.set(folder)
            self.output_mode.set("custom")
            self._on_settings_change()

    # ---------------- DnD ----------------
    def _setup_dnd(self):
        if not DND_AVAILABLE:
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._drop_files)
            self._register_dnd_recursive(self.root)
        except Exception:
            pass

    def _register_dnd_recursive(self, widget):
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._drop_files)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._register_dnd_recursive(child)

    def _drop_files(self, event):
        try:
            paths = self.root.tk.splitlist(event.data)
        except Exception:
            paths = []
        self._add_paths(paths)

    # ---------------- Files ----------------
    def select_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PNG / GIF files",
            filetypes=[("PNG / GIF", "*.png *.gif"), ("PNG", "*.png"), ("GIF", "*.gif")],
        )
        self._add_paths(paths)

    def _add_paths(self, paths):
        added = 0
        for raw in paths:
            p = os.path.normpath(raw.strip("{}"))
            if os.path.isfile(p) and Path(p).suffix.lower() in {".png", ".gif"} and p not in self.files:
                self.files.append(p)
                added += 1
        if added:
            self._refresh_file_rows()
            self._select_index(len(self.files) - added if added == 1 else len(self.files) - 1)
            self._update_export_state()
            self._update_folder_ui()
            self._set_status("Ready", MUTED)

    def clear_files(self):
        self.files.clear()
        self.selected_index = -1
        self.last_result = None
        self._stop_preview_animation()
        self._refresh_file_rows()
        self._clear_preview()
        self._update_export_state()
        self._update_folder_ui()
        self._set_status("Ready", MUTED)
        self._draw_progress(0)

    def _refresh_file_rows(self):
        for child in self.file_inner.winfo_children():
            child.destroy()

        for idx, p in enumerate(self.files):
            try:
                size = fmt_size(os.path.getsize(p))
            except OSError:
                size = "?"
            typ = Path(p).suffix.upper().replace(".", "")

            row = tk.Frame(self.file_inner, bg=PANEL_2, bd=0, highlightthickness=0, cursor="hand2")
            row.pack(fill="x", pady=(0, 2))
            row.bind("<Button-1>", lambda _e, i=idx: self._select_index(i))
            row.bind("<MouseWheel>", self._file_wheel)

            name = self._label(row, Path(p).name, 9, TEXT, bg=PANEL_2, anchor="w")
            name.pack(side="left", fill="x", expand=True, padx=(11, 5), pady=9)
            size_label = self._label(row, size, 8, MUTED, bg=PANEL_2, width=9, anchor="e")
            size_label.pack(side="left", padx=4)
            type_label = self._label(row, typ, 8, MUTED, bg=PANEL_2, width=6, anchor="center")
            type_label.pack(side="right", padx=(4, 9))

            # Every visible part of a row selects that file.
            for child in (name, size_label, type_label):
                child.bind("<Button-1>", lambda _e, i=idx: self._select_index(i))
                child.bind("<MouseWheel>", self._file_wheel)

        self.file_count.config(text=str(len(self.files)))
        self.file_inner.update_idletasks()
        self._sync_file_scroll()
        self._refresh_selection_visuals()

    def _file_wheel(self, event):
        try:
            self.file_canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass
        return "break"

    def _select_index(self, idx):
        if not (0 <= idx < len(self.files)):
            return
        self.selected_index = idx
        self._refresh_selection_visuals()
        self._show_preview(self.files[idx])

    def _refresh_selection_visuals(self):
        for idx, row in enumerate(self.file_inner.winfo_children()):
            selected = idx == self.selected_index
            bg = "#292243" if selected else PANEL_2
            row.config(bg=bg)
            for child in row.winfo_children():
                try:
                    child.config(bg=bg)
                except tk.TclError:
                    pass

    # ---------------- Folder ----------------
    def _default_folder(self):
        if self.output_mode.get() == "custom":
            return self.custom_folder.get().strip()
        return str(Path(self.files[0]).parent) if self.files else ""

    def _current_export_folder(self):
        return self.session_folder_override or self._default_folder()

    def _update_folder_ui(self):
        folder = self._current_export_folder()
        self.folder_display.config(text=Path(folder).name if folder else "No folder selected")
        if self.session_folder_override:
            reason = f"Temporary folder for this export session.\n{folder}"
        elif self.output_mode.get() == "custom":
            reason = f"Default folder from Settings.\n{folder or 'Choose a default folder'}"
        else:
            reason = "Automatic: uses the folder of the first selected file."
        self.folder_reason.config(text=reason)

    def change_current_folder(self):
        folder = filedialog.askdirectory(title="Choose export folder for this session")
        if folder:
            self.session_folder_override = folder
            self._update_folder_ui()
            self._set_status("Export folder changed for this session.", MUTED)

    def open_output(self):
        folder = self._current_export_folder()
        if not folder and self.last_result:
            folder = str(Path(self.last_result).parent)
        if not folder or not os.path.isdir(folder):
            self._set_status("Output folder is not available yet.", ERROR)
            return
        try:
            os.startfile(folder)
        except Exception as exc:
            try:
                subprocess.Popen(["explorer", folder], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception as exc2:
                self._set_status(str(exc2 or exc), ERROR)

    # ---------------- Animated preview ----------------
    def _stop_preview_animation(self):
        if self.preview_gif_after:
            try:
                self.root.after_cancel(self.preview_gif_after)
            except tk.TclError:
                pass
        self.preview_gif_after = None
        self.preview_gif = None
        self.preview_gif_frames = []
        self.preview_gif_index = 0

    def _show_preview(self, path):
        self._stop_preview_animation()
        self.preview_photo = None
        self.preview_path = path
        try:
            with Image.open(path) as src:
                frames = getattr(src, "n_frames", 1)
                if Path(path).suffix.lower() == ".gif" and frames > 1:
                    self.preview_gif = Image.open(path)
                    self.preview_gif.seek(0)
                    self.preview_gif_frames = []
                    durations = []
                    for frame in ImageSequence.Iterator(self.preview_gif):
                        self.preview_gif_frames.append(frame.convert("RGBA").copy())
                        durations.append(max(20, int(frame.info.get("duration", 80))))
                        if len(self.preview_gif_frames) >= 180:
                            break
                    self.preview_gif_durations = durations
                    first = self.preview_gif_frames[0]
                    self.preview_image = first
                    self.preview_meta.config(text=f"{Path(path).name}\n{first.width} × {first.height} px • {frames} frame(s) • animated")
                    self._resize_preview()
                    self._animate_gif()
                else:
                    im = src.convert("RGBA")
                    self.preview_image = im.copy()
                    self.preview_meta.config(text=f"{Path(path).name}\n{im.width} × {im.height} px • {'PNG' if Path(path).suffix.lower()=='.png' else 'GIF'}")
                    self._resize_preview()
        except Exception as exc:
            self.preview_image = None
            self.preview_area.config(image="", text="Preview unavailable")
            self.preview_meta.config(text=str(exc)[:200])

    def _animate_gif(self):
        if not self.preview_gif_frames or self.preview_path is None:
            return
        if self.preview_path != getattr(self, "preview_path", None):
            return
        frame = self.preview_gif_frames[self.preview_gif_index]
        self.preview_image = frame
        self._resize_preview()
        duration = self.preview_gif_durations[self.preview_gif_index]
        self.preview_gif_index = (self.preview_gif_index + 1) % len(self.preview_gif_frames)
        self.preview_gif_after = self.root.after(duration, self._animate_gif)

    def _clear_preview(self):
        self.preview_photo = None
        self.preview_image = None
        self.preview_path = None
        self._stop_preview_animation()
        self.preview_area.config(image="", text="Select a file")
        self.preview_meta.config(text="PNG / GIF preview")

    def _resize_preview(self, _event=None):
        if self.preview_image is None:
            return
        max_w = max(80, self.preview_area.winfo_width() - 18)
        max_h = max(80, self.preview_area.winfo_height() - 18)
        im = self.preview_image.copy()
        im.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(im)
        self.preview_area.config(image=self.preview_photo, text="")

    # ---------------- Status / export ----------------
    def _set_status(self, text, color=MUTED):
        self.status_line.config(text=text, fg=color)

    def _draw_progress(self, value=None):
        if value is not None:
            self.progress_value = max(0, min(float(value), 100))
        self.progress.delete("all")
        w = self.progress.winfo_width()
        if w > 0 and self.progress_value > 0:
            self.progress.create_rectangle(0, 0, w * self.progress_value / 100, 4, fill=ACCENT, outline="")

    def _update_export_state(self):
        deps_ok = self.ffmpeg_available and self.ffprobe_available
        ready = bool(self.files) and deps_ok and not (self.worker and self.worker.is_alive())
        self.export_btn.config(state="normal" if ready else "disabled")
        self.export_btn.config(bg=ACCENT if ready else PANEL_4, fg=TEXT if ready else "#70798a")
        self.export_btn._enabled_bg = ACCENT if ready else PANEL_4
        self.export_btn._hover_bg = ACCENT_HOVER if ready else PANEL_4

    def _validate(self):
        if not self.files:
            return "Add at least one PNG or GIF file."
        if not self.ffmpeg_available or not self.ffprobe_available:
            return "FFmpeg / FFprobe is missing."
        folder = self._current_export_folder()
        if not folder:
            return "Choose an export folder."
        if not os.path.isdir(folder):
            return "The export folder does not exist."
        return ""

    def start_conversion(self):
        if self.worker and self.worker.is_alive():
            return
        error = self._validate()
        if error:
            self._set_status(error, ERROR)
            return

        self._save_config()
        self.cancel_event.clear()
        self.export_btn.config(state="disabled", bg=PANEL_4)
        self._draw_progress(0)
        self._set_status(f"Preparing {len(self.files)} file(s)…", MUTED)
        self.worker = threading.Thread(target=self._convert_all, daemon=True)
        self.worker.start()

    # ---------------- FFmpeg ----------------
    def _ffprobe_duration(self, path):
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        try:
            return max(0.05, float(r.stdout.strip()))
        except Exception:
            return 1.0

    def _has_alpha(self, path):
        try:
            with Image.open(path) as im:
                return im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        except Exception:
            return True

    def _build_filter(self):
        max_side = min(MAX_SIDE_HARD, max(64, int(self.max_side.get())))
        fps = min(60, max(15, int(self.fps.get())))
        return (
            f"fps={fps},"
            f"scale='if(gt(iw,ih),{max_side},-2)':'if(gt(iw,ih),-2,{max_side})':flags=lanczos,"
            "setsar=1"
        )

    def _build_ffmpeg_cmd(self, src, temp, duration, crf=None, bitrate=None):
        ext = Path(src).suffix.lower()
        pix_fmt = "yuva420p" if self._has_alpha(src) else "yuv420p"
        fps = min(60, max(15, int(self.fps.get())))
        vf = self._build_filter()
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if ext == ".png":
            cmd += ["-loop", "1", "-framerate", str(fps), "-i", src]
        else:
            cmd += ["-i", src]
        cmd += ["-t", f"{duration:.3f}", "-vf", vf, "-c:v", "libvpx-vp9"]
        if crf is not None:
            cmd += ["-crf", str(crf), "-b:v", "0"]
        else:
            cmd += ["-b:v", str(max(10000, int(bitrate)))]
        cmd += [
            "-pix_fmt", pix_fmt,
            "-auto-alt-ref", "0",
            "-deadline", "good",
            "-cpu-used", "1",
            "-row-mt", "1",
            "-an", "-f", "webm", temp,
        ]
        return cmd

    def _encode_candidate(self, src, temp, duration, crf=None, bitrate=None):
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except OSError:
            pass
        r = subprocess.run(
            self._build_ffmpeg_cmd(src, temp, duration, crf, bitrate),
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-600:] or "ffmpeg failed")
        return os.path.getsize(temp)

    def _convert_one(self, src, out):
        ext = Path(src).suffix.lower()
        duration = 1.0 if ext == ".png" else min(self._ffprobe_duration(src), min(float(self.max_duration.get()), MAX_DURATION_HARD))
        duration = max(0.05, duration)
        limit = min(MAX_BYTES_HARD, max(64 * 1024, int(self.max_size.get()) * 1024))
        temp = out + ".tmp.webm"

        lo, hi = 0, 50
        best_crf = None
        while lo <= hi and not self.cancel_event.is_set():
            crf = (lo + hi) // 2
            size = self._encode_candidate(src, temp, duration, crf=crf)
            if size <= limit:
                best_crf = crf
                hi = crf - 1
            else:
                lo = crf + 1

        if self.cancel_event.is_set():
            raise RuntimeError("Cancelled")

        if best_crf is None:
            bitrate = int((limit * 8 * 0.78) / duration)
            size = self._encode_candidate(src, temp, duration, bitrate=bitrate)
            if size > limit:
                bitrate = int((limit * 8 * 0.60) / duration)
                size = self._encode_candidate(src, temp, duration, bitrate=bitrate)
            if size > limit:
                raise RuntimeError(f"Could not fit under {limit // 1024} KiB")
        else:
            size = self._encode_candidate(src, temp, duration, crf=best_crf)
            if size > limit:
                best_crf = min(50, best_crf + 1)
                size = self._encode_candidate(src, temp, duration, crf=best_crf)

        if size > limit:
            raise RuntimeError(f"Output is {fmt_size(size)}, above the selected limit")
        os.replace(temp, out)
        return size, duration, best_crf

    def _convert_all(self):
        total = len(self.files)
        done = 0
        errors = []
        result_paths = []
        seen_outputs = set()
        export_dir = self._current_export_folder()
        try:
            os.makedirs(export_dir, exist_ok=True)
        except Exception as exc:
            self.events.put(("finished", 0, total, [str(exc)], [], False))
            return

        for src in list(self.files):
            if self.cancel_event.is_set():
                break
            try:
                self.events.put(("status", f"Encoding {Path(src).name}…"))
                base = safe_name(Path(src).stem) if self.keep_names.get() else f"sticker_{done + 1}"
                out = os.path.join(export_dir, base + ".webm")
                if not self.overwrite.get():
                    counter = 1
                    candidate = out
                    while os.path.exists(candidate):
                        candidate = os.path.join(export_dir, f"{base}_{counter}.webm")
                        counter += 1
                    out = candidate
                elif out in seen_outputs:
                    out = os.path.join(export_dir, f"{base}_{done + 1}.webm")

                size, duration, crf = self._convert_one(src, out)
                seen_outputs.add(out)
                result_paths.append(out)
                done += 1
                self.events.put(("progress", done / total * 100))
                quality = f"CRF {crf}" if crf is not None else "optimized bitrate"
                self.events.put(("status", f"✓ {Path(src).name}  •  {fmt_size(size)}  •  {quality}"))
            except Exception as exc:
                if str(exc) == "Cancelled":
                    break
                errors.append(f"{Path(src).name}: {exc}")

        self.events.put(("finished", done, total, errors, result_paths, self.cancel_event.is_set()))

    # ---------------- Event loop ----------------
    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self._set_status(event[1], MUTED)
                elif kind == "progress":
                    self._draw_progress(event[1])
                elif kind == "finished":
                    _, done, total, errors, result_paths, cancelled = event
                    self.worker = None
                    self.last_result = result_paths[-1] if result_paths else None
                    self._update_export_state()
                    self._save_config()
                    if cancelled:
                        self._set_status(f"Cancelled • {done}/{total}", WARNING)
                    elif errors:
                        self._draw_progress(done / total * 100 if total else 0)
                        self._set_status(f"Done with errors • {done}/{total}\n{errors[0]}", ERROR)
                    else:
                        self._draw_progress(100)
                        self._set_status(f"DONE • {done} file(s)", SUCCESS)
                        if self.open_after.get():
                            self.open_output()
        except queue.Empty:
            pass
        try:
            self.root.after(60, self._poll_events)
        except tk.TclError:
            pass

    def _on_close(self):
        self._save_config()
        self.cancel_event.set()
        self._stop_preview_animation()
        self.root.destroy()


def make_root():
    if DND_AVAILABLE:
        return TkinterDnD.Tk()
    return tk.Tk()


def main():
    root = make_root()
    try:
        root.iconname(APP_NAME)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
