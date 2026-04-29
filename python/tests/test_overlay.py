"""Tests for overlay helper functions (no Tk display required)."""

import sys
from unittest.mock import MagicMock

# overlay.py imports tkinter at module level; stub it out so the tests run on Linux.
sys.modules.setdefault("tkinter", MagicMock())

import windows_navigator.overlay as _ov  # noqa: E402

from windows_navigator.models import TabInfo, WindowInfo  # noqa: E402
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


# ---------------------------------------------------------------------------
# _row_height
# ---------------------------------------------------------------------------


def test_row_height_returns_row_height_for_window_info():
    from windows_navigator.overlay import _ROW_HEIGHT, _row_height

    w = WindowInfo(
        hwnd=1, title="Test", process_name="app.exe", icon=None,
        desktop_number=1, is_current_desktop=True, has_notification=False,
    )
    assert _row_height(w) == _ROW_HEIGHT


def test_row_height_returns_tab_row_height_for_tab_info():
    from windows_navigator.overlay import _TAB_ROW_HEIGHT, _row_height

    t = TabInfo(name="Tab A", hwnd=1, index=0)
    assert _row_height(t) == _TAB_ROW_HEIGHT


def test_row_height_tab_is_shorter_than_window():
    from windows_navigator.overlay import _ROW_HEIGHT, _TAB_ROW_HEIGHT

    assert _TAB_ROW_HEIGHT < _ROW_HEIGHT


# ---------------------------------------------------------------------------
# init_scale
# ---------------------------------------------------------------------------


def test_init_scale_scales_overlay_width():
    orig = _ov._OVERLAY_WIDTH
    try:
        _ov.init_scale(2.0)
        assert _ov._OVERLAY_WIDTH == round(1240 * 2.0)
    finally:
        _ov.init_scale(orig / 1240)


def test_init_scale_scales_row_height():
    try:
        _ov.init_scale(2.0)
        assert _ov._ROW_HEIGHT == round(44 * 2.0)
    finally:
        _ov.init_scale(1.0)


def test_init_scale_restores_defaults_at_1x():
    _ov.init_scale(1.5)
    _ov.init_scale(1.0)
    assert _ov._OVERLAY_WIDTH == 1240
    assert _ov._ROW_HEIGHT == 44
    assert _ov._TAB_ROW_HEIGHT == 28


def test_init_scale_scales_strip_height():
    try:
        _ov.init_scale(2.0)
        assert _ov._STRIP_HEIGHT == _ov._ICON_SIZE + round(12 * 2.0)
    finally:
        _ov.init_scale(1.0)


def test_init_scale_scales_count_bar_height():
    try:
        _ov.init_scale(1.5)
        assert _ov._COUNT_BAR_H == round(18 * 1.5)
    finally:
        _ov.init_scale(1.0)


# ---------------------------------------------------------------------------
# PIL import fallback — _HAS_PIL = False branch
# ---------------------------------------------------------------------------


def test_haspil_is_bool():
    assert isinstance(_ov._HAS_PIL, bool)
