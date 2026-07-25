import os
import time
import pyautogui
import speech_recognition as sr
from google import genai
import pygame
import asyncio
import ctypes
import edge_tts
import webbrowser
import urllib.parse
import requests
import datetime
import io
import math
import tempfile
import queue
import random
import threading
import tkinter as tk
from tkinter import ttk

# =====================================================================
# 1. INITIALIZATION & CONFIGURATION
# =====================================================================

API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR API KEY HERE")
client = genai.Client(api_key=API_KEY)

SYSTEM_INSTRUCTION = (
    "You are Prabhat, a helpful, concise AI voice assistant. "
    "Respond in 1 to 2 sentences. You are talking to your creator, Shaurya."
)
MODEL_CANDIDATES = [
    os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
chat_session = None
active_model = None


def create_chat_session(model_name):
    return client.chats.create(
        model=model_name,
        config={"system_instruction": SYSTEM_INSTRUCTION},
    )


def ask_brain(prompt):
    """Send a prompt to Gemini, trying backup models if one is unavailable."""
    global chat_session, active_model
    errors = []

    for model_name in MODEL_CANDIDATES:
        try:
            if chat_session is None or active_model != model_name:
                ui_status(f"Connecting to {model_name}...")
                chat_session = create_chat_session(model_name)
                active_model = model_name

            response = chat_session.send_message(prompt)
            return response.text
        except Exception as error:
            errors.append(f"{model_name}: {error}")
            chat_session = None
            active_model = None

    raise RuntimeError(" | ".join(errors))

pygame.mixer.pre_init(frequency=24000, size=-16, channels=2, buffer=4096)
pygame.mixer.init()
recognizer = sr.Recognizer()

ui_events = queue.Queue()
shutdown_event = threading.Event()
screen_control_enabled = False
pause_event = threading.Event()



def ui_status(message):
    ui_events.put(("status", message))


def ui_log(speaker, message):
    ui_events.put(("log", speaker, message))


class JarvisUI:
    """Clean JARVIS-style dashboard with cards, chat, and a central listening core."""

    def __init__(self, root):
        self.root = root
        self.root.title("PRABHAT AI")
        self.root.geometry("1600x900")
        self.root.minsize(1200, 720)
        self.root.configure(bg="#050714")
        self.tick = 0
        self.start_time = time.time()
        self.status = tk.StringVar(value="Listening for wake word...")
        self.uptime = tk.StringVar(value="00:00:00")
        self.clock_text = tk.StringVar(value="")
        self.date_text = tk.StringVar(value="")
        self.command_count = 0
        self.spectrum_bars = [random.randint(20, 92) for _ in range(18)]
        self.core_particles = [
            {
                "angle": random.random() * math.tau,
                "radius": random.randint(82, 180),
                "speed": random.uniform(0.006, 0.026),
                "size": random.randint(2, 5),
            }
            for _ in range(58)
        ]
        self.camera_enabled = False
        self.camera_capture = None
        self.camera_photo = None

        self.colors = {
            "bg": "#050714",
            "panel": "#0b1422",
            "panel2": "#111f31",
            "card": "#0d1b2c",
            "line": "#5bc8ff",
            "line2": "#9f7cff",
            "cyan": "#8fe9ff",
            "cyan2": "#48c8ff",
            "text": "#eefaff",
            "muted": "#a8bfd0",
            "green": "#48f28a",
        }

        self._build_layout()
        self._animate()
        self._process_events()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _rounded_rect(self, canvas, x1, y1, x2, y2, radius=24, fill="#07121a", outline="#114563", width=1, tags=None, stipple=""):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=30, fill=fill, outline=outline, width=width, tags=tags, stipple=stipple)

    def _round_button(self, parent, text, command, width=56, height=50, fill="#07121a", hover="#0d2230", outline=None, font_size=16):
        outline = outline or self.colors["line"]
        button = tk.Canvas(parent, width=width, height=height, bg=self.colors["bg"], highlightthickness=0, bd=0, cursor="hand2")
        shape = self._rounded_rect(button, 2, 2, width - 2, height - 2, 16, fill, outline, 1, "shape")
        label = button.create_text(width / 2, height / 2, text=text, fill=self.colors["text"], font=("Segoe UI", font_size, "bold"))

        def enter(event):
            button.itemconfigure(shape, fill=hover)

        def leave(event):
            button.itemconfigure(shape, fill=fill)

        def click(event):
            command()

        button.bind("<Enter>", enter)
        button.bind("<Leave>", leave)
        button.bind("<Button-1>", click)
        button._shape = shape
        button._label = label
        button._fill = fill
        button._hover = hover
        return button

    def _round_label(self, parent, text=None, textvariable=None, width=220, height=42, fill="#07121a", outline=None, font_size=11):
        outline = outline or self.colors["line"]
        pill = tk.Canvas(parent, width=width, height=height, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self._rounded_rect(pill, 1, 1, width - 1, height - 1, 14, fill, outline, 1, "shape")
        pill.create_text(
            width / 2,
            height / 2,
            text=text or "",
            fill=self.colors["text"],
            font=("Segoe UI", font_size, "bold"),
            tags="label",
        )
        if textvariable is not None:
            def sync(*_):
                pill.itemconfigure("label", text=textvariable.get())
            textvariable.trace_add("write", sync)
            sync()
        return pill

    def _card(self, parent, title, icon="", height=None):
        shell = tk.Canvas(parent, bg=self.colors["bg"], highlightthickness=0, bd=0, height=height or 160)
        content = tk.Frame(shell, bg=self.colors["panel"])
        win = shell.create_window(14, 14, anchor="nw", window=content)

        def redraw(event):
            shell.delete("shape")
            w, h = max(event.width, 20), max(event.height, 20)
            self._rounded_rect(shell, 1, 1, w - 1, h - 1, 24, self.colors["panel"], self.colors["line"], 1, "shape")
            self._rounded_rect(shell, 7, 7, w - 7, 54, 18, self.colors["panel2"], self.colors["panel2"], 1, "shape")
            shell.create_rectangle(7, 30, w - 7, 54, fill=self.colors["panel2"], outline="", tags="shape")
            shell.create_line(10, 54, w - 10, 54, fill=self.colors["line"], tags="shape")
            shell.itemconfigure(win, width=max(w - 28, 1), height=max(h - 28, 1))
            shell.tag_lower("shape")

        shell.bind("<Configure>", redraw)
        header = tk.Frame(content, bg=self.colors["panel2"], height=36)
        header.pack(fill="x")
        tk.Label(header, text=f"{icon} {title}".strip(), fg=self.colors["cyan"], bg=self.colors["panel2"], font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", padx=8, pady=8)
        tk.Label(header, text="⟳", fg="#85a9b8", bg=self.colors["panel2"], font=("Segoe UI", 12, "bold")).pack(side="right", padx=8)
        body = tk.Frame(content, bg=self.colors["panel"])
        body.pack(fill="both", expand=True, padx=0, pady=(8, 0))
        body.grid_columnconfigure(0, weight=1)
        return shell, body

    def _mini_stat(self, parent, label, value, col):
        box = tk.Frame(parent, bg=self.colors["card"])
        box.grid(row=0, column=col, sticky="ew", padx=4, pady=6)
        tk.Label(box, text=label, fg=self.colors["cyan"], bg=self.colors["card"], font=("Segoe UI", 8)).pack(pady=(7, 0))
        tk.Label(box, text=value, fg=self.colors["cyan"], bg=self.colors["card"], font=("Consolas", 10, "bold")).pack(pady=(0, 7))
        return box

    def _bar(self, parent, label, value, pct, row):
        frame = tk.Frame(parent, bg=self.colors["panel"])
        frame.grid(row=row, column=0, sticky="ew", padx=12, pady=4)
        frame.grid_columnconfigure(0, weight=1)
        tk.Label(frame, text=label, fg=self.colors["text"], bg=self.colors["panel"], font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(frame, text=value, fg=self.colors["cyan"], bg=self.colors["panel"], font=("Consolas", 8, "bold"), anchor="e").grid(row=0, column=1)
        c = tk.Canvas(frame, height=6, bg=self.colors["panel"], highlightthickness=0)
        c.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        def draw(event):
            c.delete("all")
            w = max(c.winfo_width(), 1)
            c.create_rectangle(0, 0, w, 6, fill="#4a5565", outline="")
            c.create_rectangle(0, 0, w * pct, 6, fill="#1dd8ef", outline="")
        c.bind("<Configure>", draw)

    def _build_layout(self):
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self.background_canvas = tk.Canvas(self.root, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.background_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)

        top = tk.Frame(self.root, bg=self.colors["bg"], height=72)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        tk.Label(top, text="P.R.A.B.H.A.T", fg=self.colors["cyan"], bg=self.colors["bg"], font=("Consolas", 18, "bold")).grid(row=0, column=0, padx=22, pady=22, sticky="w")
        online = tk.Label(top, text="● Online", fg=self.colors["green"], bg="#0d2a22", font=("Segoe UI", 9, "bold"), padx=12, pady=5)
        online.grid(row=0, column=0, padx=(210, 0), sticky="w")

        center_top = tk.Frame(top, bg=self.colors["bg"])
        center_top.grid(row=0, column=1, pady=16)
        self.time_pill = tk.Canvas(center_top, width=300, height=44, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.time_pill.pack(side="left")
        self._rounded_rect(self.time_pill, 1, 1, 299, 43, 15, "#07121a", self.colors["line"], 1, "shape")
        self.clock_canvas_text = self.time_pill.create_text(92, 22, text="", fill=self.colors["text"], font=("Consolas", 12, "bold"))
        self.time_pill.create_text(150, 22, text="|", fill=self.colors["cyan"], font=("Consolas", 12, "bold"))
        self.date_canvas_text = self.time_pill.create_text(222, 22, text="", fill=self.colors["text"], font=("Segoe UI", 11, "bold"))

        top_right = tk.Frame(top, bg=self.colors["bg"])
        top_right.grid(row=0, column=2, padx=20, sticky="e")
        self._round_label(top_right, text="♨ 25.2°C  Mumbai", width=165, height=44, fill="#07121a", outline=self.colors["line"], font_size=10).pack(side="left", padx=(0, 12))
        self._round_button(top_right, "⚙", self.open_settings, 48, 44, "#07121a", "#0d2535", self.colors["line"], 14).pack(side="left")

        tk.Frame(self.root, bg="#102b3b", height=1).grid(row=0, column=0, sticky="sew")

        main = tk.Frame(self.root, bg=self.colors["bg"])
        main.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        main.grid_columnconfigure(0, weight=0, minsize=470)
        main.grid_columnconfigure(1, weight=2)
        main.grid_columnconfigure(2, weight=0, minsize=500)
        main.grid_rowconfigure(0, weight=1)

        left = tk.Frame(main, bg=self.colors["bg"], width=470)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 22))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        stats_shell, stats = self._card(left, "System Stats", "▣", 198)
        stats_shell.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        self._bar(stats, "CPU Usage", "8%", 0.08, 0)
        self._bar(stats, "RAM Usage", "7 GB", 0.44, 1)
        row = tk.Frame(stats, bg=self.colors["panel"])
        row.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        row.grid_columnconfigure((0, 1, 2), weight=1)
        self._mini_stat(row, "CPU", "8%", 0)
        self._mini_stat(row, "Memory", "44%", 1)
        self._mini_stat(row, "Disk", "439/475 GB", 2)

        weather_shell, weather = self._card(left, "Weather", "☁", 212)
        weather_shell.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        tk.Label(weather, text="25.2°C", fg=self.colors["text"], bg=self.colors["panel"], font=("Consolas", 22)).grid(row=0, column=0, sticky="w", padx=12)
        tk.Label(weather, text="Mumbai, IN\novercast clouds", fg=self.colors["cyan"], bg=self.colors["panel"], font=("Segoe UI", 9), justify="left").grid(row=1, column=0, sticky="w", padx=12)
        tk.Label(weather, text="☁", fg="#c8f4ff", bg=self.colors["panel"], font=("Segoe UI", 32)).grid(row=0, column=1, rowspan=2, sticky="e", padx=12)
        wrow = tk.Frame(weather, bg=self.colors["panel"])
        wrow.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=12)
        wrow.grid_columnconfigure((0, 1, 2), weight=1)
        self._mini_stat(wrow, "Humidity", "94%", 0)
        self._mini_stat(wrow, "Wind", "5.8 m/s", 1)
        self._mini_stat(wrow, "Feels Like", "26.3°C", 2)

        camera_shell, camera = self._card(left, "Camera", "▣", 360)
        camera_shell.grid(row=2, column=0, sticky="nsew", pady=(0, 16))
        camera.grid_rowconfigure(1, weight=1)
        camera.grid_columnconfigure(0, weight=1)
        self.camera_status = tk.StringVar(value="Camera inactive")
        tk.Label(camera, textvariable=self.camera_status, fg=self.colors["cyan2"], bg=self.colors["panel"], font=("Segoe UI", 8), anchor="w").grid(row=0, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.camera_view = tk.Label(camera, text="▮▶\n\nCamera Off", fg="#2674a7", bg="#050a0f", font=("Segoe UI", 16, "bold"), justify="center", highlightbackground=self.colors["line"], highlightthickness=1)
        self.camera_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        camera_controls = tk.Frame(camera, bg=self.colors["panel"])
        camera_controls.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 4))
        camera_controls.grid_columnconfigure((0, 1), weight=1)
        self.camera_button = tk.Button(camera_controls, text="⏻ Camera", fg=self.colors["text"], bg="#11334a", activebackground="#18506f", relief="flat", bd=0, font=("Segoe UI", 9, "bold"), command=self.toggle_camera)
        self.camera_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=5)
        self.screen_button = tk.Button(camera_controls, text="⏻ Screen Control", fg=self.colors["text"], bg="#3a1720", activebackground="#5a2532", relief="flat", bd=0, font=("Segoe UI", 9, "bold"), command=self.toggle_screen_control)
        self.screen_button.grid(row=0, column=1, sticky="ew", padx=(6, 0), ipady=5)
        self.screen_status = tk.StringVar(value="Screen control is OFF. Enable it before Prabhat can click, type, open apps, or take screenshots.")
        tk.Label(camera, textvariable=self.screen_status, fg=self.colors["cyan2"], bg=self.colors["panel"], font=("Segoe UI", 8), wraplength=430, justify="center").grid(row=3, column=0, pady=(4, 8))

        uptime_shell, uptime_body = self._card(left, "System Uptime", "ⓘ", 222)
        uptime_shell.grid(row=3, column=0, sticky="ew")
        tk.Label(uptime_body, text="System Running For:", fg=self.colors["cyan"], bg=self.colors["panel"], font=("Segoe UI", 8), anchor="w").grid(row=0, column=0, sticky="w", padx=12)
        tk.Label(uptime_body, textvariable=self.uptime, fg=self.colors["text"], bg=self.colors["panel"], font=("Consolas", 18, "bold"), anchor="e").grid(row=0, column=1, sticky="e", padx=12)
        urow = tk.Frame(uptime_body, bg=self.colors["panel"])
        urow.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=12)
        urow.grid_columnconfigure((0, 1), weight=1)
        self._mini_stat(urow, "Session", "1", 0)
        self.command_stat = tk.StringVar(value="0")
        self._mini_stat(urow, "Commands", "0", 1)
        self._bar(uptime_body, "System Load", "26%", 0.26, 2)

        center = tk.Frame(main, bg=self.colors["bg"])
        center.grid(row=0, column=1, sticky="nsew")
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=1)
        self.core_canvas = tk.Canvas(center, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.core_canvas.grid(row=0, column=0, sticky="nsew")
        controls = tk.Frame(center, bg=self.colors["bg"])
        controls.grid(row=1, column=0, pady=(12, 0))
        self._round_button(controls, "▣", lambda: ui_status("Camera controls are on the left."), 58, 52, "#07121a", "#0d2535", self.colors["line2"], 16).pack(side="left", padx=16)
        self.pause_button = self._round_button(controls, "⏸", self.toggle_pause, 58, 52, "#07121a", "#0d2535", self.colors["line2"], 16)
        self.pause_button.pack(side="left", padx=16)
        self._round_button(controls, "⌨", lambda: self.message_entry.focus_set(), 58, 52, "#07121a", "#0d2535", self.colors["line2"], 16).pack(side="left", padx=16)

        right_col = tk.Frame(main, bg=self.colors["bg"], width=500)
        right_col.grid(row=0, column=2, sticky="nsew")
        right_col.grid_columnconfigure(0, weight=1)
        right_col.grid_rowconfigure(1, weight=1)

        spectrum_shell, spectrum_body = self._card(right_col, "Spectral Frequency", "⚡", 230)
        spectrum_shell.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        spectrum_body.grid_rowconfigure(0, weight=1)
        self.spectrum_canvas = tk.Canvas(spectrum_body, bg="#080b16", highlightthickness=0, bd=0)
        self.spectrum_canvas.grid(row=0, column=0, sticky="nsew", padx=12, pady=(4, 8))
        tk.Label(spectrum_body, text="TELEMETRY RATE                                                   48.0 KHZ", fg=self.colors["cyan"], bg=self.colors["panel"], font=("Consolas", 8, "bold"), anchor="w").grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

        chat_shell = tk.Canvas(right_col, bg=self.colors["bg"], highlightthickness=0, bd=0, width=500)
        chat_shell.grid(row=1, column=0, sticky="nsew")
        chat_content = tk.Frame(chat_shell, bg=self.colors["panel"])
        chat_win = chat_shell.create_window(16, 16, anchor="nw", window=chat_content)
        def chat_redraw(event):
            chat_shell.delete("shape")
            w, h = max(event.width, 20), max(event.height, 20)
            self._rounded_rect(chat_shell, 1, 1, w - 1, h - 1, 24, self.colors["panel"], self.colors["line"], 1, "shape")
            self._rounded_rect(chat_shell, 7, 7, w - 7, 66, 18, "#071018", "#071018", 1, "shape")
            chat_shell.create_rectangle(7, 34, w - 7, 66, fill="#071018", outline="", tags="shape")
            chat_shell.create_line(10, 66, w - 10, 66, fill=self.colors["line"], tags="shape")
            chat_shell.itemconfigure(chat_win, width=max(w - 32, 1), height=max(h - 32, 1))
            chat_shell.tag_lower("shape")
        chat_shell.bind("<Configure>", chat_redraw)
        chat_content.grid_columnconfigure(0, weight=1)
        chat_content.grid_rowconfigure(1, weight=1)
        header = tk.Frame(chat_content, bg="#071018", height=56)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="Conversation", fg=self.colors["text"], bg="#071018", font=("Segoe UI", 14, "bold"), anchor="w").pack(side="left", padx=14, pady=14)
        self._round_button(header, "Clear", self._clear_chat, 72, 32, "#11334a", "#18506f", self.colors["line2"], 8).pack(side="right", padx=(0, 8), pady=12)
        self._round_button(header, "Extract Conversation", lambda: ui_status("Conversation export coming soon."), 140, 32, "#11334a", "#18506f", self.colors["line2"], 8).pack(side="right", padx=8, pady=12)
        self.transcript = tk.Text(chat_content, bg=self.colors["panel"], fg=self.colors["text"], insertbackground=self.colors["cyan"], relief="flat", wrap="word", font=("Segoe UI", 11, "bold"), padx=20, pady=20, state="disabled")
        self.transcript.grid(row=1, column=0, sticky="nsew")
        entry = tk.Frame(chat_content, bg=self.colors["panel"])
        entry.grid(row=2, column=0, sticky="ew", padx=16, pady=16)
        entry.grid_columnconfigure(0, weight=1)
        input_shell = tk.Canvas(entry, height=54, bg=self.colors["panel"], highlightthickness=0, bd=0)
        input_shell.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.message_entry = tk.Entry(input_shell, fg=self.colors["text"], bg="#07121a", insertbackground=self.colors["cyan"], relief="flat", font=("Segoe UI", 11), bd=0)
        entry_window = input_shell.create_window(18, 14, anchor="nw", window=self.message_entry)
        def redraw_input(event):
            input_shell.delete("shape")
            self._rounded_rect(input_shell, 1, 1, event.width - 1, 53, 18, "#07121a", self.colors["line2"], 1, "shape")
            input_shell.itemconfigure(entry_window, width=max(event.width - 34, 1), height=26)
            input_shell.tag_lower("shape")
        input_shell.bind("<Configure>", redraw_input)
        self.message_entry.insert(0, "Type a message...")
        self.message_entry.configure(fg="#1c79ad")
        self.message_entry.bind("<FocusIn>", self._clear_placeholder)
        self.message_entry.bind("<FocusOut>", self._restore_placeholder)
        self.message_entry.bind("<Return>", lambda event: self.send_typed_message())
        self._round_button(entry, "➤", self.send_typed_message, 58, 54, "#2e7da7", "#3998c9", "#47c9ff", 17).grid(row=0, column=1, sticky="ns")

    def _settings_button(self, parent, text, command, row):
        btn = tk.Button(
            parent,
            text=text,
            fg=self.colors["text"],
            bg="#0d2230",
            activebackground="#16394f",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            command=command,
        )
        btn.grid(row=row, column=0, sticky="ew", padx=18, pady=6, ipady=8)
        return btn

    def open_settings(self):
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return

        win = tk.Toplevel(self.root)
        self.settings_window = win
        win.title("Prabhat Settings")
        win.geometry("380x470")
        win.configure(bg=self.colors["bg"])
        win.resizable(False, False)
        win.transient(self.root)

        shell = tk.Canvas(win, bg=self.colors["bg"], highlightthickness=0, bd=0)
        shell.pack(fill="both", expand=True, padx=14, pady=14)
        content = tk.Frame(shell, bg=self.colors["panel"])
        content_id = shell.create_window(14, 14, anchor="nw", window=content)

        def redraw(event):
            shell.delete("shape")
            self._rounded_rect(shell, 1, 1, event.width - 1, event.height - 1, 24, self.colors["panel"], self.colors["line2"], 1, "shape")
            shell.itemconfigure(content_id, width=max(event.width - 28, 1), height=max(event.height - 28, 1))
            shell.tag_lower("shape")

        shell.bind("<Configure>", redraw)
        content.grid_columnconfigure(0, weight=1)

        tk.Label(content, text="Settings", fg=self.colors["text"], bg=self.colors["panel"], font=("Segoe UI", 18, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 4))
        tk.Label(content, text="Control how Prabhat listens, sees, and automates.", fg=self.colors["muted"], bg=self.colors["panel"], font=("Segoe UI", 9), anchor="w", wraplength=320).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 14))

        self.pause_setting_text = tk.StringVar(value="Resume Voice Listening" if pause_event.is_set() else "Pause Voice Listening")
        self.camera_setting_text = tk.StringVar(value="Turn Camera Off" if self.camera_enabled else "Turn Camera On")
        self.screen_setting_text = tk.StringVar(value="Disable Screen Control" if screen_control_enabled else "Enable Screen Control")

        self._settings_button(content, self.pause_setting_text.get(), self._settings_toggle_pause, 2)
        self._settings_button(content, self.camera_setting_text.get(), self._settings_toggle_camera, 3)
        self._settings_button(content, self.screen_setting_text.get(), self._settings_toggle_screen, 4)
        self._settings_button(content, "Clear Conversation", self._clear_chat, 5)
        self._settings_button(content, "Toggle Fullscreen", self.toggle_fullscreen, 6)
        self._settings_button(content, "Shutdown Prabhat", self.close, 7)

        tk.Label(content, text="Tip: screen control stays blocked until you enable it here or in the Camera card.", fg=self.colors["cyan"], bg=self.colors["panel"], font=("Segoe UI", 8), wraplength=320, justify="left").grid(row=8, column=0, sticky="ew", padx=18, pady=(14, 6))

    def _refresh_settings_window(self):
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            self.settings_window.destroy()
            self.open_settings()

    def _settings_toggle_pause(self):
        self.toggle_pause()
        self._refresh_settings_window()

    def _settings_toggle_camera(self):
        self.toggle_camera()
        self._refresh_settings_window()

    def _settings_toggle_screen(self):
        self.toggle_screen_control()
        self._refresh_settings_window()

    def toggle_fullscreen(self):
        current = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not current)
        ui_status("Fullscreen enabled." if not current else "Fullscreen disabled.")

    def toggle_pause(self):
        if pause_event.is_set():
            pause_event.clear()
            self.pause_button.itemconfigure(self.pause_button._label, text="⏸")
            self.pause_button.itemconfigure(self.pause_button._shape, fill="#07121a")
            ui_status("Listening for wake word...")
        else:
            pause_event.set()
            self.pause_button.itemconfigure(self.pause_button._label, text="▶")
            self.pause_button.itemconfigure(self.pause_button._shape, fill="#3a1720")
            ui_status("AI paused. Type or press play.")

    def _clear_placeholder(self, event=None):
        if self.message_entry.get() == "Type a message...":
            self.message_entry.delete(0, "end")
            self.message_entry.configure(fg=self.colors["text"])

    def _restore_placeholder(self, event=None):
        if not self.message_entry.get().strip():
            self.message_entry.insert(0, "Type a message...")
            self.message_entry.configure(fg="#1c79ad")

    def send_typed_message(self):
        message = self.message_entry.get().strip()
        if not message or message == "Type a message...":
            return
        self.message_entry.delete(0, "end")
        self.message_entry.configure(fg=self.colors["text"])
        threading.Thread(target=handle_user_input, args=(message, False), daemon=True).start()

    def toggle_screen_control(self):
        global screen_control_enabled
        screen_control_enabled = not screen_control_enabled
        if screen_control_enabled:
            self.screen_button.configure(text="✓ Screen Control", bg="#0b4a2a")
            self.screen_status.set("Screen control is ON. Prabhat can now use approved automation commands.")
            ui_status("Screen control enabled.")
        else:
            self.screen_button.configure(text="⏻ Screen Control", bg="#3a1720")
            self.screen_status.set("Screen control is OFF. Enable it before Prabhat can click, type, open apps, or take screenshots.")
            ui_status("Screen control disabled.")

    def toggle_camera(self):
        if self.camera_enabled:
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        try:
            import cv2
        except ImportError:
            self.camera_status.set("Install camera support: pip install opencv-python")
            ui_log("System", "Camera support needs opencv-python. Run: pip install opencv-python")
            return

        try:
            self.camera_capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self.camera_capture.isOpened():
                self.camera_capture.release()
                self.camera_capture = None
                self.camera_status.set("Camera permission denied or unavailable")
                ui_log("System", "Camera could not open. Check Windows camera privacy permissions.")
                return

            self.camera_enabled = True
            self.camera_button.configure(text="✓ Camera", bg="#0b4a2a")
            self.camera_status.set("Camera sharing ON")
            ui_status("Camera sharing enabled.")
            self._update_camera_frame()
        except Exception as error:
            self.camera_status.set("Camera failed to start")
            ui_log("System", f"Camera error: {error}")

    def stop_camera(self):
        self.camera_enabled = False
        if self.camera_capture is not None:
            try:
                self.camera_capture.release()
            except Exception:
                pass
            self.camera_capture = None
        self.camera_photo = None
        self.camera_button.configure(text="⏻ Camera", bg="#11334a")
        self.camera_status.set("Camera inactive")
        self.camera_view.configure(image="", text="▮▶\n\nCamera Off")
        ui_status("Camera sharing disabled.")

    def _update_camera_frame(self):
        if not self.camera_enabled or self.camera_capture is None:
            return

        try:
            import cv2
            ok, frame = self.camera_capture.read()
            if ok:
                frame = cv2.flip(frame, 1)
                view_w = max(self.camera_view.winfo_width(), 320)
                view_h = max(self.camera_view.winfo_height(), 160)
                frame = cv2.resize(frame, (view_w, view_h))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                success, encoded = cv2.imencode(".ppm", rgb)
                if success:
                    self.camera_photo = tk.PhotoImage(data=encoded.tobytes())
                    self.camera_view.configure(image=self.camera_photo, text="")
            else:
                self.camera_status.set("Camera frame unavailable")
        except Exception as error:
            self.camera_status.set("Camera preview error")
            ui_log("System", f"Camera preview error: {error}")
            self.stop_camera()
            return

        self.root.after(33, self._update_camera_frame)

    def _clear_chat(self):
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")

    def _draw_background(self):
        if not hasattr(self, "background_canvas"):
            return
        c = self.background_canvas
        w, h = max(c.winfo_width(), 1), max(c.winfo_height(), 1)
        c.delete("all")
        c.create_rectangle(0, 0, w, h, fill=self.colors["bg"], outline="")

        # Apple-like liquid-glass diagonal glow: blue top-right into purple bottom-left.
        for i in range(18):
            pad = i * 34
            c.create_oval(
                w - 520 - pad,
                -280 - pad,
                w + 260 + pad,
                520 + pad,
                fill="#0c6cff" if i < 9 else "#124dd8",
                outline="",
                stipple="gray75",
            )
        for i in range(18):
            pad = i * 38
            c.create_oval(
                -320 - pad,
                h - 430 - pad,
                620 + pad,
                h + 260 + pad,
                fill="#6d28ff" if i < 9 else "#35106f",
                outline="",
                stipple="gray75",
            )

        # Soft glassy atmosphere and subtle grid texture.
        c.create_polygon(w * 0.18, 0, w, 0, w, h * 0.5, w * 0.52, h * 0.26, fill="#0d3c68", outline="", stipple="gray75")
        c.create_polygon(0, h * 0.42, w * 0.45, h * 0.68, w * 0.78, h, 0, h, fill="#2f155c", outline="", stipple="gray75")
        for x in range(0, w, 34):
            c.create_line(x, 0, x, h, fill="#0b1a2a")
        for y in range(0, h, 34):
            c.create_line(0, y, w, y, fill="#0b1a2a")
        for i in range(80):
            x = (i * 97) % max(w, 1)
            y = (i * 53) % max(h, 1)
            c.create_oval(x, y, x + 2, y + 2, fill="#315d83", outline="")

    def _draw_spectrum(self):
        if not hasattr(self, "spectrum_canvas"):
            return
        c = self.spectrum_canvas
        w, h = max(c.winfo_width(), 220), max(c.winfo_height(), 120)
        c.delete("all")
        c.create_rectangle(0, 0, w, h, fill="#080b16", outline="")
        c.create_oval(-80, h * 0.22, w + 90, h + 90, fill="#261046", outline="", stipple="gray50")
        count = len(self.spectrum_bars)
        gap = 7
        bar_w = max((w - 34 - gap * count) / count, 8)
        for i in range(count):
            self.spectrum_bars[i] = max(16, min(96, self.spectrum_bars[i] + random.randint(-8, 8)))
            bh = (h - 30) * self.spectrum_bars[i] / 100
            x = 16 + i * (bar_w + gap)
            y = h - 16 - bh
            color = "#17eaff" if i % 3 else "#0cb6ce"
            c.create_rectangle(x, y, x + bar_w, h - 16, fill=color, outline="")

    def _draw_core(self):
        c = self.core_canvas
        w, h = max(c.winfo_width(), 400), max(c.winfo_height(), 400)
        c.delete("all")
        cx, cy = w // 2, h // 2 - 46
        status_text = self.status.get().replace(":: ", "")
        active = "Speaking" in status_text or "Listening" in status_text
        pulse = math.sin(self.tick / 9) * (10 if active else 6)

        c.create_rectangle(0, 0, w, h, fill=self.colors["bg"], outline="")

        # Wide transparent HUD rings like the reference visualizer.
        for r in range(70, 250, 28):
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#0a2840", width=1)
        for a in range(0, 360, 18):
            x = cx + math.cos(math.radians(a)) * 230
            y = cy + math.sin(math.radians(a)) * 230
            c.create_line(cx, cy, x, y, fill="#071b2a")

        # Orbiting cyan particles.
        for particle in self.core_particles:
            particle["angle"] += particle["speed"] * (1.6 if active else 1.0)
            wobble = math.sin(self.tick / 18 + particle["radius"]) * 5
            x = cx + math.cos(particle["angle"]) * (particle["radius"] + wobble)
            y = cy + math.sin(particle["angle"]) * (particle["radius"] + wobble)
            s = particle["size"]
            c.create_oval(x - s, y - s, x + s, y + s, fill="#11eaff", outline="")

        # Rotating segmented arcs.
        ring_data = [
            (84, "#18ecff", 5, 32),
            (106, "#0ab7dd", 3, 44),
            (132, "#126fba", 2, 52),
            (170, "#0d416a", 2, 66),
            (204, "#0a2e51", 2, 84),
        ]
        for i, (radius, color, width_line, step) in enumerate(ring_data):
            c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline="#0f2940", width=1)
            for seg in range(0, 360, step):
                c.create_arc(
                    cx - radius - pulse / 2,
                    cy - radius - pulse / 2,
                    cx + radius + pulse / 2,
                    cy + radius + pulse / 2,
                    start=seg + self.tick * (1.4 + i * 0.35),
                    extent=max(12, step * 0.34),
                    style="arc",
                    outline=color,
                    width=width_line,
                )

        # Cyan reactor core with layered glow.
        for glow_r, color in ((92, "#042f48"), (72, "#075b70"), (52, "#0aaec3")):
            c.create_oval(cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r, fill=color, outline="", stipple="gray50")
        core_pulse = 38 + math.sin(self.tick / 7) * (7 if active else 3)
        c.create_oval(cx - 66, cy - 66, cx + 66, cy + 66, fill="#073d4d", outline="#0defff", width=2)
        c.create_oval(cx - core_pulse, cy - core_pulse, cx + core_pulse, cy + core_pulse, fill="#12dff1", outline="#d9ffff", width=2)
        c.create_oval(cx - 14, cy - 14, cx + 14, cy + 14, fill="#1f415d", outline="#ffffff", width=2)

        c.create_text(cx, cy + 150, text="SYSTEMS ACTIVE", fill="#0befff", font=("Consolas", 13, "bold"))
        c.create_text(cx, cy + 170, text="SYSTEM CORE", fill="#8ba3b2", font=("Consolas", 10, "bold"))

        # Keep Prabhat status below the visualizer without overlap.
        c.create_text(cx, cy + 250, text="P.R.A.B.H.A.T", fill=self.colors["text"], font=("Consolas", 24, "bold"))
        short_status = status_text if len(status_text) <= 30 else status_text[:27] + "..."
        pill_w = min(max(270, len(short_status) * 8 + 70), max(w - 80, 270))
        pill_y1 = cy + 280
        pill_y2 = cy + 324
        pill_mid = (pill_y1 + pill_y2) / 2
        self._rounded_rect(c, cx - pill_w / 2, pill_y1, cx + pill_w / 2, pill_y2, 18, "#082033", "#103d58", 1, "status")
        c.create_oval(cx - pill_w / 2 + 20, pill_mid - 5, cx - pill_w / 2 + 30, pill_mid + 5, fill=self.colors["green"], outline="")
        c.create_text(cx + 12, pill_mid, text=short_status, fill=self.colors["cyan"], font=("Segoe UI", 10))

    def _animate(self):
        now = datetime.datetime.now()
        self.clock_text.set(now.strftime("%I:%M:%S %p"))
        self.date_text.set(now.strftime("%B %d, %Y"))
        if hasattr(self, "time_pill"):
            self.time_pill.itemconfigure(self.clock_canvas_text, text=self.clock_text.get())
            self.time_pill.itemconfigure(self.date_canvas_text, text=self.date_text.get())
        elapsed = int(time.time() - self.start_time)
        self.uptime.set(f"{elapsed // 3600:02}:{(elapsed % 3600) // 60:02}:{elapsed % 60:02}")
        self._draw_background()
        self._draw_core()
        self._draw_spectrum()
        self.tick += 1
        if not shutdown_event.is_set():
            self.root.after(40, self._animate)

    def _process_events(self):
        while True:
            try:
                event = ui_events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "status":
                self.status.set(event[1])
            elif event[0] == "log":
                self._append_log(event[1], event[2])
        if not shutdown_event.is_set():
            self.root.after(100, self._process_events)

    def _append_log(self, speaker, message):
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{speaker}: {message}\n\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")
        if speaker == "You":
            self.command_count += 1

    def close(self):
        self.stop_camera()
        shutdown_event.set()
        self.root.after(150, self.root.destroy)


# =====================================================================
# 2. CORE AI CAPABILITIES
# =====================================================================

def speak_with_windows_voice(text):
    """Speak through Windows SAPI so output follows the current default speaker."""
    try:
        import pyttsx3
    except ImportError as error:
        raise RuntimeError("Install pyttsx3 for laptop-speaker fallback: pip install pyttsx3") from error

    engine = pyttsx3.init("sapi5")
    engine.setProperty("rate", 165)
    engine.setProperty("volume", 1.0)

    voices = engine.getProperty("voices")
    if voices:
        indian_or_male_voice = next(
            (
                voice
                for voice in voices
                if "india" in voice.name.lower()
                or "ravi" in voice.name.lower()
                or "male" in voice.name.lower()
            ),
            voices[0],
        )
        engine.setProperty("voice", indian_or_male_voice.id)

    engine.say(text)
    engine.runAndWait()
    engine.stop()


def _mci_error_message(code):
    buffer = ctypes.create_unicode_buffer(255)
    ctypes.windll.winmm.mciGetErrorStringW(code, buffer, 255)
    return buffer.value or f"MCI error {code}"


def _mci(command, buffer=None):
    result = ctypes.windll.winmm.mciSendStringW(command, buffer, len(buffer) if buffer else 0, None)
    if result:
        raise RuntimeError(f"{command} -> {_mci_error_message(result)}")


def play_audio_native(audio_path):
    """Play an MP3 through Windows native audio instead of pygame."""
    alias = f"prabhat_tts_{int(time.time() * 1000)}"
    opened = False

    try:
        try:
            _mci("close all")
        except Exception:
            pass

        _mci(f'open "{audio_path}" type mpegvideo alias {alias}')
        opened = True
        _mci(f"setaudio {alias} volume to 1000")
        _mci(f"play {alias}")

        while not shutdown_event.is_set():
            status = ctypes.create_unicode_buffer(64)
            _mci(f"status {alias} mode", status)
            if status.value.lower() in {"stopped", "not ready"}:
                break
            time.sleep(0.05)
    finally:
        if opened:
            try:
                _mci(f"close {alias}")
            except Exception:
                pass


def speak_with_edge_tts(text):
    """Use the Prabhat Neural voice as a backup path."""
    audio_path = None

    try:
        async def save_audio_file(path):
            communicate = edge_tts.Communicate(
                text,
                "en-IN-PrabhatNeural",
                rate="-3%",
                volume="+0%",
            )
            await communicate.save(path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as audio_file:
            audio_path = audio_file.name

        asyncio.run(save_audio_file(audio_path))
        play_audio_native(audio_path)
    finally:
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass


def speak(text):
    """Speak in a way that recovers when Bluetooth output disconnects."""
    print(f"Prabhat: {text}")
    ui_status("Speaking...")
    ui_log("Prabhat", text)

    try:
        speak_with_windows_voice(text)
    except Exception as windows_voice_error:
        print(f"Windows Voice Error: {windows_voice_error}")
        ui_log("System", f"Windows speaker voice fallback failed: {windows_voice_error}")

        try:
            speak_with_edge_tts(text)
        except Exception as edge_error:
            print(f"Audio Error: {edge_error}")
            ui_log("System", f"Voice playback error: {edge_error}")


def listen():
    """Listens to microphone input and converts it to text."""
    with sr.Microphone() as source:
        print("\nListening...")
        ui_status("Listening...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        audio = recognizer.listen(source, timeout=8, phrase_time_limit=10)

    try:
        print("Recognizing...")
        ui_status("Recognizing...")
        query = recognizer.recognize_google(audio, language="en-in")
        print(f"You said: {query}")
        ui_log("You", query)
        return query.lower()
    except sr.UnknownValueError:
        print("Sorry, I didn't catch that.")
        ui_status("Listening missed. Try again.")
        return ""
    except sr.WaitTimeoutError:
        ui_status("No voice detected. Listening again...")
        return ""
    except sr.RequestError:
        speak("Network error. Please check your internet connection.")
        return ""


# =====================================================================
# 3. AUTOMATION & SKILLS
# =====================================================================

def execute_automation(query):
    """
    Checks if the command is a system task.
    Returns True if a task was handled, False otherwise.
    """
    screen_control_phrases = (
        "take a screenshot",
        "open ",
        "open start menu",
        "press windows key",
        "show desktop",
    )
    needs_screen_control = query == "take a screenshot" or query.startswith("open ") or any(
        phrase in query for phrase in screen_control_phrases[2:]
    )
    if needs_screen_control and not screen_control_enabled:
        speak("Screen control is off. Please enable it from the Camera section first.")
        return True
    if "generate an image" in query or "draw a" in query or "create an image" in query:
        prompt = query.replace("generate an image of", "").replace("generate an image", "").replace("draw a", "").replace("create an image of", "").strip()

        if prompt:
            speak(f"Generating an image of {prompt}. This will just take a moment.")

            try:
                encoded_prompt = urllib.parse.quote(prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"

                response = requests.get(url)
                image_path = "Prabhat_generated_image.jpg"

                with open(image_path, "wb") as file:
                    file.write(response.content)

                speak("Image generated successfully. Opening it now.")
                os.startfile(image_path)
                return True

            except Exception as e:
                print(f"Image Error: {e}")
                speak("I ran into an issue while trying to paint that image.")
                return True

    elif "directions" in query or "navigate to" in query or "how to go to" in query:
        clean_query = query.replace("show me", "").replace("get me", "").strip()
        origin = ""
        destination = ""

        if clean_query.startswith("from ") and " to " in clean_query:
            text_strip = clean_query.replace("from ", "", 1)
            parts = text_strip.split(" to ", 1)
            origin = parts[0].strip()
            destination = parts[1].strip()

        elif " from " in clean_query:
            text_strip = clean_query.replace("directions to ", "").replace("navigate to ", "").replace("how to go to ", "")
            parts = text_strip.split(" from ", 1)
            destination = parts[0].strip()
            origin = parts[1].strip()

        else:
            destination = clean_query.replace("directions to ", "").replace("navigate to ", "").replace("how to go to ", "").strip()

        if origin in ["my current location", "current location", "me", "here", "my location"]:
            origin = ""

        if destination:
            encoded_dest = urllib.parse.quote(destination)
            if origin:
                encoded_origin = urllib.parse.quote(origin)
                url = f"https://www.google.com/maps/dir/?api=1&origin={encoded_origin}&destination={encoded_dest}"
                speak(f"Mapping out the route from {origin} to {destination}.")
            else:
                url = f"https://www.google.com/maps/dir/?api=1&destination={encoded_dest}"
                speak(f"Opening directions to {destination} from your current location.")

            webbrowser.open(url)
            return True

    elif query == "take a screenshot":
        speak("Taking a screenshot now.")
        screenshot = pyautogui.screenshot()
        screenshot.save("assistant_screenshot.png")
        speak("Screenshot saved to your project folder.")
        return True

    elif query.startswith("open ") and "start menu" not in query:
        app_name = query.replace("open ", "").strip()
        speak(f"Opening {app_name}.")

        pyautogui.press("win")
        time.sleep(0.5)
        pyautogui.write(app_name)
        time.sleep(0.5)
        pyautogui.press("enter")
        return True

    elif "open start menu" in query or "press windows key" in query:
        speak("Opening start menu.")
        pyautogui.press("win")
        return True

    elif "show desktop" in query:
        speak("Minimizing windows.")
        pyautogui.hotkey("win", "d")
        return True

    elif query.startswith("play "):
        song_query = query.replace("play ", "").strip()

        if "on spotify" in song_query:
            song = song_query.replace("on spotify", "").strip()
            speak(f"Searching for {song} on Spotify.")

            encoded_song = urllib.parse.quote(song)
            webbrowser.open(f"spotify:search:{encoded_song}")
            return True

        else:
            song = song_query.replace("on youtube", "").strip()
            speak(f"Playing {song} on YouTube.")

            try:
                import pywhatkit
                pywhatkit.playonyt(song)
            except ImportError:
                speak("I am missing the pywhatkit library. Please install it.")
                print("Run this in your terminal: pip install pywhatkit")

            return True

    return False


# =====================================================================
# 4. MAIN PROGRAM LOOP
# =====================================================================

def handle_user_input(user_input, already_logged=True):
    if not user_input:
        return

    clean_input = user_input.lower().strip()
    if not already_logged:
        ui_log("You", user_input)

    if "shutdown" in clean_input or "bye" in clean_input or "goodbye" in clean_input:
        speak("Goodbye! Shutting down systems.")
        shutdown_event.set()
        return

    was_automated = execute_automation(clean_input)

    if not was_automated:
        try:
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            current_date = datetime.datetime.now().strftime("%A, %B %d, %Y")
            augmented_prompt = f"[System Note: Current time is {current_time} on {current_date}] {user_input}"
            answer = ask_brain(augmented_prompt)
            speak(answer)

        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            ui_log("System", f"Brain center error: {e}")
            speak("I could not connect to Gemini. Check the API key, model access, or internet connection.")


def assistant_loop():
    speak("Hello Shaurya. How can I help you?")

    while not shutdown_event.is_set():
        if pause_event.is_set():
            ui_status("AI paused. Voice listening is off.")
            time.sleep(0.3)
            continue

        user_input = listen()
        handle_user_input(user_input, True)
        time.sleep(0.5)

    ui_status("Systems offline.")


if __name__ == "__main__":
    root = tk.Tk()
    app = JarvisUI(root)
    threading.Thread(target=assistant_loop, daemon=True).start()
    root.mainloop()
