"""Entry point: wires together Tk root, overlay, hotkey listener, and system tray."""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk


def _start_flash_monitor(flashing: set[int]) -> None:
    """Maintain *flashing* — a set of HWNDs that have a visible notification.

    Two signals are combined:
    - HSHELL_FLASH: window called FlashWindowEx (e.g. incoming Teams/Discord DM)
    - HSHELL_REDRAW with unchanged title: taskbar button redrawn without a title
      change, which is the fingerprint of ITaskbarList3::SetOverlayIcon (used by
      Outlook, Edge, etc. for persistent badge icons).

    Entries are removed when the window is activated or destroyed.
    The set is only mutated from this daemon thread; reads from the main thread
    are safe under the GIL (set.add / set.discard / __contains__ are atomic).
    """

    def _run() -> None:
        try:
            import ctypes
            import ctypes.wintypes as wt

            u32 = ctypes.windll.user32  # type: ignore[attr-defined]

            # LRESULT/WPARAM/LPARAM are pointer-wide (64-bit on 64-bit Windows);
            # ctypes.wintypes defines them as c_long (32-bit) which overflows.
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t
            )
            u32.DefWindowProcW.restype = ctypes.c_ssize_t
            u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            _proc = WNDPROC(lambda h, m, w, lp: u32.DefWindowProcW(h, m, w, lp))

            class _WNDCLS(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wt.UINT), ("style", wt.UINT),
                    ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE),
                    ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
                    ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                    ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
                ]

            wc = _WNDCLS()
            wc.cbSize = ctypes.sizeof(_WNDCLS)
            wc.lpfnWndProc = _proc
            wc.lpszClassName = "WinNavFlashMon"
            u32.RegisterClassExW(ctypes.byref(wc))

            # HWND_MESSAGE = (HWND)(LONG_PTR)(-3) — message-only window, no taskbar entry
            hwnd = u32.CreateWindowExW(
                0, "WinNavFlashMon", None, 0, 0, 0, 0, 0,
                ctypes.c_size_t(-3), None, None, None,
            )
            if not hwnd:
                return

            WM_SHELL = u32.RegisterWindowMessageW("SHELLHOOK")
            u32.RegisterShellHookWindow(hwnd)

            HSHELL_DESTROYED = 2
            HSHELL_ACTIVATED = 4
            HSHELL_REDRAW = 6
            HSHELL_FLASH = 0x8006        # HSHELL_REDRAW | HSHELL_HIGHBIT
            HSHELL_RUDEACTIVATED = 0x8004

            def _get_title(h: int) -> str:
                buf = ctypes.create_unicode_buffer(512)
                u32.GetWindowTextW(h, buf, 512)
                return buf.value

            # Seed the title cache from all current visible windows so that
            # pre-existing overlay icons (Outlook badge already shown, etc.)
            # are detected on the first HSHELL_REDRAW that arrives for them.
            _titles: dict[int, str] = {}
            _ENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)

            def _seed(h: int, _: int) -> bool:
                if u32.IsWindowVisible(h):
                    _titles[h] = _get_title(h)
                return True

            u32.EnumWindows(_ENUM(_seed), 0)

            msg = wt.MSG()
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_SHELL:
                    target = int(msg.lParam)
                    if msg.wParam == HSHELL_FLASH:
                        flashing.add(target)
                    elif msg.wParam == HSHELL_REDRAW:
                        current = _get_title(target)
                        prev = _titles.get(target)
                        _titles[target] = current
                        if current != prev:
                            # Title changed: use (N) pattern as the signal.
                            if re.match(r"^\(\d+\)", current):
                                flashing.add(target)
                        elif u32.GetForegroundWindow() != target:
                            # Same title, background window redrawn →
                            # almost certainly an overlay icon change.
                            flashing.add(target)
                    elif msg.wParam in (HSHELL_ACTIVATED, HSHELL_RUDEACTIVATED):
                        flashing.discard(target)
                    elif msg.wParam == HSHELL_DESTROYED:
                        flashing.discard(target)
                        _titles.pop(target, None)
                u32.DispatchMessageW(ctypes.byref(msg))

            u32.DeregisterShellHookWindow(hwnd)
            u32.DestroyWindow(hwnd)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="flash-monitor").start()


def _start_hotkey_listener(show_queue: queue.Queue[int]) -> None:
    """Register Ctrl+Alt+Space via Win32 RegisterHotKey and pump its message loop.

    Unlike a WH_KEYBOARD_LL hook (the keyboard library), WM_HOTKEY exempts the
    receiving process from the foreground-lock timeout, so SetForegroundWindow
    in _grab_focus works reliably even after the user has alt-tabbed away.

    RegisterHotKey(hwnd=NULL) posts WM_HOTKEY to the calling thread's queue.
    """

    def _run() -> None:
        try:
            import ctypes
            import ctypes.wintypes as wt

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]

            MOD_ALT = 0x0001
            MOD_CONTROL = 0x0002
            VK_SPACE = 0x20
            WM_HOTKEY = 0x0312

            if not user32.RegisterHotKey(None, 1, MOD_ALT | MOD_CONTROL, VK_SPACE):
                return

            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    show_queue.put(user32.GetForegroundWindow())
                user32.DispatchMessageW(ctypes.byref(msg))

            user32.UnregisterHotKey(None, 1)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="hotkey-listener").start()


def _start_move_hotkey_listener(move_queue: queue.Queue[tuple[int, int]]) -> None:
    """Register Ctrl+Win+Shift+Left/Right for moving windows to adjacent desktops."""

    def _run() -> None:
        try:
            import ctypes
            import ctypes.wintypes as wt

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]

            MOD_CONTROL = 0x0002
            MOD_SHIFT = 0x0004
            MOD_WIN = 0x0008
            VK_LEFT = 0x25
            VK_RIGHT = 0x27
            WM_HOTKEY = 0x0312
            ID_LEFT = 1
            ID_RIGHT = 2

            ok_left = user32.RegisterHotKey(None, ID_LEFT, MOD_CONTROL | MOD_SHIFT | MOD_WIN, VK_LEFT)
            ok_right = user32.RegisterHotKey(None, ID_RIGHT, MOD_CONTROL | MOD_SHIFT | MOD_WIN, VK_RIGHT)

            msg = wt.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    fg = user32.GetForegroundWindow()
                    if msg.wParam == ID_LEFT:
                        move_queue.put((fg, -1))
                    elif msg.wParam == ID_RIGHT:
                        move_queue.put((fg, +1))
                user32.DispatchMessageW(ctypes.byref(msg))

            if ok_left:
                user32.UnregisterHotKey(None, ID_LEFT)
            if ok_right:
                user32.UnregisterHotKey(None, ID_RIGHT)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="move-hotkey-listener").start()


def main() -> None:
    # Deferred imports keep startup fast and allow module-level imports on non-Windows
    from windows_navigator.activation import activate_window
    from windows_navigator.overlay import NavigatorOverlay
    from windows_navigator.provider import RealWindowProvider
    from windows_navigator.tray import TrayIcon
    from windows_navigator.virtual_desktop import (
        get_current_desktop_number,
        move_window_to_adjacent_desktop,
        move_window_to_current_desktop,
    )

    root = tk.Tk()
    root.withdraw()  # hidden host window — never shown to the user

    def move_and_activate(hwnd: int) -> None:
        move_window_to_current_desktop(hwnd)
        activate_window(hwnd)

    flashing: set[int] = set()
    _start_flash_monitor(flashing)

    provider = RealWindowProvider(flashing=flashing)
    overlay = NavigatorOverlay(root, on_activate=activate_window, on_move=move_and_activate)
    show_queue: queue.Queue[int] = queue.Queue()
    move_queue: queue.Queue[tuple[int, int]] = queue.Queue()

    _start_hotkey_listener(show_queue)
    _start_move_hotkey_listener(move_queue)

    def poll_queue() -> None:
        try:
            while True:
                fg_hwnd = show_queue.get_nowait()
                windows = provider.get_windows()
                current_desktop = next(
                    (
                        w.desktop_number
                        for w in windows
                        if w.is_current_desktop and w.desktop_number > 0
                    ),
                    0,
                )
                initial_query = f"#{current_desktop}" if current_desktop > 0 else ""
                overlay.show(windows, initial_query=initial_query, fg_hwnd=fg_hwnd)
                tray.update(current_desktop)
                if current_desktop > 0:
                    _current_desktop[0] = current_desktop
        except queue.Empty:
            pass
        root.after(50, poll_queue)

    tray = TrayIcon(on_exit=root.quit)
    initial_desktop = get_current_desktop_number()
    tray.start(desktop_number=initial_desktop)

    _current_desktop: list[int] = [initial_desktop]

    def poll_desktop() -> None:
        num = get_current_desktop_number()
        if num != _current_desktop[0]:
            _current_desktop[0] = num
            tray.update(num)
        root.after(500, poll_desktop)

    def poll_move_queue() -> None:
        try:
            while True:
                fg_hwnd, direction = move_queue.get_nowait()
                target_n = move_window_to_adjacent_desktop(fg_hwnd, direction)
                if target_n > 0:
                    _current_desktop[0] = target_n
                    tray.update(target_n)
        except queue.Empty:
            pass
        root.after(50, poll_move_queue)

    root.after(50, poll_queue)
    root.after(50, poll_move_queue)
    root.after(500, poll_desktop)
    root.mainloop()

    tray.stop()
