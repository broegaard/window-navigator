"""Tests for tray icon rendering."""

from unittest.mock import MagicMock, patch

from windows_navigator.tray import _DESKTOP_COLORS, _make_tray_icon


def test_make_tray_icon_size_and_mode():
    img = _make_tray_icon(1)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_make_tray_icon_uses_correct_desktop_color():
    for i, (r, g, b) in enumerate(_DESKTOP_COLORS, start=1):
        img = _make_tray_icon(i)
        pixel_r, pixel_g, pixel_b, pixel_a = img.getpixel((0, 0))
        assert (pixel_r, pixel_g, pixel_b) == (r, g, b), f"Desktop {i}: wrong color"
        assert pixel_a == 255


def test_make_tray_icon_colors_cycle():
    """Desktop 9 wraps back to the same color as desktop 1."""
    img1 = _make_tray_icon(1)
    img9 = _make_tray_icon(9)
    assert img1.getpixel((0, 0)) == img9.getpixel((0, 0))


def test_make_tray_icon_unknown_desktop_uses_grey():
    img = _make_tray_icon(0)
    r, g, b, a = img.getpixel((0, 0))
    assert (r, g, b) == (60, 60, 60)
    assert a == 255


def test_make_tray_icon_all_desktops_return_correct_size():
    for n in range(0, 12):
        img = _make_tray_icon(n)
        assert img.size == (64, 64)


# ---------------------------------------------------------------------------
# _load_font — fallback paths
# ---------------------------------------------------------------------------


def test_load_font_returns_cached_result_on_second_call():
    from windows_navigator.tray import _font_cache, _load_font

    size = 777
    _font_cache.pop(size, None)
    try:
        r1 = _load_font(size)
        r2 = _load_font(size)
        assert r1 is r2
    finally:
        _font_cache.pop(size, None)


def test_load_font_falls_back_to_load_default():
    from PIL import ImageFont

    from windows_navigator.tray import _font_cache, _load_font

    size = 778
    _font_cache.pop(size, None)
    try:
        mock_font = MagicMock()
        with (
            patch.object(ImageFont, "truetype", side_effect=OSError("not found")),
            patch.object(ImageFont, "load_default", return_value=mock_font),
        ):
            result = _load_font(size)
        assert result is mock_font
        assert _font_cache[size] is mock_font
    finally:
        _font_cache.pop(size, None)


def test_load_font_returns_none_when_all_fail():
    from PIL import ImageFont

    from windows_navigator.tray import _font_cache, _load_font

    size = 779
    _font_cache.pop(size, None)
    try:
        with (
            patch.object(ImageFont, "truetype", side_effect=OSError("not found")),
            patch.object(ImageFont, "load_default", side_effect=OSError("not found")),
        ):
            result = _load_font(size)
        assert result is None
        assert _font_cache[size] is None
    finally:
        _font_cache.pop(size, None)


def test_make_tray_icon_still_returns_image_when_font_is_none():
    with patch("windows_navigator.tray._load_font", return_value=None):
        img = _make_tray_icon(1)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


# ---------------------------------------------------------------------------
# TrayIcon — constructor and callbacks (no pystray needed)
# ---------------------------------------------------------------------------


def test_tray_icon_constructor_stores_callbacks():
    from windows_navigator.tray import TrayIcon

    on_exit = MagicMock()
    on_settings = MagicMock()
    tray = TrayIcon(on_exit=on_exit, on_settings=on_settings)
    assert tray._on_exit is on_exit
    assert tray._on_settings is on_settings
    assert tray._icon is None


def test_tray_icon_update_is_noop_when_icon_is_none():
    from windows_navigator.tray import TrayIcon

    tray = TrayIcon(on_exit=MagicMock(), on_settings=MagicMock())
    tray.update(2)


def test_tray_icon_stop_is_noop_when_icon_is_none():
    from windows_navigator.tray import TrayIcon

    tray = TrayIcon(on_exit=MagicMock(), on_settings=MagicMock())
    tray.stop()
    assert tray._icon is None


def test_tray_icon_do_settings_calls_callback():
    from windows_navigator.tray import TrayIcon

    on_settings = MagicMock()
    tray = TrayIcon(on_exit=MagicMock(), on_settings=on_settings)
    tray._do_settings()
    on_settings.assert_called_once_with()


def test_tray_icon_do_exit_calls_on_exit_and_clears_icon():
    from windows_navigator.tray import TrayIcon

    on_exit = MagicMock()
    tray = TrayIcon(on_exit=on_exit, on_settings=MagicMock())
    tray._do_exit()
    on_exit.assert_called_once_with()
    assert tray._icon is None


# ---------------------------------------------------------------------------
# TrayIcon — start / update / stop (pystray mocked)
# ---------------------------------------------------------------------------


def test_tray_icon_start_creates_pystray_icon():
    from windows_navigator.tray import TrayIcon

    mock_pystray = MagicMock()
    with patch.dict("sys.modules", {"pystray": mock_pystray}):
        tray = TrayIcon(on_exit=MagicMock(), on_settings=MagicMock())
        tray.start(1)
    mock_pystray.Icon.assert_called_once()
    mock_pystray.Icon.return_value.run_detached.assert_called_once()
    assert tray._icon is mock_pystray.Icon.return_value


def test_tray_icon_update_sets_icon_image():
    from windows_navigator.tray import TrayIcon

    mock_pystray = MagicMock()
    with patch.dict("sys.modules", {"pystray": mock_pystray}):
        tray = TrayIcon(on_exit=MagicMock(), on_settings=MagicMock())
        tray.start(1)
        tray.update(2)
    assert mock_pystray.Icon.return_value.icon is not None


def test_tray_icon_stop_calls_pystray_stop_and_clears_icon():
    from windows_navigator.tray import TrayIcon

    mock_pystray = MagicMock()
    with patch.dict("sys.modules", {"pystray": mock_pystray}):
        tray = TrayIcon(on_exit=MagicMock(), on_settings=MagicMock())
        tray.start(1)
        tray.stop()
    mock_pystray.Icon.return_value.stop.assert_called_once()
    assert tray._icon is None
