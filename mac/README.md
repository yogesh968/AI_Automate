# J.A.R.V.I.S. for macOS

A voice assistant that lives on your Mac as a floating glowing orb. Say **"Hey Jarvis"** and talk in Hindi, English
or Hinglish. It controls your apps, files, windows, browser, Apple apps (Notes, Reminders, Calendar, Messages,
Music) and settings, sees your screen, remembers you, and replies in a natural voice.

This is the **macOS codebase** — separate from `../windows`. Same design and protocol, macOS-native internals
(AppleScript / System Events, Accessibility, Quartz, Keychain, zsh).

```
mac/
├── app/        Electron + React + Three.js — the orb, glass panel, menu-bar icon, shortcuts, permissions
├── engine/     Python 3.12 — Groq brain, voice, memory, safety and ~97 tools
├── setup.sh    one-time developer setup
├── build.sh    builds Jarvis.app + .dmg
└── PROTOCOL.md UI ⇄ engine WebSocket contract
```

## Requirements

- macOS 12 Monterey or newer (Apple Silicon or Intel)
- [Homebrew](https://brew.sh) — `setup.sh` installs Python 3.12, Node, and the optional `brightness` + `blueutil` helpers
- A **Groq API key** (brain + speech recognition) — https://console.groq.com/keys
- Optional **ElevenLabs API key** (premium natural voice) — without it a free Microsoft neural voice is used

## Setup

```bash
cd mac
chmod +x setup.sh build.sh
./setup.sh
cd app && npm run dev
```

Click the orb → **Settings** → paste your Groq (and ElevenLabs) keys. They are stored in the **macOS Keychain**
(service `jarvis`), never in files. For quick dev testing you can instead put them in `engine/.env`
(copy `engine/.env.example`).

## Permissions (important on macOS)

macOS protects these; Jarvis shows a **Permissions card** in the panel with **Allow** buttons until they're granted:

| Permission | Why | Where |
|---|---|---|
| Microphone | "Hey Jarvis", voice commands | asked automatically on first run |
| Accessibility | keyboard/mouse, window control, clicking buttons in apps | System Settings → Privacy & Security → Accessibility |
| Screen Recording | "what's this error on my screen?" | System Settings → Privacy & Security → Screen Recording |
| Automation | controlling Finder, Music, Notes, Reminders, Calendar, Messages, System Events | asked per app the first time |

After enabling Accessibility or Screen Recording, choose **Restart engine** (menu-bar icon or Settings).
In dev mode the permission belongs to **Electron** / your terminal; the built `Jarvis.app` asks for itself.

## What Jarvis can do (engine tools)

- **System**: volume, mute, brightness, media keys, lock, sleep, shut down / restart / log out (with delay + cancel), Wi-Fi, Bluetooth, dark/light mode, wallpaper, empty Trash, System Settings pages, battery, system info, top processes, kill process, clipboard, date/time
- **Apps**: open any app (fuzzy + Spotlight), quit / force-quit, running check, YouTube, Spotify, WhatsApp
- **Windows & UI**: list windows, focus / minimize / maximize / snap left-right / close, show desktop, switch Spaces, list and click buttons/menus and type into fields inside any app (Accessibility)
- **Keyboard & mouse**: type (incl. Hindi via paste), shortcuts (`cmd+s`…), click, move, scroll
- **Screen vision**: answer questions about the screen, click things by description (Retina-aware), save screenshots
- **Files**: list, search, read (txt/code/PDF/Word), info, open, reveal in Finder, create, write, move, copy, delete → Trash, organize folder by type, folder size
- **Apple apps**: Notes (create/search), Reminders (add), Calendar (list/add), iMessage (send), Music (play/pause/next/play song or playlist), notifications
- **Web**: search, news, read page, weather, full browser automation (Chrome or bundled Chromium, logins remembered)
- **Google**: Gmail list/read/send, Google Calendar list/create/delete (optional OAuth setup — see below)
- **Memory**: remembers facts about you; **reminders & timers**; **routines** ("good morning", "work mode")
- **Terminal**: runs zsh commands (always asks first)

## Safety

- Every action has a level: **auto** (harmless), **confirm** (you approve with a Yes/No card or by saying "haan"/"nahi"), **blocked**.
- Blocked: writing to `/System`, `/Library`, `/usr`, `/bin`, `/private`, `/Applications`, `~/Library/Keychains`, `~/.ssh`…; shell commands like `rm -rf /`, `sudo rm`, `diskutil erase…`, `dd of=/dev/…`, `csrutil`, `nvram`, `curl … | sh`, keychain dumping, etc.
- Deletes go to the **Trash**. **Dry-run mode** and **allowed folders** in Settings.
- **Kill switch**: `⌘⌥J` stops everything instantly.
- Audit log: Activity tab + `~/Library/Application Support/Jarvis/logs/audit.jsonl`.

## Gmail + Google Calendar (optional)

1. https://console.cloud.google.com → new project → enable **Gmail API** and **Google Calendar API**
2. OAuth consent screen → External → add yourself as a test user
3. Credentials → Create OAuth client ID → **Desktop app** → download the JSON
4. Save it as `~/Library/Application Support/Jarvis/google_credentials.json`
5. Ask Jarvis "read my emails" — a browser opens once to sign in

(The Apple Calendar tools work without any of this, including Google accounts added in System Settings → Internet Accounts.)

## Build the app

```bash
./build.sh               # → app/release/Jarvis-<version>-<arch>.dmg + .zip
```

Builds for the current Mac's architecture (the bundled Python engine is arch-specific): build on Apple Silicon
for `arm64`, on an Intel Mac for `x64`.

### Sign & notarize

Needed only to share the app with others without Gatekeeper warnings (requires an Apple Developer account, $99/yr):

```bash
export CSC_NAME="Developer ID Application: Your Name (TEAMID)"   # certificate in your login keychain
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="abcd-efgh-ijkl-mnop"          # appleid.apple.com → App-Specific Passwords
export APPLE_TEAM_ID="TEAMID"
./build.sh
```

Without these the app is ad-hoc signed — fine on your own Mac (first launch: right-click Jarvis.app → Open).
Entitlements (`app/build/entitlements.mac.plist`): microphone, Apple Events automation, network client/server,
JIT + unsigned executable memory + disabled library validation (needed by the bundled Python engine).

## Hosting / releases

The Mac app is released separately from Windows, via GitHub Releases on **`yogesh968/jarvis-macos`**:

```bash
export GH_TOKEN=<token with repo scope>
./build.sh --publish     # uploads .dmg, .zip and latest-mac.yml
```

Installed copies auto-update from there (electron-updater; macOS auto-update requires a signed build).
Link the `.dmg` from your download page (e.g. a Vercel landing page) with
`https://github.com/yogesh968/jarvis-macos/releases/latest`.

## Troubleshooting

- **Engine won't start** → panel shows the error; logs: menu-bar icon → *Open logs folder* (`engine.log`, `engine-core.log`).
- **"macOS blocked this"** from a tool → enable the named permission, then *Restart engine*.
- **Wake word too sensitive / deaf** → Settings → Listening → sensitivity.
- **Brightness not exact** → `brew install brightness`. **Bluetooth toggle** → `brew install blueutil`.
- Engine smoke test (no UI): `cd engine && .venv/bin/python tests/smoke_ws.py "hello jarvis"`.
