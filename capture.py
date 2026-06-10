"""
Capture all gear tooltips and stitch them into a 4x3 grid.

Usage:
    python capture.py

Press F8 with the inventory open to start a capture.
Press ESC to quit.

Outputs go to ./output/kit_<timestamp>.png.
"""
import json
import time
from datetime import datetime
from pathlib import Path

import keyboard
import mss
import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import Image
from scipy import ndimage

pyautogui.FAILSAFE = False

CONFIG_PATH = Path(__file__).parent / "slots.json"
OUTPUT_DIR = Path(__file__).parent / "output"

HOTKEY = "f8"
QUIT_KEY = "esc"
GRID_COLS = 4

GAME_TITLE_HINTS = ("dark and darker", "dungeoncrawler", "dungeon crawler")

WARMUP_DELAY = 1.0       # seconds after bringing game to front
HOVER_DELAY = 0.75       # seconds — let tooltip animate in
FIRST_HOVER_BONUS = 0.4  # extra wait on first slot
DIFF_THRESHOLD = 50      # per-pixel summed-channel diff to count as changed
                          # (higher = ignores tooltip shadow / faint UI shimmer)
CURSOR_MASK_RADIUS = 35  # px around cursor positions to ignore in diff
DILATION_ITERS = 5       # close gaps in tooltip text without bridging to the slot
MIN_TOOLTIP_AREA = 8000  # sanity check on detected component size
SLOT_CLIP_RADIUS = 80    # px around slot center to exclude from final tooltip bbox
BBOX_TIGHTEN_FRAC = 0.12 # density threshold when tightening bbox — keep rows/cols
                          # whose pixel count is >= 12% of the fullest row/col

# Empty-slot rejection — distinguishes real tooltips from the character preview
# that shows when a weapon/gear slot is empty
EMPTY_SLOT_MAX_BRIGHTNESS = 95   # tooltips are mostly dark
EMPTY_SLOT_MAX_SATURATION = 55   # tooltips have low color saturation

# Stats panel timing & behavior
DETAILS_OPEN_DELAY = 0.7   # wait for details panel to expand
SCROLL_DELAY = 0.4         # wait for scroll to settle
STATS_REST_DELAY = 0.3     # wait after parking cursor before screenshot
SCROLL_CLICKS = 30         # multi-click the scroll target to ensure it reaches the end
SCROLL_CLICK_INTERVAL = 0.02
NEEDLE_HEIGHT = 120        # rows of bottom image used as a template when searching top
STITCH_NCC_MIN = 0.70      # minimum normalized correlation to accept overlap match
IDENTICAL_DIFF = 2.0       # below this mean diff, treat images as "scrolling didn't move"


def grab_rgb(sct, monitor):
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


def make_diff_mask(baseline, current):
    diff = np.abs(current.astype(np.int16) - baseline.astype(np.int16)).sum(axis=2)
    return diff > DIFF_THRESHOLD


def punch_hole(mask, x, y, r):
    h, w = mask.shape
    y0, y1 = max(0, y - r), min(h, y + r + 1)
    x0, x1 = max(0, x - r), min(w, x + r + 1)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask[y0:y1, x0:x1] &= (xx - x) ** 2 + (yy - y) ** 2 > r * r


def _tight_bbox(component, frac=BBOX_TIGHTEN_FRAC):
    """Density-based bounding box: drop rows/columns that are nearly empty
    (e.g. faint shadow bleed around the tooltip) before taking min/max.
    """
    row_counts = component.sum(axis=1)
    col_counts = component.sum(axis=0)
    if row_counts.max() == 0 or col_counts.max() == 0:
        return None
    row_th = max(8, int(row_counts.max() * frac))
    col_th = max(8, int(col_counts.max() * frac))
    rows = np.where(row_counts >= row_th)[0]
    cols = np.where(col_counts >= col_th)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1


def find_tooltip_bbox(mask, slot_local):
    """Return (x0, y0, x1, y1) of the tooltip, excluding the gear slot area.

    Steps:
    1. Dilate the diff mask and find the largest connected blob.
    2. Clip the slot's circular region out of that blob (prevents gear
       icon / slot highlight from pulling the bbox toward the slot).
    3. Tighten the bbox by ignoring rows/columns that barely have any
       diff pixels (shadow bleed, faint edges).
    """
    dilated = ndimage.binary_dilation(mask, iterations=DILATION_ITERS)
    labels, n = ndimage.label(dilated)
    if n == 0:
        return None
    sizes = ndimage.sum(dilated, labels, index=np.arange(1, n + 1))
    biggest = int(np.argmax(sizes)) + 1
    if sizes[biggest - 1] < MIN_TOOLTIP_AREA:
        return None

    component = labels == biggest
    h, w = component.shape
    sx, sy = slot_local
    yy, xx = np.ogrid[:h, :w]
    slot_zone = (xx - sx) ** 2 + (yy - sy) ** 2 <= SLOT_CLIP_RADIUS ** 2
    component = component & ~slot_zone

    return _tight_bbox(component)


def looks_like_tooltip(img_rgb):
    """Reject character-preview captures (empty gear slots) by color profile.

    Tooltips are mostly dark with low saturation. Character previews are
    brighter and more colorful.
    """
    if img_rgb.size == 0:
        return False
    avg_bright = float(img_rgb.mean())
    if avg_bright >= EMPTY_SLOT_MAX_BRIGHTNESS:
        return False
    maxc = img_rgb.max(axis=2).astype(np.int16)
    minc = img_rgb.min(axis=2).astype(np.int16)
    sat = float((maxc - minc).mean())
    if sat >= EMPTY_SLOT_MAX_SATURATION:
        return False
    h, w = img_rgb.shape[:2]
    if h == 0 or w == 0:
        return False
    ar = w / h
    return 0.3 < ar < 2.5


def capture_slot(sct, monitor, baseline, rest_local, slot_pos, hover_delay):
    pyautogui.moveTo(slot_pos[0], slot_pos[1])
    time.sleep(hover_delay)
    current = grab_rgb(sct, monitor)

    slot_local = (slot_pos[0] - monitor["left"], slot_pos[1] - monitor["top"])
    mask = make_diff_mask(baseline, current)
    punch_hole(mask, slot_local[0], slot_local[1], CURSOR_MASK_RADIUS)
    punch_hole(mask, rest_local[0], rest_local[1], CURSOR_MASK_RADIUS)

    bbox = find_tooltip_bbox(mask, slot_local)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    crop = current[y0:y1, x0:x1]
    if not looks_like_tooltip(crop):
        return None
    return Image.fromarray(crop), bbox


def stitch_grid(images, cols=GRID_COLS, padding=12, bg=(18, 18, 20)):
    """Pack the given PIL images into a grid, skipping any None entries
    and shrinking the grid to fit only the detected pieces."""
    valid = [im for im in images if im is not None]
    if not valid:
        return Image.new("RGB", (200, 200), bg)
    cell_w = max(im.width for im in valid)
    cell_h = max(im.height for im in valid)
    n = len(valid)
    use_cols = min(cols, n)
    rows = (n + use_cols - 1) // use_cols

    canvas_w = use_cols * cell_w + (use_cols + 1) * padding
    canvas_h = rows * cell_h + (rows + 1) * padding
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)

    for i, im in enumerate(valid):
        r, c = divmod(i, use_cols)
        ox = padding + c * (cell_w + padding) + (cell_w - im.width) // 2
        oy = padding + r * (cell_h + padding) + (cell_h - im.height) // 2
        canvas.paste(im, (ox, oy))
    return canvas


def stitch_vertical(top, bottom, needle_height=NEEDLE_HEIGHT):
    """Stitch two screenshots vertically using normalized cross-correlation.

    If the images are nearly identical, scrolling didn't move anything —
    return `top` alone. If no confident overlap is found, concatenate
    with a red separator so the user knows the middle is missing.
    """
    h_top, w, _ = top.shape
    h_bot = bottom.shape[0]

    if h_top < needle_height + 20 or h_bot < needle_height:
        return np.vstack([top, bottom]), "too-small"

    # If top ≈ bottom, assume scrolling didn't move the list.
    overlap_h = min(h_top, h_bot)
    mean_diff = float(np.abs(
        top[:overlap_h].astype(np.int16) - bottom[:overlap_h].astype(np.int16)
    ).mean())
    if mean_diff < IDENTICAL_DIFF:
        return top, "identical"

    # Grayscale NCC matching — rewards matching *patterns*, not flat regions
    top_g = top.mean(axis=2).astype(np.float32)
    bot_g = bottom.mean(axis=2).astype(np.float32)

    needle = bot_g[:needle_height]
    n_dev = needle - needle.mean()
    n_norm = float(np.sqrt((n_dev ** 2).sum()))
    if n_norm < 50:
        return np.vstack([top, bottom]), "needle-blank"

    best_y, best_ncc = None, -2.0
    start_y = max(1, needle_height // 2)
    for y in range(start_y, h_top - needle_height + 1):
        cand = top_g[y:y + needle_height]
        c_dev = cand - cand.mean()
        c_norm = float(np.sqrt((c_dev ** 2).sum()))
        if c_norm < 50:
            continue
        ncc = float((c_dev * n_dev).sum() / (c_norm * n_norm))
        if ncc > best_ncc:
            best_ncc = ncc
            best_y = y

    if best_y is None or best_ncc < STITCH_NCC_MIN:
        sep = np.full((24, w, 3), (120, 40, 40), dtype=np.uint8)
        return np.vstack([top, sep, bottom]), f"no-overlap(ncc={best_ncc:.2f})"

    return np.vstack([top[:best_y], bottom]), f"stitched(y={best_y}, ncc={best_ncc:.2f})"


def multi_click(x, y, times, interval=SCROLL_CLICK_INTERVAL):
    for _ in range(times):
        pyautogui.click(x, y)
        time.sleep(interval)


def capture_stats(sct, monitor, stats_cfg, rest_global, debug_dir=None):
    """Open details, capture top + bottom of stats list, close details, stitch."""
    db = stats_cfg["details_button"]
    st = stats_cfg["scroll_top"]
    sb = stats_cfg["scroll_bottom"]
    tl = stats_cfg["panel_tl"]
    br = stats_cfg["panel_br"]

    pyautogui.click(db[0], db[1])
    time.sleep(DETAILS_OPEN_DELAY)

    multi_click(st[0], st[1], SCROLL_CLICKS)
    time.sleep(SCROLL_DELAY)
    pyautogui.moveTo(rest_global[0], rest_global[1])
    time.sleep(STATS_REST_DELAY)
    top_full = grab_rgb(sct, monitor)

    multi_click(sb[0], sb[1], SCROLL_CLICKS)
    time.sleep(SCROLL_DELAY)
    pyautogui.moveTo(rest_global[0], rest_global[1])
    time.sleep(STATS_REST_DELAY)
    bottom_full = grab_rgb(sct, monitor)

    pyautogui.click(db[0], db[1])
    time.sleep(0.4)

    x0 = min(tl[0], br[0]) - monitor["left"]
    x1 = max(tl[0], br[0]) - monitor["left"]
    y0 = min(tl[1], br[1]) - monitor["top"]
    y1 = max(tl[1], br[1]) - monitor["top"]

    top_crop = top_full[y0:y1, x0:x1]
    bot_crop = bottom_full[y0:y1, x0:x1]

    if debug_dir is not None:
        Image.fromarray(top_crop).save(debug_dir / "stats_top_raw.png")
        Image.fromarray(bot_crop).save(debug_dir / "stats_bottom_raw.png")

    stitched, status = stitch_vertical(top_crop, bot_crop)
    return Image.fromarray(stitched), status


def compose_final(stats_img, gear_grid, padding=20, bg=(18, 18, 20)):
    """Stats column on the left, gear grid on the right."""
    if stats_img is None:
        return gear_grid
    canvas_w = padding + stats_img.width + padding + gear_grid.width + padding
    canvas_h = padding + max(stats_img.height, gear_grid.height) + padding
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)
    canvas.paste(stats_img, (padding, padding + (canvas_h - 2 * padding - stats_img.height) // 2))
    canvas.paste(
        gear_grid,
        (padding + stats_img.width + padding,
         padding + (canvas_h - 2 * padding - gear_grid.height) // 2),
    )
    return canvas


def find_game_window():
    for title in gw.getAllTitles():
        low = title.lower()
        if any(hint in low for hint in GAME_TITLE_HINTS):
            wins = gw.getWindowsWithTitle(title)
            if wins:
                return wins[0]
    return None


def focus_game():
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


def run_capture(config):
    rest = config["rest"]
    order = config["order"]
    slots = config["slots"]

    OUTPUT_DIR.mkdir(exist_ok=True)

    win = focus_game()
    time.sleep(WARMUP_DELAY)

    pyautogui.moveTo(rest[0], rest[1])
    time.sleep(0.5)

    log = []
    with mss.MSS() as sct:
        monitor = pick_monitor(sct, win)
        rest_local = (rest[0] - monitor["left"], rest[1] - monitor["top"])
        baseline = grab_rgb(sct, monitor)
        images = []
        for i, slot in enumerate(order):
            delay = HOVER_DELAY + (FIRST_HOVER_BONUS if i == 0 else 0)
            result = capture_slot(sct, monitor, baseline, rest_local, slots[slot], delay)
            if result is None:
                log.append(f"  {slot:18s} -> SKIPPED (empty or no tooltip)")
                images.append(None)
            else:
                img, bbox = result
                log.append(f"  {slot:18s} -> {img.width}x{img.height} @ ({bbox[0]},{bbox[1]})")
                images.append(img)
        pyautogui.moveTo(rest[0], rest[1])

    grid = stitch_grid(images)

    stats_img = None
    stats_cfg = config.get("stats")
    if stats_cfg:
        try:
            with mss.MSS() as sct:
                monitor = pick_monitor(sct, win)
                stats_img, status = capture_stats(sct, monitor, stats_cfg, rest, debug_dir=OUTPUT_DIR)
            log.append(f"  stats              -> {stats_img.width}x{stats_img.height} [{status}]")
        except Exception as e:
            log.append(f"  stats              -> FAILED: {e}")

    final = compose_final(stats_img, grid)
    out_path = OUTPUT_DIR / f"kit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    final.save(out_path)

    print("\n[capture] Done.")
    if win is None:
        print("  WARNING: couldn't find Dark and Darker window — guessed primary monitor.")
    else:
        print(f"  Game window: '{win.title}'")
    print(f"  Captured monitor: left={monitor['left']} top={monitor['top']} {monitor['width']}x{monitor['height']}")
    for line in log:
        print(line)
    print(f"  Saved {out_path}\n")


def main():
    if not CONFIG_PATH.exists():
        print(f"Missing {CONFIG_PATH.name}. Run calibrate.py first.")
        return
    config = json.loads(CONFIG_PATH.read_text())

    print(f"Loaded {len(config['order'])} slots from {CONFIG_PATH.name}")
    print(f"Press {HOTKEY.upper()} (any window) to capture — game will be auto-focused.")
    print(f"Press {QUIT_KEY.upper()} to quit.\n")

    keyboard.add_hotkey(HOTKEY, lambda: run_capture(config))
    keyboard.wait(QUIT_KEY)
    print("Bye.")


if __name__ == "__main__":
    main()
