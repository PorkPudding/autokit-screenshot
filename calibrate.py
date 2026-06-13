"""
Full calibration: gear slots + stats panel in one pass.

Usage:
    python calibrate.py

A small always-on-top window walks you through every step. Writes
everything to slots.json next to this script. If you only want to
redo the stats portion, use calibrate_stats.py.
"""
import json

from calibration_overlay import CalibrationOverlay
from common import app_dir, find_game_window, window_rect

SLOT_ORDER = [
    "helmet",
    "necklace",
    "chest",
    "cape",
    "hands",
    "legs",
    "boots",
    "ring_left",
    "ring_right",
    "weapon1_main",
    "weapon1_offhand",
    "weapon2_main",
    "weapon2_offhand",
]

# Weapon sets hold either one two-handed weapon or two one-handers, so each
# box needs a hover point in each half. The capture script automatically
# drops the duplicate tooltip when a two-hander fills the whole box.
SLOT_DESCRIPTIONS = {
    "weapon1_main": "Hover the LEFT half of weapon set 1 (the left weapon box). "
                    "If a two-handed weapon is equipped it fills the whole box — "
                    "just aim at the left half.",
    "weapon1_offhand": "Hover the RIGHT half of weapon set 1 (the left weapon box).",
    "weapon2_main": "Hover the LEFT half of weapon set 2 (the right weapon box).",
    "weapon2_offhand": "Hover the RIGHT half of weapon set 2 (the right weapon box).",
}

STATS_STEPS = [
    (
        "details_button",
        "Hover the 'Close Details' button at the bottom of the stats panel.",
    ),
    (
        "scroll_top",
        "Hover the position you'd click to scroll the stats list to the very TOP "
        "(usually the top arrow of the scroll bar).",
    ),
    (
        "scroll_bottom",
        "Hover the position you'd click to scroll the stats list to the very BOTTOM "
        "(usually the bottom arrow of the scroll bar).",
    ),
    (
        "panel_tl",
        "Hover the TOP-LEFT corner of the area you want captured "
        "(just above 'Strength', left of the stat names).",
    ),
    (
        "panel_br",
        "Hover the BOTTOM-RIGHT corner of the area you want captured "
        "(below the last visible stat, LEFT of the scroll bar so it isn't included).",
    ),
]

CONFIG_PATH = app_dir() / "slots.json"


def build_steps():
    steps = []

    # Gear phase
    steps.append((
        "rest",
        "Pick an empty area away from any gear slot or UI button — "
        "e.g. inside the empty inventory grid at the bottom. "
        "The capture script parks the cursor here before each screenshot.",
    ))
    for slot in SLOT_ORDER:
        label = slot.replace("_", " ")
        desc = SLOT_DESCRIPTIONS.get(slot, f"Hover over the {label} slot.")
        steps.append((slot, desc))

    # Transition: user must manually open the details panel so the scroll bar appears.
    steps.append((
        None,
        "Gear positions recorded. Now click 'Open Details' in-game so the stats panel "
        "expands and the scroll bar becomes visible. Press SPACE when ready.",
    ))

    # Stats phase
    steps.extend(STATS_STEPS)
    return steps


def run_calibration(parent=None, emit=print):
    """Run the guided calibration and save slots.json. Returns True on
    success, False on abort. `parent` embeds the overlay in an existing
    Tk app instead of creating its own root."""
    steps = build_steps()
    overlay = CalibrationOverlay(
        title="DnD AKS — Full Calibration",
        intro="Open your inventory in-game with the Details panel CLOSED. "
              "Follow the prompts: hover each target and press SPACE.",
        steps=steps,
    )
    results = overlay.run(parent=parent)
    if results is None:
        emit("Calibration aborted.")
        return False

    existing = {}
    if CONFIG_PATH.exists():
        try:
            existing = json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass

    existing["rest"] = results.pop("rest")
    existing["slots"] = {k: results[k] for k in SLOT_ORDER}
    existing["order"] = SLOT_ORDER
    existing["stats"] = {key: results[key] for key, _ in STATS_STEPS}
    existing.pop("auto_calibrated", None)

    # Record where the game window sits so capture.py can refuse to run
    # against a moved/resized window (the absolute coords would be wrong).
    win = find_game_window()
    if win is not None:
        existing["window"] = window_rect(win)
    else:
        existing["window"] = None
        emit("WARNING: couldn't find the game window — calibration saved without "
             "a window-position record, so window moves can't be detected.")

    CONFIG_PATH.write_text(json.dumps(existing, indent=2))
    emit(f"Saved {len(SLOT_ORDER)} gear slots + rest + {len(STATS_STEPS)} stats points "
         f"to {CONFIG_PATH.name}")
    return True


def main():
    run_calibration()


if __name__ == "__main__":
    main()
