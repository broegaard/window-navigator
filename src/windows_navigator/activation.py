"""Win32 window activation and focus helpers.

Restores minimized windows, brings targets to the foreground, and locates
the monitor work area under the cursor.
All win32 imports are deferred so this module can be imported on any platform.
"""

from __future__ import annotations


def activate_window(hwnd: int) -> bool:
    """Restore (if minimized) and foreground the window identified by *hwnd*.

    Returns True on success, False if the window no longer exists or activation failed.
    """
    try:
        import win32con
        import win32gui

        if not win32gui.IsWindow(hwnd):
            return False
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _force_foreground(hwnd: int) -> None:
    """Bring *hwnd* to the foreground.

    RegisterHotKey grants the foreground-lock exemption to our process for the
    duration of the hotkey handling window (~200 ms), so a plain SetForegroundWindow
    call is sufficient.  AttachThreadInput is intentionally NOT used: merging the
    previous foreground thread's input queue into ours causes IDC_APPSTARTING to
    bleed into that thread's cursor state after detach, producing a persistent
    spinning cursor in Firefox and Windows Terminal until the mouse moves.
    """
    try:
        import ctypes

        ctypes.windll.user32.SetForegroundWindow(hwnd)  # type: ignore[attr-defined]
    except Exception:
        pass


def _get_cursor_monitor_workarea() -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the work area of the monitor under the cursor."""
    try:
        import ctypes
        import ctypes.wintypes

        pt = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))  # type: ignore[attr-defined]

        MONITOR_DEFAULTTONEAREST = 2
        hmonitor = ctypes.windll.user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)  # type: ignore[attr-defined]

        class _MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", ctypes.wintypes.RECT),
                ("rcWork", ctypes.wintypes.RECT),
                ("dwFlags", ctypes.c_ulong),
            ]

        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))  # type: ignore[attr-defined]
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return 0, 0, 1920, 1080
