#!/usr/bin/env bash
# One-time developer setup for JARVIS on macOS.
#   chmod +x setup.sh && ./setup.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cyan() { printf "\033[36m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }

cyan "== JARVIS setup (macOS) =="

# ---------------------------------------------------------------- Homebrew
if ! command -v brew >/dev/null 2>&1; then
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$b" ] && eval "$("$b" shellenv)"
  done
fi
if ! command -v brew >/dev/null 2>&1; then
  yellow "Homebrew not found. Install it first:"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  exit 1
fi

# ---------------------------------------------------------------- Python 3.12 + Node
if ! command -v python3.12 >/dev/null 2>&1; then
  cyan "Installing Python 3.12…"
  brew install python@3.12
fi
PY="$(command -v python3.12)"
if ! command -v node >/dev/null 2>&1; then
  cyan "Installing Node.js…"
  brew install node
fi
# portaudio is bundled in the sounddevice wheel, but keep brew's copy as a fallback
brew list portaudio >/dev/null 2>&1 || brew install portaudio || true

# ---------------------------------------------------------------- optional helpers
cyan "Optional helpers: 'brightness' (exact screen brightness) and 'blueutil' (Bluetooth on/off)"
brew list brightness >/dev/null 2>&1 || brew install brightness || yellow "  couldn't install brightness (Jarvis will use brightness keys instead)"
brew list blueutil >/dev/null 2>&1 || brew install blueutil || yellow "  couldn't install blueutil (Jarvis will open Bluetooth settings instead)"

# ---------------------------------------------------------------- engine venv
cyan "[1/4] Python virtual environment"
cd "$ROOT/engine"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/pip install -r requirements-dev.txt

cyan "[2/4] Wake word models"
.venv/bin/python -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis']); print('ok')"

cyan "[3/4] Browser for automation (used if Google Chrome isn't installed)"
.venv/bin/python -m playwright install chromium

# ---------------------------------------------------------------- app
cyan "[4/4] App dependencies"
cd "$ROOT/app"
npm install
npm run icon

green ""
green "Done! Start JARVIS with:   cd app && npm run dev"
cat <<'EOF'

First run — macOS will ask for permissions. Allow them for Jarvis (in dev mode the
permission is asked for "Electron" / your Terminal — that's expected):

  • Microphone        — "Hey Jarvis" and voice commands
  • Accessibility     — keyboard, mouse, windows, clicking buttons in apps
                        System Settings → Privacy & Security → Accessibility
  • Screen Recording  — "what's on my screen?"
                        System Settings → Privacy & Security → Screen Recording
  • Automation        — asked the first time Jarvis controls Finder, Music, Notes, …

Then click the orb → Settings → paste your Groq and ElevenLabs keys.
EOF
