"""
Diagnostic capture: dumps raw screenshots and diff masks to disk
so we can figure out why detection is failing.

Usage:
    python debug_capture.py

Press F8 with the inventory open to run a diagnostic capture.
Press ESC to quit.

Outputs go to ./debug/ — one PNG per slot (raw screenshot) and
one diff_<slot>.png (red where pixels changed vs baseline).
"""
import ctypes
import json
import time
from pathlib import Path

import keyboard
import mss
import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import Image

pyautogui.FAILSAFE = False

CONFIG_PATH = Path(__file__).parent / "slots.json"
DEBUG_DIR = Path(__file__).parent / "debug"

GAME_TITLE_HINTS = ("dark and darker", "dungeoncrawler", "dungeon crawler")
WARMUP_DELAY = 1.0
HOVER_DELAY = 0.9
DIFF_THRESHOLD = 25


def grab_rgb(sct, monitor):
    sct_img = sct.grab(monitor)
    arr = np.frombuffer(sct_img.bgra, dtype=np.uint8).reshape(sct_img.height, sct_img.width, 4)
    return np.ascontiguousarray(arr[:, :, [2, 1, 0]])


def pick_monitor(sct, win):
    if win is not None:
        cx = win.left + win.width // 2
        cy = win.top + win.height // 2
        for mon in sct.monitors[1:]:
            if (mon["left"] <= cx < mon["left"] + mon["width"]
                    and mon["top"] <= cy < mon["top"] + mon["height"]):
                return mon
    return sct.monitors[1]


def find_game_window():
    for title in gw.getAllTitles():
        low = title.lower()
        if any(hint in low for hint in GAME_TITLE_HINTS):
            wins = gw.getWindowsWithTitle(title)
            if wins:
                return wins[0]
    return None


def force_focus(win):
    if win is None:
        return False
    try:
        hwnd = win._hWnd
    except AttributeError:
        return False
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    # AttachThreadInput trick: attach our input to foreground thread, then SetForegroundWindow
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, 0)
    our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    if fg_thread != our_thread:
        user32.AttachThreadInput(our_thread, fg_thread, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if fg_thread != our_thread:
        user32.AttachThreadInput(our_thread, fg_thread, False)
    return True


def diff_visual(baseline, current):
    diff = np.abs(current.astype(np.int16) - baseline.astype(np.int16)).sum(axis=2)
    mask = diff > DIFF_THRESHOLD
    out = current.copy()
    out[mask] = [255, 0, 0]
    return out, int(mask.sum())


def run_debug(config):
    rest = config["rest"]
    order = config["order"]
    slots = config["slots"]

    DEBUG_DIR.mkdir(exist_ok=True)
    for old in DEBUG_DIR.glob("*.png"):
        old.unlink()

    win = find_game_window()
    if win is None:
        print("[debug] Game window not found.")
    else:
        print(f"[debug] Game window: {win.title!r} hwnd={getattr(win, '_hWnd', '?')}")
        print(f"[debug] Window bounds: ({win.left}, {win.top}) {win.width}x{win.height}")

    print("[debug] Focusing game...")
    force_focus(win)
    time.sleep(WARMUP_DELAY)

    print(f"[debug] Moving to rest {rest}, capturing baseline...")
    pyautogui.moveTo(rest[0], rest[1])
    time.sleep(0.6)

    with mss.MSS() as sct:
        monitor = pick_monitor(sct, win)
        print(f"[debug] Picked monitor: left={monitor['left']} top={monitor['top']} "
              f"{monitor['width']}x{monitor['height']}")
        baseline = grab_rgb(sct, monitor)
        Image.fromarray(baseline).save(DEBUG_DIR / "00_baseline.png")
        print(f"[debug] Baseline shape: {baseline.shape}, saved 00_baseline.png")

        for i, slot in enumerate(order, start=1):
            x, y = slots[slot]
            actual_before = pyautogui.position()
            pyautogui.moveTo(x, y)
            time.sleep(HOVER_DELAY)
            actual_after = pyautogui.position()
            current = grab_rgb(sct, monitor)

            diff_img, change_px = diff_visual(baseline, current)

            tag = f"{i:02d}_{slot}"
            Image.fromarray(current).save(DEBUG_DIR / f"{tag}.png")
            Image.fromarray(diff_img).save(DEBUG_DIR / f"{tag}_diff.png")
            print(
                f"  {slot:18s} target=({x},{y}) actual_before={actual_before} "
                f"actual_after={actual_after} changed_px={change_px}"
            )

        pyautogui.moveTo(rest[0], rest[1])

    print(f"\n[debug] Done. Open {DEBUG_DIR} and look at:")
    print("  - 00_baseline.png (should show inventory with cursor at rest)")
    print("  - NN_<slot>.png   (should show inventory with tooltip on that slot)")
    print("  - NN_<slot>_diff.png (red = pixels different from baseline)")


def main():
    if not CONFIG_PATH.exists():
        print(f"Missing {CONFIG_PATH.name}. Run calibrate.py first.")
        return
    config = json.loads(CONFIG_PATH.read_text())

    print("Press F8 with inventory open to run debug capture.")
    print("Press ESC to quit.\n")

    keyboard.add_hotkey("f8", lambda: run_debug(config))
    keyboard.wait("esc")


if __name__ == "__main__":
    main()
