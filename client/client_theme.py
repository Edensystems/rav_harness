"""Centralized design tokens and Tkinter styling for the automation dashboard."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

THEMES = {
    "light": {
        "background": "#F4F5FA",
        "surface_1": "#FFFFFF",
        "surface_2": "#FCFCFF",
        "surface_elevated": "#F0F1F7",
        "surface_hover": "#E8E9F2",
        "border_subtle": "#DDDDE8",
        "border_strong": "#C8C8D8",
        "text_primary": "#181721",
        "text_secondary": "#555466",
        "text_muted": "#777689",
        "accent_primary": "#6D3BDE",
        "accent_hover": "#5B2CC4",
        "accent_soft": "#ECE7FC",
        "success": "#16884A",
        "warning": "#B96B08",
        "danger": "#D33745",
        "danger_hover": "#B92534",
        "info": "#246BC4",
        "focus_ring": "#7C4DE6",
        "on_accent": "#FFFEFE",
    },
    "dark": {
        "background": "#0B0B0F",
        "surface_1": "#14141A",
        "surface_2": "#1A1A22",
        "surface_elevated": "#21212B",
        "surface_hover": "#2A2A36",
        "border_subtle": "#2E2E3A",
        "border_strong": "#3A3A48",
        "text_primary": "#F5F5FA",
        "text_secondary": "#B8B8C7",
        "text_muted": "#8A8A9A",
        "accent_primary": "#7C3AED",
        "accent_hover": "#6D28D9",
        "accent_soft": "#2D1B57",
        "success": "#22C55E",
        "warning": "#F59E0B",
        "danger": "#EF4444",
        "danger_hover": "#DC2626",
        "info": "#60A5FA",
        "focus_ring": "#A78BFA",
        "on_accent": "#FFFFFF",
    },
}

TOKENS = {
    **THEMES["light"],
    "radius_md": 10,
    "radius_lg": 14,
    "font_ui": ("Segoe UI", 10),
    "font_ui_sm": ("Segoe UI", 9),
    "font_title": ("Segoe UI", 18, "bold"),
    "font_kpi": ("Segoe UI", 26, "bold"),
    "font_mono": ("Consolas", 9),
}

CURRENT_THEME = "light"


def apply_theme(root: tk.Tk | tk.Toplevel, mode: str | None = None) -> None:
    global CURRENT_THEME
    if mode in THEMES:
        CURRENT_THEME = mode
        TOKENS.update(THEMES[mode])
    root.configure(bg=TOKENS["background"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Dark.TFrame", background=TOKENS["background"])
    style.configure("Surface.TFrame", background=TOKENS["surface_1"])
    style.configure("Card.TFrame", background=TOKENS["surface_2"])
    style.configure(
        "CardTitle.TLabel",
        background=TOKENS["surface_2"],
        foreground=TOKENS["text_muted"],
        font=TOKENS["font_ui_sm"],
    )
    style.configure(
        "CardValue.TLabel",
        background=TOKENS["surface_2"],
        foreground=TOKENS["text_primary"],
        font=TOKENS["font_kpi"],
    )
    style.configure(
        "HeaderTitle.TLabel",
        background=TOKENS["surface_1"],
        foreground=TOKENS["text_primary"],
        font=TOKENS["font_title"],
    )
    style.configure(
        "HeaderSub.TLabel",
        background=TOKENS["surface_1"],
        foreground=TOKENS["text_secondary"],
        font=TOKENS["font_ui_sm"],
    )
    style.configure(
        "Dark.TNotebook",
        background=TOKENS["background"],
        borderwidth=0,
        tabmargins=[8, 4, 8, 0],
    )
    style.configure(
        "Dark.TNotebook.Tab",
        background=TOKENS["surface_1"],
        foreground=TOKENS["text_secondary"],
        padding=[14, 8],
        font=TOKENS["font_ui"],
    )
    style.map(
        "Dark.TNotebook.Tab",
        background=[("selected", TOKENS["accent_soft"]), ("active", TOKENS["surface_hover"])],
        foreground=[("selected", TOKENS["text_primary"])],
    )
    style.configure(
        "Accent.Horizontal.TProgressbar",
        troughcolor=TOKENS["surface_elevated"],
        background=TOKENS["accent_primary"],
        bordercolor=TOKENS["border_subtle"],
        lightcolor=TOKENS["accent_primary"],
        darkcolor=TOKENS["accent_primary"],
        thickness=12,
    )
    style.configure(
        "Dark.Treeview",
        background=TOKENS["surface_elevated"],
        fieldbackground=TOKENS["surface_elevated"],
        foreground=TOKENS["text_primary"],
        bordercolor=TOKENS["border_subtle"],
        rowheight=26,
        font=TOKENS["font_ui_sm"],
    )
    style.configure(
        "Dark.Treeview.Heading",
        background=TOKENS["surface_1"],
        foreground=TOKENS["text_secondary"],
        relief="flat",
        font=TOKENS["font_ui_sm"],
    )
    style.map("Dark.Treeview", background=[("selected", TOKENS["accent_soft"])])
    style.configure(
        "TScrollbar",
        background=TOKENS["surface_elevated"],
        troughcolor=TOKENS["background"],
        bordercolor=TOKENS["border_subtle"],
        arrowcolor=TOKENS["text_secondary"],
    )


def switch_theme(root: tk.Tk | tk.Toplevel, mode: str) -> None:
    """Apply a palette live while preserving widget values and application state."""
    if mode not in THEMES:
        raise ValueError(f"Unknown theme: {mode}")

    old_tokens = dict(TOKENS)
    TOKENS.update(THEMES[mode])
    color_map = {
        str(old_tokens[key]).lower(): TOKENS[key]
        for key in THEMES[mode]
        if key in old_tokens
    }
    _recolor_widget_tree(root, color_map)
    apply_theme(root, mode)


def apply_ui_scale(root: tk.Tk | tk.Toplevel, scale: float) -> None:
    """Scale existing desktop widgets from stable base measurements."""
    scale = max(0.75, min(scale, 1.30))
    _scale_widget_tree(root, scale)

    style = ttk.Style(root)
    style.configure("Accent.Horizontal.TProgressbar", thickness=max(9, round(12 * scale)))
    style.configure("Dark.Treeview", rowheight=max(22, round(26 * scale)), font=_scaled_font(TOKENS["font_ui_sm"], scale))
    style.configure("Dark.Treeview.Heading", font=_scaled_font(TOKENS["font_ui_sm"], scale))
    style.configure("CardTitle.TLabel", font=_scaled_font(TOKENS["font_ui_sm"], scale))
    style.configure("CardValue.TLabel", font=_scaled_font(TOKENS["font_kpi"], scale))
    style.configure("HeaderTitle.TLabel", font=_scaled_font(TOKENS["font_title"], scale))
    style.configure("HeaderSub.TLabel", font=_scaled_font(TOKENS["font_ui_sm"], scale))
    style.configure("Dark.TNotebook.Tab", padding=[round(14 * scale), round(8 * scale)], font=_scaled_font(TOKENS["font_ui"], scale))


def _scaled_font(font_spec: tuple, scale: float) -> tuple:
    family, size, *styles = font_spec
    return (family, max(8, round(size * scale)), *styles)


def _scale_widget_tree(widget: tk.Misc, scale: float) -> None:
    try:
        font_value = widget.cget("font")
    except (tk.TclError, AttributeError):
        font_value = ""
    if font_value:
        base_font = getattr(widget, "_responsive_base_font", None)
        if base_font is None:
            actual = tkfont.Font(root=widget, font=font_value).actual()
            base_font = (
                actual["family"],
                abs(int(actual["size"])),
                actual["weight"],
                actual["slant"],
                actual["underline"],
                actual["overstrike"],
            )
            widget._responsive_base_font = base_font
        family, size, weight, slant, underline, overstrike = base_font
        styles = []
        if weight != "normal":
            styles.append(weight)
        if slant != "roman":
            styles.append(slant)
        if underline:
            styles.append("underline")
        if overstrike:
            styles.append("overstrike")
        widget.configure(font=(family, max(8, round(size * scale)), *styles))

    for option in ("padx", "pady", "highlightthickness", "wraplength"):
        try:
            current = float(widget.cget(option))
        except (tk.TclError, ValueError, TypeError, AttributeError):
            continue
        base_attr = f"_responsive_base_{option}"
        if not hasattr(widget, base_attr):
            setattr(widget, base_attr, current)
        base_value = getattr(widget, base_attr)
        if base_value > 0:
            widget.configure(**{option: max(1, round(base_value * scale))})

    for child in widget.winfo_children():
        _scale_widget_tree(child, scale)


def _recolor_widget_tree(widget: tk.Misc, color_map: dict[str, str]) -> None:
    color_options = (
        "background", "foreground", "activebackground", "activeforeground",
        "highlightbackground", "highlightcolor", "insertbackground",
        "selectbackground", "selectforeground", "selectcolor", "disabledforeground",
    )
    updates = {}
    for option in color_options:
        try:
            current = str(widget.cget(option)).lower()
        except (tk.TclError, AttributeError):
            continue
        if current in color_map:
            updates[option] = color_map[current]
    if updates:
        try:
            widget.configure(**updates)
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        _recolor_widget_tree(child, color_map)


def create_card(parent, *, padx=8, pady=8, highlight=False) -> tk.Frame:
    border = TOKENS["accent_primary"] if highlight else TOKENS["border_subtle"]
    card = tk.Frame(
        parent,
        bg=TOKENS["surface_2"],
        highlightbackground=border,
        highlightthickness=1 if highlight else 1,
        bd=0,
        padx=padx,
        pady=pady,
    )
    return card


def create_flat_button(
    parent,
    text: str,
    command,
    *,
    variant: str = "secondary",
    width: int | None = None,
) -> tk.Button:
    palette = {
        "primary": (TOKENS["accent_primary"], TOKENS["on_accent"], TOKENS["accent_hover"]),
        "danger": (TOKENS["danger"], TOKENS["on_accent"], TOKENS["danger_hover"]),
        "secondary": (TOKENS["surface_elevated"], TOKENS["text_primary"], TOKENS["surface_hover"]),
        "ghost": (TOKENS["surface_1"], TOKENS["text_secondary"], TOKENS["surface_hover"]),
    }
    bg, fg, active = palette.get(variant, palette["secondary"])
    kwargs = {
        "text": text,
        "command": command,
        "bg": bg,
        "fg": fg,
        "activebackground": active,
        "activeforeground": fg,
        "relief": "flat",
        "bd": 0,
        "padx": 10,
        "pady": 6,
        "cursor": "hand2",
        "font": TOKENS["font_ui"],
        "takefocus": True,
        "highlightthickness": 1,
        "highlightbackground": bg,
        "highlightcolor": TOKENS["focus_ring"],
    }
    if width:
        kwargs["width"] = width
    return tk.Button(parent, **kwargs)


def themed_entry(parent, **kwargs) -> tk.Entry:
    defaults = {
        "bg": TOKENS["surface_elevated"],
        "fg": TOKENS["text_primary"],
        "insertbackground": TOKENS["text_primary"],
        "relief": "flat",
        "font": TOKENS["font_ui"],
        "highlightthickness": 1,
        "highlightbackground": TOKENS["border_subtle"],
        "highlightcolor": TOKENS["focus_ring"],
    }
    defaults.update(kwargs)
    return tk.Entry(parent, **defaults)
