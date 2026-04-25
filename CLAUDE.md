# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (Linux/macOS — dev tools only, Win32 extras unavailable)
python3 -m venv .venv && source .venv/bin/activate.fish && pip install -e ".[dev]"  # fish shell
# python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"     # bash/zsh

# Install (Windows — full)
py -m pip install -e ".[windows,dev]"

# Run
python -m windows_navigator

# Test / lint / format
make test        # pytest
make lint        # ruff check .
make format      # ruff format .
```

Run a single test file: `pytest tests/test_filter.py`

`make test` requires `pytest` on `PATH`; if the venv is not activated: `.venv/bin/python -m pytest tests/ -q`

## Tech stack

| Concern | Choice |
|---------|--------|
| Language | Python 3.11+ |
| UI | `tkinter` (stdlib) |
| Win32 API | `pywin32` (`win32gui`, `win32process`, `win32api`, `win32con`) |
| System tray | `pystray` + `Pillow` |
| Global hotkey | Win32 `RegisterHotKey` via ctypes (no extra dep) |
| Theme detection | `darkdetect` |
| Virtual desktop | Raw ctypes COM + `pyvda` (Windows 11 22H2+ workaround) |
| UIA (tabs) | `comtypes` |
| Linter/formatter | `ruff` (rules E, F, I; line-length 100) |
| Tests | `pytest` + `pytest-mock` |

Windows-only runtime deps (`pywin32`, `pystray`, `pyvda`) are in the `[windows]` extra in `pyproject.toml`. Dev deps (`pytest`, `ruff`) are in `[dev]`. Linux CI installs `.[dev]` only.

## Architecture

Windows Navigator is a keyboard-driven window switcher for Windows. Press **Ctrl+Space** to open an overlay listing all open windows; type to filter, arrow keys to navigate, Enter to focus, **Ctrl+Enter** to move the window to the current virtual desktop and focus it.

### Repository layout

```
src/windows_navigator/
    __init__.py          # empty
    __main__.py          # entry point shim → app.main()
    app.py               # wires everything: Tk root, overlay, hotkey, flash monitor, tray
    models.py            # WindowInfo and TabInfo dataclasses
    filter.py            # filter_windows() — pure Python, no Win32
    controller.py        # OverlayController — pure Python state machine
    provider.py          # RealWindowProvider — Win32 window enumeration + icons
    virtual_desktop.py   # assign_desktop_numbers(), move_window_to_current_desktop(), move_window_to_adjacent_desktop(), switch_to_desktop_number() — COM
    activation.py        # activate_window() — Win32 restore + SetForegroundWindow
    overlay.py           # NavigatorOverlay — tkinter Canvas UI
    tabs.py              # UIA tab discovery + activation — Windows-only, deferred imports
    theme.py             # DESKTOP_COLORS, desktop_badge_color() — shared colour palette
    tray.py              # TrayIcon — pystray system tray

tests/
    test_filter.py           # filter_windows()
    test_keyboard.py         # OverlayController state machine + tab search
    test_provider.py         # RealWindowProvider icon extraction fallback
    test_virtual_desktop.py  # desktop number assignment + fallbacks
    test_tray.py             # _make_tray_icon — pixel-level color checks
    test_theme.py            # desktop_badge_color() — format, cycling, palette match
    test_overlay.py          # _desktop_badge_color() overlay helper (requires tkinter stub)
```

### Module responsibilities

| File | Role |
|------|------|
| `app.py` | Wires everything: Tk root, overlay, two hotkey listeners (overlay + window-move), flash monitor, system tray, queue-based thread marshaling, desktop-change poller |
| `controller.py` | Pure Python state machine — query string, app filter, bell filter, tab state (`_tabs`, `_expanded`), `flat_list`, selection index. No Tk dependency. Defines three focused sub-protocols (`FilterControllerProtocol`, `NavigationControllerProtocol`, `TabControllerProtocol`) composed into `OverlayControllerProtocol`. |
| `overlay.py` | Tkinter Canvas UI — renders list (window rows + inline tab rows), desktop badges, icons, handles keyboard input; resizes dynamically as filter changes |
| `provider.py` | Win32 API: enumerates windows, extracts icons, determines z-order (recency); accepts injected `DesktopAssigner`, `flashing` set, and `extra_filters` list (`WindowFilter` protocol) |
| `activation.py` | Win32 API: restores and focuses the selected window via `SetForegroundWindow`; also owns `_force_foreground` and `_get_cursor_monitor_workarea` |
| `virtual_desktop.py` | COM via ctypes: assigns 1-based virtual desktop numbers to each window; registry helpers for current desktop; `switch_to_desktop_number` and `move_window_to_adjacent_desktop` via pyvda |
| `filter.py` | Pure Python: `filter_windows(windows, query, desktop_nums)` — text filter (all whitespace-separated tokens must match title or process name) plus optional desktop set filter |
| `models.py` | `WindowInfo` and `TabInfo` dataclasses |
| `tabs.py` | UIA tab discovery (`fetch_tabs`) and activation (`select_tab`) — deferred Windows-only imports, COM must be initialised on the calling thread |
| `theme.py` | Shared colour palette: `DESKTOP_COLORS` list and `desktop_badge_color()` — single source of truth for both overlay badges and tray icon |
| `tray.py` | pystray system-tray icon showing current desktop number and color; runs in a separate thread |

### Event flow

1. `_start_hotkey_listener` thread receives `WM_HOTKEY` via `RegisterHotKey` → enqueues `fg_hwnd` to `show_queue`
2. `app.poll_queue()` runs every 50 ms on the Tk main thread, dequeues, calls `provider.get_windows()`
3. Current desktop number is derived from windows (first `is_current_desktop=True` entry) and passed as `initial_desktop=N` to `overlay.show()`
4. Overlay resets with fresh windows, renders the desktop number as a coloured badge widget in the search entry (text field starts empty), shows via Tk `Toplevel`
5. User interaction updates `OverlayController` state (pure Python)
6. On Enter: `overlay.hide()` → `activate_window(hwnd)`
   On Ctrl+Enter: `overlay.hide()` → `move_window_to_current_desktop(hwnd)` → `activate_window(hwnd)`
7. `app.poll_desktop()` runs every 500 ms, reads the registry, updates the tray icon if the desktop changed

### Key design decisions

- **Single hidden Tk root** — one withdrawn `Tk()` root with a `Toplevel` overlay prevents event-loop conflicts with pystray.
- **Queue-based hotkey marshaling** — the hotkey thread must not touch Tk directly; it enqueues `fg_hwnd`, the main thread dequeues via `poll_queue`.
- **RegisterHotKey instead of keyboard library** — `_start_hotkey_listener` in `app.py` uses Win32 `RegisterHotKey(hwnd=NULL, ...)` on a daemon thread. `WM_HOTKEY` is explicitly exempted by Windows from the foreground-lock timeout, so `SetForegroundWindow` in `_grab_focus` works reliably after alt-tab. A `WH_KEYBOARD_LL` hook (the old `keyboard` library approach) does NOT receive this exemption — even `AttachThreadInput` + `SetForegroundWindow` fails in that context on modern Windows.
- **Pure Python controller** — all filter/selection logic lives in `controller.py` with no Tk import, making it fully testable on Linux.
- **`OverlayControllerProtocol` and ISP sub-protocols** — The full interface is composed from three focused sub-protocols: `FilterControllerProtocol` (query, app filter, bell filter), `NavigationControllerProtocol` (selection, flat list, movement), and `TabControllerProtocol` (tab storage, expansion). `OverlayControllerProtocol` inherits all three and adds `reset()`. Depend on a sub-protocol when only a slice of the interface is needed; depend on `OverlayControllerProtocol` when everything is needed. `NavigatorOverlay` types its `_controller` field as `OverlayControllerProtocol | None`, not `OverlayController` directly. `toggle_expansion` is deliberately absent from all protocols — the overlay only calls `toggle_all_expansions`; per-window expansion is an `OverlayController`-only method used directly in tests.
- **Controller factory injection** — `NavigatorOverlay.__init__` accepts `controller_factory: Callable[[list[WindowInfo]], OverlayControllerProtocol] | None = None`, defaulting to `OverlayController`. `show()` calls `self._controller_factory(windows)` rather than hardcoding `OverlayController(windows)`. Pass a mock factory in tests to exercise overlay rendering without the full state machine, and to swap controller implementations without subclassing or patching.
- **Deferred Win32 imports** — all `win32*` and `pystray` imports happen inside functions/methods, never at module level. This lets the test suite run on Linux.
- **Overlay closed before activation** — `overlay.hide()` is called before `activate_window()` so the overlay doesn't steal focus back.
- **COM initialization** — `CoInitializeEx(COINIT_APARTMENTTHREADED)` must be called before `CoCreateInstance` in `_try_raw_ctypes`. Neither pywin32 nor Tkinter initialize COM on the calling thread automatically.
- **Vtable access in `_RawVDManager`** — COM vtable is two levels of indirection: `object → vtable_ptr → fn_ptrs`. Cast the object pointer to `POINTER(c_void_p)`, read index `[0]` to get the vtable pointer, cast *that* to `POINTER(c_void_p)`, then index by method number (3 = `IsWindowOnCurrentVirtualDesktop`, 4 = `GetWindowDesktopId`, 5 = `MoveWindowToDesktop`). All three methods share `_vtable_call(index, restype, argtypes, *args)` to avoid repeating the dereference sequence. `_GUID`, `_make_guid`, and `_guid_to_str` are module-level so they can be shared across `_try_raw_ctypes` and the three `_RawVDManager` methods without local redefinition.
- **`_VirtualDesktopManager` Protocol** — `virtual_desktop.py` exposes this Protocol as the DIP boundary for the COM manager. `_get_manager()` returns `_VirtualDesktopManager | None`; callers (`assign_desktop_numbers`, `move_window_to_current_desktop`) rely on the typed interface rather than `hasattr` guards. `_RawVDManager` and the comtypes-generated class both satisfy the protocol structurally; any failure at the call site is caught by the surrounding `try/except`.
- **`_ManagerCache` encapsulates COM manager state** — The two related globals (`_manager`, `_init_attempted`) that track lazy COM initialisation live in a `_ManagerCache` instance (`_manager_cache`) rather than as bare module globals. `_get_manager()` delegates to `_manager_cache.get()`. This removes the `global` keyword from the initialisation path and keeps the cache state self-contained. Tests that patch `_get_manager` directly are unaffected.
- **Win32 `BOOL` vs `c_bool`** — Win32 `BOOL` is a 4-byte `c_int`, not `c_bool` (1 byte). Using `c_bool` for an output `BOOL*` parameter corrupts memory.
- **Icon extraction fallback chain** — `WM_GETICON(ICON_BIG)` → `WM_GETICON(ICON_SMALL)` → `GetClassLong(GCL_HICON)` → `SHGetFileInfo` on the exe path. The first three return 0 for most modern/UWP apps; `SHGetFileInfo` is required to get their shell icon. Icons from `SHGetFileInfo` are caller-owned and need `DestroyIcon`; the others do not.
- **`QueryFullProcessImageNameW` for exe path** — `RealWindowProvider._get_process_name` and `_shgetfileinfo_icon` both need the process exe path; they share `_query_exe_path(handle)` which calls `QueryFullProcessImageNameW` (kernel32) via ctypes — it works with `PROCESS_QUERY_LIMITED_INFORMATION`. Do NOT use `win32api.GetModuleFileNameEx` (which does not exist in pywin32's win32api module) or the Win32 `GetModuleFileNameEx` (which requires `PROCESS_VM_READ`). Either mistake silently returns `""` from the `except Exception` guard, causing every window to share `process_name=""` and collapsing the icon strip to a single slot.
- **Provider helper methods** — `_query_exe_path(handle)` is a module-level function in `provider.py` shared by both `IconExtractor` and `RealWindowProvider`. `IconExtractor.extract` and `IconExtractor._shgetfileinfo_icon` are `@staticmethod` methods on `IconExtractor`. `RealWindowProvider._get_process_name` is a `@staticmethod` on `RealWindowProvider`. None of these have callers outside their respective classes.
- **Process exclusion list** — `_EXCLUDED_PROCESSES` in `provider.py` is a module-level `set[str]` of lowercase exe names (e.g. `"textinputhost.exe"`) that are silently skipped during window enumeration. The check runs after `_get_process_name` resolves the exe, so the process name is already normalised. Add entries here for system utility windows that pass the visibility/title filter but should never appear in the switcher.
- **`WindowFilter` and `extra_filters`** — `provider.py` defines a `WindowFilter` Protocol: `(hwnd: int, title: str, process_name: str) -> bool`. `RealWindowProvider.__init__` accepts `extra_filters: Sequence[WindowFilter] | None = None`; each filter is applied after the `_EXCLUDED_PROCESSES` check. Inject additional filters to extend exclusion behaviour without modifying `get_windows()` (OCP). The protocol is structural — any callable with matching signature satisfies it.
- **`DesktopAssigner` injection** — `RealWindowProvider.__init__` accepts an optional `assign_desktops: Callable[[list[int]], tuple[dict[int, int], dict[int, bool]]]` parameter. When omitted, it defaults to `virtual_desktop.assign_desktop_numbers`. Pass a mock in tests instead of patching module globals.
- **Multi-token text filter** — `filter.py` splits the text portion of a query on whitespace and requires every token to independently match the title or process name (case-insensitive substring). So `"aa cc"` matches `"aa bb cc"` even though the tokens are non-contiguous. Single-token queries behave identically to the old substring match.
- **Desktop badge filter** — desktop filtering is driven exclusively by the `_desktop_prefix_nums` badge list in the overlay, toggled via Ctrl+1–9. The controller receives the set via `set_desktop_nums(nums)`; `filter_windows` accepts it as `desktop_nums: set[int] | None`. Multiple badges are supported (OR logic). `#` and `#N` in the text entry are plain characters — no special parsing. Backspace on an empty entry removes the rightmost badge (bell badge if active, otherwise the rightmost desktop badge). When the last badge is gone, all windows are shown.
- **Desktop numbering from registry** — `virtual_desktop._get_registry_desktop_order()` reads `VirtualDesktopIDs` from `HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops` to get the true display order. Without this, numbers are assigned by z-order and the current desktop always gets number 1. `get_current_desktop_number()` and `get_current_desktop_guid()` both read `CurrentVirtualDesktop` from the same key — no COM needed.
- **Desktop colors** — `DESKTOP_COLORS` (blue, orange, green, purple, red, teal, amber, grey) lives in `theme.py` and is the single source of truth. Both `overlay.py` and `tray.py` import from it. Used for badge backgrounds in the overlay and the tray icon background. Always white text over these colors.
- **Overlay focus after click-away / alt+tab** — `_grab_focus` calls `_force_foreground` (defined in `activation.py`) which uses `AttachThreadInput` + `SetForegroundWindow` as a belt-and-suspenders fallback; the primary grant comes from `WM_HOTKEY` itself (see RegisterHotKey note above). After `SetForegroundWindow`, `_grab_focus` calls Win32 `SetFocus(entry_hwnd)` directly to route keyboard input to the entry widget, then `focus_force()` to update Tk's internal focus state. **`attach_to` selection**: `_grab_focus` reads `GetForegroundWindow()` at call time; if another window has focus (e.g. the user clicked while the overlay was opening), that window is passed as `attach_to` — using the stale hotkey-time hwnd would attach to the wrong thread and `SetForegroundWindow` would fail. Falls back to `_show_fg_hwnd` when no other window has foreground (normal open, alt+tab transitions). **SW_SHOWNORMAL flash**: Tk's `deiconify()` calls `ShowWindow(SW_SHOWNORMAL)` which briefly activates the window; Windows immediately revokes activation → `WM_ACTIVATE(WA_INACTIVE)` → Tk `<FocusOut>` → `_pending_hide` is scheduled. `_on_focus_in` cancels it when `_grab_focus` subsequently re-grabs focus — without this the overlay flashes (appears then immediately closes).
- **Dynamic overlay resize** — `_on_text_changed` calls `_resize_to_fit()` after every keystroke, which updates the canvas height and calls `_position_window()`. This ensures the window expands/shrinks as results change (e.g. clearing a desktop badge to show all windows). Maximum visible rows: 10.
- **Viewport-aware list scroll** — `_refresh_canvas` only calls `yview_moveto` when the selected row falls outside the current viewport. It reads `canvas.yview()` to get `(top_frac, bottom_frac)`, converts to pixel offsets against `total_h`, and scrolls the minimum amount needed (align to top when scrolling up, align to bottom when scrolling down). Scrolling unconditionally on every refresh caused the list to jump on every arrow key press even when the selection was already visible.
- **Overlay position anchored to max height** — `_position_window()` computes `y` using the maximum possible overlay height (`_ENTRY_AREA_H + _STRIP_HEIGHT + _MAX_ROWS_VISIBLE * _ROW_HEIGHT`) rather than the current height. This keeps the search box at a fixed screen position while the list grows or shrinks below it.
- **HiDPI / per-monitor DPI scaling** — `app.main()` calls `shcore.SetProcessDpiAwareness(2)` before creating the Tk root, then reads `root.winfo_fpixels('1i') / 96.0` to get the monitor DPI scale factor and calls `overlay.init_scale(factor)`. `init_scale` reassigns all pixel-based layout constants (`_ROW_HEIGHT`, `_BADGE_W`, paddings, etc.) scaled by that factor. Font sizes (in points) are intentionally excluded — they auto-scale once per-monitor DPI awareness is active. `_ICON_SIZE` is also excluded because icon images are always extracted at 32 × 32 px by `provider.py`.
- **Desktop number badge style** — badges in the window list are 22×22 px squares, vertically centred in the row, with 10 pt bold white text on the desktop colour — matching the tray icon aesthetic. `_BADGE_W = 22` controls the size; `_TEXT_X` must account for the 2 px gap between icon and badge.
- **Desktop prefix badge in the search entry** — the entry area is a composite `entry_inner` frame with `tk.Label` prefix badges on the left and a `tk.Entry` on the right. Desktop prefix badges are added only via Ctrl+1–9 and stored in `_desktop_prefix_nums`; `_set_query_state` calls `controller.set_desktop_nums(set(nums))` and `controller.set_query(text)` separately. `_on_text_changed` passes `entry.get()` directly to `controller.set_query`. Backspace at caret position 0 removes the rightmost badge (bell first, then desktop prefix badges right-to-left). **`<KeyRelease>` fires for arrows too**: `_on_text_changed` only calls `set_query` when the entry text has actually changed — without this guard any arrow key resets `selection_index` to 0.
- **Ctrl+Backspace word deletion** — `_on_ctrl_backspace` reads `entry.get()` and the integer cursor from `entry.index(tk.INSERT)`, scans back past spaces then non-space characters to find the word start, and calls `entry.delete(pos, cursor)`. Plain integer indexing — no badge-spanning complexity since desktop badges are never embedded in the entry text.
- **Ctrl+1–9 desktop badge toggle** — `<Control-Key-N>` bindings (1–9) are registered in a loop; all share `_on_ctrl_digit`. `event.keysym` for these events is the digit character (`"1"`–`"9"`), so `int(event.keysym)` gives the desktop number directly. If the number is already in `_desktop_prefix_nums` it is removed; otherwise it is appended (preserving insertion order). Returns `"break"` to prevent the digit from being typed into the entry.
- **Ctrl+/- desktop badge increment/decrement** — when exactly one desktop prefix is present (`len(_desktop_prefix_nums) == 1`), `Ctrl++` increments it and `Ctrl+-` decrements it (clamped to 1–9). Handlers read `_desktop_prefix_nums[0]` directly and call `_set_query_state([n±1], entry.get())`. `_set_query_state(nums, text)` takes badge numbers and entry text as separate arguments rather than a raw query string. Three bindings cover `+`: `<Control-equal>` (the `=` key), `<Control-plus>` (Shift+= on US layout, also numpad `+` on some systems), and `<Control-KP_Add>`.
- **Focus-out / focus-in close/cancel symmetry** — `_on_focus_out` cancels any existing `_pending_hide` before scheduling a new `self.hide` via `after(50)`. The cancel-before-reschedule is critical: `deiconify`'s SW_SHOWNORMAL flash triggers a FocusOut at T≈0, and a user click triggers a second FocusOut shortly after; without the cancel the first after-ID becomes orphaned and `_on_focus_in` only cancels the second — the orphaned callback fires later and closes a healthy overlay. `_pending_hide` is then cancelled in three places: (1) `show()` when the overlay is already visible, (2) `_on_focus_in` when focus returns (e.g. `_grab_focus` re-grabs focus after the SW_SHOWNORMAL cycle), and (3) `hide()` itself on entry. The 50 ms delay lets any in-flight canvas-click event activate its window before the overlay is destroyed.
- **Moving windows to current desktop** — `move_window_to_current_desktop(hwnd)` in `virtual_desktop.py` tries `pyvda` first (`AppView(hwnd).move(VirtualDesktop.current())`), then falls back to `IVirtualDesktopManager::MoveWindowToDesktop` (vtable index 5). `pyvda` is required because the public COM API silently does nothing for cross-process windows on Windows 11 22H2+; `pyvda` uses the version-specific internal `IVirtualDesktopManagerInternal` COM interface. `pyvda` is listed in the `[windows]` optional dependencies.
- **Ctrl+Win+Shift+Left/Right global hotkey** — `_start_move_hotkey_listener` in `app.py` registers `MOD_CONTROL | MOD_SHIFT | MOD_WIN` + `VK_LEFT`/`VK_RIGHT` (IDs 1 and 2) in a dedicated daemon thread, independent of the overlay hotkey thread. `GetForegroundWindow()` is captured at hotkey time and posted to `move_queue: Queue[tuple[int, int]]`. `poll_move_queue` on the Tk main thread dequeues and calls `move_window_to_adjacent_desktop(hwnd, direction)`. This function reads the desktop list from the registry, clamps the target to `[1, total]`, calls `pyvda.AppView(hwnd).move(VirtualDesktop(n))` to move the window, then `switch_to_desktop_number(n)` to switch desktops. Returns 0 at boundaries (does nothing). The tray is updated immediately with the target desktop number when the move succeeds.
- **Ctrl+Shift+N desktop jump** — `_on_keypress_jump` is bound as `<KeyPress>` with `add=True` on the entry widget. It uses Win32 `GetKeyState` (VK_CONTROL=0x11, VK_SHIFT=0x10, VK_1–VK_9=0x31–0x39) instead of Tkinter's `event.keycode`/`event.state`: Tkinter's keycode mapping is unreliable on Windows, and Shift changes the keysym from `"1"` to `"exclam"` etc., making keysym-based bindings unusable across keyboard layouts. When the filtered list is non-empty, the first window is activated (Windows auto-switches the desktop implicitly). When the target desktop is empty, `switch_to_desktop_number(n)` calls `pyvda.VirtualDesktop(n).go()` to switch explicitly, then `hide()` closes the overlay.
- **`show()` `fg_hwnd` parameter** — `show(windows, initial_desktop=0, fg_hwnd=0)` stores the foreground HWND captured at hotkey time in `self._show_fg_hwnd`. `_grab_focus` uses it as a fallback `attach_to` when `GetForegroundWindow()` at call time returns 0 or the overlay's own HWND (see Overlay focus note above).
- **Tray `_current_desktop[0]` sync** — `poll_queue` writes `_current_desktop[0] = current_desktop` (when `> 0`) after each `tray.update()` call; `poll_move_queue` writes it after a successful `move_window_to_adjacent_desktop`. `poll_desktop` only updates the tray when `num != _current_desktop[0]`; without these writes, `_current_desktop[0]` lags behind the tray's actual value, so if the user returns to the desktop the overlay last observed, `poll_desktop` sees equality and skips the refresh — leaving the tray showing the wrong number.
- **Hotkey toggle while overlay is visible** — when `show()` is called while the overlay is already open (hotkey pressed again), `toggle_all_expansions()` is called to expand all tab trees (or collapse them if any are already expanded). Current query, entry text, and window list are preserved.
- **App icon strip** — one 32×32 icon per unique `process_name` in z-order (from `controller.app_icons`). Tab/Shift-Tab cycle the app filter; bound on `self._entry` specifically, not `top`, so they only fire when the entry has keyboard focus (`<ISO_Left_Tab>` also bound for X11). If the active app disappears from the text-filtered list, `set_query` auto-clears `_app_filter` to keep the strip selection consistent. Strip photo images live in `self._strip_photo_images` (separate from `self._photo_images` for the list canvas); both are cleared by `hide()`.
- **Bell filter (Ctrl+` / Ctrl+½)** — bound as `<Control-grave>` and `<Control-onehalf>`, toggles `OverlayController._bell_filter`. When active, `filtered_windows` restricts to windows where `has_notification` is True (applied before the app filter). An amber 🔔 badge appears in the entry bar to the right of any desktop prefix badges. Escape and Backspace (at caret pos 0) both clear the bell badge — before clearing app filter or desktop badges respectively. `_bell_filter` is reset by `reset()` so it never persists across `show()` calls.
- **Entry bar badge sizing and height stability** — all entry-bar badges (desktop prefix numbers and the bell) are `_BADGE_ENTRY_SIZE × _BADGE_ENTRY_SIZE` (22 px) `tk.Frame` wrappers with `pack_propagate(False)`, each containing a centered `tk.Label`. This makes badge dimensions font-independent and consistently square. `entry_inner` is frozen at the Entry widget's natural height immediately after the Entry widget is packed (`update_idletasks()` then `pack_propagate(False)`) so that adding or removing badge widgets never causes a vertical resize of the search bar.
- **Notification detection** — `_start_flash_monitor(flashing: set[int])` in `app.py` creates a message-only window (`HWND_MESSAGE` = `ctypes.c_size_t(-3)`) and calls `RegisterShellHookWindow` to receive shell notifications. Two signals are combined into a shared `flashing: set[int]`: (1) `HSHELL_FLASH` (0x8006) — fired by `FlashWindowEx`, used by Teams/Discord for incoming DMs; (2) `HSHELL_REDRAW` (6) with an unchanged title on a background window — the fingerprint of `ITaskbarList3::SetOverlayIcon`, used by Outlook and Edge for badge icons. Title changes matching `^\(\d+\)` (e.g. `(3) Inbox`) on `HSHELL_REDRAW` are also caught. A title cache `_titles` is seeded at startup via `EnumWindows` so pre-existing badges are detected on the first redraw. Entries are removed on `HSHELL_ACTIVATED`, `HSHELL_RUDEACTIVATED`, and `HSHELL_DESTROYED`. The set is only mutated from the flash-monitor daemon thread; reads from the main thread are safe under the GIL. `RealWindowProvider` accepts `flashing` as a constructor argument and ORs it with the `^\(\d+\)` title regex when computing `has_notification`.
- **Notification bell rendering** — `WindowInfo.has_notification` is rendered as a 🔔 emoji (Segoe UI Emoji, 11 pt, amber `#f9a825`) via `canvas.create_text` at the right edge of the row, centred vertically. `ITaskbarList3` is not IDispatch-compatible and cannot be driven via `win32com.client.Dispatch` — it requires raw COM vtable access identical to the pattern in `virtual_desktop.py` (two-level pointer dereference, vtable index 18 for `SetOverlayIcon`).
- **UIA tab discovery** — `tabs.py` uses `comtypes` (not `win32com`) to drive UI Automation. `comtypes.client.GetModule("UIAutomationCore.dll")` must be called first to generate the type library bindings before `import comtypes.gen.UIAutomationClient` will work. `GetCurrentPatternAs` has a broken ctypes signature — use `element.GetCurrentPattern(id).QueryInterface(interface)` instead. COM must be initialised on the calling thread with `CoInitializeEx(None, 0)` before any UIA call.
- **UIA tab activation — index-based re-fetch** — `TabInfo` stores only the tab's 0-based index, not a COM element pointer. `select_tab` re-fetches the element from the root at activation time by walking `_collect_tab_items` again. This avoids STA cross-thread COM marshaling: UIA element pointers from a background STA thread cannot be used on the main Tk thread.
- **UIA tab background fetch** — `_fetch_tabs_bg` runs as a daemon thread started by `show()`. It calls `CoInitializeEx`, fetches tabs for each window, then posts results back via `root.after(0, _on_tabs_fetched, hwnd, tabs)`. Do NOT check `self._top is None` inside the loop as a sentinel: `_build_ui` sets `_top` after the thread starts, so the check races and fires immediately. `_on_tabs_fetched` guards `self._controller is None or self._canvas is None` instead — these are set before the thread starts and cleared only by `hide()`.
- **`flat_list` and variable row heights** — `OverlayController.flat_list` interleaves `TabInfo` rows immediately after their parent `WindowInfo`. `_row_height(item)` returns `_TAB_ROW_HEIGHT` (28 px) for tabs, `_ROW_HEIGHT` (44 px) for windows. Two tab-row modes are mutually exclusive: windows in `_expanded` show all their tabs; windows matched only via `_tab_query_matches` show only the matching tabs. `_tab_query_matches` explicitly excludes `title_hwnds` to enforce this.
- **Ctrl+Tab expands/collapses all** — `_on_ctrl_tab` calls `controller.toggle_all_expansions()`, which expands all visible windows that have >1 tab fetched, or collapses all if any are currently expanded. Windows with 0 or 1 tab are never expanded. `<Control-Tab>` is bound on both `self._entry` and `top` so it fires regardless of which widget has focus. **Deferred expansion**: if `toggle_all_expansions()` is called before any tabs have been fetched (`_tabs` is empty), it sets `_want_all_expanded = True` instead of silently doing nothing. `set_tabs()` checks this flag and adds each arriving window to `_expanded` as its tabs come in, so the shortcut feels immediate even though the UIA background fetch takes hundreds of milliseconds. Pressing again while the flag is set clears it (cancel). The flag is cleared on `reset()` and whenever a real collapse happens.
- **Tab title search gated on expand state** — `OverlayController._tab_query_matches` returns `{}` when `_expanded` is empty, so tab titles are never searched in the collapsed state. When any windows are expanded (i.e. `bool(self._expanded)` is true), the property searches `self._tabs` for windows whose tab titles match the text tokens but whose own title/process name does not — those windows are surfaced in `filtered_windows` with only the matching tabs in `flat_list`. The desktop badge filter (`self._desktop_nums`) also applies to these tab-only matches.
- **`_refresh_canvas` guard instead of assert** — after `show()` starts the background fetch thread, `hide()` may be called before the `root.after(0, ...)` callbacks fire. Callbacks arriving after `hide()` find `_canvas = None`. `_refresh_canvas` and `_on_tabs_fetched` use `if self._controller is None or self._canvas is None: return` instead of asserts so these late callbacks are silently dropped.
- **Flash monitor WPARAM/LPARAM overflow** — `ctypes.wintypes.WPARAM` and `LPARAM` are typedef'd as `c_long` (32-bit) even on 64-bit Windows. Shell hook message values such as `HSHELL_FLASH = 0x8006` overflow when compared as signed 32-bit integers. The `WNDPROC` in `_start_flash_monitor` uses `c_size_t`/`c_ssize_t` for the w/l parameters, and `DefWindowProcW.restype`/`.argtypes` are set explicitly to match, preventing the overflow.
- **Ghost window filtering** — Windows can retain a desktop GUID that no longer appears in the registry's `VirtualDesktopIDs` list (e.g. after a desktop was deleted). `assign_desktop_numbers` detects these by comparing each `GetWindowDesktopId` result against the registry-ordered list: when a GUID is absent and `ordered_guids is not None` (registry read succeeded), the window is marked `desktop_number = -1`. `get_windows` in `provider.py` skips any entry with `desktop_number == -1` before constructing `WindowInfo`. The `-1` sentinel never escapes into `WindowInfo`. When registry data is unavailable (`ordered_guids is None`), the old sequential-assignment fallback is used so no real windows are hidden.

### Conventions

- Line length: **100 characters** (ruff enforces)
- Sorted imports (ruff rule I)
- Type hints on all functions
- Win32 calls wrapped in `try/except` with graceful fallback (e.g., grey icon on extraction failure)
- Tests run identically on Linux and Windows — mock all Win32/COM calls
- **Keep README.md in sync** — update the hotkey/filter tables whenever user-facing behaviour changes

### Test file map

| File | What it covers |
|------|----------------|
| `test_filter.py` | `filter_windows` — text match, multi-token non-contiguous match, `desktop_nums` parameter (single, OR semantics, combined with text, unknown desktop excluded); `#` and `#N` as plain text |
| `test_keyboard.py` | `OverlayController` — navigation (arrow, page, boundary), query, reset, `all_windows` invariant, `set_desktop_nums` (single badge, OR semantics, clear, combined with text); `app_icons`, `text_filtered_windows`, `cycle_app_filter`, `clear_app_filter`, auto-clear on query change; tab search (`_tab_query_matches` gating, matching-only tab display, desktop badge filter, multi-token, app-filter preservation); `set_tabs`, `tab_count`, `is_expanded`; `toggle_expansion` (expand/collapse, single-tab guard, flat_list shape, selection lands on parent); `toggle_all_expansions` (expand-all, collapse-when-any-expanded, single-tab skip, filter-aware, non-visible windows untouched, deferred `_want_all_expanded` flag set before tabs arrive and auto-expand on `set_tabs`) |
| `test_provider.py` | `IconExtractor.extract` fallback on non-Windows |
| `test_virtual_desktop.py` | `is_on_current_desktop`, `assign_desktop_numbers` (registry order, None GUID, per-window exception, ghost GUID → `-1`), `get_current_desktop_number` (mocked winreg) |
| `test_tray.py` | `_make_tray_icon` — pixel-level color checks, cycling, unknown-desktop grey, all sizes valid |
| `test_theme.py` | `desktop_badge_color` — format, matches `theme.DESKTOP_COLORS`, cycles correctly |
| `test_overlay.py` | `_desktop_badge_color` overlay helper — format, palette match, cycling (requires tkinter stub) |

### Testing patterns for Windows-only modules

**`overlay.py` imports `tkinter` at module level.** To test pure helpers without a display, stub tkinter at the top of the test file before any import of `overlay`:
```python
import sys
from unittest.mock import MagicMock
sys.modules.setdefault("tkinter", MagicMock())
from windows_navigator.overlay import _desktop_badge_color  # now importable on Linux
from windows_navigator.theme import DESKTOP_COLORS as _DESKTOP_COLORS  # colors live in theme, not overlay
```

**`winreg` is Windows-only.** Functions that do `import winreg` inside a try/except return a safe fallback (0 or None) when the module is absent. To test the real logic on Linux, inject a mock via `patch.dict`:
```python
from unittest.mock import MagicMock, patch
mock_winreg = MagicMock()
mock_winreg.QueryValueEx.side_effect = [(current_bytes, None), (all_bytes, None)]
with patch.dict("sys.modules", {"winreg": mock_winreg}):
    result = get_current_desktop_number()
```

## Known limitations / future work

| Item | Notes |
|------|-------|
| Auto-start on login | Place `start.bat` (or a shortcut to it) in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` |
| Configurable hotkey | Read from `~/.windows-navigator.toml` or similar |
| Window thumbnail preview | Requires `DwmRegisterThumbnail` — significant complexity |
| Taskbar exclusion | The hidden `tk.Tk` root may sometimes appear in the taskbar on some Windows versions |
