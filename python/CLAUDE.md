# Python implementation

## Commands

```bash
# Install (Linux/macOS — dev tools only, Win32 extras unavailable)
python3 -m venv .venv && source .venv/bin/activate.fish && pip install -e ".[dev]"  # fish
# python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"     # bash/zsh

# Install (Windows — full)
py -m pip install -e ".[windows,dev]"

# Run
python -m windows_navigator

# Test / lint / format
make test        # pytest
make lint        # ruff check .
make format      # ruff format .
```

Run a single test file: `pytest tests/test_filter.py`

`make test` requires `pytest` on `PATH`; if the venv is not activated: `.venv/bin/python -m pytest tests/ -q`

```bash
# Release (requires: pip install build, gh authenticated)
./release.sh          # patch bump (0.1.0 → 0.1.1)
./release.sh minor    # minor bump
./release.sh major    # major bump
./release.sh 1.2.3    # explicit version
```

`release.sh` runs lint + tests, bumps `pyproject.toml`, builds wheel + sdist, commits, tags, pushes, and creates a GitHub release via `gh`.

## Tech stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| UI | `tkinter` (stdlib) |
| Win32 API | `pywin32` (`win32gui`, `win32process`, `win32api`, `win32con`) |
| System tray | `pystray` + `Pillow` |
| Global hotkey | configurable via `config.toml`; four options: double-tap Ctrl, Win+Alt+Space, Ctrl+Shift+Space, hold-Ctrl double-tap-Shift — ctypes only, no extra dep |
| Theme detection | `darkdetect` |
| Virtual desktop | Raw ctypes COM + `pyvda` (Windows 11 22H2+ workaround) |
| UIA (tabs) | `comtypes` |
| Linter/formatter | `ruff` (rules E, F, I; line-length 100) |
| Tests | `pytest` + `pytest-mock` |

Windows-only runtime deps (`pywin32`, `pystray`, `pyvda`) are in the `[windows]` extra in `pyproject.toml`. Dev deps (`pytest`, `ruff`) are in `[dev]`. Linux CI installs `.[dev]` only.

## Architecture

### Repository layout

```
src/windows_navigator/
    __init__.py          # empty
    __main__.py          # entry point shim → app.main()
    app.py               # wires everything: Tk root, overlay, hotkey, flash monitor, tray
    models.py            # WindowInfo and TabInfo dataclasses
    filter.py            # filter_windows() — pure Python, no Win32
    controller.py        # OverlayController — pure Python state machine
    provider.py          # RealWindowProvider — Win32 window enumeration + icons
    virtual_desktop.py   # assign_desktop_numbers(), move_window_to_current_desktop(), etc — COM
    activation.py        # activate_window() — Win32 restore + SetForegroundWindow
    overlay.py           # NavigatorOverlay — tkinter Canvas UI
    tabs.py              # UIA tab discovery + activation — Windows-only, deferred imports
    theme.py             # DESKTOP_COLORS, desktop_badge_color() — shared colour palette
    tray.py              # TrayIcon — pystray system tray
    config.py            # HotkeyChoice enum, load_hotkey()/save_hotkey() — %APPDATA%\windows-navigator\config.toml
    settings.py          # settings Toplevel modal — hotkey radio-button selection

tests/
    test_filter.py           # filter_windows()
    test_keyboard.py         # OverlayController state machine + tab search
    test_provider.py         # RealWindowProvider icon extraction fallback
    test_virtual_desktop.py  # desktop number assignment + fallbacks
    test_tray.py             # _make_tray_icon — pixel-level color checks
    test_theme.py            # desktop_badge_color()
    test_overlay.py          # _desktop_badge_color() overlay helper (requires tkinter stub)
```

### Event flow

1. `_start_hotkey_listener` reads `load_hotkey()` and dispatches to one of two listener functions. Polling choices (double-tap Ctrl, hold-Ctrl double-tap Shift) use `_polling_double_tap_listener` with `tap_vk_l`/`tap_vk_r` params and optional `guard_vk_l`/`guard_vk_r` for the guard-key variant; on detection they inject `VK_F24` via `SendInput`, drain `WM_HOTKEY` (foreground-lock grant), then enqueue to `show_queue`. Registered choices (Win+Alt+Space, Ctrl+Shift+Space) use `_run_registered_hotkey` with the appropriate `modifiers`/`vk` params and wait for `WM_HOTKEY` directly — the foreground-lock grant arrives with the message.
2. `_drain_show_queue()` runs on the Tk main thread (≤ 50 ms via `poll_queue`), calls `provider.get_windows()`
3. Current desktop derived from windows, passed as `initial_desktop=N` to `overlay.show()`
4. Overlay renders; user interaction updates `OverlayController` state (pure Python)
5. On Enter: `activate_window(hwnd)` → `overlay.hide()`; on Ctrl+Enter: move + activate + hide
6. `app.poll_desktop()` (every 500 ms) reads registry, updates tray if desktop changed

### Key design decisions

- **Single hidden Tk root** — one withdrawn `Tk()` root with a `Toplevel` overlay prevents event-loop conflicts with pystray.
- **`GetAsyncKeyState` polling for double-tap Ctrl detection** — polls every 30 ms, detects two rising edges within 300 ms. `WH_KEYBOARD_LL` was rejected: its hook proc must acquire the GIL, which the Tk main thread can hold during event callbacks, causing a system-wide keyboard deadlock.
- **`RegisterHotKey`/`SendInput` trick for foreground-lock acquisition** — `SetForegroundWindow` silently fails without the foreground lock. On double-tap, the listener injects a synthetic `VK_F24` keypress via `SendInput`; because `VK_F24` is registered with `RegisterHotKey(MOD_NOREPEAT)`, Windows delivers `WM_HOTKEY` to the listener thread, granting the process the foreground-lock exemption. The listener drains that message via `PeekMessageW` before putting to `show_queue`, so `_grab_focus`'s subsequent `SetForegroundWindow` is covered. Falls back to direct `put()` if `RegisterHotKey` fails (e.g. key already claimed). `PeekMessageW` must be called once before `RegisterHotKey` to create a message queue for the thread — Win32 threads have no queue until they call a message function.
- **`_run_registered_hotkey` handles both `RegisterHotKey`-based choices — no `SendInput` trick needed** — Win+Alt+Space and Ctrl+Shift+Space are registered as the actual hotkeys (not synthetic proxies), so Windows delivers `WM_HOTKEY` in response to real user input, which carries the foreground-lock exemption natively. Uses `PeekMessageW` in a 10 ms sleep loop (not blocking `GetMessageW`) so the `threading.Event` stop flag is checked between polls and `UnregisterHotKey` runs in the `finally` block.
- **`_polling_double_tap_listener` handles both polling choices via `tap_vk` and optional `guard_vk` params** — double-tap Ctrl passes `tap_vk_l=VK_LCONTROL, tap_vk_r=VK_RCONTROL` with no guard; hold-Ctrl double-tap-Shift passes `tap_vk_l=VK_LSHIFT, tap_vk_r=VK_RSHIFT, guard_vk_l=VK_LCONTROL, guard_vk_r=VK_RCONTROL`. The HOTKEY_IDs (100 and 400) must differ to avoid `RegisterHotKey` collisions if both ever coexist. `tap_was_down` is updated every poll cycle regardless of guard state, so the rising-edge latch is correct even when the guard key changes mid-poll. The 300 ms window does not require the guard to be held continuously — a release-and-repress between taps will still trigger if within the window.
- **Hotkey choice persisted in TOML, switched live** — `config.py` reads/writes `%APPDATA%\windows-navigator\config.toml` using stdlib `tomllib` (read) and a plain `str.write_text` (write; `tomllib` is read-only). When settings are saved, `_on_hotkey_saved` sets the old listener's `threading.Event` stop flag, allocates a fresh event, and starts a new listener — the old thread exits within one poll interval (≤30 ms / ≤10 ms). Always create a new event rather than clearing the old one to avoid a race between `set()` and `clear()`.
- **pystray callbacks run on a non-Tk thread** — `TrayIcon._do_settings` must use `root.after(0, ...)` to marshal `open_settings_window` to the Tk main thread. Direct Tk calls from pystray's background thread corrupt Tk state silently.
- **`_drain_show_queue` collapses multiple queued events into one call** — all items are drained from `show_queue` before `overlay.show()` fires once per poll cycle. Without this, two hotkey events within the same 50 ms window would call `toggle_all_expansions()` twice, cancelling each other out (no visible change).
- **Pure Python controller** — all filter/selection logic in `controller.py` with no Tk import, fully testable on Linux.
- **Four controller properties are `cached_property`** — `text_filtered_windows`, `_tab_query_matches`, `flat_list`, and `app_icons`. Without caching, `filter_windows` was called up to 3× per `flat_list` access and `flat_list` recomputed on every arrow-key press; `app_icons` was re-deduplicated on every render cycle. Three invalidation helpers handle the different dependency scopes:
  - `_invalidate_text_filter_cache()` — pops all four; called by `set_query`, `set_desktop_nums`, and `reset` (mutations that change `query`, `_desktop_nums`, or `all_windows`). `app_icons` depends only on `text_filtered_windows` so it belongs in this group.
  - `_invalidate_view_caches()` — pops `_tab_query_matches` and `flat_list`; called by `set_tabs`, `toggle_expansion`, and `toggle_all_expansions` (mutations that change `_tabs` or `_expanded`).
  - `_invalidate_flat_cache()` — pops just `flat_list`; called by `cycle_app_filter`, `clear_app_filter`, and `toggle_bell_filter` (`_app_filter`/`_bell_filter` are not inputs to `_tab_query_matches` or `app_icons`, so those caches stay valid).
- **`_set_query_state` is the only correct way to change badge state** — any handler modifying `_desktop_prefix_nums` must call `_set_query_state(nums, text)`, not `_update_prefix_badges` + `_on_text_changed` separately. Only `_set_query_state` reaches `controller.set_desktop_nums`, keeping badges and controller in sync.
- **Activation before hide** — `_activate_selected` calls the activate callback BEFORE `hide()`. `_closing = True` is set first so `_on_focus_out` doesn't schedule a spurious `hide()` during the focus handoff.
- **Focus-out / focus-in symmetry** — `_on_focus_out` cancels any existing `_pending_hide` before scheduling a new one. Without this, the SW_SHOWNORMAL flash from `deiconify()` fires a FocusOut at T≈0 and a user click fires another; the orphaned callback fires later and closes a healthy overlay.
- **Deferred Win32 imports** — all `win32*` and `pystray` imports happen inside functions, never at module level, so the test suite runs on Linux. Exception: `config.py` is pure stdlib (`tomllib`, `pathlib`, `enum`) so `app.py` imports it at module level.
- **COM initialization** — `CoInitializeEx(COINIT_APARTMENTTHREADED)` must be called before `CoCreateInstance`. Neither pywin32 nor Tkinter do this automatically.
- **Vtable access** — COM vtable is two levels of indirection: `object → vtable_ptr → fn_ptrs`. Cast the object pointer to `POINTER(c_void_p)`, read `[0]` to get the vtable pointer, cast that to `POINTER(c_void_p)`, then index by method number.
- **Win32 `BOOL` vs `c_bool`** — Win32 `BOOL` is `c_int` (4 bytes), not `c_bool` (1 byte). Using `c_bool` for an output `BOOL*` parameter corrupts memory.
- **Icon extraction fallback chain** — `SHGetImageList(SHIL_JUMBO)` is tried first for every window: it returns 256×256 icons from the shell cache for all apps, including Electron and UWP apps (Teams, Edge, Slack) that return a low-quality 32×32 handle from `WM_GETICON`. The icon is rendered via `DrawIconEx` then downscaled to 32×32 with Lanczos. Fallbacks in order: `WM_GETICON(ICON_BIG)` → `WM_GETICON(ICON_SMALL)` → `GetClassLong(GCL_HICON)` → `SHGetFileInfoW` on the exe path. Icons from `SHGetFileInfoW` are caller-owned and need `DestroyIcon`.
- **Icon cache on `RealWindowProvider`** — `_icon_cache: OrderedDict[str, Image.Image]` keyed by `exe_path.lower()` avoids repeating the expensive `SHGetImageList` + `DrawIconEx` + Lanczos resize on every hotkey press. Capped at 256 entries (module-level `_ICON_CACHE_MAX`) with LRU eviction: `move_to_end` on cache hit, `popitem(last=False)` when the cap is exceeded on insert. Only caches when `exe_path` is non-empty; empty-path windows fall through to per-hwnd queries that can't be shared. Icons don't change while an app is running so no explicit invalidation is needed.
- **`QueryFullProcessImageNameW` for exe path** — do NOT use `win32api.GetModuleFileNameEx` (doesn't exist in pywin32) or `GetModuleFileNameEx` (requires `PROCESS_VM_READ`). Either silently returns `""`, collapsing every window to `process_name=""`.
- **`pyvda` required for move** — `IVirtualDesktopManager::MoveWindowToDesktop` silently does nothing for cross-process windows on Windows 11 22H2+. `pyvda` uses `IVirtualDesktopManagerInternal`.
- **Flash monitor WPARAM overflow** — `ctypes.wintypes.WPARAM` is `c_long` (32-bit signed) even on 64-bit. `HSHELL_FLASH = 0x8006` overflows. Use `c_size_t`/`c_ssize_t` for w/l parameters in the `WNDPROC`.
- **Ghost window filtering** — windows can retain a GUID from a deleted desktop. `assign_desktop_numbers` marks these `desktop_number = -1`; `get_windows` skips them. The `-1` sentinel never escapes into `WindowInfo`.
- **Ctrl+0 toggles the current desktop badge** — `_on_ctrl_zero` reads `self._initial_desktop` (set at `show()` time) and toggles that number in `_desktop_prefix_nums`. If `_initial_desktop == 0` (no desktop detected), the key is a no-op. Ctrl+1–9 toggle fixed badge numbers; Ctrl+0 is the "shorthand for today's desktop" variant.
- **Ctrl+Shift+N desktop jump** — uses Win32 `GetKeyState` instead of Tkinter keysym: Shift changes `"1"` to `"exclam"` etc., making keysym bindings unusable across keyboard layouts.
- **Tray `_current_desktop[0]` sync** — `poll_queue` and `poll_move_queue` both write `_current_desktop[0]` after updating the tray. Without this `poll_desktop` lags and skips refreshes when the user returns to a previously-seen desktop.
- **UIA tab activation uses index re-fetch** — `TabInfo` stores only the 0-based index, not a COM element pointer. `select_tab` re-fetches the element at activation time. This avoids STA cross-thread COM marshaling (UIA element pointers from a background STA thread cannot be used on the main Tk thread).
- **Per-window timeout and cancellation for `_fetch_tabs_bg`** — each `fetch_tabs(hwnd)` call runs in its own daemon sub-thread joined with `_TAB_FETCH_TIMEOUT = 3.0` seconds. A hung UIA call on one window (broken COM tree, unresponsive app) no longer blocks all subsequent windows. The abandoned sub-thread continues running but dies with the process. `ThreadPoolExecutor(max_workers=1)` was rejected: a timed-out future leaves the single worker thread busy, so the next task never starts. Each sub-thread initializes its own COM apartment (`CoInitializeEx(None, 0)`); the outer background thread no longer initializes COM. The inner `_do` function uses default argument binding (`hwnd: int = w.hwnd, out: list = result`) to capture the per-iteration values clearly, even though `join()` serializes the loop so the variables are stable.
- **`_fetch_cancel: threading.Event` stops the fetch loop when the overlay is dismissed** — `show()` creates a fresh `threading.Event` on each new open (after setting any prior event); `hide()` sets and clears it immediately. The background thread checks `cancel.is_set()` at the top of each window iteration and after each sub-thread join. This prevents the thread from running to completion after the overlay is already gone.
- **Deferred tab expansion** — `toggle_all_expansions()` called before any tabs have been fetched sets `_want_all_expanded = True`. `set_tabs()` checks this flag and adds arriving windows to `_expanded`, so the shortcut feels immediate even though UIA fetch takes hundreds of milliseconds. The flag is only toggled when at least one filtered window still has pending tab data; filtering to already-loaded single-tab windows must not corrupt the flag (no visible effect → no state change). Collapse always calls `_expanded.clear()` (not `_expanded -= filtered_set`) so expansion state does not leak through the filter into a later unfiltered view.
- **OUTLOOK.EXE is excluded from UIA tab fetching** — The skip is a process-name guard (`w.process_name.upper() == "OUTLOOK.EXE"`) at the top of the per-window loop in `_fetch_tabs_bg`.
- **`toggle_all_expansions` must clamp `selection_index` after modifying `_expanded`** — Collapsing all expanded tab rows shrinks `flat_list` but does not automatically adjust `selection_index`. If the cursor was on a tab row, `selection_index` becomes out-of-bounds. Every subsequent `_refresh_canvas` call then crashes with `IndexError: list index out of range` at `ys[sel]`. Tkinter catches and prints the exception but keeps running, so the same corrupted state produces cascading tracebacks from `_on_text_changed`, `_on_arrow_up`, etc. Fix: after the collapse/expand branch, clamp `selection_index = min(sel, len(flat_list) - 1)`. The `_refresh_canvas` guard must also use `0 <= sel < len(flat)`, not `sel >= 0 and flat` (the latter allows `sel >= len(flat)` when the list is non-empty).
- **`PhotoImage` objects are cached between `_refresh_canvas` calls** — `self._photo_image_cache: dict[int, object]` keyed by `id(PIL image)` avoids recreating `ImageTk.PhotoImage` on every keystroke. The PIL icon images are stable between hotkey presses (they live in `RealWindowProvider._icon_cache`), so the Tk wrappers can safely be reused. The cache is cleared in `show()` when a fresh window list arrives and in `hide()` to release the GDI-backed objects. Both `_refresh_canvas` and `_refresh_icon_strip` share the same cache.
- **`_load_font` result is cached at module level** — `_font_cache: dict[int, object | None]` in `tray.py` prevents the six-name try/except font probe from re-running on every tray update (desktop switch). The result (font object or `None`) is stored on first call for each size.
- **Enum callback collects `(hwnd, title)` pairs** — `_enum_callback` in `RealWindowProvider.get_windows` stores the title alongside the hwnd, eliminating the second `GetWindowText` call per window in the main loop.
- **Notification detection** — two signals combined into `flashing: set[int]`: `HSHELL_FLASH` (0x8006, fired by `FlashWindowEx`) and `HSHELL_REDRAW` (6) on a background window with an unchanged title (fingerprint of `ITaskbarList3::SetOverlayIcon`). Title changes matching `^\(\d+\)` on HSHELL_REDRAW are also caught.

## Conventions

- Line length: **100 characters** (ruff enforces)
- Sorted imports (ruff rule I)
- Type hints on all functions
- Win32 calls wrapped in `try/except` with graceful fallback
- Tests run identically on Linux and Windows — mock all Win32/COM calls
- **Keep README.md in sync** — update hotkey/filter tables when user-facing behaviour changes

## Testing patterns

**`overlay.py` imports `tkinter` at module level.** Stub it before importing:
```python
import sys
from unittest.mock import MagicMock
sys.modules.setdefault("tkinter", MagicMock())
from windows_navigator.overlay import _desktop_badge_color
```

**`winreg` is Windows-only.** Inject a mock via `patch.dict`:
```python
mock_winreg = MagicMock()
mock_winreg.QueryValueEx.side_effect = [(current_bytes, None), (all_bytes, None)]
with patch.dict("sys.modules", {"winreg": mock_winreg}):
    result = get_current_desktop_number()
```

**`win32*` modules are Windows-only.** Functions that defer `import win32con` / `import win32gui` look up `sys.modules` on each call, so patching before the call works:
```python
win32con, win32gui = MagicMock(), MagicMock()
win32gui.IsWindow.return_value = True
with patch.dict(sys.modules, {"win32con": win32con, "win32gui": win32gui}):
    result = activate_window(42)
```

**`ctypes.windll` is Windows-only.** On Linux the attribute does not exist; use `create=True` to add it for the test and have `patch.object` restore the missing state afterward:
```python
import ctypes
mock_windll = MagicMock()
mock_windll.user32 = MagicMock()
with patch.object(ctypes, "windll", mock_windll, create=True):
    _force_foreground(99)
```

## Test file map

| File | What it covers |
|------|----------------|
| `test_filter.py` | `filter_windows` — text match, multi-token, `desktop_nums` OR semantics |
| `test_keyboard.py` | `OverlayController` — navigation, query, desktop badges, app filter, tab search, toggle expansions, deferred `_want_all_expanded`, collapse-clears-all, flag non-corruption for single-tab filter, `text_filtered_windows` cache (single call per `flat_list`, invalidation by mutation, reuse across reads), `flat_list` and `_tab_query_matches` cache (identity across reads, invalidation by all 8 mutation methods) |
| `test_provider.py` | `IconExtractor.extract` fallback chain; `RealWindowProvider` icon cache (same-exe hit, cross-exe miss, case-insensitive key, cache contents after enumeration, persistence across `get_windows` calls) |
| `test_virtual_desktop.py` | `assign_desktop_numbers` (registry order, ghost GUID → `-1`), `get_current_desktop_number` |
| `test_models.py` | `WindowInfo` and `TabInfo` dataclass construction and defaults |
| `test_tray.py` | `_make_tray_icon` pixel-level color checks |
| `test_theme.py` | `desktop_badge_color` format and cycling |
| `test_overlay.py` | `_desktop_badge_color` overlay helper (requires tkinter stub) |
| `test_config.py` | `_config_path` (APPDATA env var / home fallback), `load_hotkey` (missing file, invalid TOML, all valid values), `save_hotkey` (content, directory creation, roundtrip), `HotkeyChoice` enum |
| `test_activation.py` | `activate_window` (missing/minimized/normal/exception), `_force_foreground`, `_get_cursor_monitor_workarea` (happy path with mocked `windll`, fallback on exception) |
| `test_tabs.py` | `_collect_tab_items` (tab-item/document-node/recursion/max-depth/document-barrier), `_get_children`, `fetch_tabs`/`select_tab` Linux fallbacks |
