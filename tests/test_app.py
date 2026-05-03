"""Tests for app.py — hotkey dispatch config and queue drain logic."""

from __future__ import annotations

import queue
import sys
from unittest.mock import MagicMock

# app.py imports tkinter at module level; stub it before importing so tests
# run on Linux where tkinter may not be available.
sys.modules.setdefault("tkinter", MagicMock())

import threading  # noqa: E402 — needed for threading.Event in tests
from unittest.mock import ANY, patch  # noqa: E402

from windows_navigator.app import (  # noqa: E402
    _HOTKEY_ID_CTRL_SHIFT_SPACE,
    _HOTKEY_ID_DOUBLE_TAP_CTRL,
    _HOTKEY_ID_DOUBLE_TAP_SHIFT,
    _HOTKEY_ID_SHIFT_DOUBLE_TAP_CTRL,
    _HOTKEY_ID_WIN_ALT_SPACE,
    _hotkey_listener_config,
    _polling_double_tap_listener,
    _process_show_queue,
    _run_registered_hotkey,
    _start_hotkey_listener,
)
from windows_navigator.config import HotkeyChoice  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VK_SPACE = 0x20
_VK_LCONTROL = 0xA2
_VK_RCONTROL = 0xA3
_VK_LSHIFT = 0xA0
_VK_RSHIFT = 0xA1
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000


def _make_window(*, desktop_number: int = 1, is_current: bool = True) -> MagicMock:
    w = MagicMock()
    w.desktop_number = desktop_number
    w.is_current_desktop = is_current
    return w


# ---------------------------------------------------------------------------
# _hotkey_listener_config — pure dispatch logic
# ---------------------------------------------------------------------------


def test_win_alt_space_uses_registered_hotkey():
    target, kwargs = _hotkey_listener_config(HotkeyChoice.WIN_ALT_SPACE)
    assert target is _run_registered_hotkey
    assert kwargs["hotkey_id"] == _HOTKEY_ID_WIN_ALT_SPACE
    assert kwargs["vk"] == _VK_SPACE
    assert kwargs["modifiers"] == _MOD_WIN | _MOD_ALT | _MOD_NOREPEAT


def test_ctrl_shift_space_uses_registered_hotkey():
    target, kwargs = _hotkey_listener_config(HotkeyChoice.CTRL_SHIFT_SPACE)
    assert target is _run_registered_hotkey
    assert kwargs["hotkey_id"] == _HOTKEY_ID_CTRL_SHIFT_SPACE
    assert kwargs["vk"] == _VK_SPACE
    assert kwargs["modifiers"] == _MOD_CONTROL | _MOD_SHIFT | _MOD_NOREPEAT


def test_ctrl_double_tap_shift_uses_polling_listener():
    target, kwargs = _hotkey_listener_config(HotkeyChoice.CTRL_DOUBLE_TAP_SHIFT)
    assert target is _polling_double_tap_listener
    assert kwargs["hotkey_id"] == _HOTKEY_ID_DOUBLE_TAP_SHIFT
    assert kwargs["tap_vk_l"] == _VK_LSHIFT
    assert kwargs["tap_vk_r"] == _VK_RSHIFT
    assert kwargs["guard_vk_l"] == _VK_LCONTROL
    assert kwargs["guard_vk_r"] == _VK_RCONTROL


def test_double_tap_ctrl_uses_polling_listener():
    target, kwargs = _hotkey_listener_config(HotkeyChoice.DOUBLE_TAP_CTRL)
    assert target is _polling_double_tap_listener
    assert kwargs["hotkey_id"] == _HOTKEY_ID_DOUBLE_TAP_CTRL
    assert kwargs["tap_vk_l"] == _VK_LCONTROL
    assert kwargs["tap_vk_r"] == _VK_RCONTROL
    assert "guard_vk_l" not in kwargs


def test_shift_double_tap_ctrl_uses_polling_listener():
    target, kwargs = _hotkey_listener_config(HotkeyChoice.SHIFT_DOUBLE_TAP_CTRL)
    assert target is _polling_double_tap_listener
    assert kwargs["hotkey_id"] == _HOTKEY_ID_SHIFT_DOUBLE_TAP_CTRL
    assert kwargs["tap_vk_l"] == _VK_LCONTROL
    assert kwargs["tap_vk_r"] == _VK_RCONTROL
    assert kwargs["guard_vk_l"] == _VK_LSHIFT
    assert kwargs["guard_vk_r"] == _VK_RSHIFT


def test_all_four_choices_produce_distinct_hotkey_ids():
    ids = {_hotkey_listener_config(c)[1]["hotkey_id"] for c in HotkeyChoice}
    assert len(ids) == len(list(HotkeyChoice))


# ---------------------------------------------------------------------------
# _start_hotkey_listener — spawns a daemon thread
# ---------------------------------------------------------------------------


def test_start_hotkey_listener_starts_daemon_thread():
    """_start_hotkey_listener must spawn exactly one daemon thread."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    stop = threading.Event()

    with patch("windows_navigator.app.threading.Thread") as mock_thread_cls:
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        _start_hotkey_listener(q, HotkeyChoice.DOUBLE_TAP_CTRL, stop)

    mock_thread_cls.assert_called_once()
    call_kwargs = mock_thread_cls.call_args[1]
    assert call_kwargs.get("daemon") is True
    mock_thread.start.assert_called_once()


# ---------------------------------------------------------------------------
# _process_show_queue — core queue drain logic
# ---------------------------------------------------------------------------


def test_empty_queue_is_a_noop():
    """If nothing is queued, overlay.show must not be called."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    provider = MagicMock()
    overlay = MagicMock()
    tray = MagicMock()
    ref = [0]

    _process_show_queue(q, provider, overlay, tray, ref)

    provider.get_windows.assert_not_called()
    overlay.show.assert_not_called()
    tray.update.assert_not_called()


def test_single_item_triggers_overlay_show():
    """One queued item → provider.get_windows() and overlay.show() are each called once."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    windows = [_make_window(desktop_number=2, is_current=True)]
    provider = MagicMock()
    provider.get_windows.return_value = windows
    overlay = MagicMock()
    tray = MagicMock()
    ref = [0]

    _process_show_queue(q, provider, overlay, tray, ref)

    provider.get_windows.assert_called_once()
    overlay.show.assert_called_once_with(
        windows, initial_desktop=2, fetch_ms=ANY, open_start=ANY, queue_lag_ms=ANY
    )
    tray.update.assert_called_once_with(2)
    assert ref[0] == 2


def test_multiple_items_coalesced_into_one_show():
    """Multiple queued items must result in exactly one overlay.show() call."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    for i in range(5):
        q.put((i, 0.0))

    provider = MagicMock()
    provider.get_windows.return_value = [_make_window()]
    overlay = MagicMock()
    tray = MagicMock()
    ref = [0]

    _process_show_queue(q, provider, overlay, tray, ref)

    assert provider.get_windows.call_count == 1
    assert overlay.show.call_count == 1


def test_current_desktop_ref_updated_when_desktop_found():
    """*current_desktop* list is updated to the found desktop number."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    provider = MagicMock()
    provider.get_windows.return_value = [_make_window(desktop_number=3, is_current=True)]
    ref = [1]

    _process_show_queue(q, provider, MagicMock(), MagicMock(), ref)

    assert ref[0] == 3


def test_current_desktop_ref_not_updated_when_no_valid_desktop():
    """If no window has is_current_desktop=True and desktop_number>0, the ref is NOT touched."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    windows = [
        _make_window(desktop_number=0, is_current=True),  # desktop 0 — excluded from tracking
        _make_window(desktop_number=2, is_current=False),  # not current
    ]
    provider = MagicMock()
    provider.get_windows.return_value = windows
    ref = [5]

    _process_show_queue(q, provider, MagicMock(), MagicMock(), ref)

    assert ref[0] == 5  # unchanged


def test_overlay_show_receives_fetch_ms_as_float():
    """fetch_ms is derived from wall-clock time and must be a non-negative float."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    provider = MagicMock()
    provider.get_windows.return_value = [_make_window()]
    overlay = MagicMock()

    _process_show_queue(q, provider, overlay, MagicMock(), [0])

    _, call_kwargs = overlay.show.call_args
    fetch_ms = call_kwargs["fetch_ms"]
    assert isinstance(fetch_ms, float)
    assert fetch_ms >= 0.0


def test_overlay_show_receives_open_start_as_float():
    """open_start is a monotonic timestamp passed for total-load-time measurement."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    provider = MagicMock()
    provider.get_windows.return_value = [_make_window()]
    overlay = MagicMock()

    import time

    before = time.monotonic()
    _process_show_queue(q, provider, overlay, MagicMock(), [0])
    after = time.monotonic()

    _, call_kwargs = overlay.show.call_args
    open_start = call_kwargs["open_start"]
    assert isinstance(open_start, float)
    assert before <= open_start <= after


def test_tray_updated_with_correct_desktop_number():
    """tray.update() is called with the desktop number found in the window list."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    provider = MagicMock()
    provider.get_windows.return_value = [_make_window(desktop_number=4, is_current=True)]
    tray = MagicMock()

    _process_show_queue(q, provider, MagicMock(), tray, [0])

    tray.update.assert_called_once_with(4)


def test_tray_updated_with_zero_when_no_current_desktop():
    """tray.update(0) is still called when no current desktop window is found."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    windows = [_make_window(desktop_number=0, is_current=True)]
    provider = MagicMock()
    provider.get_windows.return_value = windows
    tray = MagicMock()

    _process_show_queue(q, provider, MagicMock(), tray, [0])

    tray.update.assert_called_once_with(0)


def test_progressive_load_splits_current_and_other_desktop():
    """Current-desktop windows are shown first; other-desktop deferred via schedule_extend."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    current = _make_window(desktop_number=1, is_current=True)
    other = _make_window(desktop_number=2, is_current=False)
    provider = MagicMock()
    provider.get_windows.return_value = [current, other]
    overlay = MagicMock()

    _process_show_queue(q, provider, overlay, MagicMock(), [0])

    # show() receives only the current-desktop window
    show_args, show_kwargs = overlay.show.call_args
    assert show_args[0] == [current]
    # other-desktop window deferred via schedule_extend
    overlay.schedule_extend.assert_called_once_with([other])


def test_progressive_load_shows_all_when_no_current_desktop_windows():
    """Falls back to showing all windows when none are on the current desktop."""
    q: queue.Queue[tuple[int, float]] = queue.Queue()
    q.put((1, 0.0))

    windows = [_make_window(desktop_number=2, is_current=False)]
    provider = MagicMock()
    provider.get_windows.return_value = windows
    overlay = MagicMock()

    _process_show_queue(q, provider, overlay, MagicMock(), [0])

    show_args, _ = overlay.show.call_args
    assert show_args[0] == windows
    overlay.schedule_extend.assert_not_called()
