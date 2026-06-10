"""
Full calibration: gear slots + stats panel in one pass.

Usage:
    python calibrate.py

A small always-on-top window walks you through every step. Writes
everything to slots.json next to this script. If you only want to
redo the stats portion, use calibrate_stats.py.
"""
import json
from pathlib import Path

from calibration_overlay import CalibrationOverlay

SLOT_ORDER = [
    "helmet",
    "necklace",
    "chest",
    "cape",
    "hands",
    "legs",
    "boots",
    "primary_weapon",
    "ring_left",
    "ring_right",
    "secondary_weapon",
]

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

CONFIG_PATH = Path(__file__).parent / "slots.json"


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
        steps.append((slot, f"Hover over the {label} slot."))

    # Transition: user must manually open the details panel so the scroll bar appears.
    steps.append((
        None,
        "Gear positions recorded. Now click 'Open Details' in-game so the stats panel "
        "expands and the scroll bar becomes visible. Press SPACE when ready.",
    ))

    # Stats phase
    steps.extend(STATS_STEPS)
    return steps


def main():
    steps = build_steps()
    overlay = CalibrationOverlay(
        title="D&D Full Calibration",
        intro="Open your inventory in-game with the Details panel CLOSED. "
              "Follow the prompts: hover each target and press SPACE.",
        steps=steps,
    )
    results = overlay.run()
    if results is None:
        print("Aborted.")
        return

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
    CONFIG_PATH.write_text(json.dumps(existing, indent=2))
    print(
        f"Saved {len(SLOT_ORDER)} gear slots + rest + {len(STATS_STEPS)} stats points "
        f"to {CONFIG_PATH.name}"
    )


if __name__ == "__main__":
    main()
