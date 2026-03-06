"""Tests for provider icon extraction fallback."""

from windows_navigator.provider import (
    _EXCLUDED_PROCESSES,
    _FALLBACK_ICON,
    _NOTIF_TITLE_RE,
    IconExtractor,
    RealWindowProvider,
)


def test_extract_icon_returns_fallback_when_win32_missing():
    """IconExtractor.extract must return the fallback icon when win32* is unavailable.

    On Linux, win32gui is not installed, so extract will hit the except branch
    and return the fallback icon.
    """
    result = IconExtractor.extract(0)
    assert result.size == _FALLBACK_ICON.size
    assert result.mode == _FALLBACK_ICON.mode


def test_fallback_icon_is_valid_image():
    from PIL import Image

    assert isinstance(_FALLBACK_ICON, Image.Image)
    assert _FALLBACK_ICON.size == (32, 32)


def test_fallback_icon_is_grey():
    """Fallback icon is a solid grey square (128, 128, 128, 255)."""
    r, g, b, a = _FALLBACK_ICON.getpixel((0, 0))
    assert (r, g, b, a) == (128, 128, 128, 255)


def test_extract_icon_returns_copy_not_singleton():
    """IconExtractor.extract must return a fresh image, not the _FALLBACK_ICON object itself,
    so callers that modify the image don't corrupt the shared fallback."""
    result1 = IconExtractor.extract(0)
    result2 = IconExtractor.extract(0)
    assert result1 is not _FALLBACK_ICON
    assert result2 is not _FALLBACK_ICON
    assert result1 is not result2


# ---------------------------------------------------------------------------
# _NOTIF_TITLE_RE — notification title prefix regex
# ---------------------------------------------------------------------------


def test_notif_title_re_matches_single_digit():
    assert _NOTIF_TITLE_RE.match("(3) Inbox - Gmail")


def test_notif_title_re_matches_multi_digit():
    assert _NOTIF_TITLE_RE.match("(42) unread messages")


def test_notif_title_re_no_match_normal_title():
    assert not _NOTIF_TITLE_RE.match("Normal window title")


def test_notif_title_re_no_match_empty_parens():
    assert not _NOTIF_TITLE_RE.match("() something")


def test_notif_title_re_no_match_alpha_digits():
    assert not _NOTIF_TITLE_RE.match("(abc) letters only")


def test_notif_title_re_no_match_mid_string():
    """Pattern must be anchored to the start of the string."""
    assert not _NOTIF_TITLE_RE.match("prefix (3) suffix")


def test_notif_title_re_matches_just_parens_and_space():
    assert _NOTIF_TITLE_RE.match("(1)")


# ---------------------------------------------------------------------------
# _EXCLUDED_PROCESSES
# ---------------------------------------------------------------------------


def test_excluded_processes_contains_textinputhost():
    assert "textinputhost.exe" in _EXCLUDED_PROCESSES


def test_excluded_processes_all_lowercase():
    assert all(p == p.lower() for p in _EXCLUDED_PROCESSES)


# ---------------------------------------------------------------------------
# RealWindowProvider constructor
# ---------------------------------------------------------------------------


def test_provider_constructor_stores_custom_assign_desktops():
    custom: list[list[int]] = []

    def _assigner(hwnds: list[int]) -> tuple[dict, dict]:
        custom.append(hwnds)
        return {}, {}

    provider = RealWindowProvider(assign_desktops=_assigner)
    assert provider._assign_desktops is _assigner


def test_provider_constructor_stores_custom_flashing_set():
    flashing: set[int] = {10, 20}
    provider = RealWindowProvider(assign_desktops=lambda h: ({}, {}), flashing=flashing)
    assert provider._flashing is flashing


def test_provider_default_flashing_is_empty_set():
    provider = RealWindowProvider(assign_desktops=lambda h: ({}, {}))
    assert provider._flashing == set()
    assert isinstance(provider._flashing, set)
