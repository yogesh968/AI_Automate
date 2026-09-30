# J.A.R.V.I.S.

A personal voice assistant that floats on your screen as a glowing orb, talks in natural Hinglish or English, and controls your computer.

This repo contains two separate apps:

| Folder | Platform | Hosted at |
|---|---|---|
| [`windows/`](windows/README.md) | Windows 10/11 | GitHub Releases of `jarvis-windows` |
| [`mac/`](mac/README.md) | macOS 12+ (Apple Silicon & Intel) | GitHub Releases of `jarvis-macos` |

Both use the same stack: **Electron + React + Three.js** for the orb UI and **Python** for the engine. The engine uses **Groq** for the brain, vision and speech-to-text, **ElevenLabs** (with free Edge voices as fallback) for speech, and **openWakeWord** to hear "Hey Jarvis".

Start with the README in the folder for your OS.
