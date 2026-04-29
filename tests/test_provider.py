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


# ---------------------------------------------------------------------------
# RealWindowProvider default assign_desktops
# ---------------------------------------------------------------------------


def test_provider_default_assign_desktops_is_assign_desktop_numbers():
    from windows_navigator.virtual_desktop import assign_desktop_numbers

    provider = RealWindowProvider()
    assert provider._assign_desktops is assign_desktop_numbers


# ---------------------------------------------------------------------------
# get_windows — filtering paths
# ---------------------------------------------------------------------------


def _run_get_windows(hwnd_entries, extra_filters=None, flashing=None):
    """Drive get_windows with controlled per-window attributes.

    Each entry is a dict with keys: hwnd, title, visible (default True),
    exstyle (default 0), process_name (default "app.exe"),
    exe_path (default "C:\\app.exe"), desktop_number (default 1).
    """
    import sys

    win32gui = MagicMock()
    win32con = MagicMock()
    win32process = MagicMock()
    win32con.GWL_EXSTYLE = 0
    win32con.WS_EX_TOOLWINDOW = 0x80

    def _enum(cb, _):
        for e in hwnd_entries:
            cb(e["hwnd"], None)

    win32gui.EnumWindows.side_effect = _enum
    win32gui.IsWindowVisible.side_effect = lambda h: next(
        e.get("visible", True) for e in hwnd_entries if e["hwnd"] == h
    )
    win32gui.GetWindowLong.side_effect = lambda h, _: next(
        e.get("exstyle", 0) for e in hwnd_entries if e["hwnd"] == h
    )
    win32gui.GetWindowText.side_effect = lambda h: next(
        e.get("title", "Window") for e in hwnd_entries if e["hwnd"] == h
    )

    desktop_map = {e["hwnd"]: e.get("desktop_number", 1) for e in hwnd_entries}
    is_current_map = {e["hwnd"]: True for e in hwnd_entries}

    def _fake_process_info(hwnd, _wp):
        e = next((x for x in hwnd_entries if x["hwnd"] == hwnd), {})
        return e.get("process_name", "app.exe"), e.get("exe_path", "C:\\app.exe")

    provider = RealWindowProvider(
        assign_desktops=lambda hwnds: (desktop_map, is_current_map),
        extra_filters=extra_filters or [],
        flashing=flashing or set(),
    )

    with patch.dict(sys.modules, {"win32gui": win32gui, "win32con": win32con,
                                   "win32process": win32process}):
        with patch("windows_navigator.provider.RealWindowProvider._get_process_info",
                   side_effect=_fake_process_info):
            with patch("windows_navigator.provider.IconExtractor.extract",
                       return_value=_FALLBACK_ICON.copy()):
                results = provider.get_windows()

    return results, provider


def test_get_windows_skips_invisible_windows():
    results, _ = _run_get_windows([
        {"hwnd": 1, "title": "Visible"},
        {"hwnd": 2, "title": "Hidden", "visible": False},
    ])
    assert len(results) == 1
    assert results[0].hwnd == 1


def test_get_windows_skips_toolwindows():
    results, _ = _run_get_windows([
        {"hwnd": 1, "title": "Normal"},
        {"hwnd": 2, "title": "Tool", "exstyle": 0x80},
    ])
    assert len(results) == 1
    assert results[0].hwnd == 1


def test_get_windows_skips_empty_title():
    results, _ = _run_get_windows([
        {"hwnd": 1, "title": "Has Title"},
        {"hwnd": 2, "title": ""},
    ])
    assert len(results) == 1
    assert results[0].hwnd == 1


def test_get_windows_skips_excluded_process():
    results, _ = _run_get_windows([
        {"hwnd": 1, "title": "Chrome", "process_name": "chrome.exe"},
        {"hwnd": 2, "title": "TextInput", "process_name": "textinputhost.exe"},
    ])
    assert len(results) == 1
    assert results[0].hwnd == 1


def test_get_windows_extra_filter_rejects_window():
    def _reject_two(hwnd: int, title: str, process_name: str) -> bool:
        return hwnd != 2

    results, _ = _run_get_windows([
        {"hwnd": 1, "title": "Allowed"},
        {"hwnd": 2, "title": "Blocked"},
    ], extra_filters=[_reject_two])
    assert len(results) == 1
    assert results[0].hwnd == 1


def test_get_windows_skips_ghost_window():
    results, _ = _run_get_windows([
        {"hwnd": 1, "title": "Real", "desktop_number": 1},
        {"hwnd": 2, "title": "Ghost", "desktop_number": -1},
    ])
    assert len(results) == 1
    assert results[0].hwnd == 1


def test_get_windows_no_exe_path_bypasses_icon_cache():
    results, provider = _run_get_windows([
        {"hwnd": 1, "title": "Unknown", "process_name": "unknown", "exe_path": ""},
    ])
    assert len(results) == 1
    assert len(provider._icon_cache) == 0


def test_get_windows_evicts_oldest_cache_entry_when_full():
    from windows_navigator.provider import _ICON_CACHE_MAX

    import sys

    provider = RealWindowProvider(
        assign_desktops=lambda h: ({1: 1}, {1: True})
    )
    for i in range(_ICON_CACHE_MAX):
        provider._icon_cache[f"c:\\app{i}.exe"] = _FALLBACK_ICON.copy()
    first_key = next(iter(provider._icon_cache))

    win32gui = MagicMock()
    win32con = MagicMock()
    win32process = MagicMock()
    win32con.GWL_EXSTYLE = 0
    win32con.WS_EX_TOOLWINDOW = 0x80
    win32gui.EnumWindows.side_effect = lambda cb, _: cb(1, None)
    win32gui.IsWindowVisible.return_value = True
    win32gui.GetWindowLong.return_value = 0
    win32gui.GetWindowText.return_value = "New App"

    with patch.dict(sys.modules, {"win32gui": win32gui, "win32con": win32con,
                                   "win32process": win32process}):
        with patch("windows_navigator.provider.RealWindowProvider._get_process_info",
                   return_value=("new_app.exe", "C:\\new_app.exe")):
            with patch("windows_navigator.provider.IconExtractor.extract",
                       return_value=_FALLBACK_ICON.copy()):
                provider.get_windows()

    assert len(provider._icon_cache) == _ICON_CACHE_MAX
    assert first_key not in provider._icon_cache
    assert "c:\\new_app.exe" in provider._icon_cache


# ---------------------------------------------------------------------------
# _get_process_info — happy path and exception fallback
# ---------------------------------------------------------------------------


def test_get_process_info_returns_name_and_path():
    import sys

    win32api = MagicMock()
    win32con = MagicMock()
    win32process = MagicMock()
    win32process.GetWindowThreadProcessId.return_value = (0, 1234)

    with patch.dict(sys.modules, {"win32api": win32api, "win32con": win32con}):
        with patch("windows_navigator.provider._query_exe_path",
                   return_value="/fake/notepad.exe"):
            result = RealWindowProvider._get_process_info(42, win32process)

    assert result == ("notepad.exe", "/fake/notepad.exe")
    win32api.CloseHandle.assert_called_once()


def test_get_process_info_returns_empty_strings_on_exception():
    win32process = MagicMock()
    win32process.GetWindowThreadProcessId.side_effect = OSError("access denied")
    result = RealWindowProvider._get_process_info(42, win32process)
    assert result == ("", "")
