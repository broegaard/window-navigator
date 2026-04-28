"""Filter and sort window list by a search query."""

from __future__ import annotations

from windows_navigator.models import WindowInfo


def _tokens_match(w: WindowInfo, tokens: list[str]) -> bool:
    """True if every token in *tokens* appears in title or process name."""
    title = w.title.casefold()
    proc = w.process_name.casefold()
    return all(t in title or t in proc for t in tokens)


def filter_windows(
    windows: list[WindowInfo],
    query: str,
    desktop_nums: set[int] | None = None,
) -> list[WindowInfo]:
    """Return windows matching *query* and optional *desktop_nums*.

    *desktop_nums* restricts results to windows on any of those desktops (OR logic);
    ``None`` means no desktop restriction.  *query* is matched case-insensitively
    against title and process name (all whitespace-separated tokens must match).
    An empty query with no desktop filter returns all windows unchanged.
    """
    result = list(windows)
    if desktop_nums:
        result = [w for w in result if w.desktop_number in desktop_nums]
    tokens = query.casefold().split()
    if not tokens:
        return result
    return [w for w in result if _tokens_match(w, tokens)]
