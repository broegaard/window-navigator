"""Tests for activation.py — activate_window, _force_foreground, _get_cursor_monitor_workarea."""

import ctypes
import sys
from unittest.mock import MagicMock, patch

from windows_navigator.activation import (
    _force_foreground,
    _get_cursor_monitor_workarea,
    activate_window,
)

# ---------------------------------------------------------------------------
# activate_window
# ---------------------------------------------------------------------------


def _make_win32_mocks():
    win32con = MagicMock()
    win32gui = MagicMock()
    return win32con, win32gui


def test_activate_window_returns_false_when_window_does_not_exist():
    win32con, win32gui = _make_win32_mocks()
    win32gui.IsWindow.return_value = False
    with patch.dict(sys.modules, {"win32con": win32con, "win32gui": win32gui}):
        result = activate_window(9999)
    assert result is False
    win32gui.IsWindow.assert_called_once_with(9999)


def test_activate_window_restores_minimized_window():
    win32con, win32gui = _make_win32_mocks()
    win32gui.IsWindow.return_value = True
    win32gui.IsIconic.return_value = True
    with patch.dict(sys.modules, {"win32con": win32con, "win32gui": win32gui}):
        result = activate_window(42)
    assert result is True
    win32gui.ShowWindow.assert_called_once_with(42, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow.assert_called_once_with(42)


def test_activate_window_foregrounds_normal_window_without_restore():
    win32con, win32gui = _make_win32_mocks()
    win32gui.IsWindow.return_value = True
    win32gui.IsIconic.return_value = False
    with patch.dict(sys.modules, {"win32con": win32con, "win32gui": win32gui}):
        result = activate_window(42)
    assert result is True
    win32gui.ShowWindow.assert_not_called()
    win32gui.SetForegroundWindow.assert_called_once_with(42)


def test_activate_window_returns_false_on_win32_exception():
    win32con, win32gui = _make_win32_mocks()
    win32gui.IsWindow.side_effect = OSError("win32 error")
    with patch.dict(sys.modules, {"win32con": win32con, "win32gui": win32gui}):
        result = activate_window(42)
    assert result is False


def test_activate_window_returns_false_when_win32_unavailable():
    # On Linux, win32con/win32gui import fails → except branch → False.
    # Guard against them already being in sys.modules (e.g. Windows CI).
    mods = {k: v for k, v in sys.modules.items() if k not in ("win32con", "win32gui")}
    with patch.dict(sys.modules, mods, clear=True):
        result = activate_window(1)
    assert result is False


# ---------------------------------------------------------------------------
# _force_foreground
# ---------------------------------------------------------------------------


def test_force_foreground_calls_setforegroundwindow():
    mock_u32 = MagicMock()
    mock_windll = MagicMock()
    mock_windll.user32 = mock_u32
    with patch.object(ctypes, "windll", mock_windll, create=True):
        _force_foreground(99)
    mock_u32.SetForegroundWindow.assert_called_once_with(99)


def test_force_foreground_swallows_exceptions():
    mock_u32 = MagicMock()
    mock_u32.SetForegroundWindow.side_effect = OSError("win32 failure")
    mock_windll = MagicMock()
    mock_windll.user32 = mock_u32
    with patch.object(ctypes, "windll", mock_windll, create=True):
        _force_foreground(99)  # must not raise


def test_force_foreground_without_windll_does_not_raise():
    # On Linux, ctypes.windll is absent — the except block must swallow AttributeError.
    if hasattr(ctypes, "windll"):
        return  # skip: running on Windows, windll exists
    _force_foreground(1)  # must not raise


# ---------------------------------------------------------------------------
# _get_cursor_monitor_workarea
# ---------------------------------------------------------------------------


def test_get_cursor_monitor_workarea_fallback_without_windll():
    # On Linux, ctypes.windll is absent → falls back to the hardcoded default.
    if hasattr(ctypes, "windll"):
        return  # skip: running on Windows, windll exists
    result = _get_cursor_monitor_workarea()
    assert result == (0, 0, 1920, 1080)


def test_get_cursor_monitor_workarea_returns_struct_fields_on_success():
    # Mock ctypes.windll so the happy path runs.  The MONITORINFO struct is
    # zero-initialised by ctypes, so rcWork fields default to 0.
    mock_u32 = MagicMock()
    mock_windll = MagicMock()
    mock_windll.user32 = mock_u32
    with patch.object(ctypes, "windll", mock_windll, create=True):
        result = _get_cursor_monitor_workarea()
    # Zero-initialised rcWork → (left=0, top=0, right=0, bottom=0)
    assert result == (0, 0, 0, 0)


def test_get_cursor_monitor_workarea_returns_fallback_on_exception():
    mock_u32 = MagicMock()
    mock_u32.GetCursorPos.side_effect = OSError("access denied")
    mock_windll = MagicMock()
    mock_windll.user32 = mock_u32
    with patch.object(ctypes, "windll", mock_windll, create=True):
        result = _get_cursor_monitor_workarea()
    assert result == (0, 0, 1920, 1080)
