"""
Built-in calibration profile and auto-calibration.

The reference data is a verified manual calibration captured at
2560x1440 borderless. Dark and Darker (Unreal Engine) scales its UI
uniformly with screen height, so for other resolutions we anchor every
point to the game window's center and scale by height/1440. That is
exact for any 16:9 resolution; on other aspect ratios it assumes the
inventory UI stays centered as a block — if that turns out wrong, the
manual calibration (--calibrate) is the fallback.
"""
import json

from common import REFERENCE_H, REFERENCE_W, app_dir, find_game_window, window_rect

# Verified manual calibration @ 2560x1440 borderless, window at (0, 0).
REFERENCE = {
    "rest": [1594, 713],
    "slots": {
        "helmet": [1149, 323],
        "necklace": [1227, 332],
        "chest": [1138, 451],
        "cape": [1271, 494],
        "hands": [1023, 686],
        "legs": [1137, 673],
        "boots": [1285, 709],
        "ring_left": [1030, 602],
        "ring_right": [1257, 598],
        "weapon1_main": [866, 359],
        "weapon1_offhand": [956, 358],
        "weapon2_main": [1341, 353],
        "weapon2_offhand": [1434, 354],
    },
    "order": [
        "helmet", "necklace", "chest", "cape", "hands", "legs", "boots",
        "ring_left", "ring_right",
        "weapon1_main", "weapon1_offhand", "weapon2_main", "weapon2_offhand",
    ],
    "stats": {
        "details_button": [397, 1357],
        "scroll_top": [734, 239],
        "scroll_bottom": [732, 1272],
        "panel_tl": [68, 224],
        "panel_br": [721, 1320],
    },
}


def _scale_point(p, win_cx, win_cy, scale):
    return [
        round(win_cx + (p[0] - REFERENCE_W / 2) * scale),
        round(win_cy + (p[1] - REFERENCE_H / 2) * scale),
    ]


def scale_profile(rect):
    """Map the reference profile onto a game window rect [l, t, w, h]."""
    left, top, w, h = rect
    scale = h / REFERENCE_H
    cx = left + w / 2
    cy = top + h / 2

    def sp(p):
        return _scale_point(p, cx, cy, scale)

    return {
        "rest": sp(REFERENCE["rest"]),
        "slots": {k: sp(v) for k, v in REFERENCE["slots"].items()},
        "order": list(REFERENCE["order"]),
        "stats": {k: sp(v) for k, v in REFERENCE["stats"].items()},
        "window": list(rect),
        "auto_calibrated": True,
    }


def auto_calibrate(emit=print):
    """Find the game window, scale the built-in profile to it, and write
    slots.json. Returns True on success."""
    win = find_game_window()
    if win is None:
        emit("Couldn't find the Dark and Darker window. Launch the game "
             "(borderless windowed) and try again.")
        return False

    rect = window_rect(win)
    left, top, w, h = rect
    if w <= 0 or h <= 0:
        emit(f"Game window reports an unusable size {w}x{h} — is it minimized?")
        return False

    config = scale_profile(rect)
    out = app_dir() / "slots.json"
    out.write_text(json.dumps(config, indent=2))

    scale = h / REFERENCE_H
    emit(f"Auto-calibrated for game window {w}x{h} at ({left}, {top}) "
         f"(UI scale {scale:.3f}) -> {out.name}")
    if abs(w / h - 16 / 9) > 0.01:
        emit("CAUTION: your aspect ratio is not 16:9. The built-in profile "
             "assumes the inventory UI stays centered; if captures land in "
             "the wrong places, run a manual calibration.")
    emit("Do a test capture and check the output. If tooltips are missed "
         "or misaligned, run a manual calibration.")
    return True
