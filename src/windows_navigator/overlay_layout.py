"""Theme, colour palette, and dark-mode detection for the overlay."""

from __future__ import annotations

try:
    import darkdetect

    _DARK: bool = darkdetect.isDark() or False
except Exception:
    _DARK = False

_PALETTE: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#1e1e2e",
        "row_bg": "#1e1e2e",
        "tab_bg": "#252538",  # slightly lighter/bluer than row_bg
        "row_sel": "#3d405b",
        "title_fg": "#cdd6f4",
        "proc_fg": "#a6adc8",
        "entry_bg": "#313244",
        "entry_fg": "#cdd6f4",
        "border": "#45475a",
        "tab_active": "#89b4fa",  # accent blue for active-tab indicator
    },
    "light": {
        "bg": "#f5f5f5",
        "row_bg": "#f5f5f5",
        "tab_bg": "#ebebf2",  # slightly darker/cooler than row_bg
        "row_sel": "#c8d0e7",
        "title_fg": "#1e1e2e",
        "proc_fg": "#4c4f69",
        "entry_bg": "#ffffff",
        "entry_fg": "#1e1e2e",
        "border": "#bcc0cc",
        "tab_active": "#1e66f5",  # accent blue for active-tab indicator
    },
}


def _colors() -> dict[str, str]:
    return _PALETTE["dark"] if _DARK else _PALETTE["light"]
