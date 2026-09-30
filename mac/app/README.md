# Jarvis for macOS — desktop app (Electron + React + Three.js)

This is the **floating orb UI**. It spawns the Python engine in `../engine` and talks to it over a local
WebSocket. The message contract is in [`../PROTOCOL.md`](../PROTOCOL.md).

## What it does

- **Floating orb**: transparent, always on top (even over full-screen apps and on every Space), bottom-right by default. Clicks pass through everything except the orb and panel.
  - **Click** → open/close the glass panel
  - **Hold** (½ s) → push-to-talk, release to send
  - **Right-click** → talk now
  - **Drag** → move it (position is remembered)
- **Orb states**: idle pulse · listening (reacts to your mic) · thinking (fast violet arcs) · speaking (reacts to Jarvis's voice) · muted (dim) · error (red) · offline (grey).
- **No Dock icon** (`LSUIElement`): Jarvis lives in the menu bar and the orb.
- **Panel tabs**
  - **Chat**: a macOS permissions card (until everything is allowed), streaming replies, live transcript, tool activity chips, Yes/No permission cards, text box, mic and stop buttons.
  - **Activity**: the audit log of everything Jarvis did on the Mac.
  - **Settings**: API keys (saved in the macOS Keychain by the engine), voice, Hindi writing style, wake word, models, safety (dry-run, allowed folders), macOS permissions, open at login.
- **Menu-bar icon** (Template image, adapts to light/dark): show/hide orb, open panel, settings, mute mic, open at login, restart engine, logs, quit.
- **Global shortcuts** (if a combo is taken by another app, the next one is used; Settings shows the active ones):

  | Action | Shortcut | Fallback |
  |---|---|---|
  | Talk | `⌘⌥Space` | `⌃⌥Space`, `⌘⌥K` |
  | **Kill switch** — stop everything | `⌘⌥J` | `⌃⌥J` |
  | Show/hide panel | `⌘⌥P` | `⌃⌥P` |
  | Hide/show orb | `⌘⌥H` | `⌃⌥H` |

- Engine supervision: free port + random token, waits for `JARVIS_READY`, restarts on crash (max 5 per minute), kills the engine's whole process group on quit.
- Logs: `~/Library/Application Support/Jarvis/logs/engine.log` (engine output) and `ui.log` (UI warnings/errors).
- Auto-update from GitHub Releases (`yogesh968/jarvis-macos`) in the installed app (needs a signed build).

## Develop

```bash
cd mac
./setup.sh          # once: Python 3.12 venv, engine deps, wake word, Chromium, npm install
cd app
npm run dev         # Vite dev server + Electron, hot reload for the UI
```

In dev the app runs `../engine/.venv/bin/python3 -m jarvis`. If there's no venv it falls back to `python3` on your PATH.

> **Permissions in dev:** macOS attributes the mic / Accessibility / Screen Recording use to **Electron** (or your
> terminal), so allow those. The packaged `Jarvis.app` asks for itself.

### Without Python: mock engine

```bash
npm run dev:mock
```

A fake engine that speaks the same protocol. Try typing "volume", "saaf karo" (permission card flow) or "remind" (a notification after 10 s).

## Build the .dmg

```bash
cd mac
./build.sh              # engine (PyInstaller) + Jarvis.app + .dmg/.zip for this Mac's architecture
./build.sh --publish    # same + upload to GitHub Releases for auto-update (needs GH_TOKEN)
```

Output: `app/release/Jarvis-<version>-<arch>.dmg` and `.zip`. The engine is bundled at
`Jarvis.app/Contents/Resources/engine/`. Build on Apple Silicon for `arm64`, on an Intel Mac for `x64` (the Python engine is architecture-specific).

Signing and notarization are covered in [`../README.md`](../README.md#sign--notarize).

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Vite + Electron with the real Python engine |
| `npm run dev:mock` | Same, with the mock engine |
| `npm run build` | Build the renderer into `dist/` |
| `npm run start` | Run Electron on the built `dist/` |
| `npm run smoke` | Screenshot smoke test with the mock engine |
| `npm run icon` | Regenerate icons (`build/icon.png` 1024 → .icns, orb + menu-bar Template PNGs) |
| `npm run check` | Syntax-check the Electron main-process files |
| `npm run dist` | Icons + build + mac .dmg/.zip (arm64 + x64 app shell; engine must match) |

## Layout

```
app/
├── electron/
│   ├── main.js          # window, panel resize, click-through, shortcuts, IPC, updater, Dock hiding
│   ├── engine.js        # spawns + supervises the Python engine (process group)
│   ├── permissions.js   # Microphone / Accessibility / Screen Recording / Automation status + prompts
│   ├── preload.js       # contextBridge API (window.jarvis)
│   ├── tray.js          # menu-bar menu
│   ├── windowState.js   # remembers the orb position
│   └── assets/          # trayTemplate(@2x).png, icon.png
├── src/
│   ├── App.jsx          # protocol message handling, orb gestures
│   ├── bridge.js        # window.jarvis (with a browser stub) + ⌘⌥ key symbols
│   ├── hooks/useEngine.js
│   ├── audio/player.js  # ordered MP3 playback + live amplitude
│   ├── components/      # Orb (Three.js), Panel, ChatTab, ActivityTab, SettingsTab, ConfirmCard, PermissionsCard, Toasts
│   └── styles.css       # HUD glass theme
├── scripts/
│   ├── make-icon.js     # zero-dependency PNG icon renderer
│   └── mock-engine.js   # fake engine for UI work
├── build/
│   ├── icon.png                 # 1024px app icon (electron-builder makes icon.icns)
│   └── entitlements.mac.plist   # hardened-runtime entitlements
└── index.html           # fonts: Orbitron, Inter, Noto Sans Devanagari
```
