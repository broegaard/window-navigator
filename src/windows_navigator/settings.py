"""Settings window — hotkey selection and startup behaviour."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from windows_navigator.config import HotkeyChoice

_LABELS: dict[HotkeyChoice, str] = {
    HotkeyChoice.DOUBLE_TAP_CTRL: "Double-tap Ctrl",
    HotkeyChoice.DOUBLE_TAP_SHIFT: "Double-tap Shift",
    HotkeyChoice.WIN_ALT_SPACE: "Win + Alt + Space",
    HotkeyChoice.CTRL_SHIFT_SPACE: "Ctrl + Shift + Space",
    HotkeyChoice.CTRL_DOUBLE_TAP_SHIFT: "Hold Ctrl, double-tap Shift",
    HotkeyChoice.SHIFT_DOUBLE_TAP_CTRL: "Hold Shift, double-tap Ctrl",
}


def open_settings_window(
    root: tk.Tk,
    current: HotkeyChoice,
    current_expand: bool,
    on_save: Callable[[HotkeyChoice, bool], None],
) -> None:
    """Open a modal settings window for choosing the global hotkey and startup behaviour."""
    win = tk.Toplevel(root)
    win.title("Windows Navigator — Settings")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.grab_set()

    frame = ttk.Frame(win, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="Global hotkey", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(4, 8))

    var = tk.StringVar(value=current.value)
    for choice, label in _LABELS.items():
        ttk.Radiobutton(frame, text=label, variable=var, value=choice.value).pack(
            anchor="w", pady=2
        )

    ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=(8, 4))
    ttk.Label(frame, text="Startup behaviour", font=("Segoe UI", 10, "bold")).pack(anchor="w")

    expand_var = tk.BooleanVar(value=current_expand)
    ttk.Checkbutton(frame, text="Expand tabs on startup", variable=expand_var).pack(
        anchor="w", pady=(4, 0)
    )

    def _save() -> None:
        on_save(HotkeyChoice(var.get()), expand_var.get())
        win.destroy()

    btn_row = ttk.Frame(frame)
    btn_row.pack(pady=(12, 0), fill="x")
    ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="right", padx=(4, 0))
    ttk.Button(btn_row, text="Save", command=_save).pack(side="right")
