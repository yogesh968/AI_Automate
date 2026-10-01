# JARVIS for macOS — UI ⇄ Engine Protocol

> Same protocol as the Windows build; macOS-specific notes are marked 🍎.

The desktop app has two processes:

- **app/** — Electron + React + Three.js. Shows the floating orb and the glass panel, plays audio, owns global shortcuts and the menu-bar icon.
- **engine/** — Python. Brain (Groq LLM), voice (wake word, mic, STT, TTS), memory, safety and all device tools.

Electron spawns the engine and they talk over a local WebSocket.

## Startup

Electron picks a free port and a random token, then spawns:

| Mode | Command |
|---|---|
| Dev (macOS) | `engine/.venv/bin/python3 -m jarvis --port <P> --token <T>` (cwd `engine/`) |
| Packaged | `Jarvis.app/Contents/Resources/engine/jarvis-engine --port <P> --token <T>` |

🍎 The engine is spawned `detached` (its own process group). Electron stops it with SIGTERM to the group, then SIGKILL after 2 s. `PATH` gets `/opt/homebrew/bin:/usr/local/bin` prepended so Homebrew tools (`brightness`, `blueutil`) are found when Jarvis is launched from Finder.

Env passed to the engine: `JARVIS_DATA_DIR` = Electron `app.getPath('userData')` (🍎 `~/Library/Application Support/Jarvis`).

When the server is listening the engine prints exactly one line to stdout:

```
JARVIS_READY <port>
```

The UI connects to `ws://127.0.0.1:<P>/?token=<T>`. The engine closes any connection with a wrong token (code 4401).
If the engine exits, Electron restarts it (max 5 times per minute) and the UI shows "reconnecting".

## Messages

Every message is one JSON object with a `type` field.

### Engine → UI

| type | fields | meaning |
|---|---|---|
| `hello` | `version`, `platform` (`windows`/`macos`), `keys` {`groq`: bool, `elevenlabs`: bool}, `settings` {…} | sent once right after connect |
| `state` | `state`: `idle` \| `listening` \| `thinking` \| `speaking` \| `sleeping` \| `error` | orb state |
| `mic_level` | `level` 0..1 | ~20 Hz while listening, drives the orb |
| `transcript` | `text`, `final` bool | what the user said |
| `assistant_delta` | `id`, `text` | streamed reply chunk |
| `assistant_done` | `id`, `text` | full reply text |
| `tool_start` | `id`, `name`, `args` {…}, `level` (`auto`/`confirm`/`blocked`) | a tool began |
| `tool_end` | `id`, `ok` bool, `summary` string | a tool finished |
| `confirm_request` | `id`, `tool`, `args`, `description` | needs user approval; UI shows Yes/No card |
| `confirm_resolved` | `id`, `approved` bool | approval answered (maybe by voice) — UI removes the card |
| `audio` | `id`, `seq` int, `format` (`mp3`), `data` base64, `text` | one spoken sentence; UI queues and plays in order |
| `audio_end` | `id` | no more audio for this reply |
| `notify` | `title`, `body`, `kind` (`info`/`reminder`/`warning`/`error`/`memory`) | toast in panel + system notification (`memory` = a fact learned automatically; in-app toast only) |
| `interrupt` | — | barge-in: the user said the wake word while Jarvis was talking. UI stops all audio at once |
| `hud` | `open` bool | open/close the full-screen HUD (the `show_hud` / `hide_hud` tools) |
| `system_stats` | `stats` {`cpu`, `cpu_ghz`, `cores`, `ram`, `ram_used_gb`, `ram_total_gb`, `disk`, `disk_free_gb`, `battery` {`percent`, `plugged`, `minutes_left`}\|null, `net_up_kbps`, `net_down_kbps`, `online`, `uptime_s`, `processes`, `top` [{`name`, `cpu`, `mem_mb`}]} | live telemetry, every ~1.5 s while the HUD is open |
| `hud_info` | `weather` {`place`, `now`, `forecast`}\|null, `reminders` [{`text`, `due`, `repeat`}], `memories` int, `tools` int | HUD side data, on open and every 60 s |
| `settings` | `settings` {…} | current settings after a change |
| `keys` | `groq` bool, `elevenlabs` bool | which API keys are saved |
| `audit` | `entries` [{`ts`, `tool`, `args`, `level`, `result`, `ok`}] | answer to `get_audit` |
| `history` | `messages` [{`role`, `text`, `ts`}] | answer to `get_history` |
| `error` | `message` | something failed |

### UI → Engine

| type | fields | meaning |
|---|---|---|
| `text` | `text` | typed message |
| `listen` | — | start one listening turn now (orb click / hotkey) |
| `ptt_start` / `ptt_stop` | — | push-to-talk hold |
| `confirm_response` | `id`, `approved` bool | answer a `confirm_request` |
| `stop` | — | **kill switch**: cancel current task + tools, stop speaking, clear audio |
| `audio_state` | `playing` bool | UI tells engine when playback starts/ends (engine mutes wake word while speaking) |
| `mic_mute` | `muted` bool | mute/unmute the wake word mic |
| `set_keys` | `groq`?, `elevenlabs`? (string, empty string = delete) | save API keys to the OS keychain |
| `update_settings` | `settings` {partial} | change settings |
| `get_audit` | `limit` | request audit log |
| `get_history` | `limit` | request chat history |
| `clear_history` | — | forget the conversation (not long-term memory) |
| `hud_state` | `open` bool | the HUD opened/closed; the engine streams `system_stats` only while it's open |

## Settings (stored in `<JARVIS_DATA_DIR>/settings.json`)

```json
{
  "user_name": "",
  "assistant_name": "Jarvis",
  "llm_model": "openai/gpt-oss-120b",
  "fast_model": "llama-3.1-8b-instant",
  "vision_model": "meta-llama/llama-4-scout-17b-16e-instruct",
  "stt_model": "whisper-large-v3-turbo",
  "tts_provider": "elevenlabs",
  "elevenlabs_voice_id": "",
  "elevenlabs_model": "eleven_multilingual_v2",
  "edge_voice": "hi-IN-MadhurNeural",
  "speak_replies": true,
  "hindi_script": "devanagari",
  "wake_word_enabled": true,
  "wake_word_threshold": 0.5,
  "dry_run": false,
  "allowed_write_dirs": [],
  "confirm_by_voice": true,
  "start_with_system": true,
  "persona": "classic",
  "address_as": "sir",
  "follow_up": true,
  "barge_in": true,
  "startup_greeting": true,
  "proactive_alerts": true,
  "auto_memory": true,
  "sound_effects": true,
  "home_city": ""
}
```

`persona`: `classic` (movie JARVIS — composed, dry wit, calls the user `address_as`) or `desi` (casual Hinglish friend).

`follow_up`: after a spoken reply to a *voice* command, the engine listens again for ~5 s without the wake word (purpose `followup`). Typed messages never start a follow-up.

`barge_in`: while audio plays, the wake word still runs with a stricter threshold (`wake_word_threshold + 0.25`); a hit cancels the turn, sends `interrupt` and starts listening.

`proactive_alerts`: battery 20/10/5 % (once each while discharging), battery full on charger, CPU ≥ 92 % for 90 s, RAM ≥ 93 % for 30 s, system drive ≥ 95 % (every 6 h at most), internet lost (2 failed checks) / back. Alerts are spoken only when Jarvis is idle; otherwise just a toast.

`hindi_script`: `devanagari` (Hindi words written in Devanagari — best pronunciation) or `roman` (Hinglish in English letters).

`allowed_write_dirs` empty = the user's home folder minus protected system paths.

## Secrets

API keys live in the OS keychain via `keyring` (🍎 macOS Keychain), service name `jarvis`, usernames `groq_api_key` and `elevenlabs_api_key`.
Env vars `GROQ_API_KEY` / `ELEVENLABS_API_KEY` (or `engine/.env`) override the keychain for development.

## Global shortcuts (Electron)

Each action tries its keys in order; the first one not taken by another app wins (Settings shows the active ones).

| Action | Keys (first choice → fallbacks) |
|---|---|
| talk now | `⌘⌥Space` → `⌃⌥Space` → `⌘⌥K` |
| **kill switch** (sends `stop`) | `⌘⌥J` → `⌃⌥J` |
| show/hide panel | `⌘⌥P` → `⌃⌥P` |
| hide/show the orb | `⌘⌥H` → `⌃⌥H` |
| HUD mode (full screen) on/off | `⌘⌥U` → `⌃⌥U` |

## 🍎 macOS permissions (Electron IPC, not part of the WebSocket protocol)

The renderer shows a Permissions card using these preload calls: `getPermissions()`, `requestPermission(id)`, `openPermissionPane(id)`, `onPermissions(cb)`.
Ids: `microphone`, `accessibility`, `screen`, `automation`. Status values: `granted`, `denied`, `not-determined`, `restricted`, `ask-on-use` (Automation — macOS asks per controlled app).
The engine runs as a child of Jarvis.app, so these grants cover it. Engine tools raise a readable error naming the missing permission when macOS blocks them.
