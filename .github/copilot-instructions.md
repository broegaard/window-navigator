# AGENTS.md

Keyboard-driven window switcher for Windows. Double-tap **Ctrl** to open an overlay listing all open windows; type to filter, arrow keys to navigate, Enter to focus.

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
- **Pure Python controller** — all filter/selection logic in `controller.py` with no Tk import, fully testable on Linux.
- **Four controller properties are `cached_property`** — `text_filtered_windows`, `_tab_query_matches`, `flat_list`, and `app_icons`. Three invalidation helpers handle the different dependency scopes: `_invalidate_text_filter_cache()`, `_invalidate_view_caches()`, `_invalidate_flat_cache()`.
- **Deferred Win32 imports** — all `win32*` and `pystray` imports happen inside functions, never at module level, so the test suite runs on Linux. Exception: `config.py` is pure stdlib so `app.py` imports it at module level.
- **COM initialization** — `CoInitializeEx(COINIT_APARTMENTTHREADED)` must be called before `CoCreateInstance`. Neither pywin32 nor Tkinter do this automatically.
- **pystray callbacks run on a non-Tk thread** — `TrayIcon._do_settings` must use `root.after(0, ...)` to marshal `open_settings_window` to the Tk main thread.

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

**`win32*` modules are Windows-only.** Functions defer `import win32con` etc., so patching before the call works:
```python
win32con, win32gui = MagicMock(), MagicMock()
win32gui.IsWindow.return_value = True
with patch.dict(sys.modules, {"win32con": win32con, "win32gui": win32gui}):
    result = activate_window(42)
```

**`ctypes.windll` is Windows-only.** Use `create=True`:
```python
import ctypes
with patch.object(ctypes, "windll", MagicMock(), create=True):
    _force_foreground(99)
```

## Win32 gotchas

- Use `QueryFullProcessImageNameW` for exe path — not `GetModuleFileNameEx`.
- Win32 `BOOL` is `c_int` (4 bytes), not `c_bool` — using `c_bool` for a `BOOL*` parameter corrupts memory.
- `ctypes.wintypes.WPARAM` is `c_long` (32-bit signed) even on 64-bit — `HSHELL_FLASH = 0x8006` overflows; use `c_size_t`/`c_ssize_t` for w/l parameters in `WNDPROC`.
- `CoInitializeEx(COINIT_APARTMENTTHREADED)` must be called before `CoCreateInstance`; neither pywin32 nor Tkinter do this automatically.
- `pyvda` required for move — `IVirtualDesktopManager::MoveWindowToDesktop` silently does nothing for cross-process windows on Windows 11 22H2+.
