"""
Diagnostic: dump UIA properties for tab items in Chrome/Edge/Firefox.

Run on Windows with the venv active:
    py dump_tab_props.py

Open a browser with a few tabs before running.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys

# ── UIA constants ────────────────────────────────────────────────────────────
_UIA_TabItemControlTypeId = 50019
_UIA_DocumentControlTypeId = 50030
_UIA_ImageControlTypeId = 50006

_UIA_ControlTypePropertyId = 30003
_UIA_NamePropertyId = 30005
_UIA_HelpTextPropertyId = 30013
_UIA_AutomationIdPropertyId = 30011
_UIA_ClassNamePropertyId = 30012
_UIA_FullDescriptionPropertyId = 30159  # Win 8.1+
_UIA_ValueValuePropertyId = 30045

_UIA_LegacyIAccessiblePatternId = 10018

_TreeScope_Children = 2
_TreeScope_Subtree = 7
_MAX_DEPTH = 12

COINIT_APARTMENTTHREADED = 0x2


def _init_com() -> None:
    ctypes.windll.ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)


def _create_uia():
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


def _collect_tab_items(element, uia, depth: int = 0) -> list:
    if depth > _MAX_DEPTH:
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
        items.extend(_collect_tab_items(child, uia, depth + 1))
    return items


def _safe_prop(element, prop_id: int) -> str:
    try:
        v = element.GetCurrentPropertyValue(prop_id)
        return repr(v) if v not in (None, "", 0) else ""
    except Exception as e:
        return f"<err: {e}>"


def _legacy_ia_props(element) -> dict[str, str]:
    """Try to get IUIAutomationLegacyIAccessiblePattern props."""
    out: dict[str, str] = {}
    try:
        import comtypes.gen.UIAutomationClient as uiac

        pat = element.GetCurrentPattern(_UIA_LegacyIAccessiblePatternId)
        ia = pat.QueryInterface(uiac.IUIAutomationLegacyIAccessiblePattern)
        for attr in (
            "CurrentName",
            "CurrentDescription",
            "CurrentValue",
            "CurrentDefaultAction",
            "CurrentRole",
            "CurrentState",
        ):
            try:
                v = getattr(ia, attr)
                if v not in (None, "", 0):
                    out[attr] = repr(v)
            except Exception:
                pass
    except Exception:
        pass
    return out


def _dump_children(element, uia, depth: int = 0, max_depth: int = 3) -> None:
    if depth > max_depth:
        return
    indent = "  " * (depth + 2)
    for child in _get_children(element, uia):
        try:
            ct = child.GetCurrentPropertyValue(_UIA_ControlTypePropertyId)
            name = child.GetCurrentPropertyValue(_UIA_NamePropertyId) or ""
            print(f"{indent}child ct={ct} name={name!r}")
            # for image children dump extra props
            if ct == _UIA_ImageControlTypeId:
                for pid, label in [
                    (_UIA_HelpTextPropertyId, "HelpText"),
                    (_UIA_FullDescriptionPropertyId, "FullDesc"),
                    (_UIA_AutomationIdPropertyId, "AutoId"),
                ]:
                    v = _safe_prop(child, pid)
                    if v:
                        print(f"{indent}  {label}: {v}")
        except Exception:
            pass
        _dump_children(child, uia, depth + 1, max_depth)


def _enum_windows_by_names(names: list[str]) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        if any(n.lower() in title.lower() for n in names):
            results.append((hwnd, title))
        return True

    ctypes.windll.user32.EnumWindows(cb, 0)
    return results


def _dump_tree_brief(element, uia, depth: int = 0, max_depth: int = 5) -> None:
    """Dump the top levels of the UIA tree to diagnose unknown browsers."""
    if depth > max_depth:
        return
    indent = "  " * depth
    try:
        ct = element.GetCurrentPropertyValue(_UIA_ControlTypePropertyId)
        name = element.GetCurrentPropertyValue(_UIA_NamePropertyId) or ""
        cls = _safe_prop(element, _UIA_ClassNamePropertyId)
        autid = _safe_prop(element, _UIA_AutomationIdPropertyId)
        extras = ""
        if cls:
            extras += f" cls={cls}"
        if autid:
            extras += f" autid={autid}"
        print(f"{indent}ct={ct} name={name!r}{extras}")
    except Exception as e:
        print(f"{indent}<err: {e}>")
        return
    for child in _get_children(element, uia):
        _dump_tree_brief(child, uia, depth + 1, max_depth)


def _test_favicon_fetch(domains: set[str]) -> None:
    import io
    import urllib.request

    try:
        from PIL import Image

        has_pil = True
    except ImportError:
        has_pil = False

    for domain in sorted(domains):
        if not domain or " " in domain or "." not in domain:
            continue
        for url_template in [
            f"https://{domain}/favicon.ico",
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        ]:
            try:
                req = urllib.request.Request(url_template, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    ct = resp.headers.get("Content-Type", "")
                    data = resp.read()
                if "html" in ct.lower():
                    print(f"    {domain}: {url_template} -> HTML (skipped)")
                    continue
                if has_pil:
                    img = Image.open(io.BytesIO(data)).convert("RGBA")
                    print(f"    {domain}: {url_template} -> OK ({img.size})")
                else:
                    print(
                        f"    {domain}: {url_template} -> OK ({len(data)} bytes, PIL not available)"
                    )
                break
            except Exception as e:
                print(f"    {domain}: {url_template} -> FAIL ({e})")
        else:
            print(f"    {domain}: all candidates failed")


def main() -> None:
    _init_com()
    uia = _create_uia()

    browser_names = ["chrome", "edge", "firefox", "brave", "opera", "vivaldi"]
    windows = _enum_windows_by_names(browser_names)
    if not windows:
        print("No browser windows found. Open Chrome/Edge/Firefox and try again.")
        sys.exit(1)

    for hwnd, title in windows:
        print(f"\n{'=' * 60}")
        print(f"hwnd={hwnd}  title={title!r}")
        root = uia.ElementFromHandle(hwnd)
        tabs = _collect_tab_items(root, uia)
        if not tabs:
            print("  (no tab items found — dumping top 5 levels of UIA tree)")
            _dump_tree_brief(root, uia)
            continue
        print(f"  {len(tabs)} tab item(s) found")
        for i, el in enumerate(tabs[:10]):  # limit to first 10 tabs
            print(f"\n  [tab {i}]")
            for pid, label in [
                (_UIA_NamePropertyId, "Name"),
                (_UIA_HelpTextPropertyId, "HelpText"),
                (_UIA_FullDescriptionPropertyId, "FullDesc"),
                (_UIA_AutomationIdPropertyId, "AutoId"),
                (_UIA_ClassNamePropertyId, "ClassName"),
                (_UIA_ValueValuePropertyId, "Value"),
            ]:
                v = _safe_prop(el, pid)
                if v:
                    print(f"    {label}: {v}")
            legacy = _legacy_ia_props(el)
            if legacy:
                print("    LegacyIA:", legacy)
            print("    children:")
            _dump_children(el, uia)

        # Show URL bar candidates for this window
        print("\n  --- URL bar search (Edit elements with address-bar-like IDs) ---")
        _dump_url_bar_candidates(root, uia)

        # Test favicon fetch for every unique domain found
        domains = {_safe_prop(el, _UIA_FullDescriptionPropertyId).strip("'") for el in tabs}
        domains.discard("")
        if domains:
            print("\n  --- favicon fetch test ---")
            _test_favicon_fetch(domains)


def _dump_url_bar_candidates(element, uia, depth: int = 0) -> None:
    """Print every Edit element whose AutomationId or ClassName looks like a URL bar."""
    if depth > 12:
        return
    try:
        ct = element.GetCurrentPropertyValue(_UIA_ControlTypePropertyId)
        if ct == _UIA_DocumentControlTypeId:
            return
        if ct == 50004:  # Edit
            auto_id = str(
                element.GetCurrentPropertyValue(_UIA_AutomationIdPropertyId) or ""
            ).lower()
            cls = str(element.GetCurrentPropertyValue(_UIA_ClassNamePropertyId) or "").lower()
            val = _safe_prop(element, _UIA_ValueValuePropertyId)
            name = _safe_prop(element, _UIA_NamePropertyId)
            print(f"    depth={depth} autid={auto_id!r} cls={cls!r} val={val} name={name}")
    except Exception:
        return
    for child in _get_children(element, uia):
        _dump_url_bar_candidates(child, uia, depth + 1)


if __name__ == "__main__":
    main()
