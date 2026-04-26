"""Tests for tray icon rendering."""

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
