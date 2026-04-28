# Windows Navigator

A keyboard-driven window switcher for Windows with virtual desktop awareness.

## Usage

Double-tap **Ctrl** to open the overlay. The trigger hotkey is configurable via the tray icon → Settings:

| Option | Description |
|--------|-------------|
| Double-tap Ctrl | Press Ctrl twice quickly |
| Win + Alt + Space | Chord hotkey |
| Ctrl + Shift + Space | Chord hotkey |
| Hold Ctrl, double-tap Shift | Hold Ctrl, press Shift twice quickly |

Double-tap **Ctrl** again while the overlay is open to expand / collapse all browser tabs.

### Filtering

| Input | Effect |
|-------|--------|
| Type text | Filter by window title or app name (all tokens must match) |
| `Ctrl+1`–`9` | Toggle desktop-number filter badge on/off |
| `Ctrl++` / `Ctrl+-` | Increment/decrement the active desktop badge |
| `Tab` / `Shift+Tab` | Cycle app filter (icon strip) |
| `Ctrl+`` ` | Toggle bell filter — show only windows with notifications |

### Navigation

| Key | Effect |
|-----|--------|
| `↑` / `↓` | Move selection (wraps around) |
| `PgUp` / `PgDn` | Move selection by page |
| `Ctrl+Home` / `Ctrl+End` | Jump to first / last |
| `Ctrl+Tab` | Expand / collapse browser tabs (via UIA) |

### Actions

| Key | Effect |
|-----|--------|
| `Enter` | Activate selected window |
| `Ctrl+Enter` | Move window to current desktop, then activate |
| `Ctrl+Shift+N` | Jump to desktop N (activates first window there, or switches if empty) |
| `Esc` | Clear active filter → reset to active-desktop view → dismiss |

### Global hotkeys (work without the overlay open)

| Key | Effect |
|-----|--------|
| `Ctrl+Win+Shift+←` / `→` | Move foreground window to adjacent desktop |

Runs as a system tray application. The tray icon shows the current virtual desktop number.

## Setup

### Go binary (recommended)

Build a single self-contained `.exe` — no Python or dependencies required:

```bash
# cross-compile from Linux/macOS:
cd go
GOOS=windows GOARCH=amd64 go build -ldflags="-H windowsgui" -o windows-navigator.exe .
```

Copy `windows-navigator.exe` to Windows and run it directly.

### Python (development / legacy)

**Windows** (required for the full tool):
```powershell
py -m pip install -e ".[windows,dev]"
python -m windows_navigator
```

**Linux / macOS** (dev tools only — tests and linting, no Win32 runtime):
```bash
python3 -m venv .venv && source .venv/bin/activate  # bash/zsh
# source .venv/bin/activate.fish                     # fish
pip install -e ".[dev]"
```

> **Note:** On Windows, `pip` may not be on PATH. Use `py -m pip` or `python -m pip`.

## Development

```bash
# Python
make test      # pytest
make lint      # ruff check .
make format    # ruff format .

# Go
cd go && go test ./internal/navigator/
```

Run a single Python test file: `pytest tests/test_filter.py`
