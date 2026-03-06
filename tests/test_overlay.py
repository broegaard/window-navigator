"""Tests for overlay helper functions (no Tk display required)."""

import sys
from unittest.mock import MagicMock

# overlay.py imports tkinter at module level; stub it out so the tests run on Linux.
sys.modules.setdefault("tkinter", MagicMock())

from windows_navigator.overlay import _desktop_badge_color  # noqa: E402
from windows_navigator.theme import DESKTOP_COLORS as _DESKTOP_COLORS  # noqa: E402


def test_desktop_badge_color_format():
    """All badge colors are valid 7-char hex strings."""
    for i in range(1, len(_DESKTOP_COLORS) + 1):
        color = _desktop_badge_color(i)
        assert color.startswith("#")
        assert len(color) == 7


def test_desktop_badge_color_matches_desktop_colors():
    for i, (r, g, b) in enumerate(_DESKTOP_COLORS, start=1):
        expected = f"#{r:02x}{g:02x}{b:02x}"
        assert _desktop_badge_color(i) == expected


def test_desktop_badge_color_cycles():
    """Desktop 9 produces the same color as desktop 1."""
    assert _desktop_badge_color(1) == _desktop_badge_color(9)
    assert _desktop_badge_color(2) == _desktop_badge_color(10)
