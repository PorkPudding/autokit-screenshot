"""
Calibrate stats-panel positions: details toggle button, scroll bar
click points, and crop region.

Usage:
    python calibrate_stats.py

Open the inventory and click "Open Details" first so the scroll bar is
visible. A small always-on-top window walks you through the steps.
Adds a `stats` section to slots.json without touching gear calibration.
"""
import json

from calibration_overlay import CalibrationOverlay
from common import app_dir

CONFIG_PATH = app_dir() / "slots.json"

STEPS = [
    (
        "details_button",
        "Hover the 'Close Details' / 'Open Details' button at the bottom of the stats panel.",
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


def main():
    if not CONFIG_PATH.exists():
        print("slots.json not found. Run calibrate.py first.")
        return
    config = json.loads(CONFIG_PATH.read_text())

    overlay = CalibrationOverlay(
        title="DnD AKS — Stats Calibration",
        intro="Open the inventory and click 'Open Details' first so the scroll bar is visible.",
        steps=STEPS,
    )
    results = overlay.run()
    if results is None:
        print("Aborted.")
        return

    config["stats"] = results
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    print(f"Saved stats section to {CONFIG_PATH.name}")


if __name__ == "__main__":
    main()
