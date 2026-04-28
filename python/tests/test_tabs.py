"""Tests for tabs.py — UIA tab discovery helpers."""

from unittest.mock import MagicMock, patch

from windows_navigator.models import TabInfo
from windows_navigator.tabs import (
    _UIA_DocumentControlTypeId,
    _UIA_TabItemControlTypeId,
    _collect_tab_items,
    _get_children,
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


def _make_uia_tree(tab_names: list[str]):
    """Return (mock_uia, tab_elements) for a tree whose root has named TabItem children."""
    tab_elements = []
    for name in tab_names:
        el = MagicMock()
        el.GetCurrentPropertyValue.side_effect = lambda prop, _name=name: (
            _UIA_TabItemControlTypeId if prop == 30003 else _name
        )
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
    assert result[0] == TabInfo(name="Tab A", hwnd=42, index=0)
    assert result[1] == TabInfo(name="Tab B", hwnd=42, index=1)


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
