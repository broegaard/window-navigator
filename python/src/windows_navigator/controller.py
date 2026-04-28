"""Pure-Python state machine for the overlay — no Tk dependency, fully testable."""

from __future__ import annotations

import functools
from typing import Protocol

from windows_navigator.filter import filter_windows
from windows_navigator.models import TabInfo, WindowInfo


class FilterControllerProtocol(Protocol):
    """Query text, desktop filter, app filter, and bell filter state."""

    query: str

    @property
    def desktop_nums(self) -> set[int]: ...
    @property
    def app_icons(self) -> list[WindowInfo]: ...
    @property
    def app_filter_index(self) -> int | None: ...
    @property
    def bell_filter(self) -> bool: ...
    @property
    def app_filter(self) -> str | None: ...

    def set_query(self, text: str) -> None: ...
    def set_desktop_nums(self, nums: set[int]) -> None: ...
    def toggle_bell_filter(self) -> None: ...
    def cycle_app_filter(self, direction: int) -> None: ...
    def clear_app_filter(self) -> None: ...


class NavigationControllerProtocol(Protocol):
    """Selection index and movement through the flat window/tab list."""

    selection_index: int

    @property
    def flat_list(self) -> list[WindowInfo | TabInfo]: ...
    @property
    def filtered_windows(self) -> list[WindowInfo]: ...

    def move_up(self) -> None: ...
    def move_down(self) -> None: ...
    def move_page_up(self, page_size: int) -> None: ...
    def move_page_down(self, page_size: int) -> None: ...
    def move_to_first(self) -> None: ...
    def move_to_last(self) -> None: ...
    def selected_item(self) -> WindowInfo | TabInfo | None: ...
    def selected_hwnd(self) -> int | None: ...


class TabControllerProtocol(Protocol):
    """UIA tab discovery and per-window expansion state."""

    def set_tabs(self, hwnd: int, tabs: list[TabInfo]) -> None: ...
    def toggle_all_expansions(self) -> None: ...
    def tab_count(self, hwnd: int) -> int: ...
    def is_expanded(self, hwnd: int) -> bool: ...


class OverlayControllerProtocol(
    FilterControllerProtocol,
    NavigationControllerProtocol,
    TabControllerProtocol,
    Protocol,
):
    """Full controller interface consumed by NavigatorOverlay.

    Composes the three focused sub-protocols.  Depend on a sub-protocol when
    only a subset of the interface is needed; depend on this when everything is.
    """

    def reset(self, windows: list[WindowInfo]) -> None: ...


class OverlayController:
    """Tracks query, filtered window list, tab expansions, and selection index."""

    def __init__(self, windows: list[WindowInfo]) -> None:
        self.all_windows = list(windows)
        self.query = ""
        self._desktop_nums: set[int] = set()
        self._app_filter: str | None = None
        self._bell_filter: bool = False
        self._tabs: dict[int, list[TabInfo]] = {}
        self._expanded: set[int] = set()
        self._want_all_expanded: bool = False
        self.selection_index = 0 if windows else -1

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------

    @property
    def desktop_nums(self) -> set[int]:
        return self._desktop_nums

    @functools.cached_property
    def text_filtered_windows(self) -> list[WindowInfo]:
        """Windows matching desktop badge filter + text query only (no app filter)."""
        return filter_windows(self.all_windows, self.query, self._desktop_nums or None)

    def _invalidate_text_filter_cache(self) -> None:
        self.__dict__.pop("text_filtered_windows", None)

    @property
    def _tab_query_matches(self) -> dict[int, list[TabInfo]]:
        """Expanded windows not matched by title/process but having tabs matching the text query.

        Returns empty dict when nothing is expanded — tabs are only searched in expanded state.
        """
        if not self._expanded:
            return {}
        if not self.query.strip():
            return {}
        tokens = self.query.casefold().split()
        title_hwnds = {w.hwnd for w in self.text_filtered_windows}
        hwnd_to_window = {w.hwnd: w for w in self.all_windows}
        result: dict[int, list[TabInfo]] = {}
        for hwnd, tabs in self._tabs.items():
            if hwnd in title_hwnds:
                continue
            w = hwnd_to_window.get(hwnd)
            if w is None:
                continue
            if self._desktop_nums and w.desktop_number not in self._desktop_nums:
                continue
            matching = [t for t in tabs if all(tok in t.name.casefold() for tok in tokens)]
            if matching:
                result[hwnd] = matching
        return result

    @property
    def filtered_windows(self) -> list[WindowInfo]:
        """Windows matching query AND all active filters (bell, app, and tab-query matches)."""
        title_hwnds = {w.hwnd for w in self.text_filtered_windows}
        tab_matches = self._tab_query_matches
        result: list[WindowInfo] = []
        for w in self.all_windows:
            if w.hwnd not in title_hwnds and w.hwnd not in tab_matches:
                continue
            if self._bell_filter and not w.has_notification:
                continue
            if self._app_filter is not None and w.process_name != self._app_filter:
                continue
            result.append(w)
        return result

    @property
    def flat_list(self) -> list[WindowInfo | TabInfo]:
        """Filtered windows with expanded tab rows interleaved immediately after their parent."""
        tab_matches = self._tab_query_matches
        result: list[WindowInfo | TabInfo] = []
        for w in self.filtered_windows:
            result.append(w)
            hwnd = w.hwnd
            if hwnd in tab_matches:
                result.extend(tab_matches[hwnd])
            elif hwnd in self._expanded and hwnd in self._tabs:
                result.extend(self._tabs[hwnd])
        return result

    @property
    def app_icons(self) -> list[WindowInfo]:
        """One representative WindowInfo per unique process_name in text_filtered_windows.

        Preserves the recency (z-order) of the first occurrence of each process.
        """
        seen: set[str] = set()
        result: list[WindowInfo] = []
        for w in self.text_filtered_windows:
            if w.process_name not in seen:
                seen.add(w.process_name)
                result.append(w)
        return result

    @property
    def app_filter_index(self) -> int | None:
        """Index of the selected process in app_icons, or None if no filter active."""
        if self._app_filter is None:
            return None
        for i, w in enumerate(self.app_icons):
            if w.process_name == self._app_filter:
                return i
        return None

    @property
    def bell_filter(self) -> bool:
        return self._bell_filter

    @property
    def app_filter(self) -> str | None:
        return self._app_filter

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    def tab_count(self, hwnd: int) -> int:
        """Number of UIA tabs fetched for *hwnd* (0 if none fetched yet)."""
        return len(self._tabs.get(hwnd, []))

    def is_expanded(self, hwnd: int) -> bool:
        """True if *hwnd*'s tab list is currently expanded in the overlay."""
        return hwnd in self._expanded

    def set_tabs(self, hwnd: int, tabs: list[TabInfo]) -> None:
        """Store fetched tab data for *hwnd*. Called from the main thread after background fetch."""
        self._tabs[hwnd] = tabs
        if self._want_all_expanded and len(tabs) > 1:
            self._expanded.add(hwnd)

    def toggle_expansion(self, hwnd: int) -> None:
        """Expand or collapse the tab list for *hwnd*.

        Only expands when the window has more than one tab. Always leaves
        selection on the parent window row.
        """
        if hwnd in self._expanded:
            self._expanded.discard(hwnd)
        elif hwnd in self._tabs and len(self._tabs[hwnd]) > 1:
            self._expanded.add(hwnd)
        flat = self.flat_list
        for i, item in enumerate(flat):
            if isinstance(item, WindowInfo) and item.hwnd == hwnd:
                self.selection_index = i
                break

    def toggle_all_expansions(self) -> None:
        """Expand all visible windows that have tabs, or collapse all if any are expanded.

        If tabs have not arrived yet, sets a flag so each window auto-expands when
        its tabs are fetched.  Pressing again while the flag is set cancels the intent.
        """
        hwnds_with_tabs = {
            w.hwnd for w in self.filtered_windows
            if w.hwnd in self._tabs and len(self._tabs[w.hwnd]) > 1
        }
        if not hwnds_with_tabs:
            # Only flip the deferred flag when some filtered windows still have tabs loading.
            # If all filtered windows already have tab data (just single-tab), do nothing —
            # flipping would corrupt intent state without any visible effect.
            if any(w.hwnd not in self._tabs for w in self.filtered_windows):
                self._want_all_expanded = not self._want_all_expanded
            return
        if self._expanded & hwnds_with_tabs:
            self._expanded.clear()
            self._want_all_expanded = False
        else:
            self._expanded |= hwnds_with_tabs
            self._want_all_expanded = True
        n = len(self.flat_list)
        if n == 0:
            self.selection_index = -1
        elif self.selection_index >= n:
            self.selection_index = n - 1

    def selected_item(self) -> WindowInfo | TabInfo | None:
        """Return the currently selected item (window row or tab row), or None."""
        flat = self.flat_list
        if self.selection_index < 0 or self.selection_index >= len(flat):
            return None
        return flat[self.selection_index]

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def set_desktop_nums(self, nums: set[int]) -> None:
        """Update desktop badge filter and reset selection to the first visible row.

        If the active app filter no longer appears in the new filtered list,
        it is automatically cleared.
        """
        self._desktop_nums = nums
        self._invalidate_text_filter_cache()
        if self._app_filter is not None:
            names = {w.process_name for w in self.text_filtered_windows}
            hwnd_to_window = {w.hwnd: w for w in self.all_windows}
            names |= {
                hwnd_to_window[h].process_name
                for h in self._tab_query_matches
                if h in hwnd_to_window
            }
            if self._app_filter not in names:
                self._app_filter = None
        self.selection_index = 0 if self.flat_list else -1

    def set_query(self, text: str) -> None:
        """Update text filter query and reset selection to the first visible row.

        If the active app filter no longer appears in the new text-filtered list,
        it is automatically cleared.
        """
        self.query = text
        self._invalidate_text_filter_cache()
        if self._app_filter is not None:
            names = {w.process_name for w in self.text_filtered_windows}
            hwnd_to_window = {w.hwnd: w for w in self.all_windows}
            names |= {
                hwnd_to_window[h].process_name
                for h in self._tab_query_matches
                if h in hwnd_to_window
            }
            if self._app_filter not in names:
                self._app_filter = None
        self.selection_index = 0 if self.flat_list else -1

    def cycle_app_filter(self, direction: int) -> None:
        """Advance the app filter selection by *direction* (+1 or -1) with wrap."""
        icons = self.app_icons
        if not icons:
            return
        current = self.app_filter_index
        if current is None:
            new_index = 0 if direction > 0 else len(icons) - 1
        else:
            new_index = (current + direction) % len(icons)
        self._app_filter = icons[new_index].process_name
        self.selection_index = 0 if self.flat_list else -1

    def clear_app_filter(self) -> None:
        """Remove the active app filter and reset selection."""
        self._app_filter = None
        self.selection_index = 0 if self.flat_list else -1

    def toggle_bell_filter(self) -> None:
        """Toggle the notification-only filter and reset selection."""
        self._bell_filter = not self._bell_filter
        self.selection_index = 0 if self.flat_list else -1

    def move_up(self) -> None:
        n = len(self.flat_list)
        if n == 0:
            return
        if self.selection_index <= 0:
            self.selection_index = n - 1
        else:
            self.selection_index -= 1

    def move_down(self) -> None:
        n = len(self.flat_list)
        if n == 0:
            return
        if self.selection_index >= n - 1:
            self.selection_index = 0
        else:
            self.selection_index += 1

    def move_page_up(self, page_size: int) -> None:
        if self.selection_index > 0:
            self.selection_index = max(0, self.selection_index - page_size)

    def move_page_down(self, page_size: int) -> None:
        last = len(self.flat_list) - 1
        if self.selection_index < last:
            self.selection_index = min(last, self.selection_index + page_size)

    def move_to_first(self) -> None:
        if self.flat_list:
            self.selection_index = 0

    def move_to_last(self) -> None:
        last = len(self.flat_list) - 1
        if last >= 0:
            self.selection_index = last

    def reset(self, windows: list[WindowInfo]) -> None:
        """Reset all state for a fresh show() call."""
        self.all_windows = list(windows)
        self.query = ""
        self._desktop_nums = set()
        self._app_filter = None
        self._bell_filter = False
        self._tabs = {}
        self._expanded = set()
        self._want_all_expanded = False
        self.selection_index = 0 if windows else -1
        self._invalidate_text_filter_cache()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def selected_hwnd(self) -> int | None:
        """Return the hwnd of the currently selected item (window or tab's parent), or None."""
        item = self.selected_item()
        return item.hwnd if item is not None else None
