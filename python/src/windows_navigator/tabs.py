"""UIA tab discovery and activation — deferred Windows-only imports."""
from __future__ import annotations

from windows_navigator.models import TabInfo

_UIA_TabItemControlTypeId = 50019
_UIA_DocumentControlTypeId = 50030  # rendered web-page content — stop here, don't descend
_UIA_ControlTypePropertyId = 30003
_UIA_NamePropertyId = 30005
_UIA_SelectionItemPatternId = 10010
_TreeScope_Children = 2


def _create_uia():
    """Create a UIA automation object. COM must be initialized on the calling thread."""
    import comtypes.client

    comtypes.client.GetModule("UIAutomationCore.dll")
    import comtypes.gen.UIAutomationClient as uiac

    return comtypes.client.CreateObject(
        "{ff48dba4-60ef-4201-aa87-54103eef594e}",
        interface=uiac.IUIAutomation,
    )


def _get_children(element, uia) -> list:
    try:
        col = element.FindAll(_TreeScope_Children, uia.CreateTrueCondition())
        return [col.GetElement(i) for i in range(col.Length)]
    except Exception:
        return []


def _collect_tab_items(element, uia, depth: int = 0, max_depth: int = 10) -> list:
    """Return all UIA TabItem elements found under *element*, stopping at Document nodes.

    Document (50030) is the rendered web-page area — in-page ARIA tab widgets live inside
    it and must not be mistaken for browser tabs.
    """
    if depth > max_depth:
        return []
    try:
        ct = element.GetCurrentPropertyValue(_UIA_ControlTypePropertyId)
        if ct == _UIA_TabItemControlTypeId:
            return [element]
        if ct == _UIA_DocumentControlTypeId:
            return []
    except Exception:
        pass
    items = []
    for child in _get_children(element, uia):
        items.extend(_collect_tab_items(child, uia, depth + 1, max_depth))
    return items


def fetch_tabs(hwnd: int) -> list[TabInfo]:
    """Walk the UIA tree for *hwnd* and return one TabInfo per TabItem found.

    Returns [] on any error or on non-Windows platforms.
    COM must be initialised on the calling thread before calling this.
    """
    try:
        uia = _create_uia()
        root = uia.ElementFromHandle(hwnd)
        elements = _collect_tab_items(root, uia)
        result: list[TabInfo] = []
        for idx, el in enumerate(elements):
            try:
                name = el.GetCurrentPropertyValue(_UIA_NamePropertyId) or ""
                result.append(TabInfo(name=str(name), hwnd=hwnd, index=idx))
            except Exception:
                pass
        return result
    except Exception:
        return []


def select_tab(tab: TabInfo) -> None:
    """Re-fetch the tab element at *tab.index* and call SelectionItemPattern::Select().

    Re-fetching instead of caching the element sidesteps COM cross-thread marshaling.
    COM must be initialised on the calling thread.
    """
    try:
        import comtypes.gen.UIAutomationClient as uiac

        uia = _create_uia()
        root = uia.ElementFromHandle(tab.hwnd)
        elements = _collect_tab_items(root, uia)
        if tab.index < len(elements):
            raw = elements[tab.index].GetCurrentPattern(_UIA_SelectionItemPatternId)
            raw.QueryInterface(uiac.IUIAutomationSelectionItemPattern).Select()
    except Exception:
        pass
