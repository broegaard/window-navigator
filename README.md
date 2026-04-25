# Windows Navigator

A keyboard-driven window switcher for Windows with virtual desktop awareness.

## Usage

Press **Ctrl+Shift+Space** to open the overlay.

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
| `Ctrl+Win+Shift+←` / `→` | Move foreground window to adjacent desktop |

Runs as a system tray application. The tray icon shows the current virtual desktop number.

## Setup

**Windows** (required for the full tool):
```powershell
py -m pip install -e ".[windows,dev]"
```

**Linux / macOS** (dev tools only — tests and linting, no Win32 runtime):
```bash
python3 -m venv .venv && source .venv/bin/activate  # bash/zsh
# source .venv/bin/activate.fish                     # fish
pip install -e ".[dev]"
```

> **Note:** On Windows, `pip` may not be on PATH. Use `py -m pip` or `python -m pip`.
> During Python installation, check **"Add Python to PATH"**.

## Development

```bash
make test      # pytest
make lint      # ruff check .
make format    # ruff format .
```

Run a single test file: `pytest tests/test_filter.py`
