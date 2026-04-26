"""Shared colour palette for virtual desktop badges and the system tray icon."""

from __future__ import annotations

DESKTOP_COLORS: list[tuple[int, int, int]] = [
    (0, 60, 150),    # blue
    (160, 50, 0),    # orange
    (0, 120, 60),    # green
    (120, 0, 120),   # purple
    (160, 0, 40),    # red
    (0, 110, 120),   # teal
    (100, 80, 0),    # amber
    (60, 60, 60),    # grey
]


def desktop_badge_color(desktop_number: int) -> str:
    r, g, b = DESKTOP_COLORS[(desktop_number - 1) % len(DESKTOP_COLORS)]
    return f"#{r:02x}{g:02x}{b:02x}"
