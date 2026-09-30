"""Keyboard and mouse control on macOS (needs Accessibility permission)."""

from __future__ import annotations

from .base import AUTO, CONFIRM, B, E, I, S, tool

KEY_NAMES = {
    "cmd": "command", "command": "command", "⌘": "command", "win": "command", "windows": "command",
    "super": "command", "meta": "command", "option": "option", "opt": "option", "alt": "option", "⌥": "option",
    "control": "ctrl", "ctrl": "ctrl", "^": "ctrl", "shift": "shift", "⇧": "shift",
    "return": "return", "enter": "return", "escape": "esc", "esc": "esc", "del": "delete",
    "backspace": "backspace", "forwarddelete": "del", "pgup": "pageup", "pgdn": "pagedown", "space": "space",
}


def _keys_level(args):
    keys = (args.get("keys") or "").lower().replace(" ", "")
    # cmd+shift+delete (+option) empties the Trash
    has_cmd = "cmd" in keys or "command" in keys
    if has_cmd and "shift" in keys and ("del" in keys or "backspace" in keys):
        return CONFIRM
    return AUTO


@tool("type_text", "Type text at the current cursor position in whatever app is focused.",
      {"text": S("text to type"), "press_enter": B("press Return afterwards")}, ["text"])
def type_text(text: str, press_enter: bool = False):
    import pyautogui
    import pyperclip

    if text.isascii() and len(text) < 200:
        pyautogui.write(text, interval=0.01)
    else:
        # pyautogui can't type Unicode (Hindi, emoji) — paste it instead
        old = pyperclip.paste()
        pyperclip.copy(text)
        pyautogui.hotkey("command", "v")
        pyautogui.sleep(0.25)
        pyperclip.copy(old)
    if press_enter:
        pyautogui.press("return")
    return "typed"


@tool("press_keys", "Press a key or shortcut, e.g. 'return', 'cmd+s', 'cmd+tab', 'cmd+space', 'cmd+shift+t'.",
      {"keys": S("keys joined with +"), "times": I("repeat count, default 1")}, ["keys"],
      level=_keys_level, describe=lambda a: f"Press {a.get('keys')}")
def press_keys(keys: str, times: int = 1):
    import pyautogui

    parts = [KEY_NAMES.get(k.strip().lower(), k.strip().lower()) for k in keys.split("+") if k.strip()]
    for _ in range(max(1, min(int(times), 50))):
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts, interval=0.03)
    return f"pressed {keys}"


@tool("mouse_click", "Click the mouse at screen coordinates (points). Use screen tools first to find positions.",
      {"x": I("x point"), "y": I("y point"), "button": E("button", ["left", "right", "middle"]),
       "double": B("double-click")}, ["x", "y"])
def mouse_click(x: int, y: int, button: str = "left", double: bool = False):
    import pyautogui

    pyautogui.click(x=int(x), y=int(y), button=button, clicks=2 if double else 1, interval=0.08)
    return f"clicked {button} at ({x},{y})"


@tool("mouse_move", "Move the mouse pointer to screen coordinates.", {"x": I("x"), "y": I("y")}, ["x", "y"])
def mouse_move(x: int, y: int):
    import pyautogui

    pyautogui.moveTo(int(x), int(y), duration=0.2)
    return f"moved to ({x},{y})"


@tool("scroll", "Scroll in the window under the pointer.",
      {"direction": E("direction", ["up", "down"]), "amount": I("notches, default 5")}, ["direction"])
def scroll(direction: str, amount: int = 5):
    import pyautogui

    clicks = max(1, min(int(amount), 50)) * 5  # macOS scroll units are small
    pyautogui.scroll(clicks if direction == "up" else -clicks)
    return f"scrolled {direction}"


@tool("mouse_position", "Get the current mouse position and the screen size (in points).")
def mouse_position():
    import pyautogui

    x, y = pyautogui.position()
    w, h = pyautogui.size()
    return {"x": x, "y": y, "screen_width": w, "screen_height": h}
