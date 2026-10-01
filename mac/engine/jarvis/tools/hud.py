"""The full-screen Iron Man style HUD (heads-up display)."""

from __future__ import annotations

from ..context import ctx
from .base import tool


@tool("show_hud", "Open the full-screen JARVIS HUD: live clock, CPU/RAM/disk/battery/network, weather, reminders. "
      "Use for 'HUD dikhao', 'show the HUD', 'status screen', 'full screen mode'.")
async def show_hud():
    await ctx.broadcast({"type": "hud", "open": True})
    return "HUD is open (the user can press Esc to close it)."


@tool("hide_hud", "Close the full-screen HUD and go back to the small orb.")
async def hide_hud():
    await ctx.broadcast({"type": "hud", "open": False})
    return "HUD closed."
