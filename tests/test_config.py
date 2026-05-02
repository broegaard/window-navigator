"""Tests for config.py — HotkeyChoice, load_hotkey, save_hotkey, _config_path."""

import os
from pathlib import Path
from unittest.mock import patch

from windows_navigator.config import (
    HotkeyChoice,
    _config_path,
    load_expand_on_startup,
    load_hotkey,
    save_expand_on_startup,
    save_hotkey,
)

# ---------------------------------------------------------------------------
# _config_path
# ---------------------------------------------------------------------------


def test_config_path_uses_appdata_env_var(tmp_path):
    with patch.dict(os.environ, {"APPDATA": str(tmp_path)}):
        result = _config_path()
    assert result == tmp_path / "windows-navigator" / "config.toml"


def test_config_path_falls_back_to_home_config_without_appdata(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    result = _config_path()
    assert result == Path.home() / ".config" / "windows-navigator" / "config.toml"


# ---------------------------------------------------------------------------
# load_hotkey — defaults
# ---------------------------------------------------------------------------


def test_load_hotkey_returns_default_when_file_missing(tmp_path):
    missing = tmp_path / "no-such-dir" / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=missing):
        result = load_hotkey()
    assert result == HotkeyChoice.DOUBLE_TAP_CTRL


def test_load_hotkey_returns_default_when_key_absent_from_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[general]\nsome_other_key = "value"\n')
    with patch("windows_navigator.config._config_path", return_value=cfg):
        result = load_hotkey()
    assert result == HotkeyChoice.DOUBLE_TAP_CTRL


def test_load_hotkey_returns_default_on_invalid_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("this is not valid toml }{[]")
    with patch("windows_navigator.config._config_path", return_value=cfg):
        result = load_hotkey()
    assert result == HotkeyChoice.DOUBLE_TAP_CTRL


def test_load_hotkey_returns_default_on_unknown_enum_value(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('hotkey = "totally_unknown_value"\n')
    with patch("windows_navigator.config._config_path", return_value=cfg):
        result = load_hotkey()
    assert result == HotkeyChoice.DOUBLE_TAP_CTRL


# ---------------------------------------------------------------------------
# load_hotkey — all valid values
# ---------------------------------------------------------------------------


def test_load_hotkey_double_tap_ctrl(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('hotkey = "double_tap_ctrl"\n')
    with patch("windows_navigator.config._config_path", return_value=cfg):
        assert load_hotkey() == HotkeyChoice.DOUBLE_TAP_CTRL


def test_load_hotkey_win_alt_space(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('hotkey = "win_alt_space"\n')
    with patch("windows_navigator.config._config_path", return_value=cfg):
        assert load_hotkey() == HotkeyChoice.WIN_ALT_SPACE


def test_load_hotkey_ctrl_shift_space(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('hotkey = "ctrl_shift_space"\n')
    with patch("windows_navigator.config._config_path", return_value=cfg):
        assert load_hotkey() == HotkeyChoice.CTRL_SHIFT_SPACE


def test_load_hotkey_ctrl_double_tap_shift(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('hotkey = "ctrl_double_tap_shift"\n')
    with patch("windows_navigator.config._config_path", return_value=cfg):
        assert load_hotkey() == HotkeyChoice.CTRL_DOUBLE_TAP_SHIFT


# ---------------------------------------------------------------------------
# save_hotkey
# ---------------------------------------------------------------------------


def test_save_hotkey_writes_correct_content(tmp_path):
    cfg = tmp_path / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_hotkey(HotkeyChoice.WIN_ALT_SPACE)
    assert cfg.read_text(encoding="utf-8") == 'hotkey = "win_alt_space"\n'


def test_save_hotkey_creates_parent_directory(tmp_path):
    cfg = tmp_path / "nested" / "deep" / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_hotkey(HotkeyChoice.DOUBLE_TAP_CTRL)
    assert cfg.exists()


def test_save_hotkey_all_values_produce_valid_toml(tmp_path):
    import tomllib

    for choice in HotkeyChoice:
        cfg = tmp_path / f"{choice.value}.toml"
        with patch("windows_navigator.config._config_path", return_value=cfg):
            save_hotkey(choice)
        with open(cfg, "rb") as f:
            data = tomllib.load(f)
        assert data["hotkey"] == choice.value


def test_save_then_load_roundtrip(tmp_path):
    cfg = tmp_path / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_hotkey(HotkeyChoice.CTRL_SHIFT_SPACE)
        result = load_hotkey()
    assert result == HotkeyChoice.CTRL_SHIFT_SPACE


def test_save_hotkey_preserves_other_keys(tmp_path):
    """save_hotkey must not erase unrelated keys already in the config file."""
    cfg = tmp_path / "config.toml"
    cfg.write_text('expand_on_startup = true\nhotkey = "double_tap_ctrl"\n', encoding="utf-8")
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_hotkey(HotkeyChoice.WIN_ALT_SPACE)
        assert load_hotkey() == HotkeyChoice.WIN_ALT_SPACE
        assert load_expand_on_startup() is True


# ---------------------------------------------------------------------------
# HotkeyChoice enum
# ---------------------------------------------------------------------------


def test_hotkey_choice_values_are_strings():
    for choice in HotkeyChoice:
        assert isinstance(choice.value, str)


def test_hotkey_choice_all_members_present():
    names = {c.name for c in HotkeyChoice}
    assert names == {
        "DOUBLE_TAP_CTRL",
        "DOUBLE_TAP_SHIFT",
        "WIN_ALT_SPACE",
        "CTRL_SHIFT_SPACE",
        "CTRL_DOUBLE_TAP_SHIFT",
        "SHIFT_DOUBLE_TAP_CTRL",
    }


# ---------------------------------------------------------------------------
# load_expand_on_startup / save_expand_on_startup
# ---------------------------------------------------------------------------


def test_load_expand_on_startup_returns_false_when_file_missing(tmp_path):
    missing = tmp_path / "no-such-dir" / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=missing):
        assert load_expand_on_startup() is False


def test_load_expand_on_startup_returns_false_when_key_absent(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('hotkey = "double_tap_ctrl"\n', encoding="utf-8")
    with patch("windows_navigator.config._config_path", return_value=cfg):
        assert load_expand_on_startup() is False


def test_load_expand_on_startup_returns_true_when_set(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("expand_on_startup = true\n", encoding="utf-8")
    with patch("windows_navigator.config._config_path", return_value=cfg):
        assert load_expand_on_startup() is True


def test_save_expand_on_startup_roundtrip_true(tmp_path):
    cfg = tmp_path / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_expand_on_startup(True)
        assert load_expand_on_startup() is True


def test_save_expand_on_startup_roundtrip_false(tmp_path):
    cfg = tmp_path / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_expand_on_startup(False)
        assert load_expand_on_startup() is False


def test_save_expand_on_startup_preserves_hotkey(tmp_path):
    """save_expand_on_startup must not erase the hotkey."""
    cfg = tmp_path / "config.toml"
    with patch("windows_navigator.config._config_path", return_value=cfg):
        save_hotkey(HotkeyChoice.CTRL_SHIFT_SPACE)
        save_expand_on_startup(True)
        assert load_hotkey() == HotkeyChoice.CTRL_SHIFT_SPACE
        assert load_expand_on_startup() is True
