"""Window management and Accessibility automation (click buttons by name inside any app) on macOS.
Needs Accessibility permission for Jarvis (System Settings → Privacy & Security → Accessibility)."""

from __future__ import annotations

from ._mac import as_str, osa, osascript, run
from .base import AUTO, CONFIRM, E, I, S, tool


def _cg_windows(on_screen_only: bool = False) -> list[dict]:
    import Quartz

    opts = (Quartz.kCGWindowListOptionOnScreenOnly if on_screen_only else Quartz.kCGWindowListOptionAll) \
        | Quartz.kCGWindowListExcludeDesktopElements
    out = []
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if w.get("kCGWindowLayer", 1) != 0:
            continue
        owner = str(w.get("kCGWindowOwnerName") or "")
        title = str(w.get("kCGWindowName") or "")
        if owner:
            out.append({"app": owner, "title": title, "on_screen": bool(w.get("kCGWindowIsOnscreen"))})
    return out


def _target(title: str) -> tuple[str, str]:
    """Find (process name, AppleScript window reference) for a title or app name."""
    key = title.strip().lower()
    wins = _cg_windows()
    for w in wins:  # app name match first
        if w["app"].lower() == key:
            return w["app"], "window 1"
    for w in wins:
        if w["title"] and key in w["title"].lower():
            return w["app"], f"(first window whose name contains {as_str(w['title'][:60])})"
    for w in wins:
        if key in w["app"].lower():
            return w["app"], "window 1"
    # maybe it has no windows yet but is running
    code, out = osascript('tell application "System Events" to get name of every application process '
                          "whose background only is false")
    for name in (s.strip() for s in out.split(",")) if code == 0 else []:
        if key in name.lower():
            return name, "window 1"
    raise LookupError(f"no window or app matching '{title}'")


def _visible_frame() -> tuple[int, int, int, int]:
    """(x, y, w, h) of the main screen minus menu bar and Dock, top-left origin, in points."""
    from AppKit import NSScreen

    screen = NSScreen.mainScreen()
    full = screen.frame()
    vis = screen.visibleFrame()
    top = int(full.size.height - (vis.origin.y + vis.size.height))
    return int(vis.origin.x), top, int(vis.size.width), int(vis.size.height)


@tool("list_windows", "List open windows (app — title).")
def list_windows():
    seen = []
    for w in _cg_windows(on_screen_only=True):
        label = f"{w['app']} — {w['title']}" if w["title"] else w["app"]
        if label not in seen:
            seen.append(label)
    return seen[:60] or "no windows (window titles need Screen Recording permission)"


@tool("window_action", "Focus, minimize, maximize, restore, close, or snap a window left/right.",
      {"title": S("app name or part of the window title, e.g. 'Safari' or 'Visual Studio Code'"),
       "action": E("action", ["focus", "minimize", "maximize", "restore", "close", "snap_left", "snap_right"])},
      ["title", "action"])
def window_action(title: str, action: str):
    proc, win = _target(title)
    p = as_str(proc)
    if action in ("focus", "restore"):
        osa(f'tell application "System Events" to tell process {p}\n'
            f"set frontmost to true\n"
            f'try\nset value of attribute "AXMinimized" of {win} to false\nend try\n'
            f'try\nperform action "AXRaise" of {win}\nend try\nend tell')
    elif action == "minimize":
        osa(f'tell application "System Events" to tell process {p} to set value of attribute "AXMinimized" of {win} to true')
    elif action == "close":
        osa(f'tell application "System Events" to tell process {p}\n'
            f'click (first button of {win} whose subrole is "AXCloseButton")\nend tell')
    else:
        x, y, w, h = _visible_frame()
        if action == "snap_left":
            pos, size = (x, y), (w // 2, h)
        elif action == "snap_right":
            pos, size = (x + w // 2, y), (w - w // 2, h)
        else:  # maximize (fill the screen without entering full-screen mode)
            pos, size = (x, y), (w, h)
        osa(f'tell application "System Events" to tell process {p}\n'
            f"set frontmost to true\n"
            f"set position of {win} to {{{pos[0]}, {pos[1]}}}\n"
            f"set size of {win} to {{{size[0]}, {size[1]}}}\nend tell")
    return f"{action}: {proc}"


@tool("show_desktop", "Move all windows aside and show the desktop (toggle).")
def show_desktop():
    code, _ = run(["/System/Applications/Mission Control.app/Contents/MacOS/Mission Control", "1"])
    if code != 0:
        osa('tell application "System Events" to key code 103')  # F11
    return "desktop shown"


@tool("switch_virtual_desktop", "Move to the next/previous Space (virtual desktop), or open Mission Control to add one.",
      {"direction": E("which", ["next", "previous", "new"])}, ["direction"])
def switch_virtual_desktop(direction: str):
    if direction == "new":
        run(["open", "-a", "Mission Control"])
        return "opened Mission Control — click + at the top to add a Space"
    code = 124 if direction == "next" else 123
    osa(f'tell application "System Events" to key code {code} using control down')
    return f"space: {direction}"


# ---------------------------------------------------------------- Accessibility (System Events)

_ROLE_MAP = {
    "button": "AXButton", "menuitem": "AXMenuItem", "hyperlink": "AXLink", "link": "AXLink",
    "edit": "AXTextField", "textfield": "AXTextField", "checkbox": "AXCheckBox", "radiobutton": "AXRadioButton",
    "tabitem": "AXRadioButton", "tab": "AXRadioButton", "listitem": "AXRow", "combobox": "AXComboBox",
    "popup": "AXPopUpButton", "menubutton": "AXMenuButton",
}

_LIST_SCRIPT = """
tell application "System Events" to tell process {proc}
    set out to ""
    set n to 0
    set wanted to {{"AXButton", "AXMenuItem", "AXLink", "AXTextField", "AXTextArea", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXComboBox", "AXMenuButton", "AXTab", "AXRow"}}
    repeat with e in (entire contents of {win})
        try
            set r to role of e
            if wanted contains r then
                set nm to ""
                try
                    set nm to name of e
                end try
                if nm is missing value or nm is "" then
                    try
                        set nm to description of e
                    end try
                end if
                if nm is missing value then set nm to ""
                if nm is not "" or r is "AXTextField" or r is "AXTextArea" then
                    set out to out & r & ": " & nm & linefeed
                    set n to n + 1
                    if n ≥ {limit} then exit repeat
                end if
            end if
        end try
    end repeat
    return out
end tell
"""


@tool("ui_list_elements", "List clickable/typeable controls (buttons, links, fields, menus) inside a window, "
      "so you can then use ui_click / ui_type. Use this before clicking inside apps.",
      {"window": S("app name or part of the window title"), "max_items": I("default 60")}, ["window"])
def ui_list_elements(window: str, max_items: int = 60):
    proc, win = _target(window)
    out = osa(_LIST_SCRIPT.format(proc=as_str(proc), win=win, limit=int(max_items)), timeout=45)
    lines = [ln.replace("AX", "", 1) for ln in out.splitlines() if ln.strip()]
    return list(dict.fromkeys(lines)) or "no controls found (the app may not expose accessibility info — try screen tools)"


_FIND_SCRIPT = """
tell application "System Events" to tell process {proc}
    set frontmost to true
    set key to {key}
    repeat with scope in {{{win}, menu bar 1}}
        repeat with e in (entire contents of scope)
            try
                set r to role of e
                if {role_check} then
                    set nm to ""
                    try
                        set nm to name of e
                    end try
                    if nm is missing value then set nm to ""
                    set ds to ""
                    try
                        set ds to description of e
                    end try
                    if ds is missing value then set ds to ""
                    if nm contains key or ds contains key then
                        {action}
                        return "ok"
                    end if
                end if
            end try
        end repeat
    end repeat
    return "notfound"
end tell
"""

_RISKY_WORDS = ("delete", "remove", "send", "pay", "buy", "purchase", "order", "confirm", "submit",
                "uninstall", "format", "erase", "transfer", "publish", "post", "move to trash")


def _click_level(args):
    name = (args.get("name") or "").lower()
    return CONFIRM if any(w in name for w in _RISKY_WORDS) else AUTO


@tool("ui_click", "Click a button/link/menu item by its visible name inside an app (Accessibility).",
      {"window": S("app name or part of the window title"), "name": S("text of the control to click"),
       "control_type": S("optional: Button, MenuItem, Hyperlink, TabItem, ListItem, CheckBox…")},
      ["window", "name"], level=_click_level,
      describe=lambda a: f"Click '{a.get('name')}' in {a.get('window')}")
def ui_click(window: str, name: str, control_type: str = ""):
    proc, win = _target(window)
    role = _ROLE_MAP.get(control_type.replace(" ", "").lower(), "")
    role_check = f'r is "{role}"' if role else (
        'r is in {"AXButton", "AXMenuItem", "AXLink", "AXCheckBox", "AXRadioButton", "AXPopUpButton", '
        '"AXMenuButton", "AXTab", "AXRow", "AXCell", "AXStaticText", "AXMenuBarItem"}')
    action = ('try\nperform action "AXPress" of e\non error\nclick e\nend try')
    out = osa(_FIND_SCRIPT.format(proc=as_str(proc), win=win, key=as_str(name), role_check=role_check,
                                  action=action), timeout=45)
    return f"clicked '{name}'" if out.strip() == "ok" else f"couldn't find '{name}' in {proc}"


@tool("ui_type", "Type text into a text field inside an app (by the field's name, or the first field).",
      {"window": S("app name or part of the window title"), "text": S("text to type"),
       "field": S("optional field name/label; empty = first text field")},
      ["window", "text"])
def ui_type(window: str, text: str, field: str = ""):
    proc, win = _target(window)
    role_check = 'r is in {"AXTextField", "AXTextArea", "AXComboBox", "AXSearchField"}'
    action = (f'set focused of e to true\ntry\nset value of e to {as_str(text)}\non error\n'
              f'keystroke {as_str(text)}\nend try')
    out = osa(_FIND_SCRIPT.format(proc=as_str(proc), win=win, key=as_str(field), role_check=role_check,
                                  action=action), timeout=45)
    return "typed" if out.strip() == "ok" else f"couldn't find a text field '{field}' in {proc}"
