"""Tests for filter.filter_windows and filter.parse_query."""

from windows_navigator.filter import filter_windows, parse_query
from windows_navigator.models import WindowInfo


def _make_window(title: str, process_name: str) -> WindowInfo:
    return WindowInfo(hwnd=1, title=title, process_name=process_name)


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
# Desktop-prefix (#N) tests
# ---------------------------------------------------------------------------


def _make_desktop_window(title: str, process_name: str, desktop_number: int) -> WindowInfo:
    return WindowInfo(hwnd=1, title=title, process_name=process_name, desktop_number=desktop_number)


def test_desktop_prefix_filters_by_desktop():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    w3 = _make_desktop_window("Terminal", "wt.exe", desktop_number=1)
    assert filter_windows([w1, w2, w3], "#1") == [w1, w3]
    assert filter_windows([w1, w2, w3], "#2") == [w2]


def test_desktop_prefix_with_text_filter():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Terminal", "wt.exe", desktop_number=1)
    w3 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=2)
    assert filter_windows([w1, w2, w3], "#1 note") == [w1]


def test_desktop_prefix_no_match_returns_empty():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    assert filter_windows([w1], "#99") == []


def test_desktop_prefix_unknown_desktop_excluded():
    # Windows with desktop_number=0 (unknown) are NOT shown when a #N filter is active
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=0)
    assert filter_windows([w1], "#1") == []


def test_no_desktop_prefix_unchanged():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=2)
    assert filter_windows([w1], "note") == [w1]


def test_hash_alone_returns_all():
    """'#' with no digit is ignored — returns all windows like an empty query."""
    w1 = _make_window("#tag", "app.exe")
    w2 = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w1, w2], "#") == [w1, w2]


def test_hash_followed_by_non_digit_is_text_filter():
    """'#abc' contains no desktop number — filtered as plain text."""
    w1 = _make_window("#abc window", "app.exe")
    w2 = _make_window("Notepad", "notepad.exe")
    assert filter_windows([w1, w2], "#abc") == [w1]


def test_desktop_prefix_multi_digit():
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=10)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=1)
    assert filter_windows([w1, w2], "#10") == [w1]


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


def test_desktop_prefix_trailing_space_no_text():
    """'#3 ' (trailing space, no extra text) should filter to desktop 3 only."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=3)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    assert filter_windows([w1, w2], "#3 ") == [w1]


# ---------------------------------------------------------------------------
# Whitespace and multi-space token edge cases
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


def test_desktop_prefix_zero_is_text_filter():
    """'#0' contains a digit so it IS treated as a desktop prefix for desktop 0."""
    w1 = _make_desktop_window("Unknown", "app.exe", desktop_number=0)
    w2 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    assert filter_windows([w1, w2], "#0") == [w1]


# ---------------------------------------------------------------------------
# Multi-desktop prefix (#N#M) tests
# ---------------------------------------------------------------------------


def test_multi_desktop_prefix_or_semantics():
    """'#1#2' shows windows from desktop 1 OR desktop 2."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    w3 = _make_desktop_window("Terminal", "wt.exe", desktop_number=3)
    assert filter_windows([w1, w2, w3], "#1#2") == [w1, w2]


def test_multi_desktop_prefix_with_text():
    """'#1#2note' filters to desktop 1 or 2, then text-filters for 'note'."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    w3 = _make_desktop_window("Firefox", "firefox.exe", desktop_number=1)
    assert filter_windows([w1, w2, w3], "#1#2note") == [w1]


def test_multi_desktop_prefix_three():
    """Three desktop prefixes work with OR logic."""
    w1 = _make_desktop_window("A", "a.exe", desktop_number=1)
    w2 = _make_desktop_window("B", "b.exe", desktop_number=2)
    w3 = _make_desktop_window("C", "c.exe", desktop_number=3)
    w4 = _make_desktop_window("D", "d.exe", desktop_number=4)
    assert filter_windows([w1, w2, w3, w4], "#1#2#3") == [w1, w2, w3]


# ---------------------------------------------------------------------------
# Prefix parsing boundary cases
# ---------------------------------------------------------------------------


def test_space_breaks_multi_desktop_prefix_chain():
    """'#1 #2' is NOT the same as '#1#2': the space stops prefix parsing, so '#2'
    becomes a text filter (no window title contains '#2')."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    # Desktop-1 filter active, then text '#2' → nothing in title/proc matches '#2'
    assert filter_windows([w1, w2], "#1 #2") == []


def test_trailing_hash_after_desktop_prefix_is_ignored():
    """'#1#' — after parsing #1 the rest is '#', stripped to '' or '#'.
    The bare '#' sentinel means no text filter, so only the desktop filter applies."""
    w1 = _make_desktop_window("Notepad", "notepad.exe", desktop_number=1)
    w2 = _make_desktop_window("Chrome", "chrome.exe", desktop_number=2)
    assert filter_windows([w1, w2], "#1#") == [w1]


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
# parse_query direct unit tests
# ---------------------------------------------------------------------------


def test_parse_query_empty_string():
    assert parse_query("") == (set(), "")


def test_parse_query_bare_hash():
    """A lone '#' is normalised to an empty query with no desktop filter."""
    assert parse_query("#") == (set(), "")


def test_parse_query_single_prefix():
    nums, text = parse_query("#3")
    assert nums == {3}
    assert text == ""


def test_parse_query_prefix_with_text():
    nums, text = parse_query("#3 chrome")
    assert nums == {3}
    assert text == "chrome"


def test_parse_query_multi_prefix():
    nums, text = parse_query("#1#2")
    assert nums == {1, 2}
    assert text == ""


def test_parse_query_multi_prefix_with_text():
    nums, text = parse_query("#1#2 chrome")
    assert nums == {1, 2}
    assert text == "chrome"


def test_parse_query_multi_digit_prefix():
    nums, text = parse_query("#10")
    assert nums == {10}
    assert text == ""


def test_parse_query_prefix_then_bare_hash():
    """'#1#' — trailing '#' has no digit, normalised to empty text."""
    nums, text = parse_query("#1#")
    assert nums == {1}
    assert text == ""


def test_parse_query_three_prefixes():
    nums, text = parse_query("#1#2#3")
    assert nums == {1, 2, 3}
    assert text == ""


def test_parse_query_plain_text_returns_empty_set():
    nums, text = parse_query("chrome")
    assert nums == set()
    assert text == "chrome"


def test_parse_query_hash_non_digit_is_plain_text():
    """'#abc' contains no digit after '#' — returned as-is in the text portion."""
    nums, text = parse_query("#abc")
    assert nums == set()
    assert text == "#abc"


def test_parse_query_whitespace_only_normalised_to_empty():
    """Whitespace-only queries strip to '' and are normalised to empty text."""
    nums, text = parse_query("   ")
    assert nums == set()
    assert text == ""


def test_parse_query_trailing_space_after_prefix_normalised():
    """'#3 ' — trailing space after stripping is empty, so text is normalised to ''."""
    nums, text = parse_query("#3 ")
    assert nums == {3}
    assert text == ""


def test_parse_query_prefix_zero():
    """Desktop 0 is a valid number — parse_query treats it like any other digit."""
    nums, text = parse_query("#0")
    assert nums == {0}
    assert text == ""
