# AutoKitScreenshot

Automated gear-and-stats screenshot tool for *Dark and Darker*. With your
inventory open, press a hotkey and the tool hovers each gear slot, captures
the tooltip that pops up, opens the details panel, scrolls through the full
stats list, and stitches it all into a single PNG.

Example output: a stats column on the left and a 4-wide grid of gear
tooltips on the right (helmet, necklace, chest, cape, hands, legs, boots,
primary weapon, both rings, secondary weapon).

## Requirements

- Windows (uses `pygetwindow` and `keyboard`, and `debug_capture.py` calls into `user32.dll`)
- Python 3.9+
- Dark and Darker running in **borderless windowed** mode (the overlay floats above the game; fullscreen exclusive won't work)

Install Python dependencies:

```
pip install -r requirements.txt
```

> Note: `requirements.txt` is missing `pygetwindow`. Until that's fixed, also run `pip install pygetwindow`.

The `keyboard` package may require running Python as Administrator to register global hotkeys.

## Files

| File | Purpose |
|---|---|
| `capture.py` | Main capture loop. Press F8 to grab a kit screenshot. |
| `calibrate.py` | Full calibration: records all 11 gear slot positions plus the stats panel. Writes `slots.json`. |
| `calibrate_stats.py` | Re-calibrates just the stats panel section without touching gear positions. |
| `calibration_overlay.py` | The always-on-top Tk window used by both calibrators. Not run directly. |
| `debug_capture.py` | Diagnostic tool. Dumps raw screenshots + red diff masks per slot to `debug/`, with a stronger Win32 focus call. Use when capture is misbehaving. |
| `slots.json` | Calibrated cursor positions. Created by `calibrate.py`. |
| `output/` | Where `kit_<timestamp>.png` files land. |
| `debug/` | Where `debug_capture.py` dumps its diagnostic PNGs. |

## How it works

**Capture (`capture.py`)** uses a diff approach to find each tooltip:

1. Focus the game window and park the cursor at a `rest` point outside any slot. Take a *baseline* screenshot.
2. For each gear slot in order:
   - Move the cursor onto the slot, wait `HOVER_DELAY` for the tooltip to animate in.
   - Take another screenshot.
   - Diff against the baseline. Pixels that changed by more than `DIFF_THRESHOLD` are the tooltip (plus the slot's hover-highlight and the cursor itself).
   - Punch a circular hole around the cursor's start and end positions to remove the cursor sprite from the mask.
   - Dilate, find the largest connected blob, then carve a circular slot-exclusion region out of it (so the hover highlight on the slot icon doesn't drag the bounding box back to the slot).
   - Take a density-based tight bbox — drop rows/cols that barely have any diff pixels (faint shadow bleed).
   - Reject the result if the cropped region looks like the character-preview model (too bright, too colorful) instead of a tooltip.
3. After all slots, pack the surviving tooltips into a 4-column grid.

**Stats panel** is captured by:

1. Click the *Open/Close Details* button to expand the panel.
2. Click the scroll-top arrow many times to make sure the list is at the top, screenshot it.
3. Click the scroll-bottom arrow many times to make sure it's at the bottom, screenshot it.
4. Crop both screenshots to the calibrated panel rectangle.
5. Stitch them vertically using normalized cross-correlation — take the last `NEEDLE_HEIGHT` rows of the bottom image as a needle, slide it down the top image, and concatenate at the best-matching overlap. If no good match is found, concatenate with a red separator bar so the gap is visible. If the two screenshots are nearly identical (list didn't scroll), just keep the top one.
6. Close the details panel.

**Compose:** stats column on the left, gear grid on the right, padded background, saved to `output/kit_<YYYYMMDD_HHMMSS>.png`.

## Quick start

1. Install requirements (see above).
2. Launch Dark and Darker in borderless windowed mode and open your inventory **with the Details panel closed**.
3. Run calibration once per resolution/UI-scale change:

   ```
   python calibrate.py
   ```

   A small dark always-on-top window appears. For each prompt, hover the cursor over the target in-game and press SPACE. Press ESC to abort. When the gear phase is done, click "Open Details" in-game so the scroll bar appears, then press SPACE and continue through the stats prompts.

4. Run the capture loop:

   ```
   python capture.py
   ```

   With your inventory open (Details panel closed; the script opens it for the stats phase), press **F8** to capture. Output goes to `output/kit_<timestamp>.png`. Press **ESC** to quit.

## Troubleshooting

**Captured screenshots show the desktop or VS Code, not the game.** The game window didn't get focus in time. Try `python debug_capture.py` — it uses a more aggressive Win32 `AttachThreadInput` + `SetForegroundWindow` call. If `00_baseline.png` in `debug/` shows the wrong window, focus is the problem. Increase `WARMUP_DELAY` or run as Administrator.

**A slot shows `SKIPPED (empty or no tooltip)` in the log.** Either the slot is genuinely empty (no item equipped) or the tooltip didn't animate in fast enough. Increase `HOVER_DELAY` in `capture.py`. Also check that the slot's calibrated point in `slots.json` is actually on the slot icon, not in a gap.

**Tooltip bbox is too tight or too loose.** Tune `BBOX_TIGHTEN_FRAC` (lower = looser bbox), `SLOT_CLIP_RADIUS` (size of the carved-out slot exclusion), or `DIFF_THRESHOLD` (higher = ignore more faint changes).

**Stats stitching shows a red bar in the middle.** The two top/bottom captures didn't have a recognizable overlap — usually because the panel is too short to need stitching, or the scroll didn't take effect. Confirm `scroll_top` and `scroll_bottom` in `slots.json` actually land on the scroll arrows.

**Stats shows just the top half with no error.** Means the stitcher detected the two screenshots are nearly identical — the list isn't long enough to scroll. That's fine.

## Tuning knobs (in `capture.py`)

All the constants at the top of `capture.py` are documented inline. The most useful to tweak:

- `HOVER_DELAY` — bump up if tooltips show up partial.
- `DIFF_THRESHOLD` — lower to detect subtler tooltips, raise to ignore faint UI shimmer.
- `MIN_TOOLTIP_AREA` — pixel-count sanity check; raise if you're getting tiny false positives.
- `EMPTY_SLOT_MAX_BRIGHTNESS` / `EMPTY_SLOT_MAX_SATURATION` — controls the character-preview rejector.
- `SCROLL_CLICKS` — number of times to click each scroll arrow; raise for very long stats lists.
