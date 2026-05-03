"""Entry point: wires together Tk root, overlay, hotkey listener, and system tray."""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
import tkinter as tk
from typing import Callable

from windows_navigator.config import (
    HotkeyChoice,
    load_expand_on_startup,
    load_hotkey,
    save_expand_on_startup,
    save_hotkey,
)

_log = logging.getLogger(__name__)


class _WakeQueue(queue.Queue):  # type: ignore[type-arg]
    """A Queue that immediately wakes the Tk main thread on every put().

    The hotkey listener thread calls put() when a trigger fires.  Without this,
    the Tk thread only notices via a 50 ms poll, adding up to 50 ms of latency.
    set_wakeup() must be called once from the Tk thread before any put().
    """

    def __init__(self) -> None:
        super().__init__()
        self._wakeup: "Callable[[], None] | None" = None

    def set_wakeup(self, fn: "Callable[[], None]") -> None:
        self._wakeup = fn

    def put(self, item: object, block: bool = True, timeout: "float | None" = None) -> None:
        super().put(item, block=block, timeout=timeout)
        if self._wakeup is not None:
            self._wakeup()


# Hotkey IDs passed to RegisterHotKey — must not collide with each other or with
# the move-hotkey IDs (1 = left, 2 = right) registered in _start_move_hotkey_listener.
_HOTKEY_ID_DOUBLE_TAP_CTRL = 100
_HOTKEY_ID_WIN_ALT_SPACE = 200
_HOTKEY_ID_CTRL_SHIFT_SPACE = 300
_HOTKEY_ID_DOUBLE_TAP_SHIFT = 400
_HOTKEY_ID_SHIFT_DOUBLE_TAP_CTRL = 500
_HOTKEY_ID_DOUBLE_TAP_SHIFT_SOLO = 600


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
                    ("cbSize", wt.UINT),
                    ("style", wt.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE),
                    ("hIcon", wt.HICON),
                    ("hCursor", wt.HANDLE),
                    ("hbrBackground", wt.HBRUSH),
                    ("lpszMenuName", wt.LPCWSTR),
                    ("lpszClassName", wt.LPCWSTR),
                    ("hIconSm", wt.HICON),
                ]

            wc = _WNDCLS()
            wc.cbSize = ctypes.sizeof(_WNDCLS)
            wc.lpfnWndProc = _proc
            wc.lpszClassName = "WinNavFlashMon"
            u32.RegisterClassExW(ctypes.byref(wc))

            # HWND_MESSAGE = (HWND)(LONG_PTR)(-3) — message-only window, no taskbar entry
            hwnd = u32.CreateWindowExW(
                0,
                "WinNavFlashMon",
                None,
                0,
                0,
                0,
                0,
                0,
                ctypes.c_size_t(-3),
                None,
                None,
                None,
            )
            if not hwnd:
                return

            WM_SHELL = u32.RegisterWindowMessageW("SHELLHOOK")
            u32.RegisterShellHookWindow(hwnd)

            HSHELL_DESTROYED = 2
            HSHELL_ACTIVATED = 4
            HSHELL_REDRAW = 6
            HSHELL_FLASH = 0x8006  # HSHELL_REDRAW | HSHELL_HIGHBIT
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
            _log.exception("flash-monitor thread crashed")

    threading.Thread(target=_run, daemon=True, name="flash-monitor").start()


def _polling_double_tap_listener(
    show_queue: queue.Queue[int],
    stop_event: threading.Event,
    *,
    hotkey_id: int,
    tap_vk_l: int,
    tap_vk_r: int,
    guard_vk_l: int | None = None,
    guard_vk_r: int | None = None,
) -> None:
    """Poll GetAsyncKeyState every 30 ms; fire on two rising edges of tap_vk within 300 ms.

    If guard_vk_l/guard_vk_r are given, both must be held at each rising edge.
    Injects a synthetic VK_F24 via SendInput and drains its WM_HOTKEY to acquire
    the foreground-lock exemption. Falls back to a direct put() if RegisterHotKey fails.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        import time

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        VK_F24 = 0x87
        DOUBLE_TAP_MS = 300.0
        POLL_S = 0.030
        WM_HOTKEY = 0x0312
        MOD_NOREPEAT = 0x4000
        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002

        # PeekMessageW must be called once to create a message queue before RegisterHotKey.
        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

        use_hotkey = bool(user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, VK_F24))

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
                        if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                            show_queue.put(fg)
                            return
                    time.sleep(0.005)
            show_queue.put(fg)

        last_tap_ms = 0.0
        tap_was_down = False

        while not stop_event.is_set():
            time.sleep(POLL_S)

            tap_down = bool(
                (user32.GetAsyncKeyState(tap_vk_l) | user32.GetAsyncKeyState(tap_vk_r)) & 0x8000
            )
            guard_down = guard_vk_l is None or bool(
                (user32.GetAsyncKeyState(guard_vk_l) | user32.GetAsyncKeyState(guard_vk_r)) & 0x8000
            )

            if tap_down and not tap_was_down and guard_down:
                now = time.monotonic() * 1000.0
                if now - last_tap_ms <= DOUBLE_TAP_MS:
                    _trigger()
                    last_tap_ms = 0.0
                else:
                    last_tap_ms = now

            tap_was_down = tap_down

        if use_hotkey:
            user32.UnregisterHotKey(None, hotkey_id)

    except Exception:
        _log.exception("polling-double-tap-listener thread crashed")


def _run_registered_hotkey(
    show_queue: queue.Queue[int],
    stop_event: threading.Event,
    *,
    hotkey_id: int,
    modifiers: int,
    vk: int,
) -> None:
    """Register a hotkey via RegisterHotKey; put the foreground HWND to show_queue on each trigger.

    WM_HOTKEY delivery grants the foreground-lock exemption, so SetForegroundWindow
    in the overlay succeeds without the SendInput trick used by the polling path.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        import time

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        WM_HOTKEY = 0x0312

        msg = wt.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

        if not user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            return

        try:
            while not stop_event.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                        show_queue.put(user32.GetForegroundWindow())
                else:
                    time.sleep(0.010)
        finally:
            user32.UnregisterHotKey(None, hotkey_id)

    except Exception:
        _log.exception("registered-hotkey-listener thread crashed")


_BROWSER_PROC_NAMES = frozenset(
    {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "vivaldi.exe",
    }
)


def _start_tab_cache_warmer() -> None:
    """Warm the tab domain cache whenever a browser window gains focus.

    Registers a shell hook window; on HSHELL_WINDOWACTIVATED for any browser
    process, calls fetch_tabs() on a short-lived daemon thread so inactive
    Firefox tabs accumulate domains in _tab_domain_cache between overlay opens.
    """

    def _run() -> None:
        try:
            import ctypes
            import ctypes.wintypes as wt

            u32 = ctypes.windll.user32  # type: ignore[attr-defined]
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t
            )
            u32.DefWindowProcW.restype = ctypes.c_ssize_t
            u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            _proc = WNDPROC(lambda h, m, w, lp: u32.DefWindowProcW(h, m, w, lp))

            class _WNDCLS(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wt.UINT),
                    ("style", wt.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE),
                    ("hIcon", wt.HICON),
                    ("hCursor", wt.HANDLE),
                    ("hbrBackground", wt.HBRUSH),
                    ("lpszMenuName", wt.LPCWSTR),
                    ("lpszClassName", wt.LPCWSTR),
                    ("hIconSm", wt.HICON),
                ]

            wc = _WNDCLS()
            wc.cbSize = ctypes.sizeof(_WNDCLS)
            wc.lpfnWndProc = _proc
            wc.lpszClassName = "WinNavTabWarmer"
            u32.RegisterClassExW(ctypes.byref(wc))

            hook_hwnd = u32.CreateWindowExW(
                0,
                "WinNavTabWarmer",
                None,
                0,
                0,
                0,
                0,
                0,
                ctypes.c_size_t(-3),
                None,
                None,
                None,
            )
            if not hook_hwnd:
                return

            WM_SHELL = u32.RegisterWindowMessageW("SHELLHOOK")
            u32.RegisterShellHookWindow(hook_hwnd)

            HSHELL_ACTIVATED = 4
            HSHELL_RUDEACTIVATED = 0x8004
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

            def _proc_name(hwnd: int) -> str:
                try:
                    pid = wt.DWORD()
                    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    if not h:
                        return ""
                    try:
                        buf = ctypes.create_unicode_buffer(512)
                        size = wt.DWORD(512)
                        k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                        return buf.value.split("\\")[-1].lower()
                    finally:
                        k32.CloseHandle(h)
                except Exception:
                    return ""

            _active: set[int] = set()

            def _warm(target: int) -> None:
                try:
                    import ctypes as _ct

                    _ct.windll.ole32.CoInitializeEx(None, 0)  # type: ignore[attr-defined]
                    from windows_navigator.tabs import fetch_tabs

                    fetch_tabs(target)
                except Exception:
                    pass
                finally:
                    _active.discard(target)

            msg = wt.MSG()
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_SHELL and msg.wParam in (
                    HSHELL_ACTIVATED,
                    HSHELL_RUDEACTIVATED,
                ):
                    target = int(msg.lParam)
                    if target not in _active and _proc_name(target) in _BROWSER_PROC_NAMES:
                        _active.add(target)
                        threading.Thread(
                            target=_warm,
                            args=(target,),
                            daemon=True,
                            name="tab-warmer",
                        ).start()
                u32.DispatchMessageW(ctypes.byref(msg))

            u32.DeregisterShellHookWindow(hook_hwnd)
            u32.DestroyWindow(hook_hwnd)
        except Exception:
            _log.exception("tab-cache-warmer thread crashed")

    threading.Thread(target=_run, daemon=True, name="tab-cache-warmer").start()


def _hotkey_listener_config(choice: HotkeyChoice) -> tuple[object, dict[str, int]]:
    """Return (target_function, kwargs) for the given hotkey choice.

    Pure function — no side effects. Extracted so the dispatch logic can be
    tested without spawning threads or touching Win32 APIs.
    """
    VK_LCONTROL = 0xA2
    VK_RCONTROL = 0xA3
    VK_LSHIFT = 0xA0
    VK_RSHIFT = 0xA1
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000
    VK_SPACE = 0x20

    if choice == HotkeyChoice.DOUBLE_TAP_SHIFT:
        return _polling_double_tap_listener, {
            "hotkey_id": _HOTKEY_ID_DOUBLE_TAP_SHIFT_SOLO,
            "tap_vk_l": VK_LSHIFT,
            "tap_vk_r": VK_RSHIFT,
        }
    if choice == HotkeyChoice.WIN_ALT_SPACE:
        return _run_registered_hotkey, {
            "hotkey_id": _HOTKEY_ID_WIN_ALT_SPACE,
            "modifiers": MOD_WIN | MOD_ALT | MOD_NOREPEAT,
            "vk": VK_SPACE,
        }
    if choice == HotkeyChoice.CTRL_SHIFT_SPACE:
        return _run_registered_hotkey, {
            "hotkey_id": _HOTKEY_ID_CTRL_SHIFT_SPACE,
            "modifiers": MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
            "vk": VK_SPACE,
        }
    if choice == HotkeyChoice.CTRL_DOUBLE_TAP_SHIFT:
        return _polling_double_tap_listener, {
            "hotkey_id": _HOTKEY_ID_DOUBLE_TAP_SHIFT,
            "tap_vk_l": VK_LSHIFT,
            "tap_vk_r": VK_RSHIFT,
            "guard_vk_l": VK_LCONTROL,
            "guard_vk_r": VK_RCONTROL,
        }
    if choice == HotkeyChoice.SHIFT_DOUBLE_TAP_CTRL:
        return _polling_double_tap_listener, {
            "hotkey_id": _HOTKEY_ID_SHIFT_DOUBLE_TAP_CTRL,
            "tap_vk_l": VK_LCONTROL,
            "tap_vk_r": VK_RCONTROL,
            "guard_vk_l": VK_LSHIFT,
            "guard_vk_r": VK_RSHIFT,
        }
    # Default: DOUBLE_TAP_CTRL
    return _polling_double_tap_listener, {
        "hotkey_id": _HOTKEY_ID_DOUBLE_TAP_CTRL,
        "tap_vk_l": VK_LCONTROL,
        "tap_vk_r": VK_RCONTROL,
    }


def _start_hotkey_listener(
    show_queue: queue.Queue[int],
    choice: HotkeyChoice,
    stop_event: threading.Event,
) -> None:
    """Start the overlay hotkey listener thread for the given hotkey choice."""
    target, kwargs = _hotkey_listener_config(choice)
    threading.Thread(
        target=target,
        args=(show_queue, stop_event),
        kwargs=kwargs,
        daemon=True,
        name="hotkey-listener",
    ).start()


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

            ok_left = user32.RegisterHotKey(
                None, ID_LEFT, MOD_CONTROL | MOD_SHIFT | MOD_WIN, VK_LEFT
            )
            ok_right = user32.RegisterHotKey(
                None, ID_RIGHT, MOD_CONTROL | MOD_SHIFT | MOD_WIN, VK_RIGHT
            )

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
            _log.exception("move-hotkey-listener thread crashed")

    threading.Thread(target=_run, daemon=True, name="move-hotkey-listener").start()


def _process_show_queue(
    show_queue: "queue.Queue[int]",
    provider: object,
    overlay: object,
    tray: object,
    current_desktop: list[int],
) -> None:
    """Drain *show_queue* and show the overlay once if any items were pending.

    Drains all queued items but processes only once — multiple queued hotkey
    events within one poll cycle would otherwise call overlay.show() N times,
    causing an even number of toggles to cancel each other.

    *current_desktop* is a one-element list used as a mutable reference so
    the caller's tracking variable is updated after a successful enumeration.
    Only updated when a valid desktop number (> 0) is found.

    The queue items are the foreground HWND captured at trigger time (via
    GetForegroundWindow).  EnumWindows Z-order can lag slightly after a rapid
    Alt+Tab, so we use that HWND to anchor the list: if the captured foreground
    window is not already first, we move it there.
    """
    trigger_hwnd: int = 0
    has_items = False
    try:
        while True:
            trigger_hwnd = show_queue.get_nowait()
            has_items = True
    except queue.Empty:
        pass
    if not has_items:
        return
    t0 = time.monotonic()
    windows = provider.get_windows()  # type: ignore[union-attr]
    fetch_ms = (time.monotonic() - t0) * 1000.0
    # If EnumWindows returned a stale Z-order (common after a rapid Alt+Tab),
    # the actual foreground window may not be at position 0.  Re-anchor it.
    if trigger_hwnd and windows and windows[0].hwnd != trigger_hwnd:
        idx = next((i for i, w in enumerate(windows) if w.hwnd == trigger_hwnd), -1)
        if idx > 0:
            windows = [windows[idx]] + windows[:idx] + windows[idx + 1 :]
    desktop = next(
        (w.desktop_number for w in windows if w.is_current_desktop and w.desktop_number > 0),
        0,
    )
    overlay.show(windows, initial_desktop=desktop, fetch_ms=fetch_ms)  # type: ignore[union-attr]
    tray.update(desktop)  # type: ignore[union-attr]
    if desktop > 0:
        current_desktop[0] = desktop
    if hasattr(provider, "request_refresh"):
        provider.request_refresh()  # pre-warm cache for next open


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
    from windows_navigator.provider import BackgroundWindowCache, RealWindowProvider
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
        provider.request_refresh()  # window moved; pre-warm cache for next open

    def move_windows_to_desktop(hwnds: list[int], n: int) -> None:
        """Move every hwnd in *hwnds* to desktop *n* (1-based); activate the last one.

        Pass n=0 to create a new desktop and move the windows there.
        """
        from windows_navigator.virtual_desktop import (
            create_desktop,
            move_window_to_desktop_number,
            switch_to_desktop_number,
        )

        if n == 0:
            n = create_desktop()
            if n == 0:
                return  # creation failed; do nothing
        for hwnd in hwnds[:-1]:
            move_window_to_desktop_number(hwnd, n)
        if hwnds:
            move_window_to_desktop_number(hwnds[-1], n)
            switch_to_desktop_number(n)
            activate_window(hwnds[-1])
        provider.request_refresh()

    flashing: set[int] = set()
    _start_flash_monitor(flashing)
    _start_tab_cache_warmer()

    provider = BackgroundWindowCache(RealWindowProvider(flashing=flashing))
    overlay = NavigatorOverlay(
        root,
        on_activate=activate_window,
        on_move=move_and_activate,
        on_move_to=move_windows_to_desktop,
        expand_on_startup=load_expand_on_startup(),
    )
    show_queue: _WakeQueue = _WakeQueue()
    move_queue: queue.Queue[tuple[int, int]] = queue.Queue()

    _start_move_hotkey_listener(move_queue)

    def _drain_show_queue() -> None:
        _process_show_queue(show_queue, provider, overlay, tray, _current_desktop)

    def poll_queue() -> None:
        _drain_show_queue()
        root.after(50, poll_queue)

    # Wake the Tk thread immediately whenever the hotkey fires — reduces
    # open latency from up to 50 ms (poll interval) to near-zero.
    show_queue.set_wakeup(lambda: root.after(0, _drain_show_queue))

    from windows_navigator.settings import open_settings_window

    _current_hotkey: list[HotkeyChoice] = [load_hotkey()]
    _hotkey_stop: list[threading.Event] = [threading.Event()]
    _start_hotkey_listener(show_queue, _current_hotkey[0], _hotkey_stop[0])

    def _on_settings_saved(new_choice: HotkeyChoice, new_expand: bool) -> None:
        save_hotkey(new_choice)
        save_expand_on_startup(new_expand)
        old_stop = _hotkey_stop[0]
        _hotkey_stop[0] = threading.Event()
        old_stop.set()
        _current_hotkey[0] = new_choice
        _current_expand[0] = new_expand
        _start_hotkey_listener(show_queue, new_choice, _hotkey_stop[0])
        overlay.set_expand_on_startup(new_expand)

    _current_expand: list[bool] = [load_expand_on_startup()]

    def _open_settings() -> None:
        # pystray calls this from its own thread; marshal to Tk main thread.
        root.after(
            0,
            lambda: open_settings_window(
                root, _current_hotkey[0], _current_expand[0], _on_settings_saved
            ),
        )

    tray = TrayIcon(on_exit=root.quit, on_settings=_open_settings)
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
