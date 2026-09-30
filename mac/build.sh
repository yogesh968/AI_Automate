#!/usr/bin/env bash
# Build Jarvis.app + .dmg/.zip for macOS: engine (PyInstaller) + Electron app (electron-builder).
#   ./build.sh            # builds for this Mac's architecture (arm64 on Apple Silicon, x64 on Intel)
#   ./build.sh --publish  # also uploads to GitHub Releases (needs GH_TOKEN) for auto-update
#
# Signing + notarization (optional, needed to share the app without Gatekeeper warnings):
#   export CSC_NAME="Developer ID Application: Your Name (TEAMID)"   # cert in your login keychain
#   export APPLE_ID="you@example.com"
#   export APPLE_APP_SPECIFIC_PASSWORD="abcd-efgh-ijkl-mnop"          # appleid.apple.com → App-Specific Passwords
#   export APPLE_TEAM_ID="TEAMID"
# Without them the app is ad-hoc signed and not notarized (fine for your own Mac).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VPY="$ROOT/engine/.venv/bin/python"
[ -x "$VPY" ] || { echo "Run ./setup.sh first."; exit 1; }

ARCH="$(uname -m)"
case "$ARCH" in
  arm64) EB_ARCH="--arm64" ;;
  x86_64) EB_ARCH="--x64" ;;
  *) echo "unknown arch $ARCH"; exit 1 ;;
esac

echo "[1/3] Icons"
(cd "$ROOT/app" && npm run icon)

echo "[2/3] Engine ($ARCH) -> engine/dist/jarvis-engine/"
cd "$ROOT/engine"
"$VPY" -c "import openwakeword.utils as u; u.download_models(model_names=['hey_jarvis'])"
"$VPY" -m PyInstaller --noconfirm --clean jarvis-engine.spec
[ -x dist/jarvis-engine/jarvis-engine ] || { echo "engine build failed"; exit 1; }

echo "[3/3] App"
cd "$ROOT/app"
npx vite build
EXTRA=()
if [ -n "${APPLE_ID:-}" ] && [ -n "${APPLE_APP_SPECIFIC_PASSWORD:-}" ] && [ -n "${APPLE_TEAM_ID:-}" ]; then
  echo "  notarizing with Apple ID $APPLE_ID"
  EXTRA+=("-c.mac.notarize=true")
else
  echo "  APPLE_ID / APPLE_APP_SPECIFIC_PASSWORD / APPLE_TEAM_ID not set — skipping notarization"
fi
if [ -z "${CSC_NAME:-}" ] && [ -z "${CSC_LINK:-}" ]; then
  echo "  no Developer ID certificate configured — ad-hoc signing"
  export CSC_IDENTITY_AUTO_DISCOVERY=false
  EXTRA+=("-c.mac.identity=-")
fi
if [ "${1:-}" = "--publish" ]; then
  EXTRA+=("--publish" "always")
else
  EXTRA+=("--publish" "never")
fi
npx electron-builder --mac "$EB_ARCH" "${EXTRA[@]}"
echo "Done -> app/release/"
ls -1 "$ROOT/app/release" | grep -E '\.(dmg|zip)$' || true
