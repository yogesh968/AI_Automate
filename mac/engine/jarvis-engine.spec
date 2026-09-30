# PyInstaller spec — builds engine/dist/jarvis-engine/jarvis-engine (one-folder) for the host arch
# (build on an Apple Silicon Mac for arm64, on an Intel Mac for x86_64).
# Run via build.sh (it downloads the wake-word models first so they get bundled).
import platform

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("openwakeword", "onnxruntime", "edge_tts", "playwright", "ddgs", "primp", "certifi",
            "googleapiclient", "keyring", "sounddevice", "_sounddevice_data", "AppKit", "Quartz",
            "ApplicationServices", "Foundation", "objc"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("jarvis")
hiddenimports += ["keyring.backends.macOS", "pyautogui", "pyperclip", "send2trash", "mss", "mss.darwin",
                  "pypdf", "docx", "bs4", "google_auth_oauthlib"]

a = Analysis(
    ["run_engine.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "tflite_runtime"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jarvis-engine",
    # console build so stdout (JARVIS_READY) reaches Electron; it runs headless inside Jarvis.app
    console=True,
    target_arch=platform.machine(),
    codesign_identity=None,  # electron-builder signs everything inside the .app
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="jarvis-engine")
