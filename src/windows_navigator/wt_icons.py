"""Windows Terminal per-profile icon resolution for tab rows.

Reads the first Windows Terminal settings.json found (stable → preview → unpackaged),
builds a case-folded profile-name → 16×16 PIL image map, and caches it until the
settings file is modified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

_ICON_SIZE = 16

# Maps the Windows Terminal "source" field of dynamic profiles to a fallback exe name.
_WT_SOURCE_EXE: dict[str, str] = {
    "Windows.Terminal.Wsl": "wsl.exe",
    "Windows.Terminal.PowershellCore": "pwsh.exe",
    "Windows.Terminal.Azure": "",
}

# Module-level mtime-keyed cache; _UNSET marks the settings path as not yet searched.
_UNSET: object = object()
_settings_file: Path | None | object = _UNSET
_profile_cache: tuple[float, dict[str, Image | None]] | None = None  # (mtime, map)


# ---------------------------------------------------------------------------
# Settings discovery
# ---------------------------------------------------------------------------


_WT_PKG = "Microsoft.WindowsTerminal_8wekyb3d8bbwe"
_WT_PREVIEW_PKG = "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe"


def _candidate_settings_paths() -> list[Path]:
    appdata = os.environ.get("LOCALAPPDATA", "")
    if not appdata:
        return []
    base = Path(appdata)
    return [
        base / "Packages" / _WT_PKG / "LocalState" / "settings.json",
        base / "Packages" / _WT_PREVIEW_PKG / "LocalState" / "settings.json",
        base / "Microsoft" / "Windows Terminal" / "settings.json",
    ]


def _find_settings() -> Path | None:
    for p in _candidate_settings_paths():
        if p.exists():
            return p
    return None


def _load_profiles_from(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        profiles = data.get("profiles", {})
        if isinstance(profiles, dict):
            return profiles.get("list", [])
        if isinstance(profiles, list):
            return profiles
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Icon path resolution
# ---------------------------------------------------------------------------


def _resolve_icon_path(icon_str: str, settings_dir: Path) -> Path | None:
    """Resolve an icon string to a filesystem Path.

    Handles absolute paths, paths relative to *settings_dir*, and the
    ms-appdata:///roaming/ scheme (maps to the package RoamingState directory).
    Returns None for ms-appx:// resources and missing files.
    """
    if not icon_str or icon_str.startswith("ms-appx://"):
        return None
    if icon_str.startswith("ms-appdata:///roaming/"):
        rel = icon_str[len("ms-appdata:///roaming/"):]
        # RoamingState is a sibling of LocalState (the settings dir)
        roaming = settings_dir.parent / "RoamingState" / rel
        return roaming if roaming.exists() else None
    p = Path(icon_str)
    if not p.is_absolute():
        p = settings_dir / p
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Icon loading helpers
# ---------------------------------------------------------------------------


def _load_image_from_path(path: Path) -> Image | None:
    try:
        from PIL import Image  # deferred — unavailable on non-Pillow installs
        img = Image.open(path).convert("RGBA")
        return img.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)
    except Exception:
        return None


def _hicon_to_pil(hicon: int, size: int) -> Image | None:
    """Render a Win32 HICON into a PIL Image using GDI. Returns None on any failure."""
    try:
        import ctypes
        import ctypes.wintypes

        from PIL import Image as PILImage

        class _BIH(ctypes.Structure):
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

        bmih = _BIH()
        bmih.biSize = ctypes.sizeof(_BIH)
        bmih.biWidth = size
        bmih.biHeight = -size  # negative = top-down DIB
        bmih.biPlanes = 1
        bmih.biBitCount = 32
        bmih.biCompression = 0  # BI_RGB

        hdc_screen = ctypes.windll.user32.GetDC(0)  # type: ignore[attr-defined]
        pixels_ptr = ctypes.c_void_p()
        hbmp = ctypes.windll.gdi32.CreateDIBSection(  # type: ignore[attr-defined]
            hdc_screen, ctypes.byref(bmih), 0, ctypes.byref(pixels_ptr), None, 0
        )
        ctypes.windll.user32.ReleaseDC(0, hdc_screen)  # type: ignore[attr-defined]
        if not hbmp or not pixels_ptr.value:
            return None

        hdc_mem = ctypes.windll.gdi32.CreateCompatibleDC(None)  # type: ignore[attr-defined]
        old_bmp = ctypes.windll.gdi32.SelectObject(hdc_mem, hbmp)  # type: ignore[attr-defined]
        DI_NORMAL = 0x0003
        ctypes.windll.user32.DrawIconEx(  # type: ignore[attr-defined]
            hdc_mem, 0, 0, hicon, size, size, 0, 0, DI_NORMAL
        )

        buf = (ctypes.c_ubyte * (size * size * 4))()
        ctypes.memmove(buf, pixels_ptr.value, size * size * 4)

        ctypes.windll.gdi32.SelectObject(hdc_mem, old_bmp)  # type: ignore[attr-defined]
        ctypes.windll.gdi32.DeleteDC(hdc_mem)  # type: ignore[attr-defined]
        ctypes.windll.gdi32.DeleteObject(hbmp)  # type: ignore[attr-defined]

        return PILImage.frombuffer("RGBA", (size, size), bytes(buf), "raw", "BGRA", 0, 1)
    except Exception:
        return None


def _icon_from_exe(exe: str, size: int = _ICON_SIZE) -> Image | None:
    """Return a *size*×*size* PIL image for *exe* via SHGetFileInfoW, or None on failure.

    Unlike IconExtractor.extract, this function returns None rather than a grey
    fallback square when no icon is found, so callers can try other sources.
    """
    if not exe:
        return None
    try:
        import ctypes
        import ctypes.wintypes

        class _SHFI(ctypes.Structure):
            _fields_ = [
                ("hIcon", ctypes.wintypes.HANDLE),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", ctypes.c_ulong),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80),
            ]

        SHGFI_ICON = 0x100
        SHGFI_SMALLICON = 0x1
        shfi = _SHFI()
        if not ctypes.windll.shell32.SHGetFileInfoW(  # type: ignore[attr-defined]
            exe, 0, ctypes.byref(shfi), ctypes.sizeof(shfi), SHGFI_ICON | SHGFI_SMALLICON
        ):
            return None
        hicon = int(shfi.hIcon)
        if not hicon:
            return None
        img = _hicon_to_pil(hicon, size)
        ctypes.windll.user32.DestroyIcon(hicon)  # type: ignore[attr-defined]
        return img
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Profile map
# ---------------------------------------------------------------------------


def _exe_from_commandline(cmdline: str) -> str:
    """Extract the executable name/path from a Windows Terminal commandline string."""
    if not cmdline:
        return ""
    cmdline = os.path.expandvars(cmdline.strip())
    if cmdline.startswith('"'):
        end = cmdline.find('"', 1)
        return cmdline[1:end] if end > 0 else cmdline[1:]
    parts = cmdline.split()
    return parts[0] if parts else ""


def _build_profile_map(settings_path: Path) -> dict[str, Image | None]:
    """Build a case-folded profile-name → icon image map from *settings_path*."""
    profiles = _load_profiles_from(settings_path)
    settings_dir = settings_path.parent
    result: dict[str, Image | None] = {}
    for profile in profiles:
        name: str = profile.get("name", "")
        if not name:
            continue
        icon_str: str = profile.get("icon", "")
        img: Image | None = None

        if icon_str:
            icon_path = _resolve_icon_path(icon_str, settings_dir)
            if icon_path:
                img = _load_image_from_path(icon_path)

        if img is None:
            cmdline = profile.get("commandline", "")
            source = profile.get("source", "")
            exe = _exe_from_commandline(cmdline) if cmdline else _WT_SOURCE_EXE.get(source, "")
            if exe:
                img = _icon_from_exe(exe)

        result[name.casefold()] = img
    return result


def _get_profile_map() -> dict[str, Image | None]:
    """Return the profile map, rebuilding it when the settings file mtime changes."""
    global _settings_file, _profile_cache

    if _settings_file is _UNSET:
        _settings_file = _find_settings()

    if _settings_file is None:
        return {}

    try:
        mtime = _settings_file.stat().st_mtime
    except OSError:
        return {}

    if _profile_cache is not None and _profile_cache[0] == mtime:
        return _profile_cache[1]

    profile_map = _build_profile_map(_settings_file)
    _profile_cache = (mtime, profile_map)
    return profile_map


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_wt_tab_icon(tab_name: str) -> Image | None:
    """Return a 16×16 PIL image for the Windows Terminal tab named *tab_name*, or None.

    Matching strategy (in order):
    1. Exact case-folded match against a profile name.
    2. Delimiter-aware prefix match: tab title begins with "<profile>: " or "<profile> - ".
       This covers Windows Terminal's default title format when a process is running.
    """
    try:
        profile_map = _get_profile_map()
        if not profile_map:
            return None
        key = tab_name.casefold()
        if key in profile_map:
            return profile_map[key]
        for pname, img in profile_map.items():
            if key.startswith(pname + ": ") or key.startswith(pname + " - "):
                return img
        return None
    except Exception:
        return None
