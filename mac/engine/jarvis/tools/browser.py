"""Browser automation with Playwright, driving Google Chrome (or Playwright's bundled Chromium)
with Jarvis's own profile (so logins stay saved between sessions)."""

from __future__ import annotations

import re

from ..paths import data_dir
from ._mac import clip
from .base import AUTO, CONFIRM, B, I, S, tool

_state: dict = {"pw": None, "ctx": None, "page": None}

RISKY = re.compile(r"pay|buy|purchase|order|checkout|place|send|submit|delete|remove|confirm|transfer|post|publish",
                   re.I)


async def _page():
    page = _state.get("page")
    if page and not page.is_closed():
        return page
    if _state["ctx"] is None:
        from playwright.async_api import async_playwright

        _state["pw"] = await async_playwright().start()
        profile = data_dir() / "browser_profile"
        launch = dict(user_data_dir=str(profile), headless=False, no_viewport=True,
                      args=["--start-maximized"])
        try:
            _state["ctx"] = await _state["pw"].chromium.launch_persistent_context(channel="chrome", **launch)
        except Exception:
            # no Google Chrome installed — use the Chromium that setup.sh downloaded
            _state["ctx"] = await _state["pw"].chromium.launch_persistent_context(**launch)
    pages = _state["ctx"].pages
    _state["page"] = pages[-1] if pages else await _state["ctx"].new_page()
    return _state["page"]


@tool("browser_open", "Open a URL in Jarvis's controllable browser (use this when you need to interact with the "
      "page afterwards; use open_url for just showing a site).",
      {"url": S("URL"), "new_tab": B("open in a new tab")}, ["url"])
async def browser_open(url: str, new_tab: bool = False):
    if "://" not in url:
        url = "https://" + url
    page = await _page()
    if new_tab:
        page = await _state["ctx"].new_page()
        _state["page"] = page
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    return f"opened {page.url} — title: {await page.title()}"


@tool("browser_read", "Read the visible text of the current page in Jarvis's browser, plus its links and inputs.",
      {"max_chars": I("default 10000")})
async def browser_read(max_chars: int = 10000):
    page = await _page()
    text = await page.evaluate("() => document.body ? document.body.innerText : ''")
    controls = await page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a,button,input,textarea,select,[role=button]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            const label = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') ||
                           el.name || el.title || '').trim().slice(0, 60);
            if (label) out.push(el.tagName.toLowerCase() + ': ' + label);
        });
        return [...new Set(out)].slice(0, 80);
    }""")
    return {"url": page.url, "title": await page.title(), "text": clip(text, int(max_chars)), "controls": controls}


def _click_level(args):
    return CONFIRM if RISKY.search(args.get("target", "")) else AUTO


@tool("browser_click", "Click a link/button in Jarvis's browser by its visible text (or a CSS selector).",
      {"target": S("visible text or CSS selector")}, ["target"], level=_click_level,
      describe=lambda a: f"Click '{a.get('target')}' in the browser")
async def browser_click(target: str):
    page = await _page()
    locators = [
        page.get_by_role("button", name=target),
        page.get_by_role("link", name=target),
        page.get_by_text(target, exact=False),
    ]
    if re.match(r"^[#.\[]|^\w+[#.\[]", target):
        locators.insert(0, page.locator(target))
    for loc in locators:
        try:
            if await loc.count():
                await loc.first.click(timeout=8000)
                await page.wait_for_load_state("domcontentloaded")
                return f"clicked '{target}' — now at {page.url}"
        except Exception:
            continue
    return f"couldn't find '{target}' on the page"


@tool("browser_fill", "Type into an input on the current page, found by its label/placeholder/name "
      "(or a CSS selector). Optionally press Enter.",
      {"field": S("label, placeholder, name or CSS selector"), "text": S("text to type"),
       "press_enter": B("press Enter after typing")},
      ["field", "text"],
      level=lambda a: CONFIRM if re.search(r"password|card|cvv|otp|pin", a.get("field", ""), re.I) else AUTO,
      describe=lambda a: f"Fill '{a.get('field')}' in the browser")
async def browser_fill(field: str, text: str, press_enter: bool = False):
    page = await _page()
    candidates = [
        page.get_by_label(field),
        page.get_by_placeholder(field),
        page.locator(f"[name='{field}']"),
        page.get_by_role("textbox", name=field),
        page.get_by_role("searchbox", name=field),
    ]
    if re.match(r"^[#.\[]|^\w+[#.\[]", field):
        candidates.insert(0, page.locator(field))
    for loc in candidates:
        try:
            if await loc.count():
                await loc.first.fill(text, timeout=8000)
                if press_enter:
                    await loc.first.press("Enter")
                    await page.wait_for_load_state("domcontentloaded")
                return f"filled '{field}'"
        except Exception:
            continue
    return f"couldn't find a field '{field}'"


@tool("browser_press", "Press a key in Jarvis's browser (Enter, Tab, PageDown, Escape, ctrl+f…).",
      {"key": S("key name")}, ["key"])
async def browser_press(key: str):
    page = await _page()
    names = {"ctrl": "Control", "control": "Control", "alt": "Alt", "shift": "Shift", "enter": "Enter",
             "tab": "Tab", "esc": "Escape", "escape": "Escape", "pagedown": "PageDown", "pageup": "PageUp",
             "space": "Space", "backspace": "Backspace", "delete": "Delete"}
    combo = "+".join(names.get(k.strip().lower(), k.strip()) for k in key.split("+"))
    await page.keyboard.press(combo)
    return f"pressed {key}"


@tool("browser_back", "Go back to the previous page in Jarvis's browser.")
async def browser_back():
    page = await _page()
    await page.go_back()
    return f"back to {page.url}"


@tool("browser_close", "Close Jarvis's browser.")
async def browser_close():
    if _state["ctx"]:
        await _state["ctx"].close()
    if _state["pw"]:
        await _state["pw"].stop()
    _state.update(pw=None, ctx=None, page=None)
    return "browser closed"
