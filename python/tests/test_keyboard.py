"""Tests for OverlayController — keyboard routing and filter state."""

from windows_navigator.controller import OverlayController
from windows_navigator.models import TabInfo, WindowInfo


def _windows(*titles: str) -> list[WindowInfo]:
    return [
        WindowInfo(hwnd=i + 1, title=t, process_name=f"app{i}.exe") for i, t in enumerate(titles)
    ]


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_initial_selection_is_zero():
    ctrl = OverlayController(_windows("A", "B", "C"))
    assert ctrl.selection_index == 0


def test_initial_selection_empty_list_is_minus_one():
    assert OverlayController([]).selection_index == -1


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


def test_move_down_increments():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.move_down()
    assert ctrl.selection_index == 1


def test_move_up_decrements():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.selection_index = 2
    ctrl.move_up()
    assert ctrl.selection_index == 1


def test_move_up_wraps_to_last():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.move_up()
    assert ctrl.selection_index == 1


def test_move_down_wraps_to_first():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.move_down()
    ctrl.move_down()
    assert ctrl.selection_index == 0


def test_navigation_on_empty_list_is_safe():
    ctrl = OverlayController([])
    ctrl.move_up()
    ctrl.move_down()
    assert ctrl.selection_index == -1


def test_page_down_jumps_by_page_size():
    ctrl = OverlayController(_windows(*"ABCDEFGHIJ"))  # 10 items
    ctrl.move_page_down(5)
    assert ctrl.selection_index == 5


def test_page_down_clamped_at_last():
    ctrl = OverlayController(_windows(*"ABCDE"))
    ctrl.selection_index = 3
    ctrl.move_page_down(10)
    assert ctrl.selection_index == 4


def test_page_up_jumps_by_page_size():
    ctrl = OverlayController(_windows(*"ABCDEFGHIJ"))
    ctrl.selection_index = 7
    ctrl.move_page_up(5)
    assert ctrl.selection_index == 2


def test_page_up_clamped_at_zero():
    ctrl = OverlayController(_windows(*"ABCDE"))
    ctrl.selection_index = 2
    ctrl.move_page_up(10)
    assert ctrl.selection_index == 0


def test_move_to_last():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.move_to_last()
    assert ctrl.selection_index == 2


def test_move_to_first():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.selection_index = 2
    ctrl.move_to_first()
    assert ctrl.selection_index == 0


def test_page_and_boundary_on_empty_list_is_safe():
    ctrl = OverlayController([])
    ctrl.move_page_up(5)
    ctrl.move_page_down(5)
    ctrl.move_to_first()
    ctrl.move_to_last()
    assert ctrl.selection_index == -1


# ---------------------------------------------------------------------------
# selected_hwnd — Enter behaviour
# ---------------------------------------------------------------------------


def test_selected_hwnd_returns_correct_hwnd():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.selection_index = 2
    assert ctrl.selected_hwnd() == 3  # hwnd = index + 1


def test_selected_hwnd_on_empty_list_is_none():
    assert OverlayController([]).selected_hwnd() is None


def test_selected_hwnd_when_no_match_is_none():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.set_query("zzz")
    assert ctrl.selected_hwnd() is None


# ---------------------------------------------------------------------------
# Filtering / typing
# ---------------------------------------------------------------------------


def test_set_query_filters_results():
    ctrl = OverlayController(_windows("Notepad", "Chrome", "Explorer"))
    ctrl.set_query("note")
    assert len(ctrl.filtered_windows) == 1
    assert ctrl.filtered_windows[0].title == "Notepad"


def test_set_query_resets_selection_to_zero():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.selection_index = 2
    ctrl.set_query("A")
    assert ctrl.selection_index == 0


def test_set_query_no_match_gives_minus_one():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.set_query("zzz")
    assert ctrl.selection_index == -1


def test_set_query_empty_restores_all():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.set_query("A")
    ctrl.set_query("")
    assert len(ctrl.filtered_windows) == 3


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


def test_reset_clears_query_and_selection():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.set_query("A")
    ctrl.reset(_windows("X", "Y", "Z"))
    assert ctrl.query == ""
    assert len(ctrl.filtered_windows) == 3
    assert ctrl.selection_index == 0


def test_reset_to_empty_list():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.reset([])
    assert ctrl.selection_index == -1
    assert ctrl.selected_hwnd() is None


# ---------------------------------------------------------------------------
# all_windows invariants
# ---------------------------------------------------------------------------


def test_set_query_does_not_mutate_all_windows():
    ctrl = OverlayController(_windows("A", "B", "C"))
    ctrl.set_query("A")
    assert len(ctrl.all_windows) == 3


def test_reset_replaces_all_windows():
    ctrl = OverlayController(_windows("A", "B"))
    ctrl.reset(_windows("X", "Y", "Z"))
    assert len(ctrl.all_windows) == 3
    assert ctrl.all_windows[0].title == "X"


def test_set_query_then_clear_restores_from_all_windows():
    ctrl = OverlayController(_windows("Alpha", "Beta", "Gamma"))
    ctrl.set_query("alpha")
    assert len(ctrl.filtered_windows) == 1
    ctrl.set_query("")
    assert len(ctrl.filtered_windows) == 3


# ---------------------------------------------------------------------------
# Desktop badge filter in controller
# ---------------------------------------------------------------------------


def _desktop_windows() -> list[WindowInfo]:
    return [
        WindowInfo(hwnd=1, title="Notepad", process_name="notepad.exe", desktop_number=1),
        WindowInfo(hwnd=2, title="Chrome", process_name="chrome.exe", desktop_number=2),
        WindowInfo(hwnd=3, title="Terminal", process_name="wt.exe", desktop_number=1),
    ]


def test_controller_desktop_badge_filters_correctly():
    ctrl = OverlayController(_desktop_windows())
    ctrl.set_desktop_nums({1})
    assert len(ctrl.filtered_windows) == 2
    assert all(w.desktop_number == 1 for w in ctrl.filtered_windows)


def test_controller_desktop_badge_with_text():
    ctrl = OverlayController(_desktop_windows())
    ctrl.set_desktop_nums({1})
    ctrl.set_query("note")
    assert len(ctrl.filtered_windows) == 1
    assert ctrl.filtered_windows[0].title == "Notepad"


def test_controller_switching_desktop_badge():
    ctrl = OverlayController(_desktop_windows())
    ctrl.set_desktop_nums({1})
    assert len(ctrl.filtered_windows) == 2
    ctrl.set_desktop_nums({2})
    assert len(ctrl.filtered_windows) == 1
    assert ctrl.filtered_windows[0].hwnd == 2


def test_controller_multi_desktop_badge_or_semantics():
    ctrl = OverlayController(_desktop_windows())
    ctrl.set_desktop_nums({1, 2})
    assert len(ctrl.filtered_windows) == 3


def test_controller_clear_desktop_badge_shows_all():
    ctrl = OverlayController(_desktop_windows())
    ctrl.set_desktop_nums({1})
    assert len(ctrl.filtered_windows) == 2
    ctrl.set_desktop_nums(set())
    assert len(ctrl.filtered_windows) == 3


def test_controller_hash_in_query_is_plain_text():
    """'#1' in the query string is literal text, not a desktop filter."""
    ctrl = OverlayController(_desktop_windows())
    ctrl.set_query("#1")
    # '#1' matches no window title or process name → empty list
    assert len(ctrl.filtered_windows) == 0


def test_controller_hash_text_matches_title():
    """A window whose title contains '#1' is found when querying '#1'."""
    w = WindowInfo(hwnd=99, title="#1 priority", process_name="app.exe")
    ctrl = OverlayController([w])
    ctrl.set_query("#1")
    assert ctrl.filtered_windows == [w]


# ---------------------------------------------------------------------------
# set_desktop_nums with active app filter
# ---------------------------------------------------------------------------


def test_set_desktop_nums_clears_app_filter_when_process_no_longer_visible():
    """App filter is auto-cleared when the new desktop badge hides all windows for that process."""
    windows = [
        WindowInfo(hwnd=1, title="Notepad", process_name="notepad.exe", desktop_number=1),
        WindowInfo(hwnd=2, title="Chrome", process_name="chrome.exe", desktop_number=2),
    ]
    ctrl = OverlayController(windows)
    ctrl.cycle_app_filter(1)  # select notepad
    assert ctrl._app_filter == "notepad.exe"
    ctrl.set_desktop_nums({2})  # notepad (desktop 1) is now hidden
    assert ctrl._app_filter is None


def test_set_desktop_nums_keeps_app_filter_when_process_visible_via_tab():
    """App filter is preserved when the process is still reachable through a matching tab."""
    ctrl = OverlayController([
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe", desktop_number=1),
    ])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox", "GitHub"))
    ctrl._expanded.add(1)
    ctrl.cycle_app_filter(1)    # select chrome.exe (Chrome visible by title, no query yet)
    assert ctrl._app_filter == "chrome.exe"
    ctrl.set_query("inbox")     # title no longer matches; chrome survives via tab match
    assert ctrl._app_filter == "chrome.exe"  # set_query kept it via tab path
    ctrl.set_desktop_nums({1})  # chrome is on desktop 1 — _tab_query_matches still finds it
    assert ctrl._app_filter == "chrome.exe"


# ---------------------------------------------------------------------------
# app_icons — strip source
# ---------------------------------------------------------------------------


def _mixed_windows() -> list[WindowInfo]:
    """Three windows: two notepad, one chrome — in that recency order."""
    return [
        WindowInfo(hwnd=1, title="Notepad 1", process_name="notepad.exe"),
        WindowInfo(hwnd=2, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=3, title="Notepad 2", process_name="notepad.exe"),
    ]


def test_app_icons_deduplicated_by_process_name():
    ctrl = OverlayController(_mixed_windows())
    icons = ctrl.app_icons
    assert len(icons) == 2
    assert icons[0].process_name == "notepad.exe"
    assert icons[1].process_name == "chrome.exe"


def test_app_icons_first_occurrence_chosen():
    ctrl = OverlayController(_mixed_windows())
    icons = ctrl.app_icons
    assert icons[0].hwnd == 1  # first notepad, not the second


def test_app_icons_respects_text_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.set_query("notepad")
    icons = ctrl.app_icons
    assert len(icons) == 1
    assert icons[0].process_name == "notepad.exe"


def test_app_icons_empty_when_no_text_match():
    ctrl = OverlayController(_mixed_windows())
    ctrl.set_query("zzz")
    assert ctrl.app_icons == []


# ---------------------------------------------------------------------------
# text_filtered_windows vs filtered_windows
# ---------------------------------------------------------------------------


def test_text_filtered_windows_ignores_app_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # select notepad
    assert len(ctrl.text_filtered_windows) == 3
    assert len(ctrl.filtered_windows) == 2  # only notepad windows


def test_filtered_windows_ands_app_and_text_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.set_query("notepad 1")
    ctrl.cycle_app_filter(1)  # select notepad
    fw = ctrl.filtered_windows
    assert len(fw) == 1
    assert fw[0].hwnd == 1


# ---------------------------------------------------------------------------
# cycle_app_filter
# ---------------------------------------------------------------------------


def test_cycle_app_filter_forward_starts_at_zero():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)
    assert ctrl.app_filter_index == 0
    assert ctrl._app_filter == "notepad.exe"


def test_cycle_app_filter_backward_starts_at_last():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(-1)
    assert ctrl.app_filter_index == 1
    assert ctrl._app_filter == "chrome.exe"


def test_cycle_app_filter_wraps_forward():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad
    ctrl.cycle_app_filter(1)  # chrome
    ctrl.cycle_app_filter(1)  # wraps → notepad
    assert ctrl._app_filter == "notepad.exe"


def test_cycle_app_filter_wraps_backward():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad
    ctrl.cycle_app_filter(-1)  # wraps → chrome
    assert ctrl._app_filter == "chrome.exe"


def test_cycle_app_filter_resets_selection():
    ctrl = OverlayController(_mixed_windows())
    ctrl.selection_index = 2
    ctrl.cycle_app_filter(1)
    assert ctrl.selection_index == 0


def test_cycle_app_filter_noop_on_empty():
    ctrl = OverlayController([])
    ctrl.cycle_app_filter(1)
    assert ctrl._app_filter is None


# ---------------------------------------------------------------------------
# clear_app_filter
# ---------------------------------------------------------------------------


def test_clear_app_filter_removes_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)
    ctrl.clear_app_filter()
    assert ctrl._app_filter is None
    assert ctrl.app_filter_index is None


def test_clear_app_filter_restores_all_windows():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)
    ctrl.clear_app_filter()
    assert len(ctrl.filtered_windows) == 3


# ---------------------------------------------------------------------------
# auto-clear app filter when query makes it disappear
# ---------------------------------------------------------------------------


def test_set_query_clears_app_filter_when_app_leaves_strip():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # select notepad
    assert ctrl._app_filter == "notepad.exe"
    ctrl.set_query("chrome")  # notepad disappears from text_filtered_windows
    assert ctrl._app_filter is None


def test_set_query_keeps_app_filter_when_app_still_present():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # select notepad
    ctrl.set_query("notepad")  # notepad still present
    assert ctrl._app_filter == "notepad.exe"


# ---------------------------------------------------------------------------
# reset clears app filter
# ---------------------------------------------------------------------------


def test_reset_clears_app_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)
    ctrl.reset(_windows("X", "Y"))
    assert ctrl._app_filter is None
    assert len(ctrl.filtered_windows) == 2


# ---------------------------------------------------------------------------
# app_filter_index edge case — filter set but app gone from icons
# ---------------------------------------------------------------------------


def test_app_filter_index_none_when_filter_app_not_in_icons():
    """If _app_filter is set to a process not in the current text_filtered_windows,
    app_filter_index returns None (avoids an IndexError in the strip)."""
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # select notepad
    # Manually set a filter that no window matches, bypassing auto-clear
    ctrl._app_filter = "missing.exe"
    assert ctrl.app_filter_index is None


# ---------------------------------------------------------------------------
# cycle_app_filter with a single app
# ---------------------------------------------------------------------------


def test_cycle_app_filter_single_app_forward_stays_selected():
    """With only one app, cycling forward keeps the same selection."""
    ctrl = OverlayController(_windows("Notepad 1", "Notepad 2"))
    # Both get process_name app0.exe / app1.exe — make them share one name
    from windows_navigator.models import WindowInfo

    ctrl = OverlayController(
        [
            WindowInfo(hwnd=1, title="Notepad 1", process_name="notepad.exe"),
            WindowInfo(hwnd=2, title="Notepad 2", process_name="notepad.exe"),
        ]
    )
    ctrl.cycle_app_filter(1)
    assert ctrl._app_filter == "notepad.exe"
    ctrl.cycle_app_filter(1)  # wraps — only one app
    assert ctrl._app_filter == "notepad.exe"
    assert ctrl.app_filter_index == 0


def test_cycle_app_filter_single_app_backward_stays_selected():
    from windows_navigator.models import WindowInfo

    ctrl = OverlayController(
        [
            WindowInfo(hwnd=1, title="A", process_name="solo.exe"),
            WindowInfo(hwnd=2, title="B", process_name="solo.exe"),
        ]
    )
    ctrl.cycle_app_filter(-1)
    assert ctrl._app_filter == "solo.exe"
    ctrl.cycle_app_filter(-1)
    assert ctrl._app_filter == "solo.exe"


# ---------------------------------------------------------------------------
# Navigation respects filtered_windows (not all_windows)
# ---------------------------------------------------------------------------


def test_move_down_wraps_within_filtered_windows():
    """With an app filter active, move_down wraps from last to first."""
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad only — 2 windows
    ctrl.move_down()  # index 1
    ctrl.move_down()  # wraps to 0
    assert ctrl.selection_index == 0


def test_move_up_and_down_within_filtered_windows():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad — hwnds 1 and 3
    ctrl.move_down()
    assert ctrl.selected_hwnd() == 3  # second notepad window
    ctrl.move_up()
    assert ctrl.selected_hwnd() == 1


# ---------------------------------------------------------------------------
# selected_hwnd stays consistent after filter change
# ---------------------------------------------------------------------------


def test_selected_hwnd_updates_after_query_narrows_list():
    """If the selection index doesn't shrink and the list does, selected_hwnd tracks it."""
    ctrl = OverlayController(_windows("Apple", "Apricot", "Banana"))
    ctrl.move_down()  # index=1 → Apricot
    ctrl.set_query("apple")  # only Apple remains; selection resets to 0
    assert ctrl.selected_hwnd() == ctrl.filtered_windows[0].hwnd


# ---------------------------------------------------------------------------
# move_to_first / move_to_last respect filtered_windows, not all_windows
# ---------------------------------------------------------------------------


def test_move_to_last_respects_app_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad — 2 windows (indices 0 and 1 in filtered list)
    ctrl.move_to_last()
    assert ctrl.selection_index == 1
    assert ctrl.selected_hwnd() == 3  # second notepad hwnd


def test_move_to_first_respects_app_filter():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad
    ctrl.move_to_last()
    ctrl.move_to_first()
    assert ctrl.selection_index == 0
    assert ctrl.selected_hwnd() == 1  # first notepad hwnd


def test_page_down_clamped_to_app_filtered_list():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad — only 2 windows
    ctrl.move_page_down(10)
    assert ctrl.selection_index == 1  # capped at last filtered index


def test_page_up_clamped_to_app_filtered_list():
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad
    ctrl.move_to_last()
    ctrl.move_page_up(10)
    assert ctrl.selection_index == 0


# ---------------------------------------------------------------------------
# cycle_app_filter: filter removed when all its windows leave via text query
# ---------------------------------------------------------------------------


def test_set_query_empty_string_keeps_existing_app_filter():
    """Clearing the query back to '' doesn't auto-clear the app filter,
    because the app is still present in text_filtered_windows (all windows shown)."""
    ctrl = OverlayController(_mixed_windows())
    ctrl.cycle_app_filter(1)  # notepad
    ctrl.set_query("notepad")
    ctrl.set_query("")  # back to all — notepad is still present
    assert ctrl._app_filter == "notepad.exe"


# ---------------------------------------------------------------------------
# selected_hwnd returns correct window after filter shrinks the list
# ---------------------------------------------------------------------------


def test_selected_hwnd_after_app_filter_always_valid():
    """cycle_app_filter resets selection_index, so selected_hwnd is never stale."""
    ctrl = OverlayController(_mixed_windows())
    ctrl.selection_index = 2  # third window (chrome)
    ctrl.cycle_app_filter(1)  # notepad filter — resets to 0
    assert ctrl.selection_index == 0
    assert ctrl.selected_hwnd() == 1  # first notepad hwnd


# ---------------------------------------------------------------------------
# Tab search — only active when _expanded is non-empty
# ---------------------------------------------------------------------------


def _make_tabs(hwnd: int, *names: str) -> list[TabInfo]:
    return [TabInfo(name=n, hwnd=hwnd, index=i) for i, n in enumerate(names)]


def test_tab_search_off_when_collapsed():
    """Tabs are not searched when nothing is expanded."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox", "GitHub"))
    ctrl.set_query("inbox")
    assert ctrl.filtered_windows == []


def test_tab_search_on_when_expanded():
    """With _expanded non-empty, a window appears in results if a tab title matches."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox", "GitHub"))
    ctrl._expanded.add(1)
    ctrl.set_query("inbox")
    assert len(ctrl.filtered_windows) == 1
    assert ctrl.filtered_windows[0].hwnd == 1


def test_tab_match_shows_only_matching_tabs_in_flat_list():
    """flat_list for a tab-matched window shows only the matching tabs."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox", "GitHub", "Gmail - Sent"))
    ctrl._expanded.add(1)
    ctrl.set_query("gmail")
    flat = ctrl.flat_list
    assert len(flat) == 3  # window + 2 matching tabs
    assert isinstance(flat[0], WindowInfo)
    assert {t.name for t in flat[1:]} == {"Gmail - Inbox", "Gmail - Sent"}


def test_title_matched_window_shows_all_tabs():
    """A window matched by title shows all its tabs, not just query-matching ones."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox", "GitHub", "Google"))
    ctrl._expanded.add(1)
    ctrl.set_query("chrome")
    flat = ctrl.flat_list
    assert len(flat) == 4  # window + all 3 tabs


def test_tab_search_multi_token():
    """Multi-token queries require all tokens to match the tab title."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox", "GitHub Pull Requests", "Google"))
    ctrl._expanded.add(1)
    ctrl.set_query("github pull")
    flat = ctrl.flat_list
    assert len(flat) == 2
    assert flat[1].name == "GitHub Pull Requests"


def test_tab_search_respects_desktop_badge():
    """Desktop badge restricts tab search to windows on matching desktops."""
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe", desktop_number=1),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe", desktop_number=2),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox"))
    ctrl.set_tabs(2, _make_tabs(2, "Inbox - Firefox"))
    ctrl._expanded.add(1)
    ctrl._expanded.add(2)
    ctrl.set_desktop_nums({1})
    ctrl.set_query("inbox")
    assert len(ctrl.filtered_windows) == 1
    assert ctrl.filtered_windows[0].hwnd == 1


def test_tab_search_no_match_hides_window():
    """A window with expanded tabs but no matching tab and no title match is hidden."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "GitHub", "Stack Overflow"))
    ctrl._expanded.add(1)
    ctrl.set_query("inbox")
    assert ctrl.filtered_windows == []


def test_set_query_keeps_app_filter_when_app_matches_via_tab():
    """App filter is not auto-cleared when the app still appears via a tab match."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Gmail - Inbox"))
    ctrl._expanded.add(1)
    ctrl.cycle_app_filter(1)  # select chrome
    assert ctrl._app_filter == "chrome.exe"
    ctrl.set_query("inbox")  # matches via tab, not title
    assert ctrl._app_filter == "chrome.exe"


def test_tab_query_matches_ignores_hwnd_absent_from_all_windows():
    """If tabs are stored for an hwnd that is not in all_windows, it is silently skipped."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl._tabs[99] = _make_tabs(99, "Secret Tab")  # phantom hwnd — not in all_windows
    ctrl._expanded.add(99)
    ctrl.set_query("secret")
    assert ctrl.filtered_windows == []
    assert ctrl.flat_list == []


# ---------------------------------------------------------------------------
# set_tabs / tab_count / is_expanded
# ---------------------------------------------------------------------------


def test_tab_count_zero_for_unknown_hwnd():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    assert ctrl.tab_count(1) == 0


def test_set_tabs_stores_count():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B", "Tab C"))
    assert ctrl.tab_count(1) == 3


def test_set_tabs_replaces_existing():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(1, _make_tabs(1, "Only Tab"))
    assert ctrl.tab_count(1) == 1


def test_is_expanded_false_initially():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    assert not ctrl.is_expanded(1)


def test_is_expanded_true_when_in_expanded_set():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl._expanded.add(1)
    assert ctrl.is_expanded(1)


def test_reset_clears_tabs_and_expanded():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl._expanded.add(1)
    ctrl.reset([WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe")])
    assert ctrl.tab_count(1) == 0
    assert not ctrl.is_expanded(1)


# ---------------------------------------------------------------------------
# toggle_expansion
# ---------------------------------------------------------------------------


def test_toggle_expansion_expands_multi_tab_window():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.toggle_expansion(1)
    assert ctrl.is_expanded(1)


def test_toggle_expansion_collapses_when_already_expanded():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.toggle_expansion(1)
    ctrl.toggle_expansion(1)
    assert not ctrl.is_expanded(1)


def test_toggle_expansion_does_not_expand_single_tab():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Only Tab"))
    ctrl.toggle_expansion(1)
    assert not ctrl.is_expanded(1)


def test_toggle_expansion_does_not_expand_no_tabs():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.toggle_expansion(1)
    assert not ctrl.is_expanded(1)


def test_toggle_expansion_flat_list_includes_all_tabs():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B", "Tab C"))
    ctrl.toggle_expansion(1)
    flat = ctrl.flat_list
    assert len(flat) == 4  # 1 window + 3 tabs
    assert isinstance(flat[0], WindowInfo)
    assert all(isinstance(t, TabInfo) for t in flat[1:])


def test_toggle_expansion_collapse_removes_tabs_from_flat_list():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.toggle_expansion(1)
    ctrl.toggle_expansion(1)
    assert len(ctrl.flat_list) == 1


def test_toggle_expansion_sets_selection_to_parent_row():
    """Selection lands on the parent WindowInfo row, not a tab, after toggling."""
    windows = [
        WindowInfo(hwnd=1, title="Firefox", process_name="firefox.exe"),
        WindowInfo(hwnd=2, title="Chrome", process_name="chrome.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(2, _make_tabs(2, "Tab A", "Tab B"))
    ctrl.selection_index = 1  # chrome
    ctrl.toggle_expansion(2)
    # flat_list is now [firefox, chrome, Tab A, Tab B]; chrome is at index 1
    assert ctrl.selection_index == 1
    assert isinstance(ctrl.flat_list[ctrl.selection_index], WindowInfo)
    assert ctrl.flat_list[ctrl.selection_index].hwnd == 2


def test_toggle_expansion_collapse_resets_selection_to_parent():
    """Collapsing also leaves selection on the parent window row."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.toggle_expansion(1)
    ctrl.selection_index = 2  # a tab row
    ctrl.toggle_expansion(1)  # collapse
    assert ctrl.selection_index == 0
    assert isinstance(ctrl.flat_list[0], WindowInfo)


# ---------------------------------------------------------------------------
# toggle_all_expansions
# ---------------------------------------------------------------------------


def test_toggle_all_expansions_expands_all_multi_tab_windows():
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(2, _make_tabs(2, "Tab C", "Tab D"))
    ctrl.toggle_all_expansions()
    assert ctrl.is_expanded(1)
    assert ctrl.is_expanded(2)


def test_toggle_all_expansions_collapses_all_when_any_expanded():
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(2, _make_tabs(2, "Tab C", "Tab D"))
    ctrl._expanded.add(1)  # partially expanded
    ctrl.toggle_all_expansions()
    assert not ctrl.is_expanded(1)
    assert not ctrl.is_expanded(2)


def test_toggle_all_expansions_skips_single_tab_windows():
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(2, _make_tabs(2, "Only Tab"))
    ctrl.toggle_all_expansions()
    assert ctrl.is_expanded(1)
    assert not ctrl.is_expanded(2)


def test_toggle_all_expansions_skips_windows_with_no_tabs():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.toggle_all_expansions()
    assert not ctrl.is_expanded(1)


def test_toggle_all_expansions_respects_active_filter():
    """Only visible (filtered) windows are considered for expand/collapse."""
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(2, _make_tabs(2, "Tab C", "Tab D"))
    ctrl.set_query("chrome")  # only chrome is visible
    ctrl.toggle_all_expansions()
    assert ctrl.is_expanded(1)
    assert not ctrl.is_expanded(2)  # not visible — not touched


def test_toggle_all_expansions_collapse_clears_all_expanded():
    """Collapsing clears all expanded windows, including hidden ones."""
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(2, _make_tabs(2, "Tab C", "Tab D"))
    ctrl._expanded.add(1)
    ctrl._expanded.add(2)
    ctrl.set_query("chrome")  # only chrome visible
    ctrl.toggle_all_expansions()  # collapse — should clear all, not just visible
    assert not ctrl.is_expanded(1)
    assert not ctrl.is_expanded(2)  # hidden, but still cleared


def test_toggle_all_expansions_no_residual_after_filter_expand_unfilter_collapse():
    """Expand while filtered, remove filter, collapse — no windows remain expanded."""
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl.set_tabs(2, _make_tabs(2, "Tab C", "Tab D"))
    ctrl.set_query("chrome")
    ctrl.toggle_all_expansions()  # expand only Chrome (visible)
    assert ctrl.is_expanded(1)
    assert not ctrl.is_expanded(2)
    ctrl.set_query("")  # remove filter — Firefox still not expanded
    ctrl.toggle_all_expansions()  # Chrome is expanded → collapse all
    assert not ctrl.is_expanded(1)
    assert not ctrl.is_expanded(2)


def test_toggle_all_expansions_no_flag_corruption_for_single_tab_filter():
    """Toggling when filtered to a single-tab window must not corrupt _want_all_expanded."""
    windows = [
        WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe"),
        WindowInfo(hwnd=2, title="Notepad", process_name="notepad.exe"),
    ]
    ctrl = OverlayController(windows)
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))  # 2 tabs
    ctrl.set_tabs(2, _make_tabs(2, "Tab A"))  # 1 tab — not expandable
    ctrl._want_all_expanded = True  # simulate prior expand-all intent
    ctrl.set_query("notepad")  # filter to single-tab window only
    ctrl.toggle_all_expansions()  # nothing to expand — flag must stay unchanged
    assert ctrl._want_all_expanded  # still True — not corrupted
    ctrl.toggle_all_expansions()  # second press — still nothing to expand
    assert ctrl._want_all_expanded  # flag unchanged again


def test_toggle_all_expansions_deferred_expands_when_tabs_arrive():
    """Pressing Ctrl+Tab before tabs are fetched auto-expands each window as tabs arrive."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.toggle_all_expansions()  # no tabs yet — sets _want_all_expanded
    assert not ctrl.is_expanded(1)  # nothing to expand yet
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    assert ctrl.is_expanded(1)  # auto-expanded on arrival


def test_toggle_all_expansions_deferred_skips_single_tab():
    """Deferred expansion still ignores windows with only one tab."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.toggle_all_expansions()
    ctrl.set_tabs(1, _make_tabs(1, "Only Tab"))
    assert not ctrl.is_expanded(1)


def test_toggle_all_expansions_deferred_cancel_prevents_auto_expand():
    """Pressing Ctrl+Tab twice while tabs are empty cancels the deferred intent."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.toggle_all_expansions()  # set flag
    ctrl.toggle_all_expansions()  # clear flag
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    assert not ctrl.is_expanded(1)


def test_toggle_all_expansions_collapse_clears_want_all_expanded():
    """Collapsing real expanded tabs resets _want_all_expanded to False."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl._want_all_expanded = True
    ctrl._expanded.add(1)
    ctrl.toggle_all_expansions()
    assert not ctrl.is_expanded(1)
    assert ctrl._want_all_expanded is False


def test_toggle_all_expansions_collapse_clamps_selection_when_on_tab_row():
    """Collapsing while the cursor sits on a tab row clamps selection_index (regression guard)."""
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B", "Tab C"))
    ctrl.toggle_all_expansions()   # expand: flat_list = [window, tab0, tab1, tab2]
    ctrl.selection_index = 3       # cursor on last tab row
    ctrl.toggle_all_expansions()   # collapse: flat_list = [window] — must clamp
    assert ctrl.selection_index == 0


def test_reset_clears_want_all_expanded():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl._want_all_expanded = True
    ctrl.reset([WindowInfo(hwnd=2, title="Firefox", process_name="firefox.exe")])
    assert ctrl._want_all_expanded is False


# ---------------------------------------------------------------------------
# selected_item()
# ---------------------------------------------------------------------------


def test_selected_item_returns_none_for_empty():
    assert OverlayController([]).selected_item() is None


def test_selected_item_returns_window_info():
    ctrl = OverlayController(_windows("A", "B"))
    item = ctrl.selected_item()
    assert isinstance(item, WindowInfo)
    assert item.hwnd == 1


def test_selected_item_returns_tab_info_when_on_tab_row():
    ctrl = OverlayController([WindowInfo(hwnd=1, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(1, _make_tabs(1, "Tab A", "Tab B"))
    ctrl._expanded.add(1)
    ctrl.selection_index = 1  # first tab row
    item = ctrl.selected_item()
    assert isinstance(item, TabInfo)
    assert item.name == "Tab A"


def test_selected_item_out_of_bounds_is_none():
    ctrl = OverlayController(_windows("A"))
    ctrl.selection_index = 99
    assert ctrl.selected_item() is None


def test_selected_item_negative_index_is_none():
    ctrl = OverlayController(_windows("A"))
    ctrl.selection_index = -1
    assert ctrl.selected_item() is None


def test_selected_hwnd_on_tab_row_returns_parent_hwnd():
    ctrl = OverlayController([WindowInfo(hwnd=42, title="Chrome", process_name="chrome.exe")])
    ctrl.set_tabs(42, _make_tabs(42, "Tab A", "Tab B"))
    ctrl._expanded.add(42)
    ctrl.selection_index = 1  # first tab row
    assert ctrl.selected_hwnd() == 42  # TabInfo.hwnd is the parent window


# ---------------------------------------------------------------------------
# Bell filter
# ---------------------------------------------------------------------------


def _notif_windows() -> list[WindowInfo]:
    return [
        WindowInfo(hwnd=1, title="Slack", process_name="slack.exe", has_notification=True),
        WindowInfo(hwnd=2, title="Chrome", process_name="chrome.exe", has_notification=False),
        WindowInfo(hwnd=3, title="Teams", process_name="teams.exe", has_notification=True),
    ]


def test_bell_filter_is_false_initially():
    ctrl = OverlayController(_notif_windows())
    assert ctrl.bell_filter is False


def test_toggle_bell_filter_sets_true():
    ctrl = OverlayController(_notif_windows())
    ctrl.toggle_bell_filter()
    assert ctrl.bell_filter is True


def test_toggle_bell_filter_toggles_back_to_false():
    ctrl = OverlayController(_notif_windows())
    ctrl.toggle_bell_filter()
    ctrl.toggle_bell_filter()
    assert ctrl.bell_filter is False


def test_bell_filter_restricts_to_notification_windows():
    ctrl = OverlayController(_notif_windows())
    ctrl.toggle_bell_filter()
    fw = ctrl.filtered_windows
    assert len(fw) == 2
    assert all(w.has_notification for w in fw)


def test_bell_filter_empty_when_no_notifications():
    ctrl = OverlayController(_windows("A", "B"))  # no has_notification
    ctrl.toggle_bell_filter()
    assert ctrl.filtered_windows == []
    assert ctrl.selection_index == -1


def test_bell_filter_with_text_query():
    ctrl = OverlayController(_notif_windows())
    ctrl.toggle_bell_filter()
    ctrl.set_query("slack")
    fw = ctrl.filtered_windows
    assert len(fw) == 1
    assert fw[0].title == "Slack"


def test_bell_filter_with_app_filter():
    ctrl = OverlayController(_notif_windows())
    ctrl.toggle_bell_filter()
    ctrl.cycle_app_filter(1)  # first in text_filtered_windows → slack.exe
    fw = ctrl.filtered_windows
    assert len(fw) == 1
    assert fw[0].process_name == "slack.exe"
    assert fw[0].has_notification is True


def test_bell_filter_cleared_by_reset():
    ctrl = OverlayController(_notif_windows())
    ctrl.toggle_bell_filter()
    ctrl.reset(_windows("X", "Y"))
    assert ctrl.bell_filter is False
    assert len(ctrl.filtered_windows) == 2


def test_toggle_bell_filter_resets_selection_to_first_match():
    ctrl = OverlayController(_notif_windows())
    ctrl.selection_index = 2
    ctrl.toggle_bell_filter()
    assert ctrl.selection_index == 0
