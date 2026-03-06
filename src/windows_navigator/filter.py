"""Filter and sort window list by a search query."""

from __future__ import annotations

import re

from windows_navigator.models import WindowInfo

# Matches a single leading "#N" desktop token, e.g. "#3" from "#3 chrome" or "#3#4"
_DESKTOP_TOKEN = re.compile(r"^#(\d+)(.*)", re.DOTALL)


def _tokens_match(w: WindowInfo, query: str) -> bool:
    """True if every whitespace-separated token in *query* appears in title or process name."""
    title = w.title.casefold()
    proc = w.process_name.casefold()
    return all(t in title or t in proc for t in query.casefold().split())


def parse_query(query: str) -> tuple[set[int], str]:
    """Parse *query* into ``(desktop_nums, text)``.

    Strips leading ``#N`` desktop tokens and returns the remainder as the text portion.
    A bare ``#`` or whitespace-only remainder is normalised to ``""``.
    """
    desktop_nums: set[int] = set()
    rest = query
    while True:
        m = _DESKTOP_TOKEN.match(rest)
        if not m:
            break
        desktop_nums.add(int(m.group(1)))
        rest = m.group(2)
    stripped = rest.strip()
    if stripped in ("#", ""):
        return desktop_nums, ""
    return desktop_nums, stripped


def filter_windows(windows: list[WindowInfo], query: str) -> list[WindowInfo]:
    """Return windows matching *query*.

    Leading ``#N`` tokens (e.g. ``#2#3``) restrict to those desktops (OR logic);
    any remaining text is matched case-insensitively against title and process name.
    An empty query returns all windows unchanged.
    """
    if not query:
        return list(windows)

    desktop_nums, text = parse_query(query)

    if not desktop_nums:
        if not text:
            return list(windows)
        return [w for w in windows if _tokens_match(w, text)]

    result = [w for w in windows if w.desktop_number in desktop_nums]
    if text:
        result = [w for w in result if _tokens_match(w, text)]
    return result
