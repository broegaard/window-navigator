"""Tests for wt_icons.py — Windows Terminal per-profile icon resolution."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import windows_navigator.wt_icons as _wt_mod
from windows_navigator.wt_icons import (
    _build_profile_map,
    _exe_from_commandline,
    _load_profiles_from,
    _resolve_icon_path,
    fetch_wt_tab_icon,
)

# ---------------------------------------------------------------------------
# _exe_from_commandline
# ---------------------------------------------------------------------------


def test_exe_from_commandline_bare():
    assert _exe_from_commandline("cmd.exe") == "cmd.exe"


def test_exe_from_commandline_with_args():
    assert _exe_from_commandline("wsl.exe -d Ubuntu") == "wsl.exe"


def test_exe_from_commandline_quoted_path():
    assert (
        _exe_from_commandline('"C:\\path with space\\cmd.exe" /k') == "C:\\path with space\\cmd.exe"
    )


def test_exe_from_commandline_quoted_no_close():
    # Malformed — missing closing quote; returns rest of string after opening quote
    result = _exe_from_commandline('"no-close')
    assert result == "no-close"


def test_exe_from_commandline_empty():
    assert _exe_from_commandline("") == ""


def test_exe_from_commandline_whitespace_only():
    assert _exe_from_commandline("   ") == ""


def test_exe_from_commandline_expands_env_vars(tmp_path):
    # %VAR% expansion only works on Windows; skip on Linux
    if sys.platform != "win32":
        pytest.skip("Windows env-var syntax only")
    with patch.dict(os.environ, {"MY_TEST_DIR": str(tmp_path)}):
        result = _exe_from_commandline("%MY_TEST_DIR%\\shell.exe --flag")
    assert result == str(tmp_path / "shell.exe")


# ---------------------------------------------------------------------------
# _resolve_icon_path
# ---------------------------------------------------------------------------



def test_resolve_icon_path_msappx_returns_none(tmp_path):
    assert _resolve_icon_path("ms-appx:///ProfileIcons/{guid}.png", tmp_path) is None


def test_resolve_icon_path_empty_returns_none(tmp_path):
    assert _resolve_icon_path("", tmp_path) is None


def test_resolve_icon_path_absolute_existing(tmp_path):
    f = tmp_path / "icon.png"
    f.write_bytes(b"")
    assert _resolve_icon_path(str(f), tmp_path) == f


def test_resolve_icon_path_absolute_missing(tmp_path):
    assert _resolve_icon_path(str(tmp_path / "no.png"), tmp_path) is None


def test_resolve_icon_path_relative_existing(tmp_path):
    f = tmp_path / "LocalState" / "icon.png"
    f.parent.mkdir()
    f.write_bytes(b"")
    settings_dir = f.parent
    assert _resolve_icon_path("icon.png", settings_dir) == f


def test_resolve_icon_path_relative_missing(tmp_path):
    assert _resolve_icon_path("missing.png", tmp_path) is None


def test_resolve_icon_path_msappdata_roaming_existing(tmp_path):
    # Simulate .../Packages/<pkg>/LocalState/settings.json → RoamingState/icon.png
    local_state = tmp_path / "LocalState"
    roaming = tmp_path / "RoamingState"
    local_state.mkdir()
    roaming.mkdir()
    icon = roaming / "icon.png"
    icon.write_bytes(b"")
    result = _resolve_icon_path("ms-appdata:///roaming/icon.png", local_state)
    assert result == icon


def test_resolve_icon_path_msappdata_roaming_missing(tmp_path):
    local_state = tmp_path / "LocalState"
    local_state.mkdir()
    (tmp_path / "RoamingState").mkdir()
    result = _resolve_icon_path("ms-appdata:///roaming/absent.png", local_state)
    assert result is None


# ---------------------------------------------------------------------------
# _load_profiles_from
# ---------------------------------------------------------------------------



def test_load_profiles_from_list_format(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [{"name": "PowerShell"}]}}),
        encoding="utf-8",
    )
    result = _load_profiles_from(settings)
    assert result == [{"name": "PowerShell"}]


def test_load_profiles_from_flat_list(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": [{"name": "cmd"}]}),
        encoding="utf-8",
    )
    result = _load_profiles_from(settings)
    assert result == [{"name": "cmd"}]


def test_load_profiles_from_missing_file(tmp_path):
    assert _load_profiles_from(tmp_path / "absent.json") == []


def test_load_profiles_from_bom(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"profiles": {"list": [{"name": "cmd"}]}}).encode()
    )
    result = _load_profiles_from(settings)
    assert result == [{"name": "cmd"}]


# ---------------------------------------------------------------------------
# _build_profile_map
# ---------------------------------------------------------------------------



def test_build_profile_map_file_icon(tmp_path):
    icon_file = tmp_path / "myicon.png"
    icon_file.write_bytes(b"")

    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [
            {"name": "MyShell", "icon": str(icon_file)}
        ]}}),
        encoding="utf-8",
    )

    mock_img = MagicMock()
    with patch("windows_navigator.wt_icons._load_image_from_path", return_value=mock_img):
        result = _build_profile_map(settings)

    assert result["myshell"] is mock_img


def test_build_profile_map_commandline_fallback(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [
            {"name": "PowerShell", "commandline": "pwsh.exe"}
        ]}}),
        encoding="utf-8",
    )

    mock_img = MagicMock()
    with patch("windows_navigator.wt_icons._icon_from_exe", return_value=mock_img):
        result = _build_profile_map(settings)

    assert result["powershell"] is mock_img


def test_build_profile_map_source_fallback_wsl(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [
            {"name": "Ubuntu", "source": "Windows.Terminal.Wsl"}
        ]}}),
        encoding="utf-8",
    )

    mock_img = MagicMock()
    with patch("windows_navigator.wt_icons._icon_from_exe", return_value=mock_img) as mock_fn:
        result = _build_profile_map(settings)

    assert result["ubuntu"] is mock_img
    mock_fn.assert_called_once_with("wsl.exe")


def test_build_profile_map_msappx_falls_back_to_commandline(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [
            {"name": "Windows PowerShell",
             "icon": "ms-appx:///ProfileIcons/{guid}.png",
             "commandline": "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"}
        ]}}),
        encoding="utf-8",
    )

    mock_img = MagicMock()
    with (
        patch("windows_navigator.wt_icons._load_image_from_path") as mock_load,
        patch("windows_navigator.wt_icons._icon_from_exe", return_value=mock_img),
    ):
        result = _build_profile_map(settings)

    # ms-appx is skipped so _load_image_from_path should not be called
    mock_load.assert_not_called()
    assert result["windows powershell"] is mock_img


def test_build_profile_map_skips_profiles_without_name(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [{"commandline": "cmd.exe"}]}}),
        encoding="utf-8",
    )
    result = _build_profile_map(settings)
    assert result == {}


def test_build_profile_map_icon_load_failure_falls_back_to_exe(tmp_path):
    icon_file = tmp_path / "icon.png"
    icon_file.write_bytes(b"")
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [
            {"name": "MyShell", "icon": str(icon_file), "commandline": "myshell.exe"}
        ]}}),
        encoding="utf-8",
    )

    mock_img = MagicMock()
    with (
        patch("windows_navigator.wt_icons._load_image_from_path", return_value=None),
        patch("windows_navigator.wt_icons._icon_from_exe", return_value=mock_img),
    ):
        result = _build_profile_map(settings)

    assert result["myshell"] is mock_img


# ---------------------------------------------------------------------------
# fetch_wt_tab_icon
# ---------------------------------------------------------------------------



def _mock_profile_map(profiles: dict) -> MagicMock:
    return profiles


def test_fetch_wt_tab_icon_exact_match():
    mock_img = MagicMock()
    with patch(
        "windows_navigator.wt_icons._get_profile_map", return_value={"powershell": mock_img}
    ):
        assert fetch_wt_tab_icon("PowerShell") is mock_img


def test_fetch_wt_tab_icon_exact_match_case_insensitive():
    mock_img = MagicMock()
    with patch("windows_navigator.wt_icons._get_profile_map", return_value={"ubuntu": mock_img}):
        assert fetch_wt_tab_icon("UBUNTU") is mock_img


def test_fetch_wt_tab_icon_delimiter_colon_prefix():
    mock_img = MagicMock()
    with patch(
        "windows_navigator.wt_icons._get_profile_map",
        return_value={"windows powershell": mock_img},
    ):
        assert fetch_wt_tab_icon("Windows PowerShell: C:\\Users\\dev") is mock_img


def test_fetch_wt_tab_icon_delimiter_dash_prefix():
    mock_img = MagicMock()
    with patch(
        "windows_navigator.wt_icons._get_profile_map",
        return_value={"ubuntu": mock_img},
    ):
        assert fetch_wt_tab_icon("ubuntu - /home/dev") is mock_img


def test_fetch_wt_tab_icon_no_match_returns_none():
    with patch(
        "windows_navigator.wt_icons._get_profile_map",
        return_value={"powershell": MagicMock()},
    ):
        assert fetch_wt_tab_icon("vim") is None


def test_fetch_wt_tab_icon_substring_does_not_match():
    """'ps' should not match 'powershell' via substring — only exact and delimited prefix."""
    mock_img = MagicMock()
    with patch(
        "windows_navigator.wt_icons._get_profile_map",
        return_value={"ps": mock_img},
    ):
        # "powershell" contains "ps" but that should NOT match
        assert fetch_wt_tab_icon("powershell: ~") is None


def test_fetch_wt_tab_icon_empty_map_returns_none():
    with patch("windows_navigator.wt_icons._get_profile_map", return_value={}):
        assert fetch_wt_tab_icon("anything") is None


def test_fetch_wt_tab_icon_exception_returns_none():
    with patch("windows_navigator.wt_icons._get_profile_map", side_effect=RuntimeError("oops")):
        assert fetch_wt_tab_icon("PowerShell") is None


# ---------------------------------------------------------------------------
# _get_profile_map — mtime invalidation
# ---------------------------------------------------------------------------



def test_get_profile_map_rebuilds_on_mtime_change(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"profiles": {"list": [{"name": "Shell", "commandline": "sh.exe"}]}}),
        encoding="utf-8",
    )

    first_img = MagicMock()
    second_img = MagicMock()

    with (
        patch("windows_navigator.wt_icons._find_settings", return_value=settings),
        patch("windows_navigator.wt_icons._icon_from_exe", return_value=first_img),
    ):
        # Reset module-level cache state
        _wt_mod._profile_map = None
        _wt_mod._settings_mtime = 0.0
        _wt_mod._settings_file = None
        _wt_mod._settings_file_checked = False

        map1 = _wt_mod._get_profile_map()
        assert map1["shell"] is first_img

        # Simulate mtime change by manually bumping the cached mtime
        _wt_mod._settings_mtime = _wt_mod._settings_mtime - 1.0

        with patch("windows_navigator.wt_icons._icon_from_exe", return_value=second_img):
            map2 = _wt_mod._get_profile_map()

    assert map2["shell"] is second_img


def test_get_profile_map_returns_empty_when_no_settings():
    _wt_mod._profile_map = None
    _wt_mod._settings_file = None
    _wt_mod._settings_file_checked = False

    with patch("windows_navigator.wt_icons._find_settings", return_value=None):
        result = _wt_mod._get_profile_map()

    assert result == {}
