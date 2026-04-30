"""User configuration stored in a TOML file."""
from __future__ import annotations

import logging
import os
import tomllib
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)


class HotkeyChoice(str, Enum):
    DOUBLE_TAP_CTRL = "double_tap_ctrl"
    WIN_ALT_SPACE = "win_alt_space"
    CTRL_SHIFT_SPACE = "ctrl_shift_space"
    CTRL_DOUBLE_TAP_SHIFT = "ctrl_double_tap_shift"
    SHIFT_DOUBLE_TAP_CTRL = "shift_double_tap_ctrl"


def _config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else (Path.home() / ".config")
    return base / "windows-navigator" / "config.toml"


def load_hotkey() -> HotkeyChoice:
    try:
        with open(_config_path(), "rb") as f:
            data = tomllib.load(f)
        return HotkeyChoice(data.get("hotkey", HotkeyChoice.DOUBLE_TAP_CTRL.value))
    except FileNotFoundError:
        return HotkeyChoice.DOUBLE_TAP_CTRL
    except Exception:
        log.warning("Failed to load config from %s", _config_path(), exc_info=True)
        return HotkeyChoice.DOUBLE_TAP_CTRL


def save_hotkey(choice: HotkeyChoice) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'hotkey = "{choice.value}"\n', encoding="utf-8")
