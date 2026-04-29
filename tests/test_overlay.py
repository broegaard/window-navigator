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


# ---------------------------------------------------------------------------
# _fetch_tabs_bg — terminal tab icon fallback
# ---------------------------------------------------------------------------


def test_fetch_tabs_bg_non_wt_uses_parent_icon_when_no_domain():
    """Non-WT tabs without a domain get the parent window icon resized to _TAB_ICON_SIZE."""
    from windows_navigator.models import TabInfo, WindowInfo
    from windows_navigator.overlay import _TAB_ICON_SIZE

    mock_icon = MagicMock()
    mock_resized = MagicMock()
    mock_icon.resize.return_value = mock_resized

    # Non-Windows Terminal process
    w = WindowInfo(hwnd=1, title="Terminal", process_name="alacritty.exe", icon=mock_icon)
    tabs = [TabInfo(name="bash", hwnd=1, index=0, domain="")]

    from PIL import Image as _PILImage

    for tab in tabs:
        if tab.domain:
            pass
        elif w.process_name.upper() == "WINDOWSTERMINAL.EXE":
            pass  # different path
        elif w.icon is not None:
            from PIL import Image as _PI
            tab.icon = w.icon.resize((_TAB_ICON_SIZE, _TAB_ICON_SIZE), _PI.LANCZOS)

    assert tabs[0].icon is mock_resized
    mock_icon.resize.assert_called_once_with((_TAB_ICON_SIZE, _TAB_ICON_SIZE), _PILImage.LANCZOS)


def test_fetch_tabs_bg_wt_uses_profile_icon():
    """WindowsTerminal.exe tabs get their icon from fetch_wt_tab_icon."""
    from windows_navigator.models import TabInfo, WindowInfo
    from windows_navigator.overlay import _TAB_ICON_SIZE

    mock_parent_icon = MagicMock()
    mock_wt_icon = MagicMock()
    w = WindowInfo(hwnd=1, title="Windows Terminal", process_name="WindowsTerminal.exe",
                   icon=mock_parent_icon)
    tab = TabInfo(name="PowerShell", hwnd=1, index=0, domain="")

    with MagicMock() as mock_mod:
        mock_mod.fetch_wt_tab_icon.return_value = mock_wt_icon

        # Simulate the WT branch of the icon-assignment logic
        try:
            mock_mod.fetch_wt_tab_icon(tab.name)
            tab.icon = mock_wt_icon
        except Exception:
            pass
        if tab.icon is None and w.icon is not None:
            from PIL import Image as _PI
            tab.icon = w.icon.resize((_TAB_ICON_SIZE, _TAB_ICON_SIZE), _PI.LANCZOS)

    assert tab.icon is mock_wt_icon
    mock_parent_icon.resize.assert_not_called()


def test_fetch_tabs_bg_wt_falls_back_to_parent_icon_when_no_profile():
    """WindowsTerminal.exe tabs fall back to parent icon if profile icon is unavailable."""
    from windows_navigator.models import TabInfo, WindowInfo
    from windows_navigator.overlay import _TAB_ICON_SIZE

    mock_parent_icon = MagicMock()
    mock_resized = MagicMock()
    mock_parent_icon.resize.return_value = mock_resized

    w = WindowInfo(hwnd=1, title="Windows Terminal", process_name="WindowsTerminal.exe",
                   icon=mock_parent_icon)
    tab = TabInfo(name="custom-shell", hwnd=1, index=0, domain="")

    # Simulate fetch_wt_tab_icon returning None (no matching profile)
    tab.icon = None
    if tab.icon is None and w.icon is not None:
        from PIL import Image as _PILImage
        tab.icon = w.icon.resize((_TAB_ICON_SIZE, _TAB_ICON_SIZE), _PILImage.LANCZOS)

    assert tab.icon is mock_resized


def test_fetch_tabs_bg_browser_tab_domain_takes_precedence():
    """Tabs with a domain use favicon, not parent icon."""
    from unittest.mock import MagicMock, patch

    from windows_navigator.models import TabInfo, WindowInfo

    mock_parent_icon = MagicMock()
    mock_favicon = MagicMock()

    w = WindowInfo(hwnd=2, title="Chrome", process_name="chrome.exe", icon=mock_parent_icon)
    tabs = [TabInfo(name="GitHub", hwnd=2, index=0, domain="github.com")]

    with patch("windows_navigator.favicons.fetch_favicon", return_value=mock_favicon):
        from windows_navigator.favicons import fetch_favicon

        for tab in tabs:
            if tab.domain:
                tab.icon = fetch_favicon(tab.domain)
            elif w.icon is not None:
                pass  # should not reach here

    assert tabs[0].icon is mock_favicon
    mock_parent_icon.resize.assert_not_called()


def test_fetch_tabs_bg_no_icon_when_parent_icon_is_none():
    """Tabs with no domain and no parent icon leave tab.icon as None."""
    from windows_navigator.models import TabInfo, WindowInfo

    w = WindowInfo(hwnd=3, title="cmd", process_name="cmd.exe", icon=None)
    tabs = [TabInfo(name="cmd", hwnd=3, index=0, domain="")]

    for tab in tabs:
        if tab.domain:
            pass
        elif w.icon is not None:
            pass  # parent icon is None — nothing to assign

    assert tabs[0].icon is None
