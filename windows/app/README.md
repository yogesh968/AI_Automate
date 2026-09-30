# Jarvis for Windows — desktop app (Electron + React + Three.js)

This is the **floating orb UI**. It spawns the Python engine in `../engine` and talks to it over a local
WebSocket. The message contract is in [`../PROTOCOL.md`](../PROTOCOL.md).

## What it does

- **Floating orb**: transparent, always on top, bottom-right by default. Clicks pass through everything except the orb and panel.
  - **Click** → open/close the glass panel
  - **Hold** (½ s) → push-to-talk, release to send
  - **Right-click** → talk now
  - **Drag** → move it (position is remembered)
- **Orb states**: idle pulse · listening (reacts to your mic) · thinking (fast violet arcs) · speaking (reacts to Jarvis's voice) · muted (dim) · error (red) · offline (grey).
- **Panel tabs**
  - **Chat**: streaming replies, live transcript, tool activity chips, Yes/No permission cards, text box, mic and stop buttons.
  - **Activity**: the audit log of everything Jarvis did on the PC.
  - **Settings**: API keys (saved in Windows Credential Manager by the engine), voice, Hindi writing style, wake word, models, safety (dry-run, allowed folders), start with Windows.
- **Tray icon**: show/hide orb, open panel, settings, mute mic, start with Windows, restart engine, logs, quit.
- **Global shortcuts** (if a combo is taken by another app, the next one is used; Settings shows the active ones):

  | Action | Shortcut | Fallback |
  |---|---|---|
  | Talk | `Ctrl+Alt+Space` | `Ctrl+Shift+Space`, `Ctrl+Alt+K` |
  | **Kill switch** — stop everything | `Ctrl+Alt+J` | `Ctrl+Shift+J` |
  | Show/hide panel | `Ctrl+Alt+P` | `Ctrl+Shift+P` |
  | Hide/show orb | `Ctrl+Alt+H` | `Ctrl+Shift+H` |

- Engine supervision: free port + random token, waits for `JARVIS_READY`, restarts on crash (max 5 per minute), kills the whole process tree on quit.
- Logs: `%APPDATA%\Jarvis\logs\engine.log` (engine output) and `ui.log` (UI warnings/errors).
- Auto-update from GitHub Releases (`yogesh968/jarvis-windows`) in the installed app.

## Requirements

- Node.js 20+ (22 LTS recommended)
- For the real engine: Python 3.12 and the engine venv (see `../engine/README.md`)

## Develop

```powershell
cd windows\app
npm install

# 1. Engine venv (once)
cd ..\engine
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..\app

# 2. Run the app (Vite dev server + Electron, hot reload for the UI)
npm run dev
```

In dev the app runs `..\engine\.venv\Scripts\python.exe -m jarvis`. If there's no venv it falls back to `python` on your PATH. If the engine can't start, the panel opens and shows the error with setup steps.

### Without Python: mock engine

```powershell
npm run dev:mock
```

This runs `scripts/mock-engine.js`, a fake engine that speaks the same protocol. Try typing "volume", "saaf karo" (permission card flow) or "remind" (a notification after 10 s). Hold the orb for a fake voice turn.

### Smoke test

```powershell
npm run smoke
```

This builds the UI, launches it against the mock engine, and saves screenshots to `%APPDATA%\Jarvis\smoke\` (orb, settings, chat, permission card). Then it quits.

## Build the installer

```powershell
# 1. Bundle the engine into ..\engine\dist\jarvis-engine\ (PyInstaller; see ../engine/README.md)
# 2. Build the app + NSIS installer
npm run dist
```

The output goes to `release\Jarvis Setup <version>.exe`.

`extraResources` copies `..\engine\dist\jarvis-engine\` into the installer as `resources\engine\`. **Build the engine first.** Without it the installer still builds, but the installed app shows "Engine binary missing".

To publish an auto-update: `npx electron-builder --win nsis --publish always` with a `GH_TOKEN` that can write to `yogesh968/jarvis-windows`.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Vite + Electron with the real Python engine |
| `npm run dev:mock` | Same, with the mock engine |
| `npm run build` | Build the renderer into `dist/` |
| `npm run start` | Run Electron on the built `dist/` |
| `npm run smoke` | Screenshot smoke test with the mock engine |
| `npm run icon` | Regenerate the orb icons (`build/icon.png`, `electron/assets/*.png`) |
| `npm run check` | Syntax-check the Electron main-process files |
| `npm run dist` | Icons + build + Windows installer |

## Layout

```
app/
├── electron/
│   ├── main.js          # window, panel resize, click-through, shortcuts, IPC, updater
│   ├── engine.js        # spawns + supervises the Python engine
│   ├── preload.js       # contextBridge API (window.jarvis)
│   ├── tray.js          # tray menu
│   ├── windowState.js   # remembers the orb position
│   └── assets/          # tray.png, icon.png
├── src/
│   ├── App.jsx          # protocol message handling, orb gestures
│   ├── bridge.js        # window.jarvis (with a browser stub)
│   ├── hooks/useEngine.js
│   ├── audio/player.js  # ordered MP3 playback + live amplitude
│   ├── components/      # Orb (Three.js), Panel, ChatTab, ActivityTab, SettingsTab, ConfirmCard, Toasts
│   └── styles.css       # HUD glass theme
├── scripts/
│   ├── make-icon.js     # zero-dependency PNG icon renderer
│   └── mock-engine.js   # fake engine for UI work
├── build/icon.png       # installer/app icon (electron-builder makes the .ico)
└── index.html           # fonts: Orbitron, Inter, Noto Sans Devanagari
```
