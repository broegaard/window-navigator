"""UIA tab discovery and activation — deferred Windows-only imports."""
from __future__ import annotations

import json
import os
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

from windows_navigator.models import TabInfo

_UIA_TabItemControlTypeId             = 50019
_UIA_DocumentControlTypeId            = 50030  # rendered web-page content — stop here
_UIA_EditControlTypeId                = 50004
_UIA_ControlTypePropertyId            = 30003
_UIA_NamePropertyId                   = 30005
_UIA_AutomationIdPropertyId           = 30011
_UIA_ClassNamePropertyId              = 30012
_UIA_FullDescriptionPropertyId        = 30159  # Edge/Chrome expose the domain here
_UIA_ValueValuePropertyId             = 30045
_UIA_SelectionItemIsSelectedPropertyId = 30079
_UIA_LegacyIAccessibleStatePropertyId = 30056  # MSAA state bitmask; bit 0x2 = selected
_UIA_LegacyIAccessiblePatternId       = 10018
_UIA_SelectionItemPatternId           = 10010
_STATE_SYSTEM_SELECTED = 0x2
_TreeScope_Children = 2
_MAX_UIA_DEPTH = 10
_ADDRESS_BAR_KEYWORDS = ("urlbar", "addressbar", "omnibox", "location")

_tab_domain_cache: OrderedDict[str, str] = OrderedDict()
_tab_domain_cache_lock = threading.Lock()
_TAB_DOMAIN_CACHE_MAX = 256


def _cache_file_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else (Path.home() / ".config")
    return base / "windows-navigator" / "tab_domain_cache.json"


def _load_tab_domain_cache() -> None:
    try:
        data = json.loads(_cache_file_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(k, str) and isinstance(v, str):
                    _tab_domain_cache[k] = v
                    if len(_tab_domain_cache) >= _TAB_DOMAIN_CACHE_MAX:
                        break
    except FileNotFoundError:
        pass
    except (ValueError, OSError):
        pass


def _save_tab_domain_cache(snapshot: dict[str, str]) -> None:
    try:
        path = _cache_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


_load_tab_domain_cache()


def _domain_from_full_description(value: object) -> str:
    """Return the domain string if *value* looks like a hostname, else ''."""
    s = str(value).strip() if value else ""
    # Reject free-text descriptions like "local or shared file"
    if not s or " " in s or "." not in s:
        return ""
    return s


def _domain_from_url(url: str) -> str:
    """Extract the hostname from a URL or a bare hostname/path.

    Firefox hides the scheme in its URL bar, so *url* may be 'github.com/foo'
    rather than 'https://github.com/foo'.
    """
    if not url:
        return ""
    try:
        if url.startswith(("http://", "https://")):
            host = urlparse(url).netloc.lower()
        else:
            # Strip any path/port/query — keep only the hostname part
            host = url.split("/")[0].split(":")[0].lower()
        return host if "." in host and " " not in host else ""
    except (ValueError, AttributeError):
        return ""


def _find_address_bar_url(element, uia, depth: int = 0) -> str:
    """DFS for the browser URL bar; returns the current URL/host string or ''."""
    if depth > 12:
        return ""
    try:
        ct = element.GetCurrentPropertyValue(_UIA_ControlTypePropertyId)
        if ct == _UIA_DocumentControlTypeId:
            return ""
        if ct == _UIA_EditControlTypeId:
            auto_id = str(element.GetCurrentPropertyValue(_UIA_AutomationIdPropertyId) or "").lower()
            cls = str(element.GetCurrentPropertyValue(_UIA_ClassNamePropertyId) or "").lower()
            if any(k in auto_id or k in cls for k in _ADDRESS_BAR_KEYWORDS):
                val = str(element.GetCurrentPropertyValue(_UIA_ValueValuePropertyId) or "")
                # Accept full URLs and bare hosts (Firefox omits the scheme)
                if val and "." in val and " " not in val:
                    return val
    except Exception:
        return ""
    for child in _get_children(element, uia):
        found = _find_address_bar_url(child, uia, depth + 1)
        if found:
            return found
    return ""


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


def _collect_tab_items(element, uia, depth: int = 0, max_depth: int = _MAX_UIA_DEPTH) -> list:
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


def _is_tab_selected(el) -> bool:
    """Return True if *el* is the currently active tab.

    Tries three approaches in order:
    1. SelectionItemIsSelected property (standard UIA — works for Edge/Chrome).
    2. LegacyIAccessibleState property (30056) — bitmask; bit 0x2 = selected.
    3. LegacyIAccessible pattern via GetCurrentPattern + QueryInterface — confirmed
       to work for Firefox when neither property is exposed directly.
    """
    try:
        val = el.GetCurrentPropertyValue(_UIA_SelectionItemIsSelectedPropertyId)
        if val is not None and val is not False and val != 0:
            return True
    except Exception:
        pass
    try:
        state = el.GetCurrentPropertyValue(_UIA_LegacyIAccessibleStatePropertyId)
        if isinstance(state, int) and (state & _STATE_SYSTEM_SELECTED):
            return True
    except Exception:
        pass
    # sys.modules.get avoids import-machinery complications when the module is
    # injected via patch.dict in tests (and on Windows it's already registered
    # by _create_uia() before fetch_tabs calls this helper).
    try:
        uiac = sys.modules.get("comtypes.gen.UIAutomationClient")
        if uiac is not None:
            pat = el.GetCurrentPattern(_UIA_LegacyIAccessiblePatternId)
            ia = pat.QueryInterface(uiac.IUIAutomationLegacyIAccessiblePattern)
            if ia.CurrentState & _STATE_SYSTEM_SELECTED:
                return True
    except Exception:
        pass
    return False


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
        result_elements: list = []
        for idx, el in enumerate(elements):
            try:
                name = el.GetCurrentPropertyValue(_UIA_NamePropertyId) or ""
                raw_domain = el.GetCurrentPropertyValue(_UIA_FullDescriptionPropertyId)
                domain = _domain_from_full_description(raw_domain)
                result.append(TabInfo(name=str(name), hwnd=hwnd, index=idx, domain=domain))
                result_elements.append(el)
            except Exception:
                pass
        # Browsers without FullDescription (e.g. Firefox): derive the active tab's domain
        # from the URL bar and assign it to the selected tab.
        if result and not any(t.domain for t in result):
            url = _find_address_bar_url(root, uia)
            domain = _domain_from_url(url)
            if domain:
                for i, el in enumerate(result_elements):
                    if _is_tab_selected(el):
                        result[i].domain = domain
                        break
        # Update/read persistent domain cache so that inactive tabs (e.g. Firefox tabs
        # not currently active) retain their domain across overlay opens.
        _dirty = False
        snapshot: dict[str, str] | None = None
        with _tab_domain_cache_lock:
            for tab in result:
                if tab.domain:
                    if _tab_domain_cache.get(tab.name) != tab.domain:
                        _tab_domain_cache[tab.name] = tab.domain
                        _dirty = True
                    _tab_domain_cache.move_to_end(tab.name)
                    if len(_tab_domain_cache) > _TAB_DOMAIN_CACHE_MAX:
                        _tab_domain_cache.popitem(last=False)
                elif tab.name in _tab_domain_cache:
                    tab.domain = _tab_domain_cache[tab.name]
                    _tab_domain_cache.move_to_end(tab.name)
            if _dirty:
                snapshot = dict(_tab_domain_cache)
        if snapshot is not None:
            _save_tab_domain_cache(snapshot)
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
