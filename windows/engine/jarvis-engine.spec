# PyInstaller spec — builds engine\dist\jarvis-engine\jarvis-engine.exe (one-folder).
# Run via build.ps1 (it downloads the wake-word models first so they get bundled).
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("openwakeword", "onnxruntime", "edge_tts", "playwright", "ddgs", "primp", "certifi",
            "pywinauto", "comtypes", "pycaw", "screen_brightness_control", "googleapiclient", "keyring"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("jarvis")
hiddenimports += ["keyring.backends.Windows", "win32timezone", "pyautogui", "pygetwindow", "pyperclip",
                  "send2trash", "mss", "pypdf", "docx", "bs4", "google_auth_oauthlib", "sounddevice"]

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
    # console build so stdout (JARVIS_READY) works; Electron spawns it with windowsHide, so no window shows
    console=True,
    icon="../app/build/icon.ico" if __import__("os").path.exists("../app/build/icon.ico") else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="jarvis-engine")
