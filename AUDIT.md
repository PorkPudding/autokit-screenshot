# Code audit — AutoKitScreenshot

Findings from reading `capture.py`, `calibrate.py`, `calibrate_stats.py`,
`calibration_overlay.py`, `debug_capture.py`, `slots.json`, and
`requirements.txt`. Ordered by severity.

> **Status 2026-06-10:** items 1, 2, 4, 5, 7, 8, 11 fixed (see git history).
> Item 3 mitigated with a comment; a hold-ESC mid-capture abort remains open.
> Items 6, 9, 10, 12 and the nits remain open.

## Bugs

### 1. `pygetwindow` missing from `requirements.txt`

Both `capture.py` (line 21) and `debug_capture.py` (line 23) do
`import pygetwindow as gw`, but `requirements.txt` only lists
`pyautogui`, `mss`, `Pillow`, `keyboard`, `numpy`, `scipy`. A clean
`pip install -r requirements.txt` will succeed and then crash at first
run with `ModuleNotFoundError`.

**Fix:** add `pygetwindow` to `requirements.txt`. (Note: `pyautogui`
on Windows pulls it in transitively today, but that's a fragile
assumption to rely on.)

### 2. F8 can re-enter `run_capture` while one is already running

`keyboard.add_hotkey(HOTKEY, lambda: run_capture(config))` (capture.py
line 415) runs the callback on the `keyboard` library's worker thread.
Press F8 twice quickly — or once during a long stats stitch — and two
captures will run concurrently. Both will move the mouse, both will
take screenshots, both will scroll. Output will be garbage.

**Fix:** wrap with a `threading.Lock` and `acquire(blocking=False)`;
skip the second press with a "[capture] busy, ignored" log line.

### 3. `pyautogui.FAILSAFE = False` removes the only emergency stop

Disabling failsafe (capture.py line 25, debug_capture.py line 26) means
slamming the cursor into a screen corner no longer aborts the script.
If a calibration is wrong and the script starts clicking wildly, you
have no fast way out except killing the terminal.

Probably done because the script *itself* moves the cursor to absolute
positions which might briefly hit a corner. But it's worth a comment
explaining the tradeoff, and ideally a secondary kill switch (e.g.
holding ESC for 1s during a capture, polled between slots).

### 4. `KeyError` if `slots.json` is from an older version

`capture.py` line 411 does `config['order']` without a guard. Older
`slots.json` files (e.g. produced before the `order` key was added, or
produced by `calibrate_stats.py` against a missing-gear config) will
crash with `KeyError: 'order'` instead of a friendly "re-run
calibrate.py" message.

Same risk for `config['stats']` in `capture.py` — though there the
`config.get("stats")` guard at line 380 is correct.

**Fix:** validate the config keys at load time with a clear error.

### 5. `force_focus` swallows `AttributeError` silently

`debug_capture.py` line 69: `win._hWnd` may not exist on some
pygetwindow versions. The function returns `False` without printing
anything, then `run_debug` continues as if focus succeeded. Combined
with the comment in `00_baseline.png` showing past failures of exactly
this kind (desktop captured instead of game), a silent return is the
wrong default — it masks the very problem the diagnostic exists to
surface.

**Fix:** print a warning, or raise.

## Code quality

### 6. `grab_rgb`, `pick_monitor`, `find_game_window` are duplicated

These three functions are copy-pasted between `capture.py` and
`debug_capture.py`. Any future fix has to be applied in two places.

**Fix:** extract to a `common.py` (or similar) and import.

### 7. `capture.py` has no module-level entry shielding the keyboard listener

`keyboard.wait(QUIT_KEY)` blocks forever. If `run_capture` raises an
exception inside the F8 callback, the listener stays alive but the
error message goes to whatever stderr the `keyboard` thread is using
— often invisible. Wrap the callback in a `try/except` that prints
the traceback.

### 8. `requirements.txt` is unpinned

All six packages are listed bare, so a future `numpy 2.x` or `mss`
API change could break things silently. Pin to known-good versions
(`pip freeze > requirements.txt`).

### 9. `pyautogui.click` rate is uncapped

`multi_click` does `SCROLL_CLICKS = 30` clicks with a 20ms interval.
That's 30 fast clicks aimed at a small scrollbar arrow. If the game
reads them as right-click-while-shift or interprets some as double
clicks on adjacent UI, you can get weird side effects. Lower
`SCROLL_CLICKS` to the minimum that empirically reaches the
top/bottom, or detect end-of-list (e.g. screenshot before/after and
stop when no change).

### 10. Stats panel's "did the list scroll" check is fragile

`stitch_vertical` line 222 compares `top[:overlap_h]` to
`bottom[:overlap_h]` — the top of the top screenshot vs the top of
the bottom screenshot. If the list is exactly long enough that
scrolling reveals one new row at the bottom but the first N rows
are still visible, `mean_diff` could be tiny and we'd misclassify
as "identical." Better signal: compare the *bottom* of the top
screenshot to the *bottom* of the bottom screenshot — those should
differ whenever the scroll actually moved.

### 11. `calibrate.py` writes calibration even on partial run

The overlay returns the full results dict at the end, but if the user
quits halfway via ESC (`aborted = True`), `overlay.run()` returns
`None` and we bail. Good. But there's no mid-run safeguard if the
user closes the Tk window via the X button — `mainloop` returns and
we proceed to write `results`, which may be empty or partial,
producing `KeyError` on `results.pop("rest")`. Add a window-close
handler that sets `aborted = True`.

### 12. Magic numbers throughout `capture.py` aren't traceable to anything

Constants like `CURSOR_MASK_RADIUS = 35`, `SLOT_CLIP_RADIUS = 80`,
`DILATION_ITERS = 5`, `MIN_TOOLTIP_AREA = 8000` are all "tuned by
hand on one screen." On a 4K monitor or with a different UI scale,
these are wrong. Consider scaling them to monitor DPI, or at least
documenting the resolution they were tuned for.

## Nits

- `capture.py` line 351: `OUTPUT_DIR.mkdir(exist_ok=True)` — pass
  `parents=True` defensively.
- `capture.py` line 286: hardcoded `time.sleep(0.4)` for "close
  details" — should be a named constant like the others.
- `debug_capture.py` has `DIFF_THRESHOLD = 25` while `capture.py`
  has `DIFF_THRESHOLD = 50`. Intentional (debug is more sensitive)
  but worth a comment.
- `calibration_overlay.py` `_tick` uses `keyboard.is_pressed` from
  Tk's main thread. Works, but binding Tk's `<KeyPress-space>` event
  would be more idiomatic and would let the overlay coexist nicely
  with other `keyboard` hooks.

## What's good

- The tooltip detection pipeline (baseline diff → cursor punch-out →
  dilate → largest blob → slot-zone clip → density-based bbox) is a
  thoughtful, layered approach that handles real failure modes.
- The "looks like tooltip" rejector for empty slots is a nice touch
  — without it, empty weapon slots would capture the character
  preview model.
- NCC-based vertical stitching with a fallback red separator is
  much better than blind concatenation.
- `debug_capture.py` exists at all. Most projects of this size don't
  have a dedicated diagnostic mode.
- Inline comments explaining the *why* (e.g. "carve slot zone so the
  hover highlight doesn't drag the bbox") are excellent.
