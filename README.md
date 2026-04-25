# Windows Navigator

A keyboard-driven window switcher for Windows with virtual desktop awareness. Press **Ctrl+Shift+Space** to open an overlay listing all open windows — type to filter, arrow keys to navigate, Enter to focus.

Runs as a lightweight system-tray app. No Electron, no background service — just a Python script that registers a global hotkey and stays out of your way.

## Requirements

- Windows 10 or Windows 11
- Python 3.11+
- Virtual desktop features (move window to desktop, desktop badges) work best on Windows 11 22H2 and later

## Installation

```powershell
py -m pip install -e ".[windows]"
```

Then run:

```powershell
py -m windows_navigator
```

The app starts in the system tray. Press **Ctrl+Shift+Space** to open the overlay.

> **Note:** If `py` is not found, check **"Add Python to PATH"** in the Python installer.

## Usage

Press **Ctrl+Shift+Space** to open the overlay.

### Filtering

| Input | Effect |
|-------|--------|
| Type text | Filter by window title or app name (all tokens must match) |
| `Ctrl+1`–`9` | Toggle desktop-number filter badge on/off |
| `Ctrl++` / `Ctrl+-` | Increment/decrement the active desktop badge |
| `Tab` / `Shift+Tab` | Cycle app filter (icon strip) |
| `` Ctrl+` `` | Toggle bell filter — show only windows with notifications |

### Navigation

| Key | Effect |
|-----|--------|
| `↑` / `↓` | Move selection |
| `PgUp` / `PgDn` | Move selection by page |
| `Ctrl+Home` / `Ctrl+End` | Jump to first / last |
| `Ctrl+Tab` | Expand / collapse browser tabs (via UIA) |

### Actions

| Key | Effect |
|-----|--------|
| `Enter` | Activate selected window |
| `Ctrl+Enter` | Move window to current desktop, then activate |
| `Ctrl+Shift+N` | Jump to desktop N (activates first window there, or switches if empty) |
| `Esc` | Clear active filter, or dismiss |

### Global hotkeys (work without the overlay open)

| Key | Effect |
|-----|--------|
| `Ctrl+Win+Shift+←` / `→` | Move foreground window to adjacent virtual desktop |

The tray icon shows the current virtual desktop number and updates as you switch desktops.

## Auto-start on login

To launch Windows Navigator automatically at login, place `start.pyw` (or a shortcut to it) in your Startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

`start.pyw` runs without a console window. `start.bat` is an alternative that restarts the process if it exits unexpectedly.

## Development

**Linux / macOS** (tests and linting only — no Win32 runtime):

```bash
python3 -m venv .venv && source .venv/bin/activate  # bash/zsh
# source .venv/bin/activate.fish                     # fish
pip install -e ".[dev]"
```

```bash
make test      # pytest
make lint      # ruff check .
make format    # ruff format .
```

Run a single test file: `pytest tests/test_filter.py`

## License

Copyright (c) 2026 Kasper Broegaard Simonsen. All rights reserved. See [LICENSE](LICENSE).
