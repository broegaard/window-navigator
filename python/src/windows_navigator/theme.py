"""Shared colour palette for virtual desktop badges and the system tray icon."""

from __future__ import annotations

DESKTOP_COLORS: list[tuple[int, int, int]] = [
    (160, 45, 15),   # vermilion   hue~15°
    (135, 100, 0),   # dark amber  hue~55°
    (55, 95, 0),     # dark lime   hue~100°
    (0, 115, 80),    # dark jade   hue~145°
    (0, 100, 120),   # ocean teal  hue~190°
    (25, 65, 160),   # cobalt blue hue~230°
    (80, 0, 155),    # deep violet hue~270°
    (145, 0, 115),   # dark rose   hue~315°
]


def desktop_badge_color(desktop_number: int) -> str:
    r, g, b = DESKTOP_COLORS[(desktop_number - 1) % len(DESKTOP_COLORS)]
    return f"#{r:02x}{g:02x}{b:02x}"
