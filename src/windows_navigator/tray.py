"""System tray icon using pystray."""

from __future__ import annotations

from typing import Callable

from PIL import Image, ImageDraw

from windows_navigator.theme import DESKTOP_COLORS as _DESKTOP_COLORS

_ICON_SIZE = 64
_font_cache: dict[int, object | None] = {}


def _make_tray_icon(desktop_number: int) -> Image.Image:
    if desktop_number > 0:
        r, g, b = _DESKTOP_COLORS[(desktop_number - 1) % len(_DESKTOP_COLORS)]
    else:
        r, g, b = 60, 60, 60

    img = Image.new("RGBA", (_ICON_SIZE, _ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (_ICON_SIZE - 1, _ICON_SIZE - 1)], fill=(r, g, b, 255))

    label = str(desktop_number) if desktop_number > 0 else "W"
    font_size = 28 if len(label) > 1 else 36
    font = _load_font(font_size)

    if font is not None:
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (_ICON_SIZE - tw) // 2 - bbox[0]
        y = (_ICON_SIZE - th) // 2 - bbox[1]
        draw.text((x, y), label, fill=(255, 255, 255, 255), font=font)
    else:
        draw.text((20, 18), label, fill=(255, 255, 255, 255))

    return img


def _load_font(size: int) -> object | None:
    if size in _font_cache:
        return _font_cache[size]
    from PIL import ImageFont
    for name in (
        "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
        "arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
    ):
        try:
            font = ImageFont.truetype(name, size)
            _font_cache[size] = font
            return font
        except Exception:
            pass
    try:
        font = ImageFont.load_default(size=size)
        _font_cache[size] = font
        return font
    except Exception:
        _font_cache[size] = None
        return None


class TrayIcon:
    def __init__(self, on_exit: Callable[[], None], on_settings: Callable[[], None]) -> None:
        self._on_exit = on_exit
        self._on_settings = on_settings
        self._icon = None

    def start(self, desktop_number: int = 0) -> None:
        import pystray

        img = _make_tray_icon(desktop_number)
        menu = pystray.Menu(
            pystray.MenuItem("Windows Navigator", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self._do_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._do_exit),
        )
        self._icon = pystray.Icon("windows-navigator", img, "Windows Navigator", menu)
        self._icon.run_detached()

    def update(self, desktop_number: int) -> None:
        if self._icon is not None:
            self._icon.icon = _make_tray_icon(desktop_number)

    def stop(self) -> None:
        if self._icon is not None:
            self._icon.stop()
            self._icon = None

    def _do_settings(self) -> None:
        self._on_settings()

    def _do_exit(self) -> None:
        self.stop()
        self._on_exit()
