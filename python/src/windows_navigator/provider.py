"""Win32 window enumeration and icon extraction.

RealWindowProvider enumerates visible, non-tool windows on the active virtual desktop
in z-order (most-recently-active first) and resolves their app icons.

This module imports win32* packages which are only available on Windows.
All Win32 interaction is isolated here so the rest of the codebase can be tested
on any platform by substituting a mock WindowProvider.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import re
from collections import OrderedDict
from typing import Callable, Protocol, Sequence

from PIL import Image

from windows_navigator.models import WindowInfo

# Matches "(N)" prefix in window titles — apps like Teams/Outlook use e.g. "(3) Inbox".
_NOTIF_TITLE_RE = re.compile(r"^\(\d+\)")

# Size of icons fetched from the OS (display size)
_ICON_SIZE = (32, 32)

# Render size for shell-image-list icons; downscaled to _ICON_SIZE via Lanczos
_FETCH_SIZE = (256, 256)

# Fallback icon — a plain grey square
_FALLBACK_ICON: Image.Image = Image.new("RGBA", _ICON_SIZE, color=(128, 128, 128, 255))

# Process names to never show in the window list (case-insensitive)
_EXCLUDED_PROCESSES = {"textinputhost.exe"}

_ICON_CACHE_MAX = 256


class _SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", ctypes.wintypes.HANDLE),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", ctypes.c_ulong),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]

DesktopAssigner = Callable[[list[int]], tuple[dict[int, int], dict[int, bool]]]


class WindowFilter(Protocol):
    """Predicate applied to each candidate window after process name resolution.

    Return True to include the window, False to skip it.  Inject additional
    filters into RealWindowProvider to extend filtering without modifying it.
    """

    def __call__(self, hwnd: int, title: str, process_name: str) -> bool: ...


class WindowProvider(Protocol):
    """Interface for window enumeration. Implement this to inject a mock in tests."""

    def get_windows(self) -> list[WindowInfo]: ...


def _query_exe_path(handle: object) -> str:
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    size = ctypes.c_ulong(1024)
    ctypes.windll.kernel32.QueryFullProcessImageNameW(int(handle), 0, buf, ctypes.byref(size))
    return buf.value


def _shell_imagelist_icon(exe_path: str) -> int:
    """Return an hIcon at 256×256 from the shell jumbo image list. Caller must DestroyIcon."""
    try:
        SHGFI_SYSICONINDEX = 0x4000
        shfi = _SHFILEINFO()
        if not ctypes.windll.shell32.SHGetFileInfoW(  # type: ignore[attr-defined]
            exe_path, 0, ctypes.byref(shfi), ctypes.sizeof(shfi), SHGFI_SYSICONINDEX
        ):
            return 0

        # IID_IImageList = {46EB5926-582E-4017-9FDF-E8998DAA0950}
        # Bytes in memory: Data1 LE, Data2 LE, Data3 LE, Data4 as-is
        iid = (ctypes.c_byte * 16)(
            0x26, 0x59, 0xEB, 0x46,
            0x2E, 0x58,
            0x17, 0x40,
            0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50,
        )
        SHIL_JUMBO = 4
        himl = ctypes.c_void_p()
        hr = ctypes.windll.shell32.SHGetImageList(SHIL_JUMBO, ctypes.byref(iid), ctypes.byref(himl))
        if hr != 0 or not himl.value:
            return 0

        # IImageList::GetIcon is at vtable index 10
        ILD_TRANSPARENT = 0x00000001
        hicon = ctypes.wintypes.HANDLE(0)
        vtbl = ctypes.cast(
            ctypes.cast(himl, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        GetIcon = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.wintypes.HANDLE),
        )(vtbl[10])

        if GetIcon(himl, shfi.iIcon, ILD_TRANSPARENT, ctypes.byref(hicon)) != 0:
            return 0
        return int(hicon.value)
    except Exception:
        return 0


class IconExtractor:
    """Extracts a window's app icon from Win32 APIs, with a grey fallback on failure."""

    @staticmethod
    def extract(hwnd: int, exe_path: str = "") -> Image.Image:
        try:
            import ctypes
            import ctypes.wintypes

            import win32api
            import win32con
            import win32gui
            import win32process
            from PIL import Image as PILImage

            # Resolve exe path only when the caller hasn't already done so.
            if not exe_path:
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    proc = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                    exe_path = _query_exe_path(proc)
                    win32api.CloseHandle(proc)
                except Exception:
                    pass

            owned_icon = False
            render_size = _ICON_SIZE

            # 1. Shell jumbo image list — always 256×256, covers Electron/UWP/browser apps
            icon_handle = _shell_imagelist_icon(exe_path) if exe_path else 0
            if icon_handle:
                owned_icon = True
                render_size = _FETCH_SIZE

            # 2. WM_GETICON / GetClassLong — app-provided icon (typically 32×32)
            if not icon_handle:
                icon_handle = win32gui.SendMessage(hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
            if not icon_handle:
                icon_handle = win32gui.SendMessage(
                    hwnd, win32con.WM_GETICON, win32con.ICON_SMALL, 0
                )
            if not icon_handle:
                icon_handle = win32gui.GetClassLong(hwnd, win32con.GCL_HICON)

            # 3. SHGetFileInfoW 32×32 — last resort
            if not icon_handle and exe_path:
                SHGFI_ICON = 0x100
                SHGFI_LARGEICON = 0x0
                shfi = _SHFILEINFO()
                if ctypes.windll.shell32.SHGetFileInfoW(
                    exe_path, 0, ctypes.byref(shfi), ctypes.sizeof(shfi), SHGFI_ICON | SHGFI_LARGEICON
                ):
                    icon_handle = int(shfi.hIcon)
                    owned_icon = True

            if not icon_handle:
                return _FALLBACK_ICON.copy()

            w, h = render_size

            class _BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32),
                    ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            bmih = _BITMAPINFOHEADER()
            bmih.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmih.biWidth = w
            bmih.biHeight = -h  # negative = top-down DIB
            bmih.biPlanes = 1
            bmih.biBitCount = 32
            bmih.biCompression = 0  # BI_RGB

            hdc_screen = ctypes.windll.user32.GetDC(0)
            pixels_ptr = ctypes.c_void_p()
            hbmp = ctypes.windll.gdi32.CreateDIBSection(
                hdc_screen, ctypes.byref(bmih), 0, ctypes.byref(pixels_ptr), None, 0
            )
            ctypes.windll.user32.ReleaseDC(0, hdc_screen)

            if not hbmp or not pixels_ptr.value:
                if owned_icon:
                    win32gui.DestroyIcon(icon_handle)
                return _FALLBACK_ICON.copy()

            hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(None)
            old_bmp = ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)

            DI_NORMAL = 0x0003
            ctypes.windll.user32.DrawIconEx(hdc_mem, 0, 0, icon_handle, w, h, 0, 0, DI_NORMAL)

            buf = (ctypes.c_ubyte * (w * h * 4))()
            ctypes.memmove(buf, pixels_ptr.value, w * h * 4)

            ctypes.windll.gdi32.SelectObject(hdc_mem, old_bmp)
            ctypes.windll.gdi32.DeleteDC(hdc_mem)
            ctypes.windll.gdi32.DeleteObject(hbmp)

            if owned_icon:
                win32gui.DestroyIcon(icon_handle)

            img = PILImage.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
            if render_size != _ICON_SIZE:
                img = img.resize(_ICON_SIZE, PILImage.LANCZOS)
            return img
        except Exception:
            return _FALLBACK_ICON.copy()


class RealWindowProvider:
    """Enumerates windows using the Win32 API."""

    def __init__(
        self,
        assign_desktops: DesktopAssigner | None = None,
        flashing: set[int] | None = None,
        extra_filters: Sequence[WindowFilter] | None = None,
    ) -> None:
        if assign_desktops is None:
            from windows_navigator.virtual_desktop import assign_desktop_numbers
            assign_desktops = assign_desktop_numbers
        self._assign_desktops = assign_desktops
        self._flashing: set[int] = flashing if flashing is not None else set()
        self._extra_filters: list[WindowFilter] = list(extra_filters) if extra_filters else []
        self._icon_cache: OrderedDict[str, Image.Image] = OrderedDict()

    def get_windows(self) -> list[WindowInfo]:
        import win32con
        import win32gui
        import win32process

        hwnd_titles: list[tuple[int, str]] = []

        def _enum_callback(hwnd: int, _: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
                return True
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return True
            hwnd_titles.append((hwnd, title))
            return True

        win32gui.EnumWindows(_enum_callback, None)
        hwnds = [hwnd for hwnd, _ in hwnd_titles]

        desktop_numbers, is_current_map = self._assign_desktops(hwnds)

        results: list[WindowInfo] = []
        for hwnd, title in hwnd_titles:
            process_name, exe_path = self._get_process_info(hwnd, win32process)
            if process_name.lower() in _EXCLUDED_PROCESSES:
                continue
            if not all(f(hwnd, title, process_name) for f in self._extra_filters):
                continue
            desktop_number = desktop_numbers.get(hwnd, 0)
            if desktop_number == -1:
                continue  # ghost window on a desktop that no longer exists
            if exe_path:
                cache_key = exe_path.lower()
                if cache_key in self._icon_cache:
                    self._icon_cache.move_to_end(cache_key)
                    icon = self._icon_cache[cache_key]
                else:
                    icon = IconExtractor.extract(hwnd, exe_path)
                    self._icon_cache[cache_key] = icon
                    if len(self._icon_cache) > _ICON_CACHE_MAX:
                        self._icon_cache.popitem(last=False)
            else:
                icon = IconExtractor.extract(hwnd, exe_path)
            is_current = is_current_map.get(hwnd, True)
            results.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=title,
                    process_name=process_name,
                    icon=icon,
                    desktop_number=desktop_number,
                    is_current_desktop=is_current,
                    has_notification=hwnd in self._flashing or bool(_NOTIF_TITLE_RE.match(title)),
                )
            )

        return results

    @staticmethod
    def _get_process_info(hwnd: int, win32process: object) -> tuple[str, str]:
        """Return (process_name, exe_path) for *hwnd*, opening the process handle once."""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            import win32api
            import win32con as wc

            handle = win32api.OpenProcess(wc.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            exe_path = _query_exe_path(handle)
            win32api.CloseHandle(handle)
            return os.path.basename(exe_path), exe_path
        except Exception:
            return "", ""
