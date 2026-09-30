"""Keyboard and mouse control."""

from __future__ import annotations

from .base import AUTO, CONFIRM, B, E, I, S, tool


def _keys_level(args):
    keys = (args.get("keys") or "").lower().replace(" ", "")
    # shift+delete skips the Recycle Bin
    if "shift" in keys and "del" in keys:
        return CONFIRM
    return AUTO


@tool("type_text", "Type text at the current cursor position in whatever app is focused.",
      {"text": S("text to type"), "press_enter": B("press Enter afterwards")}, ["text"])
def type_text(text: str, press_enter: bool = False):
    import pyautogui
    import pyperclip

    if text.isascii():
        pyautogui.write(text, interval=0.01)
    else:
        # pyautogui can't type Unicode (Hindi, emoji) — paste it instead
        old = pyperclip.paste()
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        pyautogui.sleep(0.2)
        pyperclip.copy(old)
    if press_enter:
        pyautogui.press("enter")
    return "typed"


@tool("press_keys", "Press a key or shortcut, e.g. 'enter', 'ctrl+s', 'alt+tab', 'win+e', 'ctrl+shift+t'.",
      {"keys": S("keys joined with +"), "times": I("repeat count, default 1")}, ["keys"],
      level=_keys_level, describe=lambda a: f"Press {a.get('keys')}")
def press_keys(keys: str, times: int = 1):
    import pyautogui

    parts = [k.strip().lower() for k in keys.split("+") if k.strip()]
    mapping = {"windows": "win", "control": "ctrl", "return": "enter", "escape": "esc", "del": "delete",
               "cmd": "win", "option": "alt", "pgup": "pageup", "pgdn": "pagedown"}
    parts = [mapping.get(p, p) for p in parts]
    for _ in range(max(1, min(int(times), 50))):
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
    return f"pressed {keys}"


@tool("mouse_click", "Click the mouse at screen coordinates (pixels). Use screen tools first to find positions.",
      {"x": I("x pixel"), "y": I("y pixel"), "button": E("button", ["left", "right", "middle"]),
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


@tool("scroll", "Scroll the mouse wheel in the window under the pointer.",
      {"direction": E("direction", ["up", "down"]), "amount": I("notches, default 5")}, ["direction"])
def scroll(direction: str, amount: int = 5):
    import pyautogui

    clicks = max(1, min(int(amount), 50)) * 120
    pyautogui.scroll(clicks if direction == "up" else -clicks)
    return f"scrolled {direction}"


@tool("mouse_position", "Get the current mouse position and the screen size.")
def mouse_position():
    import pyautogui

    x, y = pyautogui.position()
    w, h = pyautogui.size()
    return {"x": x, "y": y, "screen_width": w, "screen_height": h}
