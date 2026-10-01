# J.A.R.V.I.S. — Windows

A voice assistant that lives as a glowing orb on your screen, talks in natural Hinglish or English, and controls your PC.

```
windows/
├── app/        Electron + React + Three.js — the full-screen JARVIS display, mini orb, settings, tray, hotkeys, audio
├── engine/     Python — brain (Groq), voice (wake word, STT, TTS), memory, safety, 88 device tools
├── PROTOCOL.md how app and engine talk (WebSocket)
├── setup.ps1   one-time developer setup
└── build.ps1   builds the installer (app\release\Jarvis Setup x.y.z.exe)
```

## Quick start

```powershell
cd windows
powershell -ExecutionPolicy Bypass -File setup.ps1    # Python venv, packages, wake-word model, npm install
cd app
npm run dev                                            # orb appears bottom-right
```

Then click the orb → **Settings** → paste your keys:

| Key | Where to get it | Used for |
|---|---|---|
| **Groq** (required) | console.groq.com → API Keys | brain (LLM), screen vision, speech-to-text (Whisper) |
| **ElevenLabs** (optional) | elevenlabs.io → Profile → API Keys | natural human voice. Without it Jarvis uses a free Microsoft Edge Hindi voice. |

Keys are stored in **Windows Credential Manager**, never in files. For development you can instead put them in `engine\.env` (see `.env.example`).

### Pick a voice (important for "not sounding like AI")
In ElevenLabs → **Voice Library**, filter *Language: Hindi*, pick a voice you like (young, conversational), click **Add**, copy its **Voice ID** into Settings → *ElevenLabs voice ID*. The default model `eleven_flash_v2_5` starts speaking fastest; `eleven_multilingual_v2` sounds a little richer but is much slower.

## What makes it feel like the real JARVIS

| Feature | What it does |
|---|---|
| **Classic persona** | Composed, dry-witted, calls you *sir* (Settings → Personality → *Address me as*). Switch to *Desi friend* for casual Hinglish. |
| **Boot greeting** | "Good evening, sir. It's 7:05 PM. All systems are online." — works even before any API key is set. |
| **Continuous conversation** | After answering a voice command it keeps listening ~5 s, so you can just keep talking. |
| **Interrupt** | Say "Hey Jarvis" while it's talking to cut it off and give a new command. |
| **Voice-only JARVIS screen** | Jarvis opens as one big full-screen arc-reactor display (live CPU/RAM/disk/battery gauges, network, top processes, weather, reminders). There is no chat window — just talk. Approvals show as a big YES/NO prompt and can be answered by voice. `Esc` / *Minimize* shrinks it to the small orb; click the orb, `Ctrl+Alt+U` or say "HUD dikhao" to bring it back. Apps Jarvis opens appear in front of it. |
| **Fast replies** | Each request only carries the ~20 everyday tools plus the groups your words point at (the model can load more itself), and when Groq throttles one model Jarvis instantly switches to the next (`gpt-oss-120b` → `gpt-oss-20b` → `qwen3.8-27b`) instead of waiting. |
| **Proactive alerts** | Speaks up on its own: low battery, battery full, CPU overload, memory pressure, disk almost full, internet down/back. |
| **Learns about you** | Quietly remembers lasting facts you mention ("my sister Priya…") — shows a small *Noted* toast. Manage them by asking "what do you remember about me?" / "forget #12". |
| **HUD sound effects** | Soft chimes when it starts/stops listening. |

For the most movie-like voice: ElevenLabs default voice (*George*, British) or the free **Ryan — British English** voice.

## Using Jarvis

| Do this | What happens |
|---|---|
| Say **"Hey Jarvis"** | orb wakes and listens, then you speak normally |
| Click the orb | open the full JARVIS screen |
| Hold the orb / right-click | push-to-talk |
| `Ctrl+Alt+Space` | talk now (falls back to `Ctrl+Shift+Space` / `Ctrl+Alt+K` if taken — Settings shows the active one) |
| `Ctrl+Alt+J` | **kill switch** — stops everything instantly |
| `Ctrl+Alt+P` | show/hide Settings |
| `Ctrl+Alt+H` | hide/show the orb |
| `Ctrl+Alt+U` | show the JARVIS screen / minimize it to the orb |

Examples: *"Hey Jarvis, Downloads folder saaf kar do"*, *"Chrome kholo aur YouTube pe Arijit Singh chalao"*, *"screen pe jo error hai woh samjhao"*, *"kal subah 7 baje yaad dilana gym jaana hai"*, *"good morning"*, *"volume 30 kar do aur dark mode on"*, *"mera unread email padh ke sunao"*.

## What it can do (90 tools)

- **System** — volume, mute, brightness, media keys, lock/sleep/shutdown/restart, Wi-Fi & Bluetooth on/off, dark/light mode, wallpaper, Settings pages, battery, system info, top processes, kill process, clipboard, empty Recycle Bin
- **Apps & windows** — open any installed app (Start Menu + Store apps, fuzzy names), close politely or force, list/focus/minimize/maximize/snap windows, virtual desktops, **click buttons inside apps by name** (UI Automation)
- **Keyboard & mouse** — type (incl. Hindi via paste), shortcuts, click, move, scroll
- **Screen vision** — "what's on my screen", read errors, **click things by description**, screenshots
- **Files** — list, search, read (txt/code/PDF/Word), create, move, copy, rename, delete (→ Recycle Bin), organize folder by type, folder sizes, open
- **Internet** — web search, news, read any web page, weather (no key needed)
- **Browser automation** — Jarvis's own Edge window: open, read, click, fill forms, press keys (logins persist)
- **Gmail & Google Calendar** — read/search/send email, list/create/delete events
- **YouTube / Spotify / WhatsApp** — play a song, search Spotify, pre-fill WhatsApp messages
- **Memory** — remembers facts about you and uses them in every conversation
- **Reminders, timers, routines** — "good morning", "work mode", or your own
- **PowerShell** — anything else, always with your approval

## Safety

| Level | Examples | Behaviour |
|---|---|---|
| 🟢 auto | open app, read file, search, volume | runs immediately |
| 🟡 confirm | delete, move, overwrite, send email, run command, shutdown, force-close, risky clicks ("Pay", "Send") | Jarvis asks — answer **"haan" / "nahi"** by voice or click Yes/No |
| 🔴 blocked | anything in `C:\Windows`, `Program Files`, drive roots; `format`, `diskpart`, `bcdedit`, registry deletes, encoded PowerShell… | refused |

- **Kill switch** `Ctrl+Alt+J` cancels the current task, tools and speech.
- **Dry-run mode** (Settings) simulates every change.
- **Allowed folders** (Settings) limit where Jarvis may change files (default: your user folder).
- Deletes go to the **Recycle Bin**.
- **Activity tab** = audit log of every action (also `%APPDATA%\Jarvis\logs\audit.jsonl`).
- Wake word and mic processing run locally; audio is sent to Groq only after "Hey Jarvis" / hotkey.

## Gmail & Calendar setup (optional, one time)

1. console.cloud.google.com → create a project → enable **Gmail API** and **Google Calendar API**
2. OAuth consent screen → External → add your Gmail as a test user
3. Credentials → Create credentials → OAuth client ID → **Desktop app** → Download JSON
4. Save it as `%APPDATA%\Jarvis\google_credentials.json`
5. Ask Jarvis "mera email check karo" — a browser opens once to sign in.

## Data locations

`%APPDATA%\Jarvis\` — `settings.json`, `jarvis.db` (chat history, memory, reminders, audit), `routines.json`, `browser_profile\`, `logs\` (`engine.log`, `engine-core.log`, `ui.log`, `audit.jsonl`).

## Build the installer

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

1. `engine\dist\jarvis-engine\jarvis-engine.exe` (PyInstaller)
2. `app\release\Jarvis Setup 0.1.0.exe` (NSIS installer, bundles the engine)

## Release & auto-update (GitHub Releases)

The app auto-updates from GitHub Releases of `yogesh968/jarvis-windows` (see `app/package.json` → `build.publish`).

```powershell
cd app
$env:GH_TOKEN = "<a GitHub token with repo scope>"
npx electron-builder --win nsis --publish always
```

Bump `version` in `app/package.json` for each release. Users get the update on next launch.

## Troubleshooting

| Problem | Fix |
|---|---|
| Orb says engine error | check `%APPDATA%\Jarvis\logs\engine.log`; re-run `setup.ps1` |
| "Hey Jarvis" doesn't trigger | Settings → lower *wake word threshold* (e.g. 0.35); check the right mic is default in Windows Sound settings |
| Triggers randomly | raise the threshold (0.6–0.7) |
| Voice sounds robotic | add ElevenLabs key + Hindi voice ID; keep *Hindi writing style* = Devanagari |
| Groq 429 errors | free-tier rate limit — Jarvis falls back to the fast model automatically; wait a minute |
| Jarvis interrupts itself while talking | Settings → Listening → turn off *Interrupt with “Hey Jarvis”* (or use headphones) |
| It keeps listening after answering | that's *Continuous conversation* — just stay quiet for 5 s, or turn it off in Settings → Listening |
| Brightness doesn't change | external monitors need DDC/CI enabled in the monitor menu |
| Browser tools fail | install Microsoft Edge or run `engine\.venv\Scripts\python -m playwright install chromium` |
