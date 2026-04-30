"""Tests for overlay_layout — colour palette and dark-mode helpers."""

from __future__ import annotations

import windows_navigator.overlay_layout as _ol
from windows_navigator.overlay_layout import _PALETTE, _colors

# ---------------------------------------------------------------------------
# _PALETTE structure
# ---------------------------------------------------------------------------


def test_palette_has_dark_and_light_variants():
    assert "dark" in _PALETTE
    assert "light" in _PALETTE


def test_palette_variants_have_identical_key_sets():
    assert set(_PALETTE["dark"].keys()) == set(_PALETTE["light"].keys())


def test_palette_contains_required_keys():
    required = {
        "bg",
        "row_bg",
        "tab_bg",
        "row_sel",
        "title_fg",
        "proc_fg",
        "entry_bg",
        "entry_fg",
        "border",
    }
    assert required <= set(_PALETTE["dark"].keys())


def test_palette_all_values_are_7_char_hex_strings():
    for variant_name, variant in _PALETTE.items():
        for key, color in variant.items():
            assert color.startswith("#"), f"{variant_name}[{key!r}] = {color!r} not a hex color"
            assert len(color) == 7, f"{variant_name}[{key!r}] = {color!r} wrong length"


def test_palette_dark_and_light_differ():
    assert _PALETTE["dark"]["bg"] != _PALETTE["light"]["bg"]


# ---------------------------------------------------------------------------
# _colors() — returns the active palette variant
# ---------------------------------------------------------------------------


def test_colors_returns_dict_with_all_required_keys():
    colors = _colors()
    for key in (
        "bg",
        "row_bg",
        "tab_bg",
        "row_sel",
        "title_fg",
        "proc_fg",
        "entry_bg",
        "entry_fg",
        "border",
    ):
        assert key in colors


def test_colors_returns_light_palette_when_dark_is_false():
    orig = _ol._DARK
    try:
        _ol._DARK = False
        assert _colors() is _PALETTE["light"]
    finally:
        _ol._DARK = orig


def test_colors_returns_dark_palette_when_dark_is_true():
    orig = _ol._DARK
    try:
        _ol._DARK = True
        assert _colors() is _PALETTE["dark"]
    finally:
        _ol._DARK = orig


def test_colors_light_bg_is_light():
    orig = _ol._DARK
    try:
        _ol._DARK = False
        bg = _colors()["bg"]
        r = int(bg[1:3], 16)
        assert r > 200, f"light bg {bg!r} should be light, got r={r}"
    finally:
        _ol._DARK = orig


def test_colors_dark_bg_is_dark():
    orig = _ol._DARK
    try:
        _ol._DARK = True
        bg = _colors()["bg"]
        r = int(bg[1:3], 16)
        assert r < 50, f"dark bg {bg!r} should be dark, got r={r}"
    finally:
        _ol._DARK = orig


# ---------------------------------------------------------------------------
# _DARK — exception branch (darkdetect unavailable)
# ---------------------------------------------------------------------------


def test_dark_is_false_when_darkdetect_raises():
    """If darkdetect raises during import, _DARK must default to False."""
    import importlib
    import sys

    orig_darkdetect = sys.modules.get("darkdetect", _sentinel := object())
    orig_ol = sys.modules.pop("windows_navigator.overlay_layout", None)

    try:
        sys.modules["darkdetect"] = None  # causes ImportError on `import darkdetect`
        import windows_navigator.overlay_layout as fresh_ol

        assert fresh_ol._DARK is False
    finally:
        if orig_darkdetect is _sentinel:
            sys.modules.pop("darkdetect", None)
        else:
            sys.modules["darkdetect"] = orig_darkdetect  # type: ignore[assignment]
        if orig_ol is not None:
            sys.modules["windows_navigator.overlay_layout"] = orig_ol
        else:
            sys.modules.pop("windows_navigator.overlay_layout", None)
        # Reload to restore the module to its correct state for subsequent tests
        importlib.reload(_ol)
