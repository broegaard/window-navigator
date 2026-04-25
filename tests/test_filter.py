"""Tests for filter.filter_windows."""

from windows_navigator.filter import filter_windows
from windows_navigator.models import WindowInfo


def _make_window(title: str, process_name: str) -> WindowInfo:
    return WindowInfo(hwnd=1, title=title, process_name=process_name)


def _make_desktop_window(title: str, process_name: str, desktop_number: int) -> WindowInfo:
    return WindowInfo(hwnd=1, title=title, process_name=process_name, desktop_number=desktop_number)


def test_empty_query_returns_all():
    windows = [_make_window("Notepad", "notepad.exe"), _make_window("Chrome", "chrome.exe")]
    assert filter_windows(windows, "") == windows


def test_match_on_title():
    w1 = _make_window("Notepad", "notepad.exe")
    w2 = _make_window("Chrome", "chrome.exe")
    assert filter_windows([w1, w2], "note") == [w1]


def test_match_on_process_name():
    w1 = _make_window("New Tab", "chrome.exe")
    w2 = _make_window("Editor", "notepad.exe")
    assert filter_windows([w1, w2], "chrome") == [w1]


def test_case_insensitive():
    w = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w], "NOTE") == [w]
    assert filter_windows([w], "NoteP") == [w]


def test_no_match_returns_empty():
    windows = [_make_window("Notepad", "notepad.exe")]
    assert filter_windows(windows, "zzz") == []


def test_preserves_order():
    windows = [
        _make_window("Alpha App", "alpha.exe"),
        _make_window("Beta App", "beta.exe"),
        _make_window("Gamma App", "gamma.exe"),
    ]
    result = filter_windows(windows, "app")
    assert result == windows


def test_matches_both_title_and_process():
    w1 = _make_window("explorer", "notepad.exe")  # matches on title
    w2 = _make_window("Untitled", "explorer.exe")  # matches on process
    w3 = _make_window("Chrome", "chrome.exe")  # no match
    assert filter_windows([w1, w2, w3], "explorer") == [w1, w2]


def test_empty_windows_list():
    assert filter_windows([], "anything") == []


def test_returns_copy_not_original_list():
    windows = [_make_window("Notepad", "notepad.exe")]
    result = filter_windows(windows, "")
    assert result == windows
    assert result is not windows


# ---------------------------------------------------------------------------
# Hash character — plain text, no special meaning
# ---------------------------------------------------------------------------


def test_hash_alone_matches_titles_containing_hash():
    """'#' is a regular character matched against title and process name."""
    w1 = _make_window("#tag title", "app.exe")
    w2 = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w1, w2], "#") == [w1]


def test_hash_number_is_plain_text():
    """'#1' is matched as a literal string — no desktop filtering."""
    w1 = _make_window("#1 priority", "app.exe")
    w2 = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w1, w2], "#1") == [w1]
    assert filter_windows([w1, w2], "#1", desktop_nums={1}) == []


def test_hash_non_digit_is_text_filter():
    """'#abc' is plain text — matched against title."""
    w1 = _make_window("#abc window", "app.exe")
    w2 = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w1, w2], "#abc") == [w1]


# ---------------------------------------------------------------------------
# Desktop badge filter (desktop_nums parameter)
# ---------------------------------------------------------------------------


def test_desktop_nums_filters_by_desktop():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    w3 = _make_desktop_window("Terminal", "wt.exe", desktop_number=1)
    assert filter_windows([w1, w2, w3], "", desktop_nums={1}) == [w1, w3]
    assert filter_windows([w1, w2, w3], "", desktop_nums={2}) == [w2]


def test_desktop_nums_with_text():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Terminal", "wt.exe", desktop_number=1)
    w3 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=2)
    assert filter_windows([w1, w2, w3], "note", desktop_nums={1}) == [w1]


def test_desktop_nums_with_digit_starting_text():
    """Desktop badge + text starting with a digit: no conflation with desktop number."""
    w1 = _make_desktop_window("1foo", "app.exe", desktop_number=2)
    w2 = _make_desktop_window("1foo", "app.exe", desktop_number=1)
    assert filter_windows([w1, w2], "1foo", desktop_nums={2}) == [w1]


def test_desktop_nums_or_semantics():
    """Multiple desktops show windows from any of those desktops."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    w3 = _make_desktop_window("Terminal", "wt.exe", desktop_number=3)
    assert filter_windows([w1, w2, w3], "", desktop_nums={1, 2}) == [w1, w2]


def test_desktop_nums_three():
    """Three desktops active shows all matching windows."""
    w1 = _make_desktop_window("A", "a.exe", desktop_number=1)
    w2 = _make_desktop_window("B", "b.exe", desktop_number=2)
    w3 = _make_desktop_window("C", "c.exe", desktop_number=3)
    w4 = _make_desktop_window("D", "d.exe", desktop_number=4)
    assert filter_windows([w1, w2, w3, w4], "", desktop_nums={1, 2, 3}) == [w1, w2, w3]


def test_desktop_nums_none_means_no_filter():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    assert filter_windows([w1, w2], "", desktop_nums=None) == [w1, w2]


def test_desktop_nums_unknown_desktop_excluded():
    """Windows with desktop_number=0 are excluded when a desktop_nums filter is active."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=0)
    assert filter_windows([w1], "", desktop_nums={1}) == []


def test_desktop_nums_no_match_returns_empty():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    assert filter_windows([w1], "", desktop_nums={99}) == []


def test_desktop_nums_default_is_none():
    """Omitting desktop_nums applies no desktop restriction."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=2)
    assert filter_windows([w1], "note") == [w1]


# ---------------------------------------------------------------------------
# Multi-word text query
# ---------------------------------------------------------------------------


def test_multi_word_query_non_contiguous():
    w1 = _make_window("aa bb cc", "app.exe")
    w2 = _make_window("aa dd", "app.exe")
    assert filter_windows([w1, w2], "aa cc") == [w1]


def test_multi_word_query_all_must_match():
    w = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w], "note zzz") == []


def test_multi_word_query_across_title_and_process():
    w = _make_window("Editor", "chrome.exe")
    assert filter_windows([w], "edit chrome") == [w]


def test_token_match_only_on_process_name():
    """A token that only appears in process_name (not title) still matches."""
    w = _make_window("Untitled", "devenv.exe")
    assert filter_windows([w], "devenv") == [w]
    assert filter_windows([w], "untitled devenv") == [w]


def test_token_match_only_on_title():
    """A token that only appears in title (not process_name) still matches."""
    w = _make_window("Visual Studio Code", "code.exe")
    assert filter_windows([w], "visual") == [w]
    assert filter_windows([w], "visual code") == [w]


# ---------------------------------------------------------------------------
# Whitespace edge cases
# ---------------------------------------------------------------------------


def test_whitespace_only_query_matches_all():
    """A query containing only spaces has no tokens after split() → matches everything."""
    windows = [_make_window("Notepad", "notepad.exe"), _make_window("Chrome", "chrome.exe")]
    assert filter_windows(windows, "   ") == windows


def test_multi_space_between_tokens_still_matches():
    """Multiple spaces between tokens are collapsed by split(); both tokens must match."""
    w1 = _make_window("aa bb cc", "app.exe")
    w2 = _make_window("aa dd", "app.exe")
    assert filter_windows([w1, w2], "aa  cc") == [w1]


def test_token_matching_process_name_across_tokens():
    """Each token is independently checked against title OR process name."""
    w = _make_window("Visual Studio", "devenv.exe")
    assert filter_windows([w], "visual devenv") == [w]
