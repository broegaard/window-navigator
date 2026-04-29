# Copilot Instructions

Keyboard-driven window switcher for Windows. Double-tap **Ctrl** opens an overlay listing all open windows; type to filter, arrow keys to navigate, Enter to focus.

Python 3.11+, tkinter UI, pywin32 for Win32, pystray for the system tray. Tests and linting run on Linux (no Win32 deps needed).

## Commands

```bash
# Install (Linux/macOS — dev tools only, no Win32 deps)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Install (Windows — full runtime)
py -m pip install -e ".[windows,dev]"

make test      # pytest
make lint      # ruff check .
make format    # ruff format .

# Single test file
pytest tests/test_filter.py
```

`make test` requires `pytest` on `PATH`; if venv is not activated: `.venv/bin/python -m pytest tests/ -q`

## Architecture

| Module | Role |
|--------|------|
| `app.py` | Wires everything: Tk root, overlay, hotkey listener, flash monitor, tray |
| `controller.py` | `OverlayController` — pure Python state machine, no Tk, testable on Linux |
| `filter.py` | `filter_windows()` — pure Python, no Win32 |
| `provider.py` | `RealWindowProvider` — Win32 window enumeration + icon cache |
| `overlay.py` | `NavigatorOverlay` — tkinter Canvas UI |
| `virtual_desktop.py` | Desktop number assignment, window move — raw ctypes COM |
| `activation.py` | `activate_window()` — Win32 restore + `SetForegroundWindow` |
| `tabs.py` | UIA tab discovery + activation — Windows-only, deferred imports |
| `tray.py` | `TrayIcon` — pystray system tray |
| `config.py` | `HotkeyChoice` enum, `load_hotkey()`/`save_hotkey()` — `%APPDATA%\windows-navigator\config.toml` |

**Hotkey flow**: double-tap polling injects a synthetic `VK_F24` via `SendInput` to acquire the foreground-lock exemption before calling `SetForegroundWindow`. `RegisterHotKey`-based choices (Win+Alt+Space etc.) receive the lock with `WM_HOTKEY` directly.

**`cached_property` on `OverlayController`** — `text_filtered_windows`, `_tab_query_matches`, `flat_list`, and `app_icons` are cached. Three scoped invalidation helpers manage them (`_invalidate_text_filter_cache`, `_invalidate_view_caches`, `_invalidate_flat_cache`); always call these rather than mutating properties directly.

## Key conventions

- Line length: **100 characters** (ruff enforces, rules E, F, I)
- Type hints on all functions
- Win32 calls wrapped in `try/except` with graceful fallback
- Keep `README.md` hotkey/filter tables in sync when user-facing behaviour changes

**Deferred Win32 imports** — all `win32*`, `pystray`, and `comtypes` imports happen inside functions, never at module level. Exception: `config.py` is pure stdlib and is imported at module level.

## Testing patterns

**Mock Win32 modules** via `patch.dict("sys.modules", ...)` since they are imported inside functions:
```python
with patch.dict(sys.modules, {"win32con": MagicMock(), "win32gui": MagicMock()}):
    result = activate_window(42)
```

**`winreg`** — inject mock via `patch.dict`:
```python
mock_winreg = MagicMock()
mock_winreg.QueryValueEx.side_effect = [(current_bytes, None), (all_bytes, None)]
with patch.dict("sys.modules", {"winreg": mock_winreg}):
    result = get_current_desktop_number()
```

**`ctypes.windll`** — does not exist on Linux; use `create=True`:
```python
with patch.object(ctypes, "windll", MagicMock(), create=True):
    _force_foreground(99)
```

**`overlay.py` imports tkinter at module level** — stub before importing:
```python
sys.modules.setdefault("tkinter", MagicMock())
from windows_navigator.overlay import _desktop_badge_color
```

## Win32 gotchas

- Use `QueryFullProcessImageNameW` for exe path — not `GetModuleFileNameEx`.
- Win32 `BOOL` is `c_int` (4 bytes), not `c_bool` — using `c_bool` for a `BOOL*` parameter corrupts memory.
- `ctypes.wintypes.WPARAM` is `c_long` (32-bit signed) even on 64-bit — `HSHELL_FLASH = 0x8006` overflows; use `c_size_t`/`c_ssize_t` for w/l parameters in `WNDPROC`.
- `CoInitializeEx(COINIT_APARTMENTTHREADED)` must be called before `CoCreateInstance`; neither pywin32 nor Tkinter do this automatically.
- `pyvda` required for cross-process window moves — `IVirtualDesktopManager::MoveWindowToDesktop` silently does nothing on Windows 11 22H2+.
