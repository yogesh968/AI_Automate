"""Window management and UI Automation (click buttons by name inside any app)."""

from __future__ import annotations

import time

from ._win import com_init
from .base import AUTO, CONFIRM, E, I, S, tool


def _find(title: str):
    import pygetwindow as gw

    key = title.lower()
    wins = [w for w in gw.getAllWindows() if w.title and key in w.title.lower() and w.width > 0]
    if not wins:
        raise LookupError(f"no window matching '{title}'")
    return wins[0]


@tool("list_windows", "List open windows (titles).")
def list_windows():
    import pygetwindow as gw

    titles = [w.title for w in gw.getAllWindows() if w.title.strip() and w.width > 0 and w.visible]
    return list(dict.fromkeys(titles))[:60]


@tool("window_action", "Focus, minimize, maximize, restore, close, or snap a window left/right.",
      {"title": S("part of the window title, e.g. 'chrome' or 'Visual Studio Code'"),
       "action": E("action", ["focus", "minimize", "maximize", "restore", "close", "snap_left", "snap_right"])},
      ["title", "action"])
def window_action(title: str, action: str):
    import pyautogui

    w = _find(title)
    if action in ("focus", "snap_left", "snap_right"):
        if w.isMinimized:
            w.restore()
        try:
            w.activate()
        except Exception:
            # Windows blocks focus stealing; an Alt tap unlocks SetForegroundWindow
            pyautogui.press("alt")
            w.activate()
        if action == "snap_left":
            time.sleep(0.2)
            pyautogui.hotkey("win", "left")
        elif action == "snap_right":
            time.sleep(0.2)
            pyautogui.hotkey("win", "right")
    elif action == "minimize":
        w.minimize()
    elif action == "maximize":
        w.maximize()
    elif action == "restore":
        w.restore()
    elif action == "close":
        w.close()
    return f"{action}: {w.title}"


@tool("show_desktop", "Minimize everything and show the desktop (toggle).")
def show_desktop():
    import pyautogui

    pyautogui.hotkey("win", "d")
    return "desktop shown"


@tool("switch_virtual_desktop", "Move to the next/previous virtual desktop or create a new one.",
      {"direction": E("which", ["next", "previous", "new"])}, ["direction"])
def switch_virtual_desktop(direction: str):
    import pyautogui

    keys = {"next": ("ctrl", "win", "right"), "previous": ("ctrl", "win", "left"), "new": ("ctrl", "win", "d")}
    pyautogui.hotkey(*keys[direction])
    return f"virtual desktop: {direction}"


# ---------------------------------------------------------------- UI Automation


def _uia_window(title: str):
    com_init()
    from pywinauto import Desktop

    key = title.lower()
    for w in Desktop(backend="uia").windows():
        try:
            if key in (w.window_text() or "").lower():
                return w
        except Exception:
            continue
    raise LookupError(f"no window matching '{title}'")


@tool("ui_list_elements", "List clickable/typeable controls (buttons, links, fields, menus) inside a window, "
      "so you can then use ui_click / ui_type. Use this before clicking inside apps.",
      {"window": S("part of the window title"), "max_items": I("default 60")}, ["window"])
def ui_list_elements(window: str, max_items: int = 60):
    w = _uia_window(window)
    wanted = {"Button", "MenuItem", "Hyperlink", "Edit", "ComboBox", "CheckBox", "RadioButton",
              "TabItem", "ListItem", "TreeItem", "Document", "SplitButton"}
    out = []
    for el in w.descendants():
        try:
            ctype = el.element_info.control_type
            name = (el.window_text() or "").strip()
            if ctype in wanted and (name or ctype == "Edit") and el.is_visible():
                out.append(f"{ctype}: {name[:80]}")
        except Exception:
            continue
        if len(out) >= max_items:
            break
    return list(dict.fromkeys(out)) or "no controls found (the app may not expose accessibility info — try screen tools)"


_RISKY_WORDS = ("delete", "remove", "send", "pay", "buy", "purchase", "order", "confirm", "submit",
                "uninstall", "format", "erase", "transfer", "publish", "post")


def _click_level(args):
    name = (args.get("name") or "").lower()
    return CONFIRM if any(w in name for w in _RISKY_WORDS) else AUTO


@tool("ui_click", "Click a button/link/menu item by its visible name inside a window (UI Automation).",
      {"window": S("part of the window title"), "name": S("text of the control to click"),
       "control_type": S("optional: Button, MenuItem, Hyperlink, TabItem, ListItem…")},
      ["window", "name"], level=_click_level,
      describe=lambda a: f"Click '{a.get('name')}' in {a.get('window')}")
def ui_click(window: str, name: str, control_type: str = ""):
    w = _uia_window(window)
    w.set_focus()
    kwargs = {"title_re": f"(?i).*{_re_escape(name)}.*"}
    if control_type:
        kwargs["control_type"] = control_type
    el = w.child_window(**kwargs, found_index=0)
    try:
        el.invoke()
    except Exception:
        el.click_input()
    return f"clicked '{name}'"


@tool("ui_type", "Type text into a text field inside a window (by the field's name, or the focused field).",
      {"window": S("part of the window title"), "text": S("text to type"),
       "field": S("optional field name/label; empty = first edit box")},
      ["window", "text"])
def ui_type(window: str, text: str, field: str = ""):
    w = _uia_window(window)
    w.set_focus()
    if field:
        el = w.child_window(title_re=f"(?i).*{_re_escape(field)}.*", control_type="Edit", found_index=0)
    else:
        el = w.child_window(control_type="Edit", found_index=0)
    try:
        el.set_edit_text(text)
    except Exception:
        el.click_input()
        el.type_keys(text, with_spaces=True, with_newlines=True, pause=0.01)
    return "typed"


def _re_escape(s: str) -> str:
    import re

    return re.escape(s)
