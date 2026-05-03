"""Tkinter overlay window for the Windows Navigator."""

from __future__ import annotations

import threading
import tkinter as tk
from typing import TYPE_CHECKING, Callable

try:
    from PIL import ImageTk

    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

from windows_navigator.activation import _force_foreground, _get_cursor_monitor_workarea
from windows_navigator.controller import OverlayController, OverlayControllerProtocol
from windows_navigator.models import TabInfo, WindowInfo
from windows_navigator.overlay_layout import _colors
from windows_navigator.theme import desktop_badge_color as _desktop_badge_color

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

# All pixel constants are defined at 96 DPI (100 % scaling).  Call
# init_scale(dpi / 96) before creating NavigatorOverlay so they are
# recomputed for the actual monitor DPI.  Font sizes are in points and
# scale automatically once per-monitor DPI awareness is active.

_OVERLAY_WIDTH = 1240
_MAX_ROWS_VISIBLE = 10
_ROW_HEIGHT = 44
_TAB_ROW_HEIGHT = 28  # leaf (tab) rows are slimmer than window rows
_ICON_SIZE = 32  # icon images are always 32 × 32 px; not scaled
_TAB_ICON_SIZE = 16  # favicons for tab rows
_ICON_PAD_X = 8
_ICON_PAD_Y = (_ROW_HEIGHT - _ICON_SIZE) // 2
_BADGE_W = 22  # desktop number badge — square, same height as width
_TEXT_X = _ICON_PAD_X + _ICON_SIZE + 2 + _BADGE_W + 4  # icon + gap + badge + gap
_TITLE_Y = 7
_PROC_Y = 24
_NOTIF_COLOR = "#f9a825"  # amber
_NOTIF_BELL_CHAR = "🔔"
_NOTIF_BELL_FONT = ("Segoe UI Emoji", 11)
_BADGE_ENTRY_SIZE = 22  # px — square size for all entry-bar badges (desktop + bell)
_ENTRY_FRAME_PAD = 8  # outer entry frame padding (px)
_ENTRY_INNER_PAD = 4  # inner entry frame padding (px)
_ENTRY_AREA_H = 56  # total height of the entry section (pads + entry widget)
_ARROW_X = 6  # expand/collapse arrow x position
_NOTIF_X_OFFSET = 14  # notification bell offset from right canvas edge
_STRIP_DIV_PAD = 3  # vertical inset for strip slot divider lines
_CHECKBOX_SIZE = 14  # checkbox square side length
_CHECKBOX_MARGIN = 8  # gap between checkbox and right canvas edge

# Icon strip (between entry and window list)
_STRIP_HEIGHT = _ICON_SIZE + 12  # 44 px — icon + top/bottom padding
_STRIP_SLOT_W = _ICON_SIZE + 12  # 44 px — horizontal room per icon slot
_STRIP_PAD_Y = (_STRIP_HEIGHT - _ICON_SIZE) // 2
_STRIP_PAD_X = (_STRIP_SLOT_W - _ICON_SIZE) // 2
_COUNT_BAR_H = 18  # height of the result-count footer strip


def init_scale(scale: float) -> None:
    """Recompute pixel layout constants for *scale* (= monitor_dpi / 96).

    Must be called before the first NavigatorOverlay is created.
    Font sizes (in points) are intentionally omitted — they auto-scale
    once per-monitor DPI awareness is active.
    """
    global _OVERLAY_WIDTH, _ROW_HEIGHT, _TAB_ROW_HEIGHT
    global _ICON_PAD_X, _ICON_PAD_Y, _BADGE_W, _TEXT_X, _TITLE_Y, _PROC_Y
    global _BADGE_ENTRY_SIZE, _ENTRY_FRAME_PAD, _ENTRY_INNER_PAD, _ENTRY_AREA_H
    global _ARROW_X, _NOTIF_X_OFFSET, _STRIP_DIV_PAD
    global _STRIP_HEIGHT, _STRIP_SLOT_W, _STRIP_PAD_Y, _STRIP_PAD_X, _COUNT_BAR_H
    global _CHECKBOX_SIZE, _CHECKBOX_MARGIN

    def s(n: int) -> int:
        return round(n * scale)

    _OVERLAY_WIDTH = s(1240)
    _ROW_HEIGHT = s(44)
    _TAB_ROW_HEIGHT = s(28)
    _ICON_PAD_X = s(8)
    _ICON_PAD_Y = (_ROW_HEIGHT - _ICON_SIZE) // 2
    _BADGE_W = s(22)
    _TEXT_X = _ICON_PAD_X + _ICON_SIZE + s(2) + _BADGE_W + s(4)
    _TITLE_Y = s(7)
    _PROC_Y = s(24)
    _BADGE_ENTRY_SIZE = s(22)
    _ENTRY_FRAME_PAD = s(8)
    _ENTRY_INNER_PAD = s(4)
    _ENTRY_AREA_H = s(56)
    _ARROW_X = s(6)
    _NOTIF_X_OFFSET = s(14)
    _STRIP_DIV_PAD = s(3)
    _STRIP_HEIGHT = _ICON_SIZE + s(12)
    _STRIP_SLOT_W = _ICON_SIZE + s(12)
    _STRIP_PAD_Y = (_STRIP_HEIGHT - _ICON_SIZE) // 2
    _STRIP_PAD_X = (_STRIP_SLOT_W - _ICON_SIZE) // 2
    _COUNT_BAR_H = s(18)
    _CHECKBOX_SIZE = s(14)
    _CHECKBOX_MARGIN = s(8)


def _row_height(item: WindowInfo | TabInfo) -> int:
    return _TAB_ROW_HEIGHT if isinstance(item, TabInfo) else _ROW_HEIGHT


def _get_desktop_count() -> int:
    """Return the number of virtual desktops; defaults to 9 when unavailable."""
    try:
        from windows_navigator.virtual_desktop import _get_registry_desktop_order

        guids = _get_registry_desktop_order()
        if guids:
            return max(len(guids), 1)
    except Exception:
        pass
    return 9


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------


class NavigatorOverlay:
    """Tkinter-based overlay window. Must only be used from the Tk main thread."""

    def __init__(
        self,
        root: tk.Tk,
        on_activate: Callable[[int], None],
        on_move: Callable[[int], None],
        on_move_to: Callable[[list[int], int], None] | None = None,
        controller_factory: Callable[[list[WindowInfo]], OverlayControllerProtocol] | None = None,
        expand_on_startup: bool = False,
    ) -> None:
        self._root = root
        self._on_activate = on_activate
        self._on_move = on_move
        self._on_move_to = on_move_to
        self._controller_factory: Callable[[list[WindowInfo]], OverlayControllerProtocol] = (
            controller_factory if controller_factory is not None else OverlayController
        )
        self._expand_on_startup: bool = expand_on_startup
        self._top: tk.Toplevel | None = None
        self._controller: OverlayControllerProtocol | None = None
        self._canvas: tk.Canvas | None = None
        self._strip_canvas: tk.Canvas | None = None
        self._entry: tk.Entry | None = None
        self._entry_inner: tk.Frame | None = None
        self._prefix_badge_widgets: list[tk.Label] = []
        self._desktop_prefix_nums: list[int] = []
        self._initial_desktop: int = 0
        self._photo_image_cache: dict[int, object] = {}  # id(PIL image) → PhotoImage
        self._pending_hide: str | None = None  # after() ID for a scheduled hide()
        self._bell_badge_widget: tk.Label | None = None
        self._count_label: tk.Label | None = None
        self._fetch_time_label: tk.Label | None = None
        self._fetch_ms: float | None = None
        self._closing: bool = False  # True while handing focus to a target window
        self._picker_open: bool = False  # True while desktop-picker popup is visible
        self._fetch_cancel: threading.Event | None = None
        self._fetch_gen: int = 0  # incremented each show(); guards stale worker callbacks

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_expand_on_startup(self, value: bool) -> None:
        """Update the expand-on-startup setting (takes effect on the next show())."""
        self._expand_on_startup = value

    def show(
        self,
        windows: list[WindowInfo],
        initial_desktop: int = 0,
        fetch_ms: float | None = None,
    ) -> None:
        """Open (or refresh) the overlay with *windows*.

        *initial_desktop* pre-selects a desktop badge so the user sees only that
        desktop's windows on first open.  Pass 0 to show all desktops.
        """
        if self._top is not None:
            # Already visible — cancel pending hide, then toggle tree expansion
            if self._pending_hide is not None:
                self._top.after_cancel(self._pending_hide)
                self._pending_hide = None
            assert self._controller is not None
            self._controller.toggle_all_expansions()
            self._refresh_canvas()
            self._resize_to_fit()
            self._top.lift()
            self._top.after(50, self._grab_focus)
            return

        self._controller = self._controller_factory(windows)
        self._initial_desktop = initial_desktop
        self._fetch_ms = fetch_ms
        self._photo_image_cache.clear()
        if self._fetch_cancel is not None:
            self._fetch_cancel.set()
        self._fetch_cancel = threading.Event()
        self._fetch_gen += 1
        threading.Thread(
            target=self._fetch_tabs_bg,
            args=(list(windows), self._fetch_cancel, self._fetch_gen),
            daemon=True,
        ).start()
        self._build_ui()

    def hide(self) -> None:
        """Close the overlay without activating any window."""
        if self._fetch_cancel is not None:
            self._fetch_cancel.set()
            self._fetch_cancel = None
        self._closing = False
        self._picker_open = False
        self._pending_hide = None
        if self._top is not None:
            self._top.destroy()
            self._top = None
            # After destroy(), Windows won't send WM_SETCURSOR to the window beneath
            # until the mouse moves. A 1-px nudge-and-return injects two WM_MOUSEMOVE
            # messages that force WM_SETCURSOR on the underlying window (Firefox /
            # Terminal). The nudge is sub-frame so the cursor position is unchanged
            # by the time any rendering occurs.
            try:
                import ctypes
                import ctypes.wintypes

                _u = ctypes.windll.user32  # type: ignore[attr-defined]
                _pt = ctypes.wintypes.POINT()
                _u.GetCursorPos(ctypes.byref(_pt))
                _u.SetCursorPos(_pt.x + 1, _pt.y)
                _u.SetCursorPos(_pt.x, _pt.y)
            except Exception:
                pass
            self._photo_image_cache.clear()
            self._canvas = None
            self._strip_canvas = None
            self._entry = None
            self._entry_inner = None
            self._prefix_badge_widgets = []
            self._desktop_prefix_nums = []
            self._bell_badge_widget = None
            self._count_label = None
            self._fetch_time_label = None
            self._fetch_ms = None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        assert self._controller is not None
        c = _colors()

        top = tk.Toplevel(self._root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg=c["border"])

        # --- Search entry ---
        entry_frame = tk.Frame(top, bg=c["bg"], padx=_ENTRY_FRAME_PAD, pady=_ENTRY_FRAME_PAD)
        entry_frame.pack(fill="x")

        # Inner frame provides the visual "entry field" background + padding.
        # Holds the desktop-prefix badge (when active) and the text entry side-by-side.
        self._entry_inner = tk.Frame(
            entry_frame, bg=c["entry_bg"], padx=_ENTRY_INNER_PAD, pady=_ENTRY_INNER_PAD
        )
        self._entry_inner.pack(fill="x")

        self._entry = tk.Entry(
            self._entry_inner,
            bg=c["entry_bg"],
            fg=c["entry_fg"],
            insertbackground=c["entry_fg"],
            relief="flat",
            font=("Segoe UI", 13),
            bd=0,
            highlightthickness=0,
        )
        self._entry.pack(side="left", fill="x", expand=True)
        # Freeze the entry bar height at the Text widget's natural size so that
        # adding or removing badge widgets never causes a vertical resize.
        self._entry_inner.update_idletasks()
        self._entry_inner.pack_propagate(False)
        self._entry.bind("<BackSpace>", self._on_backspace)
        self._entry.bind("<Control-BackSpace>", self._on_ctrl_backspace)
        self._entry.bind("<Control-w>", self._on_ctrl_backspace)
        for _d in range(1, 10):
            self._entry.bind(f"<Control-Key-{_d}>", self._on_ctrl_digit)
        self._entry.bind("<Control-Key-0>", self._on_ctrl_zero)
        self._entry.bind("<KeyPress>", self._on_keypress_jump, add=True)
        self._entry.bind("<Control-equal>", self._on_ctrl_plus)
        self._entry.bind("<Control-plus>", self._on_ctrl_plus)
        self._entry.bind("<Control-KP_Add>", self._on_ctrl_plus)
        self._entry.bind("<Control-minus>", self._on_ctrl_minus)
        self._entry.bind("<Control-KP_Subtract>", self._on_ctrl_minus)
        self._entry.bind("<Control-grave>", self._on_ctrl_grave)
        self._entry.bind("<Control-onehalf>", self._on_ctrl_grave)
        self._entry.bind("<Control-space>", self._on_ctrl_space)

        # --- Icon strip (between entry and window list) ---
        strip_frame = tk.Frame(top, bg=c["bg"])
        strip_frame.pack(fill="x")

        self._strip_canvas = tk.Canvas(
            strip_frame,
            bg=c["bg"],
            width=_OVERLAY_WIDTH - 2,
            height=_STRIP_HEIGHT,
            highlightthickness=0,
        )
        self._strip_canvas.pack(fill="x")

        # --- Canvas ---
        visible_rows = min(len(self._controller.filtered_windows), _MAX_ROWS_VISIBLE)
        list_height = max(visible_rows, 1) * _ROW_HEIGHT

        list_frame = tk.Frame(top, bg=c["bg"])
        list_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(
            list_frame,
            bg=c["row_bg"],
            width=_OVERLAY_WIDTH,
            height=list_height,
            highlightthickness=0,
            cursor="arrow",
        )
        self._canvas.pack(fill="both", expand=True)

        # --- Result count footer ---
        footer = tk.Frame(top, bg=c["bg"], height=_COUNT_BAR_H)
        footer.pack(fill="x")
        footer.pack_propagate(False)
        self._count_label = tk.Label(
            footer,
            text="",
            bg=c["bg"],
            fg=c["proc_fg"],
            font=("Segoe UI", 8),
            anchor="w",
            padx=6,
        )
        self._count_label.pack(side="left", fill="y")
        self._fetch_time_label = tk.Label(
            footer,
            text=f"{self._fetch_ms:.0f} ms" if self._fetch_ms is not None else "",
            bg=c["bg"],
            fg=c["proc_fg"],
            font=("Segoe UI", 8),
            anchor="e",
            padx=6,
        )
        self._fetch_time_label.pack(side="right", fill="y")

        # --- Bindings ---
        assert self._entry is not None
        self._entry.bind("<Escape>", self._on_escape)
        self._entry.bind("<Return>", lambda _e: self._activate_selected() or "break")
        self._entry.bind(
            "<Control-Return>", lambda _e: self._move_and_activate_selected() or "break"
        )
        self._entry.bind(
            "<Control-Shift-Return>", lambda _e: self._on_ctrl_shift_enter() or "break"
        )
        self._entry.bind("<Up>", self._on_arrow_up)
        self._entry.bind("<Down>", self._on_arrow_down)
        self._entry.bind("<Prior>", self._on_page_up)
        self._entry.bind("<Next>", self._on_page_down)
        self._entry.bind("<Control-Home>", self._on_ctrl_home)
        self._entry.bind("<Control-End>", self._on_ctrl_end)
        self._entry.bind("<Tab>", self._on_tab)
        self._entry.bind("<Shift-Tab>", self._on_shift_tab)
        self._entry.bind("<ISO_Left_Tab>", self._on_shift_tab)
        self._entry.bind("<Control-Tab>", self._on_ctrl_tab)
        # KeyRelease fires after text is updated (and after KeyPress "break" handlers).
        self._entry.bind("<KeyRelease>", lambda _: self._on_text_changed())
        self._entry.bind("<<Paste>>", lambda _: self._entry.after(1, self._on_text_changed))  # type: ignore[union-attr]
        # Dismiss when focus leaves the overlay entirely; cancel that if focus returns.
        top.bind("<FocusOut>", self._on_focus_out)
        top.bind("<FocusIn>", self._on_focus_in)
        top.bind("<Control-Tab>", self._on_ctrl_tab)

        self._top = top
        # Apply initial desktop badge and controller filter.
        self._set_query_state([self._initial_desktop] if self._initial_desktop else [], "")
        if self._expand_on_startup:
            self._controller.toggle_all_expansions()
        self._entry.icursor(tk.END)
        self._position_window()
        top.deiconify()
        # A brief delay lets the SW_SHOWNORMAL focus-flash complete before we
        # grab focus; 10 ms is enough on all tested hardware (was 50 ms).
        top.after(10, self._grab_focus)

    # ------------------------------------------------------------------
    # Canvas rendering
    # ------------------------------------------------------------------

    def _refresh_canvas(self) -> None:
        if self._controller is None or self._canvas is None:
            return
        c = _colors()
        self._canvas.delete("all")

        flat = self._controller.flat_list
        sel = self._controller.selection_index
        canvas_w = _OVERLAY_WIDTH
        any_selected = bool(self._controller.selected_hwnds)

        n = len(self._controller.filtered_windows)
        if self._count_label is not None:
            self._count_label.config(text=f"{n} result{'s' if n != 1 else ''}")

        # Build cumulative y positions (rows have different heights)
        ys: list[int] = []
        y = 0
        for item in flat:
            ys.append(y)
            y += _row_height(item)
        total_h = max(y, 1)

        self._canvas.configure(scrollregion=(0, 0, canvas_w, total_h))

        for i, item in enumerate(flat):
            y0 = ys[i]
            rh = _row_height(item)
            y1 = y0 + rh

            if isinstance(item, TabInfo):
                row_bg = c["row_sel"] if i == sel else c["tab_bg"]
                self._canvas.create_rectangle(
                    0, y0, canvas_w, y1, fill=row_bg, outline="", tags=(f"row_bg_{i}",)
                )
                if _HAS_PIL and item.icon is not None:
                    try:
                        icon_id = id(item.icon)
                        photo = self._photo_image_cache.get(icon_id)
                        if photo is None:
                            photo = ImageTk.PhotoImage(item.icon)
                            self._photo_image_cache[icon_id] = photo
                        self._canvas.create_image(
                            _ICON_PAD_X,
                            y0 + (rh - _TAB_ICON_SIZE) // 2,
                            anchor="nw",
                            image=photo,
                        )
                    except Exception:
                        pass
                if item.is_active:
                    dot_x = _ICON_PAD_X + _TAB_ICON_SIZE + 8
                    dot_y = y0 + rh // 2
                    self._canvas.create_oval(
                        dot_x - 3,
                        dot_y - 3,
                        dot_x + 3,
                        dot_y + 3,
                        fill=c["tab_active"],
                        outline="",
                    )
                self._canvas.create_text(
                    _TEXT_X,
                    y0 + rh // 2,
                    anchor="w",
                    text=item.name,
                    fill=c["tab_active"] if item.is_active else c["title_fg"],
                    font=("Segoe UI", 9, "bold") if item.is_active else ("Segoe UI", 9),
                    width=canvas_w - _TEXT_X - 8,
                )
                continue

            # --- Window row ---
            w = item
            row_bg = c["row_sel"] if i == sel else c["row_bg"]
            self._canvas.create_rectangle(
                0, y0, canvas_w, y1, fill=row_bg, outline="", tags=(f"row_bg_{i}",)
            )

            # Expand/collapse indicator (shown only for windows with >1 tab)
            if self._controller.tab_count(w.hwnd) > 1:
                arrow = "▾" if self._controller.is_expanded(w.hwnd) else "▸"
                self._canvas.create_text(
                    _ARROW_X,
                    y0 + rh // 2,
                    text=arrow,
                    fill=c["proc_fg"],
                    font=("Segoe UI", 8),
                    anchor="w",
                )

            # Icon
            if _HAS_PIL and w.icon is not None:
                try:
                    icon_id = id(w.icon)
                    photo = self._photo_image_cache.get(icon_id)
                    if photo is None:
                        photo = ImageTk.PhotoImage(w.icon)
                        self._photo_image_cache[icon_id] = photo
                    self._canvas.create_image(
                        _ICON_PAD_X, y0 + _ICON_PAD_Y, anchor="nw", image=photo
                    )
                except Exception:
                    pass

            # Desktop number badge — square, vertically centered, styled like the tray icon
            if w.desktop_number > 0:
                bx0 = _ICON_PAD_X + _ICON_SIZE + 2
                bx1 = bx0 + _BADGE_W
                by0 = y0 + (rh - _BADGE_W) // 2
                by1 = by0 + _BADGE_W
                self._canvas.create_rectangle(
                    bx0, by0, bx1, by1, fill=_desktop_badge_color(w.desktop_number), outline=""
                )
                self._canvas.create_text(
                    (bx0 + bx1) // 2,
                    (by0 + by1) // 2,
                    text=str(w.desktop_number),
                    fill="#ffffff",
                    font=("Segoe UI", 10, "bold"),
                    anchor="center",
                )

            # Window title (bold)
            self._canvas.create_text(
                _TEXT_X,
                y0 + _TITLE_Y,
                anchor="nw",
                text=w.title,
                fill=c["title_fg"],
                font=("Segoe UI", 10, "bold"),
                width=canvas_w - _TEXT_X - 8,
            )
            # Process name (smaller, muted)
            self._canvas.create_text(
                _TEXT_X,
                y0 + _PROC_Y,
                anchor="nw",
                text=w.process_name,
                fill=c["proc_fg"],
                font=("Segoe UI", 8),
                width=canvas_w - _TEXT_X - 8,
            )

            # Notification bell — amber bell glyph at right edge; shifts left in multi-select mode
            if w.has_notification:
                cy = (y0 + y1) // 2
                notif_x = (
                    canvas_w - _NOTIF_X_OFFSET - _CHECKBOX_SIZE - _CHECKBOX_MARGIN
                    if any_selected
                    else canvas_w - _NOTIF_X_OFFSET
                )
                self._canvas.create_text(
                    notif_x,
                    cy,
                    text=_NOTIF_BELL_CHAR,
                    fill=_NOTIF_COLOR,
                    font=_NOTIF_BELL_FONT,
                    anchor="center",
                )

            # Checkbox — only shown when at least one window is checked
            if any_selected:
                cx1 = canvas_w - _CHECKBOX_MARGIN
                cx0 = cx1 - _CHECKBOX_SIZE
                cy0 = y0 + (rh - _CHECKBOX_SIZE) // 2
                cy1 = cy0 + _CHECKBOX_SIZE
                is_checked = w.hwnd in self._controller.selected_hwnds
                box_fill = c["row_sel"] if is_checked else ""
                self._canvas.create_rectangle(
                    cx0, cy0, cx1, cy1, outline=c["proc_fg"], fill=box_fill, width=1
                )
                if is_checked:
                    self._canvas.create_text(
                        (cx0 + cx1) // 2,
                        (cy0 + cy1) // 2,
                        text="✓",
                        fill=c["title_fg"],
                        font=("Segoe UI", 9, "bold"),
                        anchor="center",
                    )

        # Scroll the selected row into view only when it falls outside the viewport
        if 0 <= sel < len(flat):
            sel_y0 = ys[sel]
            sel_y1 = sel_y0 + _row_height(flat[sel])
            top_frac, bottom_frac = self._canvas.yview()
            view_top = top_frac * total_h
            view_bottom = bottom_frac * total_h
            if sel_y0 < view_top:
                self._canvas.yview_moveto(sel_y0 / total_h)
            elif sel_y1 > view_bottom:
                visible_h = (bottom_frac - top_frac) * total_h
                self._canvas.yview_moveto((sel_y1 - visible_h) / total_h)

    def _refresh_selection_only(self, old_sel: int, new_sel: int) -> None:
        """Update only the highlight color of the two affected rows and scroll into view.

        Avoids a full canvas redraw when only the selection index changes.
        """
        if self._controller is None or self._canvas is None:
            return
        c = _colors()
        flat = self._controller.flat_list

        def _bg(i: int) -> str:
            if i == new_sel:
                return c["row_sel"]
            return c["tab_bg"] if isinstance(flat[i], TabInfo) else c["row_bg"]

        for idx in (old_sel, new_sel):
            if 0 <= idx < len(flat):
                self._canvas.itemconfig(f"row_bg_{idx}", fill=_bg(idx))

        if 0 <= new_sel < len(flat):
            y = 0
            ys: list[int] = []
            for item in flat:
                ys.append(y)
                y += _row_height(item)
            total_h = max(y, 1)
            sel_y0 = ys[new_sel]
            sel_y1 = sel_y0 + _row_height(flat[new_sel])
            top_frac, bottom_frac = self._canvas.yview()
            view_top = top_frac * total_h
            view_bottom = bottom_frac * total_h
            if sel_y0 < view_top:
                self._canvas.yview_moveto(sel_y0 / total_h)
            elif sel_y1 > view_bottom:
                visible_h = (bottom_frac - top_frac) * total_h
                self._canvas.yview_moveto((sel_y1 - visible_h) / total_h)

    def _refresh_icon_strip(self) -> None:
        if self._strip_canvas is None or self._controller is None:
            return
        c = _colors()
        self._strip_canvas.delete("all")

        icons = self._controller.app_icons
        sel_idx = self._controller.app_filter_index
        total_w = max(len(icons) * _STRIP_SLOT_W, _OVERLAY_WIDTH - 2)

        self._strip_canvas.configure(scrollregion=(0, 0, total_w, _STRIP_HEIGHT))

        for i, w in enumerate(icons):
            x0 = i * _STRIP_SLOT_W
            x1 = x0 + _STRIP_SLOT_W
            slot_bg = c["row_sel"] if i == sel_idx else c["bg"]
            self._strip_canvas.create_rectangle(x0, 0, x1, _STRIP_HEIGHT, fill=slot_bg, outline="")

            icon_drawn = False
            if _HAS_PIL and w.icon is not None:
                try:
                    icon_id = id(w.icon)
                    photo = self._photo_image_cache.get(icon_id)
                    if photo is None:
                        photo = ImageTk.PhotoImage(w.icon)
                        self._photo_image_cache[icon_id] = photo
                    self._strip_canvas.create_image(
                        x0 + _STRIP_PAD_X, _STRIP_PAD_Y, anchor="nw", image=photo
                    )
                    icon_drawn = True
                except Exception:
                    pass

            if not icon_drawn:
                # Text fallback: process name without extension, up to 4 chars
                name = w.process_name.rsplit(".", 1)[0][:4].upper()
                self._strip_canvas.create_text(
                    x0 + _STRIP_SLOT_W // 2,
                    _STRIP_HEIGHT // 2,
                    text=name,
                    fill=c["title_fg"],
                    font=("Segoe UI", 8, "bold"),
                    anchor="center",
                )

            # Vertical separator between slots
            if i < len(icons) - 1:
                self._strip_canvas.create_line(
                    x1,
                    _STRIP_DIV_PAD,
                    x1,
                    _STRIP_HEIGHT - _STRIP_DIV_PAD,
                    fill=c["border"],
                    width=1,
                )

        # Scroll selected slot into view
        if sel_idx is not None and icons:
            frac = (sel_idx * _STRIP_SLOT_W) / total_w
            self._strip_canvas.xview_moveto(frac)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_text_changed(self, *_: object) -> None:
        if self._controller is None or self._entry is None:
            return
        new_text = self._entry.get()
        if new_text != self._controller.query:
            self._controller.set_query(new_text)
        self._refresh_icon_strip()
        self._refresh_canvas()
        self._resize_to_fit()

    def _on_tab(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            self._controller.cycle_app_filter(1)
            self._refresh_icon_strip()
            self._refresh_canvas()
        return "break"

    def _on_shift_tab(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            self._controller.cycle_app_filter(-1)
            self._refresh_icon_strip()
            self._refresh_canvas()
        return "break"

    def _on_ctrl_tab(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            self._controller.toggle_all_expansions()
            self._refresh_canvas()
            self._resize_to_fit()
        return "break"

    def _fetch_tabs_bg(self, windows: list[WindowInfo], cancel: threading.Event, gen: int) -> None:
        """Launch one daemon thread per window to fetch UIA tabs and favicons in parallel."""
        try:
            from windows_navigator.tabs import fetch_tabs
        except ImportError:
            return

        sem = threading.Semaphore(8)  # cap concurrent UIA + network threads

        def _fetch_one(w: WindowInfo) -> None:
            with sem:
                if cancel.is_set():
                    return
                result: list[TabInfo] = []
                try:
                    import ctypes as _ct

                    _ct.windll.ole32.CoInitializeEx(None, 0)  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    result.extend(fetch_tabs(w.hwnd) or [])
                except Exception:
                    pass
                finally:
                    try:
                        import ctypes as _ct

                        _ct.windll.ole32.CoUninitialize()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                if cancel.is_set() or not result:
                    return
                try:
                    from windows_navigator.favicons import fetch_favicon

                    _is_wt = w.process_name.upper() == "WINDOWSTERMINAL.EXE"
                    for tab in result:
                        if cancel.is_set():
                            break
                        if tab.domain:
                            tab.icon = fetch_favicon(tab.domain)
                        else:
                            if _is_wt:
                                try:
                                    from windows_navigator.wt_icons import fetch_wt_tab_icon

                                    tab.icon = fetch_wt_tab_icon(tab.name)
                                except Exception:
                                    pass
                            if tab.icon is None and w.icon is not None:
                                try:
                                    from PIL import Image as _PILImage

                                    tab.icon = w.icon.resize(
                                        (_TAB_ICON_SIZE, _TAB_ICON_SIZE), _PILImage.LANCZOS
                                    )
                                except Exception:
                                    pass
                except Exception:
                    pass
                if cancel.is_set() or self._controller is None or self._fetch_gen != gen:
                    return
                self._root.after(0, self._on_tabs_fetched, w.hwnd, result, gen)

        for w in windows:
            if cancel.is_set():
                break
            if w.process_name.upper() == "OUTLOOK.EXE":
                continue
            threading.Thread(target=_fetch_one, args=(w,), daemon=True).start()

    def _on_tabs_fetched(self, hwnd: int, tabs: list[TabInfo], gen: int) -> None:
        """Main-thread callback: store fetched tabs and refresh if the window is expanded."""
        if self._controller is None or self._canvas is None or self._fetch_gen != gen:
            return
        self._controller.set_tabs(hwnd, tabs)
        if self._controller.is_expanded(hwnd):
            self._refresh_canvas()
            self._resize_to_fit()
        else:
            # Redraw just to show the ▸ indicator on the window row
            self._refresh_canvas()

    def _on_escape(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        if self._controller and self._controller.bell_filter:
            self._controller.toggle_bell_filter()
            self._update_bell_badge()
            self._refresh_icon_strip()
            self._refresh_canvas()
            self._resize_to_fit()
        elif self._controller and self._controller.app_filter is not None:
            self._controller.clear_app_filter()
            self._refresh_icon_strip()
            self._refresh_canvas()
        else:
            startup_nums = [self._initial_desktop] if self._initial_desktop else []
            at_startup = self._desktop_prefix_nums == startup_nums and (
                self._entry is None or self._entry.get() == ""
            )
            if at_startup:
                self.hide()
            else:
                self._set_query_state(startup_nums, "")

    def _on_backspace(self, _event: tk.Event) -> str | None:  # type: ignore[type-arg]
        """Backspace at caret 0: remove the rightmost badge (bell first, then desktop badges)."""
        if self._entry is None or self._entry.index(tk.INSERT) != 0:
            return None
        if self._controller and self._controller.bell_filter:
            self._controller.toggle_bell_filter()
            self._update_bell_badge()
            self._refresh_icon_strip()
            self._refresh_canvas()
            self._resize_to_fit()
            return "break"
        if self._desktop_prefix_nums:
            self._set_query_state(
                self._desktop_prefix_nums[:-1],
                self._entry.get() if self._entry is not None else "",
            )
            return "break"
        return None

    def _on_ctrl_backspace(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        """Delete the word (and any leading spaces) to the left of the cursor."""
        if self._entry is not None:
            text = self._entry.get()
            cursor = self._entry.index(tk.INSERT)
            pos = cursor
            while pos > 0 and text[pos - 1] == " ":
                pos -= 1
            while pos > 0 and text[pos - 1] != " ":
                pos -= 1
            if pos < cursor:
                self._entry.delete(pos, cursor)
                self._on_text_changed()
        return "break"

    def _on_ctrl_digit(self, event: tk.Event) -> str:  # type: ignore[type-arg]
        """Toggle a desktop-number prefix badge (Ctrl+1–9)."""
        num = int(event.keysym)
        nums = list(self._desktop_prefix_nums)
        if num in nums:
            nums.remove(num)
        else:
            nums.append(num)
        self._set_query_state(nums, self._entry.get() if self._entry is not None else "")
        return "break"

    def _on_ctrl_zero(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        """Toggle the current desktop's prefix badge (Ctrl+0)."""
        num = self._initial_desktop
        if num:
            nums = list(self._desktop_prefix_nums)
            if num in nums:
                nums.remove(num)
            else:
                nums.append(num)
            self._set_query_state(nums, self._entry.get() if self._entry is not None else "")
        return "break"

    def _on_keypress_jump(self, _event: tk.Event) -> str | None:  # type: ignore[type-arg]
        """Ctrl+Shift+1–9: filter to #N and activate the first window on that desktop.

        Uses Win32 GetKeyState instead of event.keycode/state — Tkinter's keycode mapping
        is unreliable on Windows and keysym changes under Shift ("1" → "exclam", etc.).
        """
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            if not (user32.GetKeyState(0x11) & 0x8000):  # VK_CONTROL
                return None
            if not (user32.GetKeyState(0x10) & 0x8000):  # VK_SHIFT
                return None
            for i in range(9):
                if user32.GetKeyState(0x31 + i) & 0x8000:  # VK_1–VK_9
                    num = i + 1
                    self._set_query_state([num], "")
                    if self._controller and self._controller.flat_list:
                        self._activate_selected()
                    else:
                        from windows_navigator.virtual_desktop import switch_to_desktop_number

                        switch_to_desktop_number(num)
                        self.hide()
                    return "break"
        except AttributeError:
            pass  # non-Windows: windll unavailable
        return None

    def _on_ctrl_plus(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        """Increment the sole desktop badge (Ctrl+/=) when exactly one badge is shown."""
        if len(self._desktop_prefix_nums) == 1 and self._entry is not None:
            n = self._desktop_prefix_nums[0]
            if n < 9:
                self._set_query_state([n + 1], self._entry.get())
        return "break"

    def _on_ctrl_minus(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        """Decrement the sole desktop badge (Ctrl+-) when exactly one badge is shown."""
        if len(self._desktop_prefix_nums) == 1 and self._entry is not None:
            n = self._desktop_prefix_nums[0]
            if n > 1:
                self._set_query_state([n - 1], self._entry.get())
        return "break"

    def _on_ctrl_grave(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        """Toggle the bell filter (Ctrl+` / Ctrl+½) — show only windows with notifications."""
        if self._controller:
            self._controller.toggle_bell_filter()
            self._update_bell_badge()
            self._refresh_icon_strip()
            self._refresh_canvas()
            self._resize_to_fit()
        return "break"

    def _on_ctrl_space(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        """Toggle multi-select checkbox on the currently highlighted window (Ctrl+Space)."""
        if self._controller:
            hwnd = self._controller.selected_hwnd()
            if hwnd is not None:
                self._controller.toggle_hwnd_selection(hwnd)
                self._refresh_canvas()
        return "break"

    def _update_bell_badge(self) -> None:
        """Create or destroy the bell badge in the entry bar to reflect controller._bell_filter."""
        if self._entry_inner is None or self._entry is None or self._controller is None:
            return
        if self._bell_badge_widget is not None:
            self._bell_badge_widget.destroy()
            self._bell_badge_widget = None
        if self._controller.bell_filter:
            frame = tk.Frame(
                self._entry_inner,
                bg=_NOTIF_COLOR,
                width=_BADGE_ENTRY_SIZE,
                height=_BADGE_ENTRY_SIZE,
            )
            frame.pack_propagate(False)
            tk.Label(
                frame, text=_NOTIF_BELL_CHAR, bg=_NOTIF_COLOR, fg="#ffffff", font=_NOTIF_BELL_FONT
            ).pack(fill="both", expand=True)
            frame.pack(side="left", before=self._entry, padx=(0, 2))
            self._bell_badge_widget = frame

    def _grab_focus(self) -> None:
        if self._top is None or self._entry is None:
            return
        _force_foreground(int(self._top.winfo_id()))
        try:
            import ctypes

            ctypes.windll.user32.SetFocus(int(self._entry.winfo_id()))  # type: ignore[attr-defined]
        except Exception:
            pass
        self._entry.focus_force()

    def _resize_to_fit(self) -> None:
        """Resize the canvas and window to match the current flat list height."""
        if self._canvas is None or self._controller is None or self._top is None:
            return
        flat = self._controller.flat_list
        max_h = _MAX_ROWS_VISIBLE * _ROW_HEIGHT
        new_h = max(min(sum(_row_height(item) for item in flat), max_h), _ROW_HEIGHT)
        self._canvas.configure(height=new_h)
        self._position_window()

    def _on_arrow_up(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            old = self._controller.selection_index
            self._controller.move_up()
            self._refresh_selection_only(old, self._controller.selection_index)
        return "break"  # prevent Entry cursor movement

    def _on_arrow_down(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            old = self._controller.selection_index
            self._controller.move_down()
            self._refresh_selection_only(old, self._controller.selection_index)
        return "break"

    def _on_page_up(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            old = self._controller.selection_index
            self._controller.move_page_up(_MAX_ROWS_VISIBLE)
            self._refresh_selection_only(old, self._controller.selection_index)
        return "break"

    def _on_page_down(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            old = self._controller.selection_index
            self._controller.move_page_down(_MAX_ROWS_VISIBLE)
            self._refresh_selection_only(old, self._controller.selection_index)
        return "break"

    def _on_ctrl_home(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            old = self._controller.selection_index
            self._controller.move_to_first()
            self._refresh_selection_only(old, self._controller.selection_index)
        return "break"

    def _on_ctrl_end(self, _event: tk.Event) -> str:  # type: ignore[type-arg]
        if self._controller:
            old = self._controller.selection_index
            self._controller.move_to_last()
            self._refresh_selection_only(old, self._controller.selection_index)
        return "break"

    def _on_focus_in(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        # Focus returned (e.g. _grab_focus re-grabbed after the SW_SHOWNORMAL
        # brief-activate/deactivate cycle) — cancel any pending hide.
        if self._pending_hide is not None and self._top is not None:
            self._top.after_cancel(self._pending_hide)
            self._pending_hide = None

    def _on_focus_out(self, _event: tk.Event) -> None:  # type: ignore[type-arg]
        # Small delay lets any in-flight canvas click fire and activate before we close.
        # Cancel any existing pending hide first — FocusOut can fire twice (once from the
        # SW_SHOWNORMAL flash on deiconify, once from the user click) and without this the
        # first after-ID becomes orphaned: _on_focus_in only cancels _pending_hide (the
        # latest ID), so the orphaned callback fires later and closes a healthy overlay.
        if self._closing or self._picker_open:
            return
        if self._top is not None:
            if self._pending_hide is not None:
                self._top.after_cancel(self._pending_hide)
            self._pending_hide = self._top.after(50, self.hide)

    def _activate_selected(self) -> None:
        if self._controller is None:
            return
        item = self._controller.selected_item()
        if item is None:
            self.hide()
            return
        # Activate BEFORE hiding: gives the target window one clean WM_ACTIVATE rather
        # than letting Windows auto-activate it when we destroy the overlay and then
        # activating it again explicitly — the double-activation causes a spinning cursor
        # in apps like Firefox and Windows Terminal that are slow to process WM_SETCURSOR.
        self._closing = True
        if isinstance(item, TabInfo):
            try:
                from windows_navigator.tabs import select_tab

                select_tab(item)
            except Exception:
                pass
        self._on_activate(item.hwnd)
        self.hide()

    def _move_and_activate_selected(self) -> None:
        if self._controller is None:
            return
        multi = self._controller.selected_hwnds
        if multi:
            focused = self._controller.selected_hwnd()
            # Only move checked windows; activate focused last if it's also checked,
            # otherwise activate an arbitrary checked window.
            hwnds = [h for h in multi if h != focused]
            if focused in multi:
                hwnds.append(focused)
            self._closing = True
            for hwnd in hwnds[:-1]:
                self._on_move(hwnd)
            self._on_move(hwnds[-1])
            self.hide()
        else:
            hwnd = self._controller.selected_hwnd()
            if hwnd is None:
                self.hide()
                return
            self._closing = True
            self._on_move(hwnd)
            self.hide()

    def _on_ctrl_shift_enter(self) -> None:
        """Show the desktop-picker popup (Ctrl+Shift+Enter)."""
        if self._controller is None or self._on_move_to is None:
            return
        multi = self._controller.selected_hwnds
        focused = self._controller.selected_hwnd()
        if multi:
            # Only include checked windows; put focused last if it's also checked
            hwnds = [h for h in multi if h != focused]
            if focused in multi:
                hwnds.append(focused)
        else:
            hwnds = [focused] if focused is not None else []
        if hwnds:
            self._show_desktop_picker(hwnds)

    def _show_desktop_picker(self, hwnds: list[int]) -> None:
        """Open a small popup letting the user choose a target desktop for *hwnds*."""
        if self._top is None or self._on_move_to is None:
            return
        c = _colors()
        desktop_count = _get_desktop_count()

        picker = tk.Toplevel(self._top)
        picker.overrideredirect(True)
        picker.attributes("-topmost", True)
        picker.configure(bg=c["border"])

        frame = tk.Frame(picker, bg=c["bg"], padx=10, pady=8)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Label(
            frame,
            text="Move to desktop:",
            bg=c["bg"],
            fg=c["proc_fg"],
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(0, 8))

        def _select(n: int) -> None:
            picker.destroy()
            self._picker_open = False
            assert self._on_move_to is not None
            self._on_move_to(hwnds, n)
            self.hide()

        def _cancel() -> None:
            picker.destroy()
            self._picker_open = False
            if self._entry is not None:
                self._entry.focus_force()

        for i in range(1, desktop_count + 1):
            color = _desktop_badge_color(i)
            btn = tk.Button(
                frame,
                text=str(i),
                bg=color,
                fg="#ffffff",
                font=("Segoe UI", 10, "bold"),
                relief="flat",
                cursor="hand2",
                width=2,
                height=1,
                command=lambda n=i: _select(n),
            )
            btn.pack(side="left", padx=2)

        # "New desktop" button
        tk.Button(
            frame,
            text="+ N",
            bg=c["border"],
            fg=c["title_fg"],
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            height=1,
            command=lambda: _select(0),
        ).pack(side="left", padx=(6, 2))

        # Position the picker just below the overlay, horizontally centred
        self._top.update_idletasks()
        picker.update_idletasks()
        pw = picker.winfo_reqwidth()
        x = self._top.winfo_x() + (self._top.winfo_width() - pw) // 2
        y = self._top.winfo_y() + self._top.winfo_height() + 2
        picker.geometry(f"+{x}+{y}")

        def _on_key(event: tk.Event) -> None:  # type: ignore[type-arg]
            if event.keysym.isdigit():
                n = int(event.keysym)
                if 1 <= n <= desktop_count:
                    _select(n)
            elif event.keysym in ("n", "N"):
                _select(0)
            elif event.keysym == "Escape":
                _cancel()

        picker.bind("<KeyPress>", _on_key)
        self._picker_open = True
        picker.focus_force()
        picker.grab_set()

    # ------------------------------------------------------------------
    # Query state helpers
    # ------------------------------------------------------------------

    def _set_query_state(self, nums: list[int], text: str) -> None:
        """Update badges, entry text, and controller filter state."""
        self._update_prefix_badges(nums)
        if self._entry is None:
            return
        old_cursor = self._entry.index(tk.INSERT)
        self._entry.delete(0, tk.END)
        if text:
            self._entry.insert(0, text)
            self._entry.icursor(min(old_cursor, len(text)))
        if self._controller:
            self._controller.set_desktop_nums(set(nums))
            self._controller.set_query(text)
        self._refresh_icon_strip()
        self._refresh_canvas()
        self._resize_to_fit()

    def _update_prefix_badges(self, nums: list[int]) -> None:
        self._desktop_prefix_nums = nums
        if self._entry_inner is None or self._entry is None:
            return
        for badge in self._prefix_badge_widgets:
            badge.destroy()
        self._prefix_badge_widgets = []
        for num in nums:
            color = _desktop_badge_color(num)
            frame = tk.Frame(
                self._entry_inner,
                bg=color,
                width=_BADGE_ENTRY_SIZE,
                height=_BADGE_ENTRY_SIZE,
            )
            frame.pack_propagate(False)
            tk.Label(
                frame, text=str(num), bg=color, fg="#ffffff", font=("Segoe UI", 10, "bold")
            ).pack(fill="both", expand=True)
            frame.pack(side="left", before=self._entry, padx=(0, 2))
            self._prefix_badge_widgets.append(frame)
        # Keep bell badge after all desktop badges
        if self._bell_badge_widget is not None:
            self._bell_badge_widget.pack_forget()
            self._bell_badge_widget.pack(side="left", before=self._entry, padx=(0, 2))

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _position_window(self) -> None:
        if self._top is None or self._controller is None:
            return
        left, top, right, bottom = _get_cursor_monitor_workarea()
        mon_w = right - left
        mon_h = bottom - top

        flat = self._controller.flat_list
        max_h = _MAX_ROWS_VISIBLE * _ROW_HEIGHT
        list_h = max(min(sum(_row_height(item) for item in flat), max_h), _ROW_HEIGHT)
        overlay_h = _ENTRY_AREA_H + _STRIP_HEIGHT + list_h + _COUNT_BAR_H
        overlay_w = _OVERLAY_WIDTH

        # Anchor y to where the window sits at max height so the search box
        # doesn't move as the result list grows or shrinks while typing.
        max_overlay_h = (
            _ENTRY_AREA_H + _STRIP_HEIGHT + _MAX_ROWS_VISIBLE * _ROW_HEIGHT + _COUNT_BAR_H
        )
        x = left + (mon_w - overlay_w) // 2
        y = top + (mon_h - max_overlay_h) // 2
        self._top.geometry(f"{overlay_w}x{overlay_h}+{x}+{y}")
