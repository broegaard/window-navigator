# CLAUDE.md

Keyboard-driven window switcher for Windows. Press **Ctrl+Shift+Space** to open an overlay listing all open windows; type to filter, arrow keys to navigate, Enter to focus.

## Repository layout

| Directory | Contents |
|-----------|----------|
| `python/` | Original Python implementation |
| `go/` | Go port (complete — the shipping binary) |

Each subdirectory has its own `CLAUDE.md` with commands, architecture, and gotchas.

```
CLAUDE.md          ← this file
python/CLAUDE.md   ← Python implementation details
go/CLAUDE.md       ← Go implementation details
README.md
pack.sh
```
