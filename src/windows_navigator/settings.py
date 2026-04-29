"""Settings window — hotkey selection."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from windows_navigator.config import HotkeyChoice, save_hotkey

_LABELS: dict[HotkeyChoice, str] = {
    HotkeyChoice.DOUBLE_TAP_CTRL: "Double-tap Ctrl",
    HotkeyChoice.WIN_ALT_SPACE: "Win + Alt + Space",
    HotkeyChoice.CTRL_SHIFT_SPACE: "Ctrl + Shift + Space",
    HotkeyChoice.CTRL_DOUBLE_TAP_SHIFT: "Hold Ctrl, double-tap Shift",
}


def open_settings_window(
    root: tk.Tk,
    current: HotkeyChoice,
    on_save: Callable[[HotkeyChoice], None],
) -> None:
    """Open a modal settings window for choosing the global hotkey."""
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

    def _save() -> None:
        chosen = HotkeyChoice(var.get())
        save_hotkey(chosen)
        on_save(chosen)
        win.destroy()

    btn_row = ttk.Frame(frame)
    btn_row.pack(pady=(12, 0), fill="x")
    ttk.Button(btn_row, text="Cancel", command=win.destroy).pack(side="right", padx=(4, 0))
    ttk.Button(btn_row, text="Save", command=_save).pack(side="right")
