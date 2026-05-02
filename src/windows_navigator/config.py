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
    DOUBLE_TAP_SHIFT = "double_tap_shift"
    WIN_ALT_SPACE = "win_alt_space"
    CTRL_SHIFT_SPACE = "ctrl_shift_space"
    CTRL_DOUBLE_TAP_SHIFT = "ctrl_double_tap_shift"
    SHIFT_DOUBLE_TAP_CTRL = "shift_double_tap_ctrl"


def _config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else (Path.home() / ".config")
    return base / "windows-navigator" / "config.toml"


def _load_raw() -> dict:
    """Read the config file and return its contents as a dict. Returns {} on any error."""
    try:
        with open(_config_path(), "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        log.warning("Failed to parse config from %s", _config_path(), exc_info=True)
        return {}


def _save_raw(data: dict) -> None:
    """Write config dict back to the TOML file. Only str and bool values are supported."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}\n")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"\n')
        else:
            log.warning(
                "Skipping unsupported config key %r with type %s", key, type(value).__name__
            )
    path.write_text("".join(lines), encoding="utf-8")


def load_hotkey() -> HotkeyChoice:
    try:
        return HotkeyChoice(_load_raw().get("hotkey", HotkeyChoice.DOUBLE_TAP_CTRL.value))
    except Exception:
        return HotkeyChoice.DOUBLE_TAP_CTRL


def save_hotkey(choice: HotkeyChoice) -> None:
    data = _load_raw()
    data["hotkey"] = choice.value
    _save_raw(data)


def load_expand_on_startup() -> bool:
    return bool(_load_raw().get("expand_on_startup", False))


def save_expand_on_startup(value: bool) -> None:
    data = _load_raw()
    data["expand_on_startup"] = value
    _save_raw(data)
