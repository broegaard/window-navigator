"""Tests for tabs.py — UIA tab discovery helpers."""

from unittest.mock import MagicMock, patch

from windows_navigator.models import TabInfo
import json

import windows_navigator.tabs as tabs_module
from windows_navigator.tabs import (
    _cache_file_path,
    _load_tab_domain_cache,
    _save_tab_domain_cache,
    _UIA_DocumentControlTypeId,
    _UIA_EditControlTypeId,
    _UIA_FullDescriptionPropertyId,
    _UIA_LegacyIAccessibleStatePropertyId,
    _UIA_SelectionItemIsSelectedPropertyId,
    _UIA_TabItemControlTypeId,
    _STATE_SYSTEM_SELECTED,
    _collect_tab_items,
    _domain_from_full_description,
    _domain_from_url,
    _find_address_bar_url,
    _get_children,
    _is_tab_selected,
    fetch_tabs,
    select_tab,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_tab_item_control_type_id():
    assert _UIA_TabItemControlTypeId == 50019


def test_document_control_type_id():
    assert _UIA_DocumentControlTypeId == 50030


# ---------------------------------------------------------------------------
# fetch_tabs / select_tab — Linux fallback (comtypes unavailable)
# ---------------------------------------------------------------------------


def test_fetch_tabs_returns_empty_without_comtypes():
    result = fetch_tabs(12345)
    assert result == []


def test_select_tab_is_silent_without_comtypes():
    tab = TabInfo(name="Tab", hwnd=123, index=0)
    select_tab(tab)  # must not raise


# ---------------------------------------------------------------------------
# _get_children
# ---------------------------------------------------------------------------


def test_get_children_returns_elements():
    child1, child2 = MagicMock(), MagicMock()
    col = MagicMock()
    col.Length = 2
    col.GetElement.side_effect = [child1, child2]
    element = MagicMock()
    element.FindAll.return_value = col
    uia = MagicMock()

    result = _get_children(element, uia)
    assert result == [child1, child2]


def test_get_children_returns_empty_list_on_find_all_exception():
    element = MagicMock()
    element.FindAll.side_effect = OSError("COM error")
    result = _get_children(element, MagicMock())
    assert result == []


def test_get_children_returns_empty_when_length_zero():
    col = MagicMock()
    col.Length = 0
    element = MagicMock()
    element.FindAll.return_value = col
    result = _get_children(element, MagicMock())
    assert result == []


# ---------------------------------------------------------------------------
# _collect_tab_items
# ---------------------------------------------------------------------------


def test_collect_tab_items_returns_self_when_tab_item():
    element = MagicMock()
    element.GetCurrentPropertyValue.return_value = _UIA_TabItemControlTypeId
    result = _collect_tab_items(element, MagicMock())
    assert result == [element]


def test_collect_tab_items_returns_empty_for_document_node():
    element = MagicMock()
    element.GetCurrentPropertyValue.return_value = _UIA_DocumentControlTypeId
    result = _collect_tab_items(element, MagicMock())
    assert result == []


def test_collect_tab_items_returns_empty_when_max_depth_exceeded():
    element = MagicMock()
    result = _collect_tab_items(element, MagicMock(), depth=11, max_depth=10)
    assert result == []
    element.GetCurrentPropertyValue.assert_not_called()


def test_collect_tab_items_recurses_into_children():
    child = MagicMock()
    child.GetCurrentPropertyValue.return_value = _UIA_TabItemControlTypeId

    col = MagicMock()
    col.Length = 1
    col.GetElement.return_value = child

    parent = MagicMock()
    parent.GetCurrentPropertyValue.return_value = 0  # not tab, not document
    parent.FindAll.return_value = col

    uia = MagicMock()
    result = _collect_tab_items(parent, uia)
    assert result == [child]


def test_collect_tab_items_collects_multiple_tab_children():
    tab_a, tab_b = MagicMock(), MagicMock()
    tab_a.GetCurrentPropertyValue.return_value = _UIA_TabItemControlTypeId
    tab_b.GetCurrentPropertyValue.return_value = _UIA_TabItemControlTypeId

    col = MagicMock()
    col.Length = 2
    col.GetElement.side_effect = [tab_a, tab_b]

    parent = MagicMock()
    parent.GetCurrentPropertyValue.return_value = 0
    parent.FindAll.return_value = col

    uia = MagicMock()
    result = _collect_tab_items(parent, uia)
    assert result == [tab_a, tab_b]


def test_collect_tab_items_get_property_exception_falls_through_to_children():
    # GetCurrentPropertyValue raises → except pass → recurse into children.
    # Children return an empty collection so the overall result is [].
    col = MagicMock()
    col.Length = 0

    element = MagicMock()
    element.GetCurrentPropertyValue.side_effect = OSError("COM error")
    element.FindAll.return_value = col

    result = _collect_tab_items(element, MagicMock())
    assert result == []


def test_collect_tab_items_does_not_descend_into_document():
    # A Document child must NOT be recursed into — its sub-tree may contain
    # ARIA tab widgets that look like browser tabs but aren't.
    inner_tab = MagicMock()
    inner_tab.GetCurrentPropertyValue.return_value = _UIA_TabItemControlTypeId

    doc_col = MagicMock()
    doc_col.Length = 1
    doc_col.GetElement.return_value = inner_tab

    document = MagicMock()
    document.GetCurrentPropertyValue.return_value = _UIA_DocumentControlTypeId
    document.FindAll.return_value = doc_col

    outer_col = MagicMock()
    outer_col.Length = 1
    outer_col.GetElement.return_value = document

    root = MagicMock()
    root.GetCurrentPropertyValue.return_value = 0
    root.FindAll.return_value = outer_col

    result = _collect_tab_items(root, MagicMock())
    assert result == []
    inner_tab.GetCurrentPropertyValue.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_tabs / select_tab — happy path with _create_uia patched
# ---------------------------------------------------------------------------


def _make_uia_tree(tab_names: list[str], domains: list[str] | None = None):
    """Return (mock_uia, tab_elements) for a tree whose root has named TabItem children."""
    if domains is None:
        domains = [""] * len(tab_names)
    tab_elements = []
    for name, domain in zip(tab_names, domains):
        el = MagicMock()

        def _prop(prop, _name=name, _domain=domain):
            if prop == 30003:
                return _UIA_TabItemControlTypeId
            if prop == _UIA_FullDescriptionPropertyId:
                return _domain
            return _name

        el.GetCurrentPropertyValue.side_effect = _prop
        tab_elements.append(el)

    col = MagicMock()
    col.Length = len(tab_elements)
    col.GetElement.side_effect = tab_elements

    root = MagicMock()
    root.GetCurrentPropertyValue.return_value = 0  # not a tab, not a document
    root.FindAll.return_value = col

    mock_uia = MagicMock()
    mock_uia.ElementFromHandle.return_value = root

    return mock_uia, tab_elements


def test_fetch_tabs_happy_path_returns_tab_infos():
    mock_uia, _ = _make_uia_tree(["Tab A", "Tab B"])

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        result = fetch_tabs(hwnd=42)

    assert len(result) == 2
    assert result[0].name == "Tab A" and result[0].hwnd == 42 and result[0].index == 0
    assert result[1].name == "Tab B" and result[1].hwnd == 42 and result[1].index == 1


def test_select_tab_happy_path_calls_select():
    mock_uia, tab_elements = _make_uia_tree(["Tab A"])
    mock_pattern = MagicMock()
    tab_elements[0].GetCurrentPattern.return_value = mock_pattern
    mock_uiac = MagicMock()
    mock_comtypes_gen = MagicMock()
    mock_comtypes_gen.UIAutomationClient = mock_uiac

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia), \
         patch.dict("sys.modules", {
             "comtypes": MagicMock(),
             "comtypes.gen": mock_comtypes_gen,
             "comtypes.gen.UIAutomationClient": mock_uiac,
         }):
        select_tab(TabInfo(name="Tab A", hwnd=42, index=0))

    mock_pattern.QueryInterface.return_value.Select.assert_called_once()


def test_fetch_tabs_skips_element_when_name_extraction_raises():
    """If GetCurrentPropertyValue(_UIA_NamePropertyId) raises on one element,
    that element is silently skipped and remaining elements are still collected."""
    tab_ok = MagicMock()
    tab_ok.GetCurrentPropertyValue.side_effect = lambda prop: (
        _UIA_TabItemControlTypeId if prop == 30003 else "Good Tab"
    )
    tab_bad = MagicMock()

    def _bad_side_effect(prop):
        if prop == 30003:
            return _UIA_TabItemControlTypeId
        raise OSError("COM error")

    tab_bad.GetCurrentPropertyValue.side_effect = _bad_side_effect

    col = MagicMock()
    col.Length = 2
    col.GetElement.side_effect = [tab_ok, tab_bad]

    root = MagicMock()
    root.GetCurrentPropertyValue.return_value = 0
    root.FindAll.return_value = col

    mock_uia = MagicMock()
    mock_uia.ElementFromHandle.return_value = root

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        result = fetch_tabs(hwnd=99)

    assert len(result) == 1
    assert result[0].name == "Good Tab"
    assert result[0].hwnd == 99
    assert result[0].index == 0


# ---------------------------------------------------------------------------
# _domain_from_full_description
# ---------------------------------------------------------------------------


def test_domain_from_full_description_returns_hostname():
    assert _domain_from_full_description("github.com") == "github.com"


def test_domain_from_full_description_rejects_free_text():
    assert _domain_from_full_description("local or shared file") == ""


def test_domain_from_full_description_rejects_no_dot():
    assert _domain_from_full_description("localhost") == ""


def test_domain_from_full_description_rejects_empty():
    assert _domain_from_full_description("") == ""
    assert _domain_from_full_description(None) == ""


def test_fetch_tabs_populates_domain():
    mock_uia, _ = _make_uia_tree(["GitHub"], domains=["github.com"])

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        result = fetch_tabs(hwnd=1)

    assert result[0].domain == "github.com"


def test_fetch_tabs_domain_empty_for_local_file():
    mock_uia, _ = _make_uia_tree(["Report.pdf"], domains=["local or shared file"])

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        result = fetch_tabs(hwnd=2)

    assert result[0].domain == ""


# ---------------------------------------------------------------------------
# _domain_from_url
# ---------------------------------------------------------------------------


def test_domain_from_url_extracts_host():
    assert _domain_from_url("https://github.com/foo/bar") == "github.com"


def test_domain_from_url_handles_subdomain():
    assert _domain_from_url("https://docs.github.com/en") == "docs.github.com"


def test_domain_from_url_handles_bare_host_firefox_style():
    # Firefox hides the scheme; URL bar shows "github.com/foo" instead of "https://..."
    assert _domain_from_url("github.com/foo/bar") == "github.com"
    assert _domain_from_url("github.com") == "github.com"


def test_domain_from_url_returns_empty_for_non_url():
    assert _domain_from_url("not a url") == ""
    assert _domain_from_url("") == ""


# ---------------------------------------------------------------------------
# _is_tab_selected
# ---------------------------------------------------------------------------


def _make_tab_el(selection_item_val, legacy_state: int):
    el = MagicMock()

    def _prop(prop):
        if prop == _UIA_SelectionItemIsSelectedPropertyId:
            return selection_item_val
        if prop == _UIA_LegacyIAccessibleStatePropertyId:
            return legacy_state
        return None

    el.GetCurrentPropertyValue.side_effect = _prop
    return el


def test_is_tab_selected_true_via_selection_item():
    el = _make_tab_el(selection_item_val=True, legacy_state=0)
    assert _is_tab_selected(el) is True


def test_is_tab_selected_true_via_legacy_state():
    # SelectionItemIsSelected returns None (unsupported); LegacyIA state has selected bit
    el = _make_tab_el(selection_item_val=None, legacy_state=0x1303C02)
    assert _is_tab_selected(el) is True


def test_is_tab_selected_false_when_neither_set():
    el = _make_tab_el(selection_item_val=None, legacy_state=0x1303C00)
    assert _is_tab_selected(el) is False


def test_is_tab_selected_false_when_selection_item_false():
    el = _make_tab_el(selection_item_val=False, legacy_state=0x1303C00)
    assert _is_tab_selected(el) is False


def test_is_tab_selected_true_via_legacy_ia_pattern():
    # Both properties return None; LegacyIA pattern has the selected state bit set.
    el = MagicMock()
    el.GetCurrentPropertyValue.return_value = None

    mock_ia = MagicMock()
    mock_ia.CurrentState = 0x1303C02  # STATE_SYSTEM_SELECTED bit set
    mock_pattern = MagicMock()
    mock_pattern.QueryInterface.return_value = mock_ia
    el.GetCurrentPattern.return_value = mock_pattern

    mock_uiac = MagicMock()
    with patch.dict("sys.modules", {"comtypes.gen.UIAutomationClient": mock_uiac}):
        result = _is_tab_selected(el)

    assert result is True


# ---------------------------------------------------------------------------
# _find_address_bar_url
# ---------------------------------------------------------------------------


def _make_url_bar_element(url: str, auto_id: str = "urlbar-input"):
    """Return a mock Edit element that looks like a browser URL bar."""
    el = MagicMock()

    def _prop(prop):
        if prop == 30003:  # ControlType
            return _UIA_EditControlTypeId
        if prop == 30011:  # AutomationId
            return auto_id
        if prop == 30012:  # ClassName
            return ""
        if prop == 30045:  # Value
            return url
        return ""

    el.GetCurrentPropertyValue.side_effect = _prop
    # No children
    col = MagicMock()
    col.Length = 0
    el.FindAll.return_value = col
    return el


def test_find_address_bar_url_finds_urlbar_input():
    url_bar = _make_url_bar_element("https://github.com/foo")

    col = MagicMock()
    col.Length = 1
    col.GetElement.return_value = url_bar

    root = MagicMock()
    root.GetCurrentPropertyValue.return_value = 0
    root.FindAll.return_value = col

    result = _find_address_bar_url(root, MagicMock())
    assert result == "https://github.com/foo"


def test_find_address_bar_url_returns_empty_when_not_found():
    col = MagicMock()
    col.Length = 0
    root = MagicMock()
    root.GetCurrentPropertyValue.return_value = 0
    root.FindAll.return_value = col

    result = _find_address_bar_url(root, MagicMock())
    assert result == ""


# ---------------------------------------------------------------------------
# fetch_tabs — Firefox address-bar fallback
# ---------------------------------------------------------------------------


def _make_firefox_tree(tab_names: list[str], active_index: int, active_url: str):
    """Build a mock UIA tree resembling Firefox: tabs have no FullDescription,
    but a URL bar is present as a sibling of the tab strip."""
    tab_elements = []
    for i, name in enumerate(tab_names):
        el = MagicMock()

        def _prop(prop, _name=name, _is_active=(i == active_index)):
            if prop == 30003:  # ControlType
                return _UIA_TabItemControlTypeId
            if prop == 30005:  # Name
                return _name
            if prop == 30159:  # FullDescription — not present in Firefox
                return ""
            if prop == 30079:  # SelectionItemIsSelected — Firefox may not support this
                return None
            if prop == _UIA_LegacyIAccessibleStatePropertyId:  # LegacyIA state
                return 0x1303C02 if _is_active else 0x1303C00
            return ""

        el.GetCurrentPropertyValue.side_effect = _prop
        child_col = MagicMock()
        child_col.Length = 0
        el.FindAll.return_value = child_col
        tab_elements.append(el)

    url_bar = _make_url_bar_element(active_url)

    # root has tab_elements + url_bar as children (via FindAll).
    # Use a lambda so the side_effect is not consumed on the first traversal —
    # fetch_tabs walks the tree twice (collect_tab_items then find_address_bar_url).
    all_children = tab_elements + [url_bar]
    col = MagicMock()
    col.Length = len(all_children)
    col.GetElement.side_effect = lambda i, _c=all_children: _c[i]

    root = MagicMock()
    root.GetCurrentPropertyValue.return_value = 0  # not a tab or document
    root.FindAll.return_value = col

    mock_uia = MagicMock()
    mock_uia.ElementFromHandle.return_value = root

    return mock_uia


def test_fetch_tabs_firefox_fallback_assigns_domain_to_active_tab():
    tabs_module._tab_domain_cache.clear()
    # Firefox URL bar shows bare host+path without scheme
    mock_uia = _make_firefox_tree(
        ["Gmail", "New Tab", "DR News"],
        active_index=2,
        active_url="dr.dk/nyheder",
    )

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        result = fetch_tabs(hwnd=99)

    assert len(result) == 3
    assert result[0].domain == ""
    assert result[1].domain == ""
    assert result[2].domain == "dr.dk"


def test_fetch_tabs_firefox_fallback_no_domain_when_no_url_bar():
    tabs_module._tab_domain_cache.clear()
    mock_uia, _ = _make_uia_tree(["Gmail", "New Tab"])  # no FullDesc, no URL bar

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        result = fetch_tabs(hwnd=99)

    assert all(t.domain == "" for t in result)


# ---------------------------------------------------------------------------
# _tab_domain_cache — inactive-tab domain persistence
# ---------------------------------------------------------------------------


def test_fetch_tabs_domain_cache_stores_active_tab_domain():
    tabs_module._tab_domain_cache.clear()
    mock_uia = _make_firefox_tree(
        ["DR News", "New Tab"],
        active_index=0,
        active_url="www.dr.dk/nyheder",
    )

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia):
        fetch_tabs(hwnd=10)

    assert tabs_module._tab_domain_cache.get("DR News") == "www.dr.dk"


def test_fetch_tabs_domain_cache_restores_domain_for_inactive_tab():
    # First open: DR News is active → domain www.dr.dk stored in cache.
    tabs_module._tab_domain_cache.clear()
    mock_uia_1 = _make_firefox_tree(
        ["DR News", "Gmail"],
        active_index=0,
        active_url="www.dr.dk/nyheder",
    )
    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia_1), \
         patch("windows_navigator.tabs._save_tab_domain_cache"):
        fetch_tabs(hwnd=10)

    # Second open: Gmail is now active. DR News is inactive → no URL bar domain.
    mock_uia_2 = _make_firefox_tree(
        ["DR News", "Gmail"],
        active_index=1,
        active_url="mail.google.com",
    )
    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia_2), \
         patch("windows_navigator.tabs._save_tab_domain_cache"):
        result = fetch_tabs(hwnd=10)

    dr_tab = next(t for t in result if t.name == "DR News")
    gmail_tab = next(t for t in result if t.name == "Gmail")
    assert dr_tab.domain == "www.dr.dk"
    assert gmail_tab.domain == "mail.google.com"


# ---------------------------------------------------------------------------
# _cache_file_path / _load_tab_domain_cache / _save_tab_domain_cache
# ---------------------------------------------------------------------------


def test_cache_file_path_uses_appdata(tmp_path):
    with patch.dict("os.environ", {"APPDATA": str(tmp_path)}):
        path = _cache_file_path()
    assert path == tmp_path / "windows-navigator" / "tab_domain_cache.json"


def test_cache_file_path_falls_back_to_home_config(tmp_path):
    env = {k: v for k, v in __import__("os").environ.items() if k != "APPDATA"}
    with patch.dict("os.environ", env, clear=True), \
         patch("windows_navigator.tabs.Path.home", return_value=tmp_path):
        path = _cache_file_path()
    assert path == tmp_path / ".config" / "windows-navigator" / "tab_domain_cache.json"


def test_save_and_load_roundtrip(tmp_path):
    tabs_module._tab_domain_cache.clear()
    tabs_module._tab_domain_cache["DR News"] = "www.dr.dk"
    tabs_module._tab_domain_cache["Gmail"] = "mail.google.com"

    with patch("windows_navigator.tabs._cache_file_path", return_value=tmp_path / "tab_domain_cache.json"):
        _save_tab_domain_cache(dict(tabs_module._tab_domain_cache))
        tabs_module._tab_domain_cache.clear()
        _load_tab_domain_cache()

    assert tabs_module._tab_domain_cache.get("DR News") == "www.dr.dk"
    assert tabs_module._tab_domain_cache.get("Gmail") == "mail.google.com"


def test_load_ignores_missing_file(tmp_path):
    tabs_module._tab_domain_cache.clear()
    with patch("windows_navigator.tabs._cache_file_path",
               return_value=tmp_path / "nonexistent.json"):
        _load_tab_domain_cache()  # must not raise
    assert len(tabs_module._tab_domain_cache) == 0


def test_load_ignores_corrupt_file(tmp_path):
    bad = tmp_path / "tab_domain_cache.json"
    bad.write_text("not json {{{", encoding="utf-8")
    tabs_module._tab_domain_cache.clear()
    with patch("windows_navigator.tabs._cache_file_path", return_value=bad):
        _load_tab_domain_cache()  # must not raise
    assert len(tabs_module._tab_domain_cache) == 0


def test_fetch_tabs_saves_cache_on_new_domain(tmp_path):
    tabs_module._tab_domain_cache.clear()
    cache_path = tmp_path / "tab_domain_cache.json"
    mock_uia = _make_firefox_tree(["DR News"], active_index=0, active_url="www.dr.dk")

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia), \
         patch("windows_navigator.tabs._cache_file_path", return_value=cache_path):
        fetch_tabs(hwnd=10)

    assert cache_path.exists()
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data.get("DR News") == "www.dr.dk"


def test_fetch_tabs_does_not_save_when_domain_unchanged(tmp_path):
    tabs_module._tab_domain_cache.clear()
    tabs_module._tab_domain_cache["DR News"] = "www.dr.dk"
    cache_path = tmp_path / "tab_domain_cache.json"
    mock_uia = _make_firefox_tree(["DR News"], active_index=0, active_url="www.dr.dk")

    with patch("windows_navigator.tabs._create_uia", return_value=mock_uia), \
         patch("windows_navigator.tabs._cache_file_path", return_value=cache_path), \
         patch("windows_navigator.tabs._save_tab_domain_cache") as mock_save:
        fetch_tabs(hwnd=10)

    mock_save.assert_not_called()
