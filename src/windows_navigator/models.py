"""Shared data model for a window entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    icon: Image | None = field(default=None, repr=False)
    desktop_number: int = 0  # 1-based; 0 = unknown
    is_current_desktop: bool = True  # False if on a different virtual desktop
    has_notification: bool = False


@dataclass
class TabInfo:
    name: str
    hwnd: int  # parent window hwnd
    index: int  # 0-based position in parent's TabItem list; used to re-fetch on select
    domain: str = ""
    icon: Image | None = field(default=None, repr=False)
    is_active: bool = False  # True if this is the currently selected tab
