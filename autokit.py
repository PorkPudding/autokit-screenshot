"""
AutoKitScreenshot — unified entry point (and the PyInstaller exe target).

Default behavior (double-click the exe / run with no args): open the GUI.
It auto-calibrates on first run and provides Capture / calibration buttons;
F8 works globally while it's open.

CLI options (for troubleshooting / power users; run from source for
console output):
  --cli              headless capture listener (the old console mode)
  --calibrate        full manual calibration (18 guided steps)
  --calibrate-stats  re-calibrate just the stats panel
  --auto-calibrate   regenerate slots.json from the built-in profile
  --check            verify environment and config, then exit
"""
import argparse
import io
import sys

from common import app_dir

# In a windowed (no-console) exe, stdout/stderr may be missing; stray
# print()s from library code must not crash the app.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()


def pause_if_frozen():
    """Keep the console window open when launched by double-click."""
    if getattr(sys, "frozen", False):
        try:
            input("\nPress Enter to exit...")
        except Exception:
            # No usable stdin (windowed build) — nothing to hold open.
            pass


def run_check():
    print(f"App dir:  {app_dir()}")
    cfg_path = app_dir() / "slots.json"
    if not cfg_path.exists():
        print("Config:   slots.json missing (auto-calibration will run on start)")
    else:
        import capture
        config = capture.load_config()
        if config is None:
            print("Config:   slots.json INVALID — delete it or re-calibrate")
        else:
            auto = " (auto-calibrated)" if config.get("auto_calibrated") else ""
            print(f"Config:   {len(config['order'])} slots, "
                  f"stats={'yes' if config.get('stats') else 'no'}{auto}")
    from common import find_game_window
    win = find_game_window()
    print(f"Game:     {'found: ' + win.title.strip() if win else 'not running'}")
    print("OK")


def main():
    parser = argparse.ArgumentParser(
        prog="AutoKitScreenshot",
        description="Capture Dark and Darker gear tooltips + stats into one image.",
    )
    parser.add_argument("--cli", action="store_true",
                        help="headless console capture listener (no GUI)")
    parser.add_argument("--calibrate", action="store_true",
                        help="full manual calibration (guided overlay)")
    parser.add_argument("--calibrate-stats", action="store_true",
                        help="re-calibrate just the stats panel")
    parser.add_argument("--auto-calibrate", action="store_true",
                        help="regenerate slots.json from the built-in profile")
    parser.add_argument("--check", action="store_true",
                        help="verify environment and config, then exit")
    args = parser.parse_args()

    if args.check:
        run_check()
        return

    if args.calibrate:
        import calibrate
        calibrate.main()
        pause_if_frozen()
        return

    if args.calibrate_stats:
        import calibrate_stats
        calibrate_stats.main()
        pause_if_frozen()
        return

    if args.auto_calibrate:
        from reference_profile import auto_calibrate
        auto_calibrate()
        pause_if_frozen()
        return

    if args.cli:
        # Headless console mode: ensure a config exists, then listen for F8.
        cfg_path = app_dir() / "slots.json"
        if not cfg_path.exists():
            print("No calibration found — auto-calibrating from the built-in profile.")
            print("(Make sure Dark and Darker is running in borderless windowed mode.)\n")
            from reference_profile import auto_calibrate
            if not auto_calibrate():
                print("\nAuto-calibration failed. Start the game and run this again, "
                      "or run with --calibrate for manual setup.")
                pause_if_frozen()
                return
            print()
        import capture
        capture.main()
        pause_if_frozen()
        return

    # Default: the GUI.
    import gui
    gui.main()


if __name__ == "__main__":
    main()
