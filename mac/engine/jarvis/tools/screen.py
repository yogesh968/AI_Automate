"""Screen vision: screenshots + asking the vision model what's on screen / where to click.
Needs Screen Recording permission (System Settings → Privacy & Security → Screen Recording)."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import io
import json
import re
from pathlib import Path

from ..context import ctx
from .base import AUTO, CONFIRM, B, I, S, tool

MAX_W = 1280


def _grab(monitor: int = 1):
    """Returns (image, monitor dict in points, retina ratio = image pixels per point)."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        mons = sct.monitors
        mon = mons[monitor] if 0 < monitor < len(mons) else mons[1]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
    ratio = img.width / mon["width"] if mon["width"] else 1.0
    return img, mon, ratio


def _encode(img) -> tuple[str, float]:
    scale = 1.0
    if img.width > MAX_W:
        scale = MAX_W / img.width
        img = img.resize((MAX_W, round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode(), scale


def _looks_blank(img) -> bool:
    """Without Screen Recording permission macOS returns only the wallpaper/blank frames."""
    small = img.resize((32, 20)).convert("L")
    return max(small.getdata()) - min(small.getdata()) < 3


PERMISSION_HINT = ("The screenshot came back empty — Jarvis needs Screen Recording permission: System Settings → "
                   "Privacy & Security → Screen Recording → enable Jarvis, then restart Jarvis.")


@tool("look_at_screen", "Take a screenshot and answer a question about what's on screen (read errors, text, "
      "describe windows, find things). Use whenever the user says 'this', 'here', 'on my screen'.",
      {"question": S("what to find out"), "monitor": I("monitor number, default 1")}, ["question"])
async def look_at_screen(question: str, monitor: int = 1):
    img, _, _ = await asyncio.to_thread(_grab, monitor)
    if _looks_blank(img):
        return PERMISSION_HINT
    b64, _ = await asyncio.to_thread(_encode, img)
    return await ctx.llm.vision(b64, f"This is a screenshot of the user's Mac screen. {question}\n"
                                     "Answer precisely; quote exact text (errors, numbers) when relevant.")


@tool("click_on_screen", "Find something visible on screen by description (e.g. 'the blue Sign in button') "
      "and click it. Prefer ui_click when the app supports it.",
      {"target": S("what to click, described visually"), "double": B("double-click"), "monitor": I("default 1")},
      ["target"],
      level=lambda a: CONFIRM if re.search(r"delete|remove|send|pay|buy|order|submit|confirm|uninstall|trash",
                                           a.get("target", ""), re.I) else AUTO,
      describe=lambda a: f"Click '{a.get('target')}' on screen")
async def click_on_screen(target: str, double: bool = False, monitor: int = 1):
    import pyautogui

    img, mon, ratio = await asyncio.to_thread(_grab, monitor)
    if _looks_blank(img):
        return PERMISSION_HINT
    b64, scale = await asyncio.to_thread(_encode, img)
    w, h = round(img.width * scale), round(img.height * scale)
    answer = await ctx.llm.vision(
        b64,
        f"The image is {w}x{h} pixels. Find: {target}. Reply ONLY with JSON "
        '{"found": true, "x": <center x>, "y": <center y>} in image pixels, or {"found": false}.',
    )
    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        return f"couldn't locate '{target}'"
    data = json.loads(match.group(0))
    if not data.get("found"):
        return f"'{target}' is not visible on screen"
    # image pixels -> physical pixels -> points (Retina screens have 2 pixels per point)
    x = mon["left"] + round(float(data["x"]) / scale / ratio)
    y = mon["top"] + round(float(data["y"]) / scale / ratio)
    await asyncio.to_thread(pyautogui.click, x, y, clicks=2 if double else 1, interval=0.08)
    return f"clicked '{target}' at ({x},{y})"


@tool("take_screenshot", "Save a screenshot to ~/Pictures/Screenshots and return the file path.",
      {"monitor": I("monitor number, 0 = all monitors, default 1")})
def take_screenshot(monitor: int = 1):
    import mss
    import mss.tools

    folder = Path.home() / "Pictures" / "Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Jarvis {dt.datetime.now():%Y-%m-%d at %H.%M.%S}.png"
    with mss.mss() as sct:
        mons = sct.monitors
        mon = mons[monitor] if 0 <= monitor < len(mons) else mons[1]
        shot = sct.grab(mon)
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    return str(path)
