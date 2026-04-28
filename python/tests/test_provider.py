"""Tests for provider icon extraction fallback."""

from unittest.mock import MagicMock, patch

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


def test_provider_icon_cache_starts_empty():
    provider = RealWindowProvider(assign_desktops=lambda h: ({}, {}))
    assert provider._icon_cache == {}


# ---------------------------------------------------------------------------
# Icon cache — get_windows() caching behaviour
# ---------------------------------------------------------------------------


def _make_provider_with_windows(hwnds_titles_exes):
    """Return a RealWindowProvider wired to enumerate the given (hwnd, title, exe) triples."""
    import sys
    from unittest.mock import MagicMock

    win32gui = MagicMock()
    win32con = MagicMock()
    win32process = MagicMock()
    win32con.GWL_EXSTYLE = 0
    win32con.WS_EX_TOOLWINDOW = 0x80

    hwnds = [h for h, _, _ in hwnds_titles_exes]
    title_map = {h: t for h, t, _ in hwnds_titles_exes}
    exe_map = {h: e for h, _, e in hwnds_titles_exes}

    def enum_windows_side_effect(cb, _):
        for hwnd in hwnds:
            cb(hwnd, None)

    win32gui.EnumWindows.side_effect = enum_windows_side_effect
    win32gui.IsWindowVisible.return_value = True
    win32gui.GetWindowLong.return_value = 0
    win32gui.GetWindowText.side_effect = lambda h: title_map.get(h, "")

    def get_process_info_side_effect(hwnd, _wp):
        exe = exe_map.get(hwnd, "")
        return (exe.split("\\")[-1] if exe else ""), exe

    provider = RealWindowProvider(assign_desktops=lambda h: ({hw: 1 for hw in h}, {hw: True for hw in h}))

    with patch.dict(sys.modules, {
        "win32gui": win32gui,
        "win32con": win32con,
        "win32process": win32process,
    }):
        with patch("windows_navigator.provider.RealWindowProvider._get_process_info",
                   side_effect=get_process_info_side_effect):
            with patch("windows_navigator.provider.IconExtractor.extract") as mock_extract:
                mock_extract.return_value = _FALLBACK_ICON.copy()
                provider.get_windows()
                return provider, mock_extract


def test_icon_cache_hit_on_same_exe():
    """Two windows sharing the same exe path must only call IconExtractor.extract once."""
    exe = "C:\\Windows\\chrome.exe"
    triples = [(1, "Window A", exe), (2, "Window B", exe)]
    _, mock_extract = _make_provider_with_windows(triples)
    assert mock_extract.call_count == 1


def test_icon_cache_miss_on_different_exe():
    """Two windows with different exe paths each get a fresh extract call."""
    triples = [
        (1, "Window A", "C:\\Windows\\chrome.exe"),
        (2, "Window B", "C:\\Windows\\notepad.exe"),
    ]
    _, mock_extract = _make_provider_with_windows(triples)
    assert mock_extract.call_count == 2


def test_icon_cache_key_is_case_insensitive():
    """exe paths differing only in case must share one cache entry."""
    triples = [
        (1, "Window A", "C:\\Windows\\Chrome.exe"),
        (2, "Window B", "C:\\Windows\\chrome.exe"),
    ]
    _, mock_extract = _make_provider_with_windows(triples)
    assert mock_extract.call_count == 1


def test_icon_cache_populated_after_get_windows():
    """After get_windows(), _icon_cache holds one entry per unique exe path."""
    import sys

    win32gui = MagicMock()
    win32con = MagicMock()
    win32process = MagicMock()
    win32con.GWL_EXSTYLE = 0
    win32con.WS_EX_TOOLWINDOW = 0x80

    triples = [(1, "A", "C:\\a.exe"), (2, "B", "C:\\b.exe"), (3, "C", "C:\\a.exe")]
    hwnds = [h for h, _, _ in triples]
    title_map = {h: t for h, t, _ in triples}
    exe_map = {h: e for h, _, e in triples}

    win32gui.EnumWindows.side_effect = lambda cb, _: [cb(h, None) for h in hwnds]
    win32gui.IsWindowVisible.return_value = True
    win32gui.GetWindowLong.return_value = 0
    win32gui.GetWindowText.side_effect = lambda h: title_map.get(h, "")

    provider = RealWindowProvider(
        assign_desktops=lambda h: ({hw: 1 for hw in h}, {hw: True for hw in h})
    )

    def _fake_get_process_info(hwnd, _wp):
        exe = exe_map.get(hwnd, "")
        return exe.split("\\")[-1], exe

    with patch.dict(sys.modules, {"win32gui": win32gui, "win32con": win32con, "win32process": win32process}):
        with patch("windows_navigator.provider.RealWindowProvider._get_process_info",
                   side_effect=_fake_get_process_info):
            with patch("windows_navigator.provider.IconExtractor.extract",
                       return_value=_FALLBACK_ICON.copy()):
                provider.get_windows()

    assert set(provider._icon_cache.keys()) == {"c:\\a.exe", "c:\\b.exe"}


def test_icon_cache_persists_across_get_windows_calls():
    """On a second get_windows() call, cached icons are reused without re-extracting."""
    import sys

    win32gui = MagicMock()
    win32con = MagicMock()
    win32process = MagicMock()
    win32con.GWL_EXSTYLE = 0
    win32con.WS_EX_TOOLWINDOW = 0x80

    exe = "C:\\app.exe"
    win32gui.EnumWindows.side_effect = lambda cb, _: cb(1, None)
    win32gui.IsWindowVisible.return_value = True
    win32gui.GetWindowLong.return_value = 0
    win32gui.GetWindowText.return_value = "App"

    provider = RealWindowProvider(
        assign_desktops=lambda h: ({hw: 1 for hw in h}, {hw: True for hw in h})
    )

    with patch.dict(sys.modules, {"win32gui": win32gui, "win32con": win32con, "win32process": win32process}):
        with patch("windows_navigator.provider.RealWindowProvider._get_process_info",
                   return_value=("app.exe", exe)):
            with patch("windows_navigator.provider.IconExtractor.extract",
                       return_value=_FALLBACK_ICON.copy()) as mock_extract:
                provider.get_windows()
                provider.get_windows()

    assert mock_extract.call_count == 1
