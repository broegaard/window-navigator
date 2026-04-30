"""Tests for WindowInfo and TabInfo dataclasses."""

from windows_navigator.models import TabInfo, WindowInfo

# ---------------------------------------------------------------------------
# WindowInfo
# ---------------------------------------------------------------------------


def test_window_info_required_fields():
    w = WindowInfo(hwnd=1, title="Test", process_name="test.exe")
    assert w.hwnd == 1
    assert w.title == "Test"
    assert w.process_name == "test.exe"


def test_window_info_defaults():
    w = WindowInfo(hwnd=1, title="Test", process_name="test.exe")
    assert w.icon is None
    assert w.desktop_number == 0
    assert w.is_current_desktop is True
    assert w.has_notification is False


def test_window_info_all_optional_fields():
    w = WindowInfo(
        hwnd=42,
        title="Notepad",
        process_name="notepad.exe",
        desktop_number=3,
        is_current_desktop=False,
        has_notification=True,
    )
    assert w.desktop_number == 3
    assert w.is_current_desktop is False
    assert w.has_notification is True


def test_window_info_equality():
    w1 = WindowInfo(hwnd=1, title="A", process_name="a.exe")
    w2 = WindowInfo(hwnd=1, title="A", process_name="a.exe")
    assert w1 == w2


def test_window_info_inequality_by_hwnd():
    w1 = WindowInfo(hwnd=1, title="A", process_name="a.exe")
    w2 = WindowInfo(hwnd=2, title="A", process_name="a.exe")
    assert w1 != w2


def test_window_info_inequality_by_title():
    w1 = WindowInfo(hwnd=1, title="A", process_name="a.exe")
    w2 = WindowInfo(hwnd=1, title="B", process_name="a.exe")
    assert w1 != w2


def test_window_info_desktop_number_zero_is_unknown():
    """desktop_number=0 is the sentinel for 'unknown desktop'."""
    w = WindowInfo(hwnd=1, title="A", process_name="a.exe", desktop_number=0)
    assert w.desktop_number == 0


# ---------------------------------------------------------------------------
# TabInfo
# ---------------------------------------------------------------------------


def test_tab_info_fields():
    t = TabInfo(name="Gmail - Inbox", hwnd=10, index=2)
    assert t.name == "Gmail - Inbox"
    assert t.hwnd == 10
    assert t.index == 2


def test_tab_info_zero_based_index():
    t = TabInfo(name="First Tab", hwnd=1, index=0)
    assert t.index == 0


def test_tab_info_equality():
    t1 = TabInfo(name="Tab A", hwnd=1, index=0)
    t2 = TabInfo(name="Tab A", hwnd=1, index=0)
    assert t1 == t2


def test_tab_info_inequality_by_name():
    t1 = TabInfo(name="Tab A", hwnd=1, index=0)
    t2 = TabInfo(name="Tab B", hwnd=1, index=0)
    assert t1 != t2


def test_tab_info_inequality_by_index():
    t1 = TabInfo(name="Tab A", hwnd=1, index=0)
    t2 = TabInfo(name="Tab A", hwnd=1, index=1)
    assert t1 != t2


def test_tab_info_hwnd_is_parent_window():
    """TabInfo.hwnd refers to the parent window, not a tab-level handle."""
    parent_hwnd = 999
    t = TabInfo(name="Some Tab", hwnd=parent_hwnd, index=5)
    assert t.hwnd == parent_hwnd


def test_tab_info_is_active_defaults_to_false():
    t = TabInfo(name="Tab A", hwnd=1, index=0)
    assert t.is_active is False


def test_tab_info_is_active_can_be_set():
    t = TabInfo(name="Tab A", hwnd=1, index=0, is_active=True)
    assert t.is_active is True


def test_tab_info_inequality_by_is_active():
    t1 = TabInfo(name="Tab A", hwnd=1, index=0, is_active=False)
    t2 = TabInfo(name="Tab A", hwnd=1, index=0, is_active=True)
    assert t1 != t2
