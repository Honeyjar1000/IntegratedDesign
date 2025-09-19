"""
UI styling constants and helper functions.
"""
import tkinter as tk
from app.constants import (
    BG_COLOR, FRAME_COLOR, BUTTON_COLOR, BUTTON_ACTIVE_COLOR, 
    TEXT_COLOR, MUTED_TEXT_COLOR, STATUS_BG_COLOR, HIGHLIGHT_COLOR, TROUGH_COLOR
)


def create_button(parent, text, command, **kwargs):
    """Create a styled button."""
    defaults = {
        "bg": BUTTON_COLOR,
        "fg": TEXT_COLOR,
        "activebackground": BUTTON_ACTIVE_COLOR,
        "relief": "raised",
        "bd": 1,
        "padx": 12,
        "pady": 6
    }
    defaults.update(kwargs)
    return tk.Button(parent, text=text, command=command, **defaults)


def create_label(parent, text="", **kwargs):
    """Create a styled label."""
    defaults = {
        "bg": BG_COLOR,
        "fg": TEXT_COLOR
    }
    defaults.update(kwargs)
    return tk.Label(parent, text=text, **defaults)


def create_muted_label(parent, text="", **kwargs):
    """Create a muted/secondary label."""
    defaults = {
        "bg": BG_COLOR,
        "fg": MUTED_TEXT_COLOR
    }
    defaults.update(kwargs)
    return tk.Label(parent, text=text, **defaults)


def create_frame(parent, **kwargs):
    """Create a styled frame."""
    defaults = {"bg": BG_COLOR}
    defaults.update(kwargs)
    return tk.Frame(parent, **defaults)


def create_panel_frame(parent, **kwargs):
    """Create a styled panel frame with border."""
    defaults = {
        "bg": FRAME_COLOR,
        "highlightthickness": 1,
        "highlightbackground": HIGHLIGHT_COLOR
    }
    defaults.update(kwargs)
    return tk.Frame(parent, **defaults)


def create_scale(parent, **kwargs):
    """Create a styled scale/slider."""
    defaults = {
        "bg": BG_COLOR,
        "troughcolor": TROUGH_COLOR,
        "highlightthickness": 0,
        "showvalue": False
    }
    defaults.update(kwargs)
    return tk.Scale(parent, **defaults)


def create_status_label(parent, text="", **kwargs):
    """Create a styled status label."""
    defaults = {
        "fg": TEXT_COLOR,
        "bg": STATUS_BG_COLOR,
        "bd": 1,
        "relief": "solid",
        "padx": 8,
        "pady": 4
    }
    defaults.update(kwargs)
    return tk.Label(parent, text=text, **defaults)
