"""
AutoKitScreenshot main window.

Single-window tkinter app aimed at non-technical users:
- live status (game running? calibrated?)
- one big Capture button (F8 also works globally)
- auto / manual calibration buttons
- activity log and a preview of the last capture
"""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox

import keyboard
from PIL import Image, ImageTk

import capture
from common import app_dir, find_game_window, resource_path, window_rect

BG = "#14141a"
PANEL = "#1d1d26"
FG = "#dddddd"
FG_DIM = "#888c9a"
GOOD = "#7fd27f"
BAD = "#d27f7f"
WARN = "#ffc454"
ACCENT = "#2e5d8a"
ACCENT_ACTIVE = "#3a74ac"

STATUS_POLL_MS = 2000
QUEUE_POLL_MS = 100
PREVIEW_MAX_W = 560
PREVIEW_MAX_H = 220


class AutoKitGUI:
    def __init__(self):
        self.root = tk.Tk()
        # NOTE: the title must NOT contain the game's name — find_game_window
        # matches window titles, and we must never match ourselves.
        self.root.title("D.A.D's A.Ss")
        ico = resource_path("assets/icon.ico")
        if ico.exists():
            try:
                self.root.iconbitmap(str(ico))
            except tk.TclError:
                pass
        self.root.configure(bg=BG)
        self.root.geometry("600x680")
        self.root.minsize(520, 560)

        self.queue = queue.Queue()
        self.last_output = None
        self._preview_photo = None
        self._hotkey_handle = None
        self._calibrating = False

        self._build_widgets()
        self._register_hotkey()
        self._poll_queue()
        self._refresh_status()
        self.root.after(300, self._first_run)

    # ---------- UI construction ----------

    def _build_widgets(self):
        logo_path = resource_path("assets/logo.png")
        self._logo_photo = None
        if logo_path.exists():
            try:
                img = Image.open(logo_path)
                img.thumbnail((460, 130))
                self._logo_photo = ImageTk.PhotoImage(img)
            except Exception:
                self._logo_photo = None
        if self._logo_photo is not None:
            tk.Label(self.root, image=self._logo_photo, bg=BG).pack(pady=(14, 2))
        else:
            tk.Label(self.root, text="D.A.D's A.Ss",
                     font=("Segoe UI", 16, "bold"), fg=FG, bg=BG).pack(pady=(14, 2))
            tk.Label(self.root, text="Dark and Darker Auto Screenshot",
                     font=("Segoe UI", 9), fg=FG_DIM, bg=BG).pack()

        # Status panel
        status = tk.Frame(self.root, bg=PANEL)
        status.pack(fill="x", padx=16, pady=(12, 6))
        self.game_label = tk.Label(status, font=("Segoe UI", 10), bg=PANEL, anchor="w")
        self.game_label.pack(fill="x", padx=12, pady=(8, 2))
        self.calib_label = tk.Label(status, font=("Segoe UI", 10), bg=PANEL, anchor="w")
        self.calib_label.pack(fill="x", padx=12, pady=(2, 8))

        # Big capture button
        self.capture_btn = tk.Button(
            self.root, text="Capture  (F8)", font=("Segoe UI", 14, "bold"),
            bg=ACCENT, fg="white", activebackground=ACCENT_ACTIVE,
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._capture_async, height=2,
        )
        self.capture_btn.pack(fill="x", padx=16, pady=(6, 4))

        # Secondary buttons
        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=16, pady=(2, 8))
        for text, cmd in (
            ("Auto-Calibrate", self._auto_calibrate_async),
            ("Manual Calibration…", self._manual_calibrate),
            ("Open Output Folder", self._open_output),
        ):
            tk.Button(row, text=text, font=("Segoe UI", 10), bg=PANEL, fg=FG,
                      activebackground="#2a2a36", activeforeground=FG,
                      relief="flat", cursor="hand2", command=cmd
                      ).pack(side="left", expand=True, fill="x", padx=3)

        # Preview of last capture
        self.preview_label = tk.Label(self.root, bg=BG, fg=FG_DIM,
                                      text="Your capture preview will appear here",
                                      font=("Segoe UI", 9, "italic"), cursor="hand2")
        self.preview_label.pack(pady=6)
        self.preview_label.bind("<Button-1>", lambda e: self._open_last())

        # Log
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 12))
        self.log = tk.Text(log_frame, bg=PANEL, fg=FG, font=("Consolas", 9),
                           relief="flat", state="disabled", wrap="word", height=8)
        scroll = tk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        tk.Label(self.root,
                 text="Open your inventory in-game, then press F8 or click Capture. "
                      "Hold ESC to abort a running capture.",
                 font=("Segoe UI", 8), fg=FG_DIM, bg=BG, wraplength=560).pack(pady=(0, 8))

    # ---------- queue / threading plumbing ----------

    def _emit(self, line):
        """Thread-safe log line."""
        self.queue.put(("log", str(line)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "preview":
                    self._show_preview(payload)
                elif kind == "refresh":
                    self._refresh_status()
        except queue.Empty:
            pass
        self.root.after(QUEUE_POLL_MS, self._poll_queue)

    def _append_log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ---------- status ----------

    def _config_summary(self):
        """(text, color) for the calibration status row."""
        path = app_dir() / "slots.json"
        if not path.exists():
            return "Calibration: none yet — click Auto-Calibrate", BAD
        try:
            cfg = json.loads(path.read_text())
            n = len(cfg["order"])
        except Exception:
            return "Calibration: file unreadable — re-calibrate", BAD
        kind = "auto" if cfg.get("auto_calibrated") else "manual"
        win = find_game_window()
        saved = cfg.get("window")
        if win is not None and saved is not None:
            cur = window_rect(win)
            if any(abs(a - b) > capture.WINDOW_MOVE_TOLERANCE
                   for a, b in zip(saved, cur)):
                return ("Calibration: game window moved since calibration — "
                        "click Auto-Calibrate to fix"), WARN
        return f"Calibration: ready ({n} slots, {kind})", GOOD

    def _refresh_status(self):
        win = find_game_window()
        if win is not None:
            self.game_label.config(text="●  Game: running", fg=GOOD)
        else:
            self.game_label.config(
                text="○  Game: not found — launch Dark and Darker (borderless windowed)",
                fg=BAD)

        text, color = self._config_summary()
        dot = "●" if color == GOOD else "○"
        self.calib_label.config(text=f"{dot}  {text}", fg=color)

        ready = win is not None and color != BAD and not self._calibrating
        self.capture_btn.config(state="normal" if ready else "disabled",
                                bg=ACCENT if ready else PANEL)

        self.root.after(STATUS_POLL_MS, self._refresh_status)

    def _first_run(self):
        if (app_dir() / "slots.json").exists():
            self._emit("Ready. Open your inventory in-game and press F8 (or click Capture).")
            return
        if find_game_window() is None:
            self._emit("Welcome! Launch Dark and Darker in borderless windowed mode, "
                       "then click Auto-Calibrate.")
            return
        self._emit("First run — auto-calibrating to your game window...")
        self._auto_calibrate_async()

    # ---------- actions ----------

    def _register_hotkey(self):
        self._hotkey_handle = keyboard.add_hotkey(
            capture.HOTKEY, self._capture_async)

    def _unregister_hotkey(self):
        if self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except (KeyError, ValueError):
                pass
            self._hotkey_handle = None

    def _capture_async(self):
        if self._calibrating:
            return
        threading.Thread(target=self._capture_worker, daemon=True).start()

    def _capture_worker(self):
        config = capture.load_config(emit=self._emit)
        if config is None:
            return
        self._emit("Capturing — keep your hands off the mouse...")
        path = capture.trigger_capture(config, emit=self._emit)
        if path is not None:
            self.queue.put(("preview", str(path)))

    def _auto_calibrate_async(self):
        def worker():
            from reference_profile import auto_calibrate
            auto_calibrate(emit=self._emit)
            self.queue.put(("refresh", None))
        threading.Thread(target=worker, daemon=True).start()

    def _manual_calibrate(self):
        if self._calibrating:
            return
        proceed = messagebox.askokcancel(
            "Manual calibration",
            "This window will minimize and a small guide window will appear "
            "over the game.\n\n"
            "Have your inventory open with the Details panel CLOSED, then "
            "follow the prompts: hover each highlighted target and press "
            "SPACE. Press ESC to abort.",
            parent=self.root)
        if not proceed:
            return

        self._calibrating = True
        self._unregister_hotkey()
        self.root.iconify()
        try:
            from calibrate import run_calibration
            run_calibration(parent=self.root, emit=self._emit)
        finally:
            self._calibrating = False
            self._register_hotkey()
            self.root.deiconify()
            self.queue.put(("refresh", None))

    def _open_output(self):
        out = app_dir() / "output"
        out.mkdir(parents=True, exist_ok=True)
        os.startfile(out)

    def _open_last(self):
        if self.last_output and os.path.exists(self.last_output):
            os.startfile(self.last_output)

    def _show_preview(self, path):
        self.last_output = path
        try:
            img = Image.open(path)
            img.thumbnail((PREVIEW_MAX_W, PREVIEW_MAX_H))
            self._preview_photo = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self._preview_photo, text="")
        except Exception as e:
            self._emit(f"(couldn't render preview: {e})")

    def run(self):
        self.root.mainloop()


def main():
    AutoKitGUI().run()


if __name__ == "__main__":
    main()
