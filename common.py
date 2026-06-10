"""
Shared screen/window helpers and app paths.
"""
import ctypes
import sys
from pathlib import Path

import numpy as np
import pygetwindow as gw

GAME_TITLE_HINTS = ("dark and darker", "dungeoncrawler", "dungeon crawler")

# Resolution the built-in profile and detection constants were tuned at.
REFERENCE_W = 2560
REFERENCE_H = 1440


def app_dir():
    """Directory for slots.json / output — next to the exe when frozen
    (PyInstaller unpacks __file__ into a temp dir), else the source dir."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def grab_rgb(sct, monitor):
    """Screenshot one monitor as an HxWx3 RGB numpy array."""
    sct_img = sct.grab(monitor)
    arr = np.frombuffer(sct_img.bgra, dtype=np.uint8).reshape(sct_img.height, sct_img.width, 4)
    return np.ascontiguousarray(arr[:, :, [2, 1, 0]])


def pick_monitor(sct, win):
    """Return the mss monitor dict that contains the game window's center."""
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


def focus_game():
    """Find the game window and politely ask Windows to focus it."""
    win = find_game_window()
    if win is None:
        return None
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:
        pass
    return win


def force_focus(win):
    """Stronger Win32 focus: AttachThreadInput + SetForegroundWindow.

    Use when focus_game()'s polite activate() isn't enough (Windows
    refuses foreground changes from background processes).
    """
    if win is None:
        return False
    try:
        hwnd = win._hWnd
    except AttributeError:
        print("[focus] WARNING: window object has no _hWnd — cannot force focus.")
        return False
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
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


def window_rect(win):
    """[left, top, width, height] of a pygetwindow window."""
    return [win.left, win.top, win.width, win.height]
