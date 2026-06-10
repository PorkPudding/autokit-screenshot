"""
Always-on-top calibration overlay.

Shows a small draggable window over the game that walks the user through
a sequence of hover-and-press-SPACE steps. Works on single-monitor
setups because it floats above the game (borderless windowed only).
"""
import tkinter as tk

import keyboard
import pyautogui

POLL_MS = 30

BG = "#14141a"
FG_STEP = "#ffc454"
FG_INSTR = "#7fa8d4"
FG_DESC = "#dddddd"
FG_POS = "#7fd27f"
FG_LAST = "#888c9a"
FG_HINT = "#888888"


class CalibrationOverlay:
    """Drive a calibration sequence with a small floating window.

    Parameters
    ----------
    title : str
        Window title (also shown in taskbar).
    intro : str
        One-line intro shown before step prompts begin.
    steps : list[tuple[str | None, str]]
        (key, description) tuples. If key is None, the step is an
        instruction-only prompt — SPACE advances without recording.
        Descriptions may wrap.
    start_xy : tuple[int, int] | None
        Initial window position. Defaults to (60, 60).
    """

    def __init__(self, title, intro, steps, start_xy=(60, 60)):
        self.title = title
        self.intro = intro
        self.steps = steps
        self.start_xy = start_xy

        self.results = {}
        self.current = 0
        self.aborted = False
        self._await_release = True  # wait for SPACE to be up before arming
        self._last_recorded = None

    def run(self):
        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"520x260+{self.start_xy[0]}+{self.start_xy[1]}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        tk.Label(
            self.root, text=self.intro, font=("Segoe UI", 9, "italic"),
            fg=FG_LAST, bg=BG, wraplength=490, justify="left",
        ).pack(fill="x", padx=14, pady=(10, 4))

        self.step_label = tk.Label(
            self.root, font=("Segoe UI", 14, "bold"), fg=FG_STEP, bg=BG,
        )
        self.step_label.pack(pady=(6, 2))

        self.desc_label = tk.Label(
            self.root, font=("Segoe UI", 10), fg=FG_DESC, bg=BG,
            wraplength=490, justify="left",
        )
        self.desc_label.pack(fill="x", padx=14, pady=4)

        self.pos_label = tk.Label(
            self.root, font=("Consolas", 10), fg=FG_POS, bg=BG,
        )
        self.pos_label.pack(pady=(10, 2))

        self.last_label = tk.Label(
            self.root, font=("Segoe UI", 9), fg=FG_LAST, bg=BG, text="",
        )
        self.last_label.pack(pady=(0, 4))

        self.hint_label = tk.Label(
            self.root, font=("Segoe UI", 9), fg=FG_HINT, bg=BG,
        )
        self.hint_label.pack(side="bottom", pady=8)

        self._refresh_step()
        self.root.after(POLL_MS, self._tick)
        self.root.mainloop()
        return None if self.aborted else self.results

    def _refresh_step(self):
        if self.current >= len(self.steps):
            self.step_label.config(text="Done!", fg=FG_STEP)
            self.desc_label.config(text="Saving and closing...")
            self.hint_label.config(text="")
            return
        key, desc = self.steps[self.current]
        if key is None:
            self.step_label.config(
                text=f"{self.current + 1}/{len(self.steps)} — NEXT STEP",
                fg=FG_INSTR,
            )
            self.hint_label.config(text="SPACE to continue    ·    ESC to abort")
        else:
            self.step_label.config(
                text=f"{self.current + 1}/{len(self.steps)} — {key.upper()}",
                fg=FG_STEP,
            )
            self.hint_label.config(text="SPACE to record cursor position    ·    ESC to abort")
        self.desc_label.config(text=desc)

    def _tick(self):
        x, y = pyautogui.position()
        self.pos_label.config(text=f"cursor: ({x:>5}, {y:>5})")

        if keyboard.is_pressed("esc"):
            self.aborted = True
            self.root.destroy()
            return

        space_down = keyboard.is_pressed("space")
        if self._await_release:
            if not space_down:
                self._await_release = False
        else:
            if space_down and self.current < len(self.steps):
                key, _ = self.steps[self.current]
                if key is not None:
                    self.results[key] = [x, y]
                    self.last_label.config(text=f"last: {key} = ({x}, {y})")
                self.current += 1
                self._await_release = True
                self._refresh_step()
                if self.current >= len(self.steps):
                    self.root.after(500, self.root.destroy)
                    return

        self.root.after(POLL_MS, self._tick)
