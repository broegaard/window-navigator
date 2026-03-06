"""Tests for virtual_desktop fallback behaviour."""

import uuid
from unittest.mock import MagicMock, patch

from windows_navigator.virtual_desktop import (
    _get_registry_desktop_order,
    _guid_to_str,
    _make_guid,
    assign_desktop_numbers,
    get_current_desktop_guid,
    get_current_desktop_number,
    is_on_current_desktop,
    move_window_to_adjacent_desktop,
    move_window_to_current_desktop,
    switch_to_desktop_number,
)

# ---------------------------------------------------------------------------
# is_on_current_desktop
# ---------------------------------------------------------------------------


def test_returns_true_when_manager_is_none():
    """If COM manager cannot be created, include the window (show all)."""
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=None):
        assert is_on_current_desktop(12345) is True


def test_returns_true_on_com_exception():
    """If IsWindowOnCurrentVirtualDesktop raises, include the window."""

    class _BadManager:
        def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
            raise OSError("COM failure")

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_BadManager()):
        assert is_on_current_desktop(12345) is True


def test_returns_false_when_manager_says_false():
    class _OffDesktopManager:
        def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
            return False

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_OffDesktopManager()):
        assert is_on_current_desktop(12345) is False


def test_returns_true_when_manager_says_true():
    class _OnDesktopManager:
        def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
            return True

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_OnDesktopManager()):
        assert is_on_current_desktop(12345) is True


# ---------------------------------------------------------------------------
# assign_desktop_numbers
# ---------------------------------------------------------------------------


def _make_manager(guid_map: dict[int, str], current_hwnds: set[int]) -> object:
    """Build a mock manager with GetWindowDesktopId and IsWindowOnCurrentVirtualDesktop."""

    class _MockManager:
        def GetWindowDesktopId(self, hwnd: int) -> str | None:
            return guid_map.get(hwnd)

        def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
            return hwnd in current_hwnds

    return _MockManager()


def test_assign_numbers_returns_empty_when_manager_none():
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=None):
        nums, cur = assign_desktop_numbers([1, 2, 3])
    assert nums == {}
    assert cur == {}


def test_assign_numbers_same_guid_gets_same_number():
    mgr = _make_manager({1: "guid-A", 2: "guid-A", 3: "guid-B"}, {1, 2})
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr):
        nums, cur = assign_desktop_numbers([1, 2, 3])
    assert nums[1] == nums[2]
    assert nums[3] != nums[1]


def test_assign_numbers_are_one_based():
    mgr = _make_manager({1: "guid-A", 2: "guid-B"}, {1})
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr):
        nums, _ = assign_desktop_numbers([1, 2])
    assert min(nums.values()) == 1


def test_assign_current_desktop_flag():
    mgr = _make_manager({1: "guid-A", 2: "guid-B"}, current_hwnds={1})
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr):
        _, cur = assign_desktop_numbers([1, 2])
    assert cur[1] is True
    assert cur[2] is False


def test_assign_numbers_follow_registry_order():
    """Desktop numbers follow registry order, not z-order of the hwnd list."""
    # guid-B is first in the registry → should be desktop 1 even though guid-A appears first
    mgr = _make_manager({1: "guid-A", 2: "guid-B"}, current_hwnds={2})
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr), \
         patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["guid-B", "guid-A"]):
        nums, _ = assign_desktop_numbers([1, 2])
    assert nums[2] == 1  # guid-B is first in registry
    assert nums[1] == 2  # guid-A is second


def test_assign_numbers_fallback_to_encounter_order_when_no_registry():
    """Without registry data, desktops are numbered in first-encountered order."""
    mgr = _make_manager({1: "guid-B", 2: "guid-A"}, current_hwnds={1})
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr), \
         patch("windows_navigator.virtual_desktop._get_registry_desktop_order", return_value=None):
        nums, _ = assign_desktop_numbers([1, 2])
    assert nums[1] == 1  # guid-B first in hwnd list → desktop 1
    assert nums[2] == 2


def test_assign_numbers_none_guid_gives_desktop_zero():
    """Windows whose desktop GUID cannot be determined get desktop_number=0."""
    mgr = _make_manager({1: "guid-A", 2: None}, current_hwnds={1})
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr), \
         patch("windows_navigator.virtual_desktop._get_registry_desktop_order", return_value=None):
        nums, cur = assign_desktop_numbers([1, 2])
    assert nums[2] == 0
    assert cur[2] is True  # unknown → include window (is_current defaults to True)


def test_assign_numbers_per_window_exception_gives_desktop_zero():
    """A COM exception on a single window yields desktop_number=0 for that window only."""

    class _FlakyManager:
        def GetWindowDesktopId(self, hwnd: int) -> str | None:
            if hwnd == 2:
                raise OSError("COM failure")
            return "guid-A"

        def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
            return True

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_FlakyManager()), \
         patch("windows_navigator.virtual_desktop._get_registry_desktop_order", return_value=None):
        nums, cur = assign_desktop_numbers([1, 2])
    assert nums.get(1, -1) > 0   # hwnd 1 got a valid number
    assert nums[2] == 0
    assert cur[2] is True


# ---------------------------------------------------------------------------
# get_current_desktop_number
# ---------------------------------------------------------------------------


def test_get_current_desktop_number_returns_zero_without_winreg():
    """On Linux (no winreg), the function falls back to 0."""
    # winreg is not in sys.modules on Linux; the try/except catches ImportError → 0
    result = get_current_desktop_number()
    assert result == 0


def test_get_current_desktop_number_from_mocked_registry():
    g1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    g2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    g3 = uuid.UUID("33333333-3333-3333-3333-333333333333")

    # Currently on g2 → expected desktop number 2 (second in the ordered list)
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.side_effect = [
        (g2.bytes_le, None),                               # CurrentVirtualDesktop
        (g1.bytes_le + g2.bytes_le + g3.bytes_le, None),  # VirtualDesktopIDs
    ]

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = get_current_desktop_number()

    assert result == 2


def test_get_current_desktop_number_first_desktop():
    g1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    g2 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.side_effect = [
        (g1.bytes_le, None),
        (g1.bytes_le + g2.bytes_le, None),
    ]

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = get_current_desktop_number()

    assert result == 1


def test_get_current_desktop_number_guid_not_in_list():
    """Returns 0 if the current GUID is not in the ordered list."""
    g1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    g_unknown = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.side_effect = [
        (g_unknown.bytes_le, None),
        (g1.bytes_le, None),
    ]

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = get_current_desktop_number()

    assert result == 0


# ---------------------------------------------------------------------------
# get_current_desktop_guid
# ---------------------------------------------------------------------------


def test_get_current_desktop_guid_returns_none_without_winreg():
    """On Linux (no winreg), falls back to None."""
    result = get_current_desktop_guid()
    assert result is None


def test_get_current_desktop_guid_from_mocked_registry():
    g1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.return_value = (g1.bytes_le, None)

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = get_current_desktop_guid()

    assert result == str(g1)


def test_get_current_desktop_guid_returns_none_on_short_data():
    """Registry value shorter than 16 bytes → None."""
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.return_value = (b"\x00" * 8, None)

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = get_current_desktop_guid()

    assert result is None


def test_get_current_desktop_guid_returns_none_on_exception():
    mock_winreg = MagicMock()
    mock_winreg.OpenKey.side_effect = OSError("no key")

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = get_current_desktop_guid()

    assert result is None


# ---------------------------------------------------------------------------
# _get_registry_desktop_order
# ---------------------------------------------------------------------------


def test_get_registry_desktop_order_returns_none_without_winreg():
    """On Linux (no winreg), falls back to None."""
    result = _get_registry_desktop_order()
    assert result is None


def test_get_registry_desktop_order_from_mocked_registry():
    g1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    g2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.return_value = (g1.bytes_le + g2.bytes_le, None)

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = _get_registry_desktop_order()

    assert result == [str(g1), str(g2)]


def test_get_registry_desktop_order_returns_none_on_misaligned_data():
    """Data whose length is not a multiple of 16 is treated as corrupt → None."""
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.return_value = (b"\x00" * 17, None)

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = _get_registry_desktop_order()

    assert result is None


def test_get_registry_desktop_order_returns_none_on_empty_data():
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.return_value = (b"", None)

    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        result = _get_registry_desktop_order()

    assert result is None


# ---------------------------------------------------------------------------
# move_window_to_current_desktop
# ---------------------------------------------------------------------------


def test_move_window_returns_false_when_manager_none():
    """pyvda unavailable and no COM manager → False."""
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=None):
        assert move_window_to_current_desktop(12345) is False


def test_move_window_returns_false_when_guid_unavailable():
    """Manager exists but current desktop GUID cannot be read → False."""

    class _MockManager:
        def MoveWindowToDesktop(self, hwnd: int, guid: str) -> bool:
            return True

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_MockManager()), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_guid", return_value=None):
        assert move_window_to_current_desktop(12345) is False


def test_move_window_calls_manager_move_to_desktop():
    """Falls back to manager.MoveWindowToDesktop when pyvda is absent."""
    moved: list[tuple[int, str]] = []
    target_guid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    class _MockManager:
        def MoveWindowToDesktop(self, hwnd: int, guid: str) -> bool:
            moved.append((hwnd, guid))
            return True

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_MockManager()), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_guid",
               return_value=target_guid):
        result = move_window_to_current_desktop(99)

    assert result is True
    assert moved == [(99, target_guid)]


def test_move_window_returns_false_when_manager_lacks_method():
    """Manager without MoveWindowToDesktop attribute → False."""

    class _NoMoveManager:
        def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
            return True

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_NoMoveManager()):
        assert move_window_to_current_desktop(12345) is False


def test_move_window_pyvda_path_succeeds():
    """When pyvda is importable and succeeds, returns True without touching the manager."""
    mock_pyvda = MagicMock()
    with patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        result = move_window_to_current_desktop(42)
    assert result is True
    mock_pyvda.AppView.assert_called_once_with(42)


def test_move_window_manager_raises_returns_false():
    """If MoveWindowToDesktop raises an exception, returns False."""
    target_guid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    class _FlakyManager:
        def MoveWindowToDesktop(self, hwnd: int, guid: str) -> bool:
            raise OSError("COM failure")

    with patch("windows_navigator.virtual_desktop._get_manager", return_value=_FlakyManager()), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_guid",
               return_value=target_guid):
        assert move_window_to_current_desktop(99) is False


# ---------------------------------------------------------------------------
# get_current_desktop_number: data validation paths
# ---------------------------------------------------------------------------


def test_get_current_desktop_number_short_current_data():
    """current_data shorter than 16 bytes → 0."""
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.side_effect = [
        (b"\x00" * 8, None),   # CurrentVirtualDesktop — too short
        (b"\x00" * 16, None),  # VirtualDesktopIDs
    ]
    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        assert get_current_desktop_number() == 0


def test_get_current_desktop_number_misaligned_all_data():
    """all_data length not a multiple of 16 → 0."""
    g1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
    mock_winreg = MagicMock()
    mock_winreg.QueryValueEx.side_effect = [
        (g1.bytes_le, None),       # CurrentVirtualDesktop — valid 16 bytes
        (g1.bytes_le + b"\x00",    # VirtualDesktopIDs — 17 bytes, misaligned
         None),
    ]
    with patch.dict("sys.modules", {"winreg": mock_winreg}):
        assert get_current_desktop_number() == 0


# ---------------------------------------------------------------------------
# assign_desktop_numbers: guid not in registry gets appended number
# ---------------------------------------------------------------------------


def test_assign_numbers_new_guid_beyond_registry_gets_appended():
    """A window whose GUID doesn't appear in the registry list gets a number
    appended beyond the registry-ordered range."""
    guid_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    guid_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    guid_c = "cccccccc-cccc-cccc-cccc-cccccccccccc"  # not in registry

    mgr = _make_manager({1: guid_a, 2: guid_b, 3: guid_c}, current_hwnds={1})
    # Registry has only guid_a and guid_b → guid_c gets number 3 (appended)
    with patch("windows_navigator.virtual_desktop._get_manager", return_value=mgr), \
         patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=[guid_a, guid_b]):
        nums, _ = assign_desktop_numbers([1, 2, 3])
    assert nums[1] == 1   # guid_a → desktop 1
    assert nums[2] == 2   # guid_b → desktop 2
    assert nums[3] == 3   # guid_c → appended as desktop 3


# ---------------------------------------------------------------------------
# _make_guid / _guid_to_str roundtrip
# ---------------------------------------------------------------------------


def test_guid_roundtrip_preserves_value():
    """_make_guid and _guid_to_str must be inverse operations."""
    original = "aa509086-5ca9-4c25-8f95-589d3c07b48a"
    g = _make_guid("{" + original + "}")
    assert _guid_to_str(g) == original


def test_guid_roundtrip_multiple_guids():
    guids = [
        "11111111-1111-1111-1111-111111111111",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        "00000000-0000-0000-0000-000000000000",
    ]
    for s in guids:
        assert _guid_to_str(_make_guid("{" + s + "}")) == s


def test_guid_roundtrip_matches_uuid_module():
    s = "{6ba7b810-9dad-11d1-80b4-00c04fd430c8}"
    assert _guid_to_str(_make_guid(s)) == str(uuid.UUID(s))


# ---------------------------------------------------------------------------
# switch_to_desktop_number
# ---------------------------------------------------------------------------


def test_switch_to_desktop_number_success():
    mock_pyvda = MagicMock()
    with patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        result = switch_to_desktop_number(3)
    assert result is True
    mock_pyvda.VirtualDesktop.assert_called_once_with(3)
    mock_pyvda.VirtualDesktop.return_value.go.assert_called_once()


def test_switch_to_desktop_number_exception_returns_false():
    mock_pyvda = MagicMock()
    mock_pyvda.VirtualDesktop.return_value.go.side_effect = OSError("pyvda error")
    with patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        result = switch_to_desktop_number(2)
    assert result is False


def test_switch_to_desktop_number_no_pyvda_returns_false():
    """Without pyvda available, switch_to_desktop_number returns False."""
    import sys

    original = sys.modules.pop("pyvda", None)
    try:
        result = switch_to_desktop_number(1)
    finally:
        if original is not None:
            sys.modules["pyvda"] = original
    assert result is False


# ---------------------------------------------------------------------------
# move_window_to_adjacent_desktop
# ---------------------------------------------------------------------------


def test_move_to_adjacent_left_boundary_returns_zero():
    """At the leftmost desktop, moving left is a no-op."""
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2", "g3"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=1):
        result = move_window_to_adjacent_desktop(99, -1)
    assert result == 0


def test_move_to_adjacent_right_boundary_returns_zero():
    """At the rightmost desktop, moving right is a no-op."""
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2", "g3"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=3):
        result = move_window_to_adjacent_desktop(99, +1)
    assert result == 0


def test_move_to_adjacent_right_returns_target():
    mock_pyvda = MagicMock()
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2", "g3"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=1), \
         patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        result = move_window_to_adjacent_desktop(99, +1)
    assert result == 2


def test_move_to_adjacent_left_returns_target():
    mock_pyvda = MagicMock()
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2", "g3"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=3), \
         patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        result = move_window_to_adjacent_desktop(99, -1)
    assert result == 2


def test_move_to_adjacent_calls_appview_with_hwnd():
    mock_pyvda = MagicMock()
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=1), \
         patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        move_window_to_adjacent_desktop(777, +1)
    mock_pyvda.AppView.assert_called_once_with(777)


def test_move_to_adjacent_no_registry_data_returns_zero():
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=None):
        result = move_window_to_adjacent_desktop(99, +1)
    assert result == 0


def test_move_to_adjacent_empty_registry_returns_zero():
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=[]):
        result = move_window_to_adjacent_desktop(99, +1)
    assert result == 0


def test_move_to_adjacent_unknown_current_desktop_returns_zero():
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=0):
        result = move_window_to_adjacent_desktop(99, +1)
    assert result == 0


def test_move_to_adjacent_appview_exception_still_returns_target():
    """AppView.move failure is silently ignored; the target desktop is still returned."""
    mock_pyvda = MagicMock()
    mock_pyvda.AppView.return_value.move.side_effect = OSError("move failed")
    with patch("windows_navigator.virtual_desktop._get_registry_desktop_order",
               return_value=["g1", "g2", "g3"]), \
         patch("windows_navigator.virtual_desktop.get_current_desktop_number", return_value=2), \
         patch.dict("sys.modules", {"pyvda": mock_pyvda}):
        result = move_window_to_adjacent_desktop(99, +1)
    assert result == 3
