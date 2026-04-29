"""Tests for theme.desktop_badge_color."""

from windows_navigator.theme import DESKTOP_COLORS, desktop_badge_color


def test_badge_color_format():
    """All badge colors are valid 7-char hex strings."""
    for i in range(1, len(DESKTOP_COLORS) + 1):
        c = desktop_badge_color(i)
        assert c.startswith("#")
        assert len(c) == 7


def test_badge_color_matches_palette():
    for i, (r, g, b) in enumerate(DESKTOP_COLORS, start=1):
        assert desktop_badge_color(i) == f"#{r:02x}{g:02x}{b:02x}"


def test_badge_color_cycles():
    """Desktop N+len wraps to the same color as desktop N."""
    n = len(DESKTOP_COLORS)
    for i in range(1, n + 1):
        assert desktop_badge_color(i) == desktop_badge_color(i + n)


def test_badge_color_desktop_zero_returns_grey():
    """Desktop 0 (unknown) resolves to index 7 (grey) via Python's -1 % 8 = 7."""
    assert desktop_badge_color(0) == desktop_badge_color(len(DESKTOP_COLORS))
