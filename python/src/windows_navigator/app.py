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
    """Detect double-tap of Ctrl via GetAsyncKeyState polling.

    WH_KEYBOARD_LL is incompatible with Python: its hook proc must acquire the GIL,
    but the GIL may be held by the Tk main thread at the moment a key event occurs,
    causing a deadlock that blocks all keyboard input system-wide.

    Poll GetAsyncKeyState every 30 ms instead — no hook, no GIL contention.
    Two rising edges of either Ctrl key within 300 ms trigger the overlay:

    On detection, SendInput injects a synthetic VK_F24 keypress. VK_F24 is
    registered with RegisterHotKey so Windows delivers WM_HOTKEY to this thread.
    WM_HOTKEY carries the foreground-lock exemption, making SetForegroundWindow in
    _grab_focus reliable. Falls back to a direct put() if RegisterHotKey fails.
    """

    def _run() -> None:
        try:
            import ctypes
            import ctypes.wintypes as wt
            import time

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]

            VK_LCONTROL = 0xA2
            VK_RCONTROL = 0xA3
            VK_F24 = 0x87
            DOUBLE_TAP_MS = 300.0
            POLL_S = 0.030
            WM_HOTKEY = 0x0312
            HOTKEY_ID = 100
            MOD_NOREPEAT = 0x4000
            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002

            # Create a message queue for this thread so RegisterHotKey / WM_HOTKEY work.
            msg = wt.MSG()
            user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

            use_hotkey = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F24))

            class _KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", ctypes.c_ushort),
                    ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_uint),
                    ("time", ctypes.c_uint),
                    ("dwExtraInfo", ctypes.c_size_t),
                ]

            # Union must be sized by its largest member (MOUSEINPUT = 7 × 4 bytes).
            class _INPUT_PADDING(ctypes.Structure):
                _fields_ = [("_pad", ctypes.c_byte * 28)]

            class _INPUT_UNION(ctypes.Union):
                _fields_ = [("ki", _KEYBDINPUT), ("_pad", _INPUT_PADDING)]

            class _INPUT(ctypes.Structure):
                _fields_ = [("type", ctypes.c_uint), ("_u", _INPUT_UNION)]

            def _send_vk(vk: int, flags: int = 0) -> None:
                inp = _INPUT()
                inp.type = INPUT_KEYBOARD
                inp._u.ki.wVk = vk
                inp._u.ki.dwFlags = flags
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

            def _trigger() -> None:
                fg = user32.GetForegroundWindow()
                if use_hotkey:
                    _send_vk(VK_F24)
                    _send_vk(VK_F24, KEYEVENTF_KEYUP)
                    # Wait up to 100 ms for WM_HOTKEY — it grants the foreground lock.
                    deadline = time.monotonic() + 0.10
                    while time.monotonic() < deadline:
                        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                                show_queue.put(fg)
                                return
                        time.sleep(0.005)
                show_queue.put(fg)

            last_tap_ms = 0.0
            ctrl_was_down = False

            while True:
                time.sleep(POLL_S)

                lc = user32.GetAsyncKeyState(VK_LCONTROL)
                rc = user32.GetAsyncKeyState(VK_RCONTROL)
                ctrl_down = bool((lc | rc) & 0x8000)

                if ctrl_down and not ctrl_was_down:
                    now = time.monotonic() * 1000.0
                    if now - last_tap_ms <= DOUBLE_TAP_MS:
                        _trigger()
                        last_tap_ms = 0.0
                    else:
                        last_tap_ms = now

                ctrl_was_down = ctrl_down

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
    # Per-monitor v2 DPI awareness must be set before the Tk window is created;
    # without it Windows bitmap-scales the window and text appears blurry on HiDPI displays.
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        pass

    # Deferred imports keep startup fast and allow module-level imports on non-Windows
    from windows_navigator.activation import activate_window
    from windows_navigator.overlay import NavigatorOverlay, init_scale
    from windows_navigator.provider import RealWindowProvider
    from windows_navigator.tray import TrayIcon
    from windows_navigator.virtual_desktop import (
        get_current_desktop_number,
        move_window_to_adjacent_desktop,
        move_window_to_current_desktop,
    )

    root = tk.Tk()
    root.withdraw()  # hidden host window — never shown to the user

    # Scale pixel layout constants to match the actual monitor DPI.
    # winfo_fpixels('1i') returns pixels-per-inch; 96 is the baseline DPI.
    try:
        dpi_scale = root.winfo_fpixels("1i") / 96.0
        if dpi_scale != 1.0:
            init_scale(dpi_scale)
    except Exception:
        pass

    def move_and_activate(hwnd: int) -> None:
        move_window_to_current_desktop(hwnd)
        activate_window(hwnd)

    flashing: set[int] = set()
    _start_flash_monitor(flashing)

    provider = RealWindowProvider(flashing=flashing)
    overlay = NavigatorOverlay(root, on_activate=activate_window, on_move=move_and_activate)
    show_queue: queue.Queue[int] = queue.Queue()
    move_queue: queue.Queue[tuple[int, int]] = queue.Queue()

    _start_move_hotkey_listener(move_queue)

    def _drain_show_queue() -> None:
        try:
            while True:
                show_queue.get_nowait()  # fg_hwnd captured at hotkey time (no longer used)
                windows = provider.get_windows()
                current_desktop = next(
                    (
                        w.desktop_number
                        for w in windows
                        if w.is_current_desktop and w.desktop_number > 0
                    ),
                    0,
                )
                overlay.show(windows, initial_desktop=current_desktop)
                tray.update(current_desktop)
                if current_desktop > 0:
                    _current_desktop[0] = current_desktop
        except queue.Empty:
            pass

    def poll_queue() -> None:
        _drain_show_queue()
        root.after(50, poll_queue)

    _start_hotkey_listener(show_queue)

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
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass

    tray.stop()
