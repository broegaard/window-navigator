"""Virtual desktop detection via IVirtualDesktopManager COM interface.

Uses ctypes to call IsWindowOnCurrentVirtualDesktop — no extra dependencies.
Falls back to True (include window) on any failure so the tool degrades
gracefully on unsupported configurations.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Protocol

# IVirtualDesktopManager
_CLSID_VirtualDesktopManager = "{AA509086-5CA9-4C25-8F95-589D3C07B48A}"
_IID_IVirtualDesktopManager = "{A5CD92FF-29BE-454C-8D04-D82879FB3F1B}"


class _VirtualDesktopManager(Protocol):
    """Interface for virtual desktop manager implementations (DIP boundary)."""

    def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool: ...
    def GetWindowDesktopId(self, hwnd: int) -> str | None: ...
    def MoveWindowToDesktop(self, hwnd: int, desktop_guid_str: str) -> bool: ...


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _make_guid(s: str) -> _GUID:
    """Convert a GUID string (with braces) to a _GUID struct."""
    import uuid

    b = uuid.UUID(s).bytes_le
    g = _GUID()
    g.Data1 = int.from_bytes(b[0:4], "little")
    g.Data2 = int.from_bytes(b[4:6], "little")
    g.Data3 = int.from_bytes(b[6:8], "little")
    for i in range(8):
        g.Data4[i] = b[8 + i]
    return g


def _guid_to_str(g: _GUID) -> str:
    """Convert a _GUID struct to a UUID string."""
    import uuid

    b = (
        g.Data1.to_bytes(4, "little")
        + g.Data2.to_bytes(2, "little")
        + g.Data3.to_bytes(2, "little")
        + bytes(g.Data4)
    )
    return str(uuid.UUID(bytes_le=b))


class _ManagerCache:
    """Lazy-initialises the COM manager once and caches the result.

    Encapsulating the two related globals (_manager, _init_attempted) here
    removes mutable module-level state and makes the initialisation logic
    self-contained.
    """

    def __init__(self) -> None:
        self._manager: _VirtualDesktopManager | None = None
        self._attempted = False

    def get(self) -> _VirtualDesktopManager | None:
        if self._attempted:
            return self._manager
        self._attempted = True
        try:
            from comtypes import CLSCTX_ALL, CoCreateInstance, GUID  # type: ignore[import] # noqa: I001
            from comtypes.gen import IVirtualDesktopManager as _vdm  # type: ignore[import]

            self._manager = CoCreateInstance(
                GUID(_CLSID_VirtualDesktopManager),
                interface=_vdm.IVirtualDesktopManager,
                clsctx=CLSCTX_ALL,
            )
        except Exception:
            self._manager = _try_raw_ctypes()
        return self._manager


_thread_local = threading.local()


def _get_manager() -> _VirtualDesktopManager | None:
    """Return the per-thread IVirtualDesktopManager instance, initialising COM on first use.

    Each thread gets its own COM apartment and interface pointer — sharing raw vtable
    pointers across STA threads is unsafe, so _ManagerCache is kept thread-local.
    """
    if not hasattr(_thread_local, "_manager_cache"):
        _thread_local._manager_cache = _ManagerCache()
    return _thread_local._manager_cache.get()


def _try_raw_ctypes() -> _VirtualDesktopManager | None:
    """Attempt to create IVirtualDesktopManager via raw ctypes COM."""
    try:
        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]

        # COM must be initialized on the calling thread before CoCreateInstance.
        COINIT_APARTMENTTHREADED = 0x2
        ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)

        clsid = _make_guid(_CLSID_VirtualDesktopManager)
        iid = _make_guid(_IID_IVirtualDesktopManager)
        ptr = ctypes.c_void_p()
        CLSCTX_INPROC_SERVER = 1
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(iid),
            ctypes.byref(ptr),
        )
        if hr != 0 or not ptr.value:
            return None
        return _RawVDManager(ptr)
    except Exception:
        return None


class _RawVDManager:
    """Thin wrapper around a raw IVirtualDesktopManager COM pointer."""

    # IVirtualDesktopManager vtable layout:
    #   3 = IsWindowOnCurrentVirtualDesktop
    #   4 = GetWindowDesktopId
    #   5 = MoveWindowToDesktop
    _VTBL_IS_ON_CURRENT = 3
    _VTBL_GET_DESKTOP_ID = 4
    _VTBL_MOVE_TO_DESKTOP = 5

    def __init__(self, ptr: ctypes.c_void_p) -> None:
        self._ptr = ptr

    def _vtable_call(self, index: int, restype: object, argtypes: tuple, *args: object) -> int:
        """Dereference the COM vtable at *index*, build the function type, and call it."""
        vtbl_ptr = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.c_void_p))
        vtbl = ctypes.cast(vtbl_ptr[0], ctypes.POINTER(ctypes.c_void_p))
        fn_ptr = ctypes.cast(vtbl[index], ctypes.c_void_p)
        FUNC = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)  # type: ignore[attr-defined]
        return FUNC(fn_ptr.value)(self._ptr, *args)  # type: ignore[return-value]

    def IsWindowOnCurrentVirtualDesktop(self, hwnd: int) -> bool:
        result = ctypes.c_int(0)
        hr = self._vtable_call(
            self._VTBL_IS_ON_CURRENT,
            ctypes.HRESULT,  # type: ignore[attr-defined]
            (ctypes.wintypes.HWND, ctypes.POINTER(ctypes.c_int)),
            hwnd, ctypes.byref(result),
        )
        return True if hr != 0 else bool(result.value)

    def GetWindowDesktopId(self, hwnd: int) -> str | None:
        guid = _GUID()
        hr = self._vtable_call(
            self._VTBL_GET_DESKTOP_ID,
            ctypes.HRESULT,  # type: ignore[attr-defined]
            (ctypes.wintypes.HWND, ctypes.POINTER(_GUID)),
            hwnd, ctypes.byref(guid),
        )
        return None if hr != 0 else _guid_to_str(guid)

    def MoveWindowToDesktop(self, hwnd: int, desktop_guid_str: str) -> bool:
        guid = _make_guid(desktop_guid_str)
        hr = self._vtable_call(
            self._VTBL_MOVE_TO_DESKTOP,
            ctypes.HRESULT,  # type: ignore[attr-defined]
            (ctypes.wintypes.HWND, ctypes.POINTER(_GUID)),
            hwnd, ctypes.byref(guid),
        )
        return hr == 0


def get_current_desktop_number() -> int:
    """Return the 1-based number of the active virtual desktop, or 0 on failure.

    Reads VirtualDesktopIDs and CurrentVirtualDesktop from the registry —
    no COM required, so it works instantly at startup.
    """
    try:
        import uuid
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops",
        )
        current_data, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
        all_data, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
        winreg.CloseKey(key)
        if len(current_data) != 16 or len(all_data) % 16 != 0:
            return 0
        current_guid = str(uuid.UUID(bytes_le=bytes(current_data)))
        all_guids = [
            str(uuid.UUID(bytes_le=bytes(all_data[i : i + 16])))
            for i in range(0, len(all_data), 16)
        ]
        return all_guids.index(current_guid) + 1 if current_guid in all_guids else 0
    except Exception:
        return 0


def get_current_desktop_guid() -> str | None:
    """Return the GUID string of the active virtual desktop, read from the registry."""
    try:
        import uuid
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops",
        )
        current_data, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
        winreg.CloseKey(key)
        if len(current_data) != 16:
            return None
        return str(uuid.UUID(bytes_le=bytes(current_data)))
    except Exception:
        return None


def move_window_to_current_desktop(hwnd: int) -> bool:
    """Move *hwnd* to the current virtual desktop. Returns True on success.

    Tries pyvda first (handles Windows 11 cross-process restrictions via internal COM
    interfaces), then falls back to the public IVirtualDesktopManager::MoveWindowToDesktop.
    """
    # pyvda handles Windows 11 version-specific COM internals
    try:
        from pyvda import AppView, VirtualDesktop  # type: ignore[import]

        AppView(hwnd).move(VirtualDesktop.current())
        return True
    except Exception:
        pass
    # Fallback: public IVirtualDesktopManager::MoveWindowToDesktop (works on Windows 10,
    # unreliable on Windows 11 for cross-process windows)
    try:
        manager = _get_manager()
        if manager is None:
            return False
        guid = get_current_desktop_guid()
        if guid is None:
            return False
        return bool(manager.MoveWindowToDesktop(hwnd, guid))
    except Exception:
        return False


def switch_to_desktop_number(n: int) -> bool:
    """Switch to the Nth virtual desktop (1-based). Returns True on success."""
    try:
        from pyvda import VirtualDesktop  # type: ignore[import]

        VirtualDesktop(n).go()
        return True
    except Exception:
        return False


def move_window_to_adjacent_desktop(hwnd: int, direction: int) -> int:
    """Move *hwnd* to the adjacent virtual desktop and switch to it.

    direction: +1 for right, -1 for left. Stops at desktop boundaries.
    Returns the target desktop number (1-based) on success, 0 if at boundary or on failure.
    """
    try:
        all_guids = _get_registry_desktop_order()
        if not all_guids:
            return 0
        current_n = get_current_desktop_number()
        if current_n <= 0:
            return 0
        target_n = current_n + direction
        if target_n < 1 or target_n > len(all_guids):
            return 0
        try:
            from pyvda import AppView, VirtualDesktop  # type: ignore[import]

            AppView(hwnd).move(VirtualDesktop(target_n))
        except Exception:
            return 0
        switch_to_desktop_number(target_n)
        return target_n
    except Exception:
        return 0


def is_on_current_desktop(hwnd: int) -> bool:
    """Return True if *hwnd* is on the currently active virtual desktop.

    Always returns True on failure — the tool shows all windows rather than none.
    """
    try:
        manager = _get_manager()
        if manager is None:
            return True
        return bool(manager.IsWindowOnCurrentVirtualDesktop(hwnd))
    except Exception:
        return True


def _get_registry_desktop_order() -> list[str] | None:
    """Return GUIDs of all virtual desktops in display order, read from the registry.

    Returns None on any failure so callers can fall back gracefully.
    """
    try:
        import uuid
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops",
        )
        data, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
        winreg.CloseKey(key)
        if not data or len(data) % 16 != 0:
            return None
        return [str(uuid.UUID(bytes_le=bytes(data[i : i + 16]))) for i in range(0, len(data), 16)]
    except Exception:
        return None


def assign_desktop_numbers(hwnds: list[int]) -> tuple[dict[int, int], dict[int, bool]]:
    """Return (hwnd→desktop_number, hwnd→is_current_desktop) mappings.

    Desktop numbers reflect the actual Windows virtual desktop order (1 = leftmost in Task View),
    read from the registry. Falls back to first-encountered order if the registry is unavailable.
    Windows whose desktop cannot be determined get number 0 and is_current=True.
    """
    try:
        manager = _get_manager()
        if manager is None:
            return {}, {}

        # Build guid→number from the registry-ordered list so numbers match Task View order.
        ordered_guids = _get_registry_desktop_order()
        guid_to_number: dict[str, int] = (
            {g: i + 1 for i, g in enumerate(ordered_guids)} if ordered_guids else {}
        )

        # Read the current desktop GUID once — avoids one COM call per window.
        current_guid = get_current_desktop_guid()

        numbers: dict[int, int] = {}
        is_current: dict[int, bool] = {}
        for hwnd in hwnds:
            try:
                guid = manager.GetWindowDesktopId(hwnd)
                if guid is None:
                    numbers[hwnd] = 0
                    is_current[hwnd] = True
                    continue
                if guid not in guid_to_number:
                    if ordered_guids is not None:
                        # Ghost window on a desktop that no longer exists — exclude it.
                        numbers[hwnd] = -1
                        is_current[hwnd] = False
                        continue
                    guid_to_number[guid] = len(guid_to_number) + 1
                numbers[hwnd] = guid_to_number[guid]
                is_current[hwnd] = (guid == current_guid) if current_guid is not None else True
            except Exception:
                numbers[hwnd] = 0
                is_current[hwnd] = True
        return numbers, is_current
    except Exception:
        return {}, {}
