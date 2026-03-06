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


def _force_foreground(hwnd: int, attach_to: int = 0) -> None:
    """Bring *hwnd* to the foreground even when our process lacks foreground rights.

    Windows restricts SetForegroundWindow to the foreground process. The
    AttachThreadInput trick temporarily joins our input queue to the current
    foreground thread's queue, giving us permission to steal focus.

    *attach_to* is the HWND whose thread we attach to. Pass the foreground window
    captured at hotkey time so the correct thread is used even if GetForegroundWindow()
    returns something unexpected 100 ms later (e.g. after alt+tab transitions).
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        fg_hwnd = attach_to if attach_to else user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        our_tid = kernel32.GetCurrentThreadId()

        if fg_tid and fg_tid != our_tid:
            user32.AttachThreadInput(fg_tid, our_tid, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(fg_tid, our_tid, False)
        else:
            user32.SetForegroundWindow(hwnd)
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
