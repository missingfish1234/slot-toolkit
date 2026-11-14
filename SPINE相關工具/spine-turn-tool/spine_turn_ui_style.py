"""Shared colours and event-driven interaction feedback for the desktop UI."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


PALETTE = {
    "BG": "#0d151e",
    "PANEL": "#14212d",
    "SURFACE": "#182936",
    "CARD": "#1d3040",
    "TEXT": "#edf5fa",
    "MUTED": "#a2b5c5",
    "ACCENT": "#5ddbc7",
    "ACCENT_SOFT": "#1b3d40",
    "LINE": "#304657",
    "HOVER": "#2a4458",
    "PRESSED": "#142733",
    "ACCENT_HOVER": "#85ecdb",
    "ACCENT_PRESSED": "#3ac0ac",
    "FOCUS": "#9af4e6",
    "SUCCESS": "#79ddae",
    "WARNING": "#eac080",
    "DANGER": "#f29ba7",
    "DISABLED": "#6e8799",
}

FONT = ("Microsoft JhengHei UI", 10)
SMALL_FONT = ("Microsoft JhengHei UI", 9)


def configure_theme(root):
    """Apply one dark theme to Tk inputs and the existing ttk style names."""
    p = PALETTE
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=FONT, background=p["PANEL"], foreground=p["TEXT"])
    for name in ("TCombobox", "TSpinbox", "TEntry"):
        style.configure(
            name, fieldbackground=p["CARD"], background=p["CARD"],
            foreground=p["TEXT"], arrowcolor=p["MUTED"],
            bordercolor=p["LINE"], lightcolor=p["LINE"], darkcolor=p["LINE"],
            insertcolor=p["TEXT"], borderwidth=1, padding=(7, 5),
            selectbackground=p["ACCENT_SOFT"], selectforeground=p["TEXT"],
        )
        style.map(
            name,
            fieldbackground=[("disabled", p["PANEL"]), ("readonly", p["CARD"])],
            background=[("disabled", p["PANEL"]), ("active", p["HOVER"])],
            foreground=[("disabled", p["DISABLED"]), ("readonly", p["TEXT"])],
            arrowcolor=[("disabled", p["DISABLED"]), ("active", p["ACCENT"])],
            bordercolor=[("focus", p["ACCENT"]), ("active", p["HOVER"])],
            lightcolor=[("focus", p["ACCENT"])], darkcolor=[("focus", p["ACCENT"])],
            selectbackground=[("readonly", p["CARD"])],
            selectforeground=[("readonly", p["TEXT"])],
        )
    style.configure("Turn.TNotebook", background=p["PANEL"], borderwidth=0)
    style.configure(
        "Turn.TNotebook.Tab", background=p["PANEL"], foreground=p["MUTED"],
        padding=(10, 8), font=SMALL_FONT, borderwidth=0,
        lightcolor=p["PANEL"], darkcolor=p["PANEL"],
    )
    style.map(
        "Turn.TNotebook.Tab",
        background=[("selected", p["ACCENT_SOFT"]), ("active", p["CARD"])],
        foreground=[("selected", p["ACCENT"]), ("active", p["TEXT"])],
        lightcolor=[("selected", p["ACCENT_SOFT"])],
    )
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            name, background=p["LINE"], troughcolor=p["PANEL"],
            arrowcolor=p["MUTED"], bordercolor=p["PANEL"],
            lightcolor=p["PANEL"], darkcolor=p["PANEL"],
            arrowsize=12, borderwidth=0, gripcount=0,
        )
        style.map(name, background=[("pressed", p["ACCENT"]), ("active", p["HOVER"])])
    style.configure(
        "Studio.Horizontal.TScale", background=p["ACCENT"],
        troughcolor=p["CARD"], bordercolor=p["LINE"],
        lightcolor=p["ACCENT"], darkcolor=p["ACCENT"], sliderlength=17,
        borderwidth=0,
    )
    style.map(
        "Studio.Horizontal.TScale",
        background=[("disabled", p["DISABLED"]), ("active", p["ACCENT_HOVER"])],
    )
    style.configure(
        "TProgressbar", background=p["ACCENT"], troughcolor=p["CARD"],
        bordercolor=p["CARD"], lightcolor=p["ACCENT"], darkcolor=p["ACCENT"],
        borderwidth=0,
    )
    style.configure("TSeparator", background=p["LINE"])
    style.configure(
        "TCheckbutton", background=p["PANEL"], foreground=p["MUTED"],
        font=SMALL_FONT, padding=(1, 3), indicatorsize=14,
        indicatorbackground=p["CARD"], indicatorforeground=p["BG"],
        upperbordercolor=p["LINE"], lowerbordercolor=p["LINE"],
        focuscolor=p["FOCUS"],
    )
    style.map(
        "TCheckbutton", foreground=[("disabled", p["DISABLED"]), ("selected", p["TEXT"]), ("active", p["TEXT"])],
        background=[("active", p["PANEL"])],
        indicatorbackground=[("disabled", p["PANEL"]), ("selected", p["ACCENT"]), ("active", p["HOVER"])],
        upperbordercolor=[("focus", p["FOCUS"]), ("selected", p["ACCENT"])],
        lowerbordercolor=[("focus", p["FOCUS"]), ("selected", p["ACCENT"])],
    )
    for pattern, value in {
        "*Font": FONT,
        "*Entry.background": p["CARD"], "*Entry.foreground": p["TEXT"],
        "*Entry.insertBackground": p["TEXT"],
        "*Entry.selectBackground": p["ACCENT_SOFT"],
        "*Entry.selectForeground": p["TEXT"],
        "*Entry.highlightColor": p["ACCENT"],
        "*Entry.highlightBackground": p["LINE"],
        "*Checkbutton.selectColor": p["CARD"],
        "*Checkbutton.activeForeground": p["ACCENT"],
        "*Checkbutton.highlightColor": p["ACCENT"],
        "*Checkbutton.highlightThickness": 1,
        "*TCombobox*Listbox.background": p["CARD"],
        "*TCombobox*Listbox.foreground": p["TEXT"],
        "*TCombobox*Listbox.selectBackground": p["ACCENT_SOFT"],
        "*TCombobox*Listbox.selectForeground": p["ACCENT"],
        "*Menu.background": p["PANEL"], "*Menu.foreground": p["TEXT"],
        "*Menu.activeBackground": p["ACCENT_SOFT"],
        "*Menu.activeForeground": p["ACCENT"],
    }.items():
        root.option_add(pattern, value)
    return style


class StudioButton(tk.Button):
    """Native button semantics with stable-size hover, press and focus feedback."""

    def __init__(self, parent, text="", command=None, primary=False, variant=None,
                 selected=False, tooltip=None, **kwargs):
        self.variant = variant or ("primary" if primary else "secondary")
        if self.variant not in {"primary", "secondary", "ghost", "danger"}:
            raise ValueError("Unknown button variant: " + str(self.variant))
        self._ready = False
        self._selected = bool(selected)
        self._hovered = False
        self._pressed = False
        self._focused = False
        self._pointer_down = False
        self._key_down = None
        self._parent_bg = str(parent.cget("bg"))
        bg, fg, border = self._colours()
        options = {
            "text": text, "command": command, "background": bg,
            "foreground": fg, "activebackground": bg,
            "activeforeground": fg, "disabledforeground": PALETTE["DISABLED"],
            "highlightbackground": border, "highlightcolor": PALETTE["FOCUS"],
            "highlightthickness": 1, "borderwidth": 0, "relief": "flat",
            "overrelief": "flat", "cursor": "hand2", "takefocus": True,
            "font": FONT, "padx": 11, "pady": 6,
        }
        options.update(kwargs)
        self._base_bg = str(options.get("bg", options["background"]))
        self._base_fg = str(options.get("fg", options["foreground"]))
        super().__init__(parent, **options)
        self._ready = True
        for sequence, callback in (
            ("<Enter>", self._on_enter), ("<Leave>", self._on_leave),
            ("<ButtonPress-1>", self._on_press), ("<ButtonRelease-1>", self._on_release),
            ("<FocusIn>", self._on_focus_in), ("<FocusOut>", self._on_focus_out),
            ("<Unmap>", self._on_focus_out),
        ):
            self.bind(sequence, callback, add="+")
        for key in ("space", "Return", "KP_Enter"):
            self.bind("<KeyPress-" + key + ">", self._on_key_press, add="+")
            self.bind("<KeyRelease-" + key + ">", self._on_key_release, add="+")
        self._paint()
        self.tooltip = attach_tooltip(self, tooltip) if tooltip else None

    def _colours(self):
        p = PALETTE
        if self.variant == "primary":
            return p["ACCENT"], p["BG"], p["ACCENT"]
        if self.variant == "danger":
            return "#382735", p["DANGER"], "#65404d"
        if self.variant == "ghost":
            return self._parent_bg, p["MUTED"], self._parent_bg
        return p["CARD"], p["TEXT"], p["LINE"]

    def _enabled(self):
        return str(super().cget("state")) != "disabled"

    def _paint(self):
        if not self._ready:
            return
        p = PALETTE
        bg, fg, border = self._base_bg, self._base_fg, self._colours()[2]
        try:
            enabled = self._enabled()
        except tk.TclError:
            return
        if not enabled:
            bg, fg, border = p["PANEL"], p["DISABLED"], p["LINE"]
        elif self.variant == "primary":
            if self._pressed:
                bg = p["ACCENT_PRESSED"]
            elif self._hovered:
                bg = p["ACCENT_HOVER"]
            border = bg
        elif self.variant == "danger":
            if self._pressed:
                bg = "#2b202b"
            elif self._hovered:
                bg, border = "#50303f", p["DANGER"]
        else:
            if self._selected:
                bg, fg, border = p["ACCENT_SOFT"], p["ACCENT"], p["ACCENT"]
            if self._pressed:
                bg = p["PRESSED"]
            elif self._hovered:
                bg = p["HOVER"]
                border = p["ACCENT"] if self._selected else "#4a677b"
        if enabled and self._focused:
            border = p["FOCUS"]
        super().configure(
            background=bg, foreground=fg, activebackground=bg,
            activeforeground=fg, highlightbackground=border,
            highlightcolor=p["FOCUS"] if enabled else p["LINE"],
            cursor="hand2" if enabled else "arrow",
        )

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, str) or (cnf is None and not kwargs):
            return super().configure(cnf, **kwargs)
        options = dict(cnf or {})
        options.update(kwargs)
        if "selected" in options:
            self._selected = bool(options.pop("selected"))
        for key in ("background", "bg"):
            if key in options:
                self._base_bg = str(options[key])
        for key in ("foreground", "fg"):
            if key in options:
                self._base_fg = str(options[key])
        result = super().configure(**options)
        if self._ready:
            if not self._enabled():
                self._pressed = self._pointer_down = False
                self._key_down = None
                if self.tooltip:
                    self.tooltip.hide()
            self._paint()
        return result

    config = configure

    def set_selected(self, selected):
        self._selected = bool(selected)
        self._paint()

    def invoke(self):
        return super().invoke() if self._enabled() else ""

    def _on_enter(self, _event):
        self._hovered = True
        self._pressed = self._enabled() and (self._pointer_down or self._key_down is not None)
        self._paint()

    def _on_leave(self, _event):
        self._hovered = False
        self._pressed = self._key_down is not None and self._enabled()
        self._paint()

    def _on_press(self, _event):
        if self._enabled():
            self._pointer_down = self._pressed = True
            self._paint()

    def _on_release(self, _event):
        self._pointer_down = False
        self._pressed = self._key_down is not None and self._enabled()
        self._paint()

    def _on_focus_in(self, _event):
        self._focused = True
        self._paint()

    def _on_focus_out(self, _event):
        self._focused = self._pressed = self._pointer_down = False
        self._key_down = None
        self._paint()

    def _on_key_press(self, event):
        if self._enabled() and self._key_down is None:
            if self.tooltip:
                self.tooltip.hide()
            self._key_down = event.keysym
            self._pressed = True
            self._paint()
        return "break"

    def _on_key_release(self, event):
        invoke = self._key_down == event.keysym and self._enabled()
        self._key_down = None
        self._pressed = False
        self._paint()
        if invoke:
            self.invoke()
        return "break"


class Tooltip:
    """A delayed hint that cancels on click, leave, unmap or destruction."""

    def __init__(self, widget, text, delay=600):
        self.widget = widget
        self.text = str(text)
        self.delay = max(0, int(delay))
        self._job = None
        self._window = None
        widget.bind("<Enter>", self._schedule, add="+")
        for sequence in ("<Leave>", "<ButtonPress-1>", "<ButtonPress-2>",
                         "<ButtonPress-3>", "<FocusOut>", "<Unmap>"):
            widget.bind(sequence, self.hide, add="+")
        widget.bind("<Destroy>", self._destroyed, add="+")

    def _schedule(self, _event=None):
        self.hide()
        try:
            if "state" in self.widget.keys() and str(self.widget.cget("state")) == "disabled":
                return
            self._job = self.widget.after(self.delay, self._show)
        except tk.TclError:
            pass

    def _show(self):
        self._job = None
        try:
            if not self.widget.winfo_exists() or not self.widget.winfo_ismapped():
                return
            if "state" in self.widget.keys() and str(self.widget.cget("state")) == "disabled":
                return
            window = self._window = tk.Toplevel(self.widget)
            window.withdraw()
            window.overrideredirect(True)
            try:
                window.wm_attributes("-topmost", True)
            except tk.TclError:
                pass
            tk.Label(
                window, text=self.text, bg=PALETTE["SURFACE"], fg=PALETTE["TEXT"],
                font=SMALL_FONT, padx=10, pady=7, justify="left", wraplength=280,
                highlightthickness=1, highlightbackground=PALETTE["LINE"],
            ).pack()
            window.update_idletasks()
            x = min(self.widget.winfo_pointerx() + 12,
                    self.widget.winfo_screenwidth() - window.winfo_reqwidth() - 12)
            y = min(self.widget.winfo_rooty() + self.widget.winfo_height() + 7,
                    self.widget.winfo_screenheight() - window.winfo_reqheight() - 12)
            window.geometry(f"+{max(0, x)}+{max(0, y)}")
            window.deiconify()
        except tk.TclError:
            self.hide()

    def hide(self, _event=None):
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        window, self._window = self._window, None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _destroyed(self, event):
        if event.widget is self.widget:
            self.hide()


def attach_tooltip(widget, text, delay=600):
    existing = getattr(widget, "_studio_tooltip", None)
    if existing is not None:
        existing.text = str(text)
        existing.delay = max(0, int(delay))
        return existing
    tooltip = Tooltip(widget, text, delay)
    widget._studio_tooltip = tooltip
    widget.tooltip = tooltip
    return tooltip


class FeedbackToast(tk.Frame):
    """Nonmodal stage notification; only a pending dismissal uses a timer."""

    def __init__(self, parent):
        super().__init__(parent, bg=PALETTE["SURFACE"], padx=12, pady=9,
                         highlightthickness=1, highlightbackground=PALETTE["LINE"])
        self._job = None
        self.icon = tk.Label(self, bg=PALETTE["SURFACE"], font=("Segoe UI", 12, "bold"))
        self.icon.grid(row=0, column=0, sticky="n", padx=(0, 8))
        self.label = tk.Label(self, bg=PALETTE["SURFACE"], fg=PALETTE["TEXT"],
                              font=SMALL_FONT, justify="left", wraplength=300)
        self.label.grid(row=0, column=1, sticky="w")
        self.bind("<Button-1>", lambda _event: self.hide())
        self.label.bind("<Button-1>", lambda _event: self.hide())
        self.icon.bind("<Button-1>", lambda _event: self.hide())
        self.bind("<Destroy>", self._destroyed, add="+")

    def show(self, message, kind="success", duration=2400):
        self.hide()
        colour, icon = {
            "success": (PALETTE["SUCCESS"], "✓"),
            "error": (PALETTE["DANGER"], "!"),
            "warning": (PALETTE["WARNING"], "!"),
            "info": (PALETTE["ACCENT"], "i"),
        }.get(kind, (PALETTE["ACCENT"], "i"))
        self.configure(highlightbackground=colour)
        self.icon.configure(text=icon, fg=colour)
        self.label.configure(text=str(message), wraplength=max(150, min(300, self.master.winfo_width() - 90)))
        self.place(relx=1, x=-14, y=14, anchor="ne")
        self.lift()
        self._job = self.after(max(1, int(duration)), self.hide)

    def hide(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        try:
            self.place_forget()
        except tk.TclError:
            pass

    def _destroyed(self, event):
        if event.widget is self:
            self.hide()
