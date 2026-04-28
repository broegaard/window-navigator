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

## Tech stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| UI | `tkinter` (stdlib) |
| Win32 API | `pywin32` (`win32gui`, `win32process`, `win32api`, `win32con`) |
| System tray | `pystray` + `Pillow` |
| Global hotkey | `GetAsyncKeyState` polling + `RegisterHotKey`/`SendInput` trick via ctypes — double-tap Ctrl (no extra dep) |
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

1. `_start_hotkey_listener` thread polls `GetAsyncKeyState` every 30 ms; on double-tap Ctrl it injects a synthetic `VK_F24` via `SendInput`, drains `WM_HOTKEY` from its own message queue (granting the foreground-lock exemption), then enqueues the foreground HWND to `show_queue`
2. `_drain_show_queue()` runs on the Tk main thread (≤ 50 ms via `poll_queue`), calls `provider.get_windows()`
3. Current desktop derived from windows, passed as `initial_desktop=N` to `overlay.show()`
4. Overlay renders; user interaction updates `OverlayController` state (pure Python)
5. On Enter: `activate_window(hwnd)` → `overlay.hide()`; on Ctrl+Enter: move + activate + hide
6. `app.poll_desktop()` (every 500 ms) reads registry, updates tray if desktop changed

### Key design decisions

- **Single hidden Tk root** — one withdrawn `Tk()` root with a `Toplevel` overlay prevents event-loop conflicts with pystray.
- **`GetAsyncKeyState` polling for double-tap Ctrl detection** — polls every 30 ms, detects two rising edges within 300 ms. `WH_KEYBOARD_LL` was rejected: its hook proc must acquire the GIL, which the Tk main thread can hold during event callbacks, causing a system-wide keyboard deadlock.
- **`RegisterHotKey`/`SendInput` trick for foreground-lock acquisition** — `SetForegroundWindow` silently fails without the foreground lock. On double-tap, the listener injects a synthetic `VK_F24` keypress via `SendInput`; because `VK_F24` is registered with `RegisterHotKey(MOD_NOREPEAT)`, Windows delivers `WM_HOTKEY` to the listener thread, granting the process the foreground-lock exemption. The listener drains that message via `PeekMessageW` before putting to `show_queue`, so `_grab_focus`'s subsequent `SetForegroundWindow` is covered. Falls back to direct `put()` if `RegisterHotKey` fails (e.g. key already claimed). `PeekMessageW` must be called once before `RegisterHotKey` to create a message queue for the thread — Win32 threads have no queue until they call a message function.
- **`_drain_show_queue` is idempotent** — the 50 ms `poll_queue` timer is the only consumer path; double-firing is safe.
- **Pure Python controller** — all filter/selection logic in `controller.py` with no Tk import, fully testable on Linux.
- **`_set_query_state` is the only correct way to change badge state** — any handler modifying `_desktop_prefix_nums` must call `_set_query_state(nums, text)`, not `_update_prefix_badges` + `_on_text_changed` separately. Only `_set_query_state` reaches `controller.set_desktop_nums`, keeping badges and controller in sync.
- **Activation before hide** — `_activate_selected` calls the activate callback BEFORE `hide()`. `_closing = True` is set first so `_on_focus_out` doesn't schedule a spurious `hide()` during the focus handoff.
- **Focus-out / focus-in symmetry** — `_on_focus_out` cancels any existing `_pending_hide` before scheduling a new one. Without this, the SW_SHOWNORMAL flash from `deiconify()` fires a FocusOut at T≈0 and a user click fires another; the orphaned callback fires later and closes a healthy overlay.
- **Deferred Win32 imports** — all `win32*` and `pystray` imports happen inside functions, never at module level, so the test suite runs on Linux.
- **COM initialization** — `CoInitializeEx(COINIT_APARTMENTTHREADED)` must be called before `CoCreateInstance`. Neither pywin32 nor Tkinter do this automatically.
- **Vtable access** — COM vtable is two levels of indirection: `object → vtable_ptr → fn_ptrs`. Cast the object pointer to `POINTER(c_void_p)`, read `[0]` to get the vtable pointer, cast that to `POINTER(c_void_p)`, then index by method number.
- **Win32 `BOOL` vs `c_bool`** — Win32 `BOOL` is `c_int` (4 bytes), not `c_bool` (1 byte). Using `c_bool` for an output `BOOL*` parameter corrupts memory.
- **Icon extraction fallback chain** — `SHGetImageList(SHIL_JUMBO)` is tried first for every window: it returns 256×256 icons from the shell cache for all apps, including Electron and UWP apps (Teams, Edge, Slack) that return a low-quality 32×32 handle from `WM_GETICON`. The icon is rendered via `DrawIconEx` then downscaled to 32×32 with Lanczos. Fallbacks in order: `WM_GETICON(ICON_BIG)` → `WM_GETICON(ICON_SMALL)` → `GetClassLong(GCL_HICON)` → `SHGetFileInfoW` on the exe path. Icons from `SHGetFileInfoW` are caller-owned and need `DestroyIcon`.
- **`QueryFullProcessImageNameW` for exe path** — do NOT use `win32api.GetModuleFileNameEx` (doesn't exist in pywin32) or `GetModuleFileNameEx` (requires `PROCESS_VM_READ`). Either silently returns `""`, collapsing every window to `process_name=""`.
- **`pyvda` required for move** — `IVirtualDesktopManager::MoveWindowToDesktop` silently does nothing for cross-process windows on Windows 11 22H2+. `pyvda` uses `IVirtualDesktopManagerInternal`.
- **Flash monitor WPARAM overflow** — `ctypes.wintypes.WPARAM` is `c_long` (32-bit signed) even on 64-bit. `HSHELL_FLASH = 0x8006` overflows. Use `c_size_t`/`c_ssize_t` for w/l parameters in the `WNDPROC`.
- **Ghost window filtering** — windows can retain a GUID from a deleted desktop. `assign_desktop_numbers` marks these `desktop_number = -1`; `get_windows` skips them. The `-1` sentinel never escapes into `WindowInfo`.
- **Ctrl+Shift+N desktop jump** — uses Win32 `GetKeyState` instead of Tkinter keysym: Shift changes `"1"` to `"exclam"` etc., making keysym bindings unusable across keyboard layouts.
- **Tray `_current_desktop[0]` sync** — `poll_queue` and `poll_move_queue` both write `_current_desktop[0]` after updating the tray. Without this `poll_desktop` lags and skips refreshes when the user returns to a previously-seen desktop.
- **UIA tab activation uses index re-fetch** — `TabInfo` stores only the 0-based index, not a COM element pointer. `select_tab` re-fetches the element at activation time. This avoids STA cross-thread COM marshaling (UIA element pointers from a background STA thread cannot be used on the main Tk thread).
- **Deferred tab expansion** — `toggle_all_expansions()` called before any tabs have been fetched sets `_want_all_expanded = True`. `set_tabs()` checks this flag and adds arriving windows to `_expanded`, so the shortcut feels immediate even though UIA fetch takes hundreds of milliseconds.
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

## Test file map

| File | What it covers |
|------|----------------|
| `test_filter.py` | `filter_windows` — text match, multi-token, `desktop_nums` OR semantics |
| `test_keyboard.py` | `OverlayController` — navigation, query, desktop badges, app filter, tab search, toggle expansions, deferred `_want_all_expanded` |
| `test_provider.py` | `IconExtractor.extract` fallback chain |
| `test_virtual_desktop.py` | `assign_desktop_numbers` (registry order, ghost GUID → `-1`), `get_current_desktop_number` |
| `test_tray.py` | `_make_tray_icon` pixel-level color checks |
| `test_theme.py` | `desktop_badge_color` format and cycling |
| `test_overlay.py` | `_desktop_badge_color` overlay helper (requires tkinter stub) |
