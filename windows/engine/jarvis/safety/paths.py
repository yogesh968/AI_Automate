"""Path helpers: friendly names -> real Windows folders, and protected-path checks."""

from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path

from ..context import ctx

# Windows Known Folder IDs (handles OneDrive-redirected Desktop/Documents etc.)
_KNOWN = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}

_ALIASES = {
    "desktop": "desktop", "डेस्कटॉप": "desktop",
    "documents": "documents", "document": "documents", "docs": "documents",
    "downloads": "downloads", "download": "downloads",
    "pictures": "pictures", "photos": "pictures", "images": "pictures",
    "music": "music", "songs": "music",
    "videos": "videos", "video": "videos",
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


@lru_cache(maxsize=None)
def known_folder(key: str) -> Path:
    fallback = Path.home() / key.capitalize()
    guid_str = _KNOWN.get(key)
    if not guid_str:
        return fallback
    try:
        u = uuid.UUID(guid_str)
        guid = _GUID.from_buffer_copy(u.bytes_le)
        out = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
        if res == 0 and out.value:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return fallback


def resolve(path: str | None) -> Path:
    """Turn 'downloads/report.pdf', '~/x', '%USERPROFILE%\\y' or a full path into an absolute Path."""
    if not path or not str(path).strip():
        return Path.home()
    raw = os.path.expandvars(str(path).strip().strip('"'))
    raw = raw.replace("/", os.sep)
    if raw.startswith("~"):
        return Path(os.path.expanduser(raw)).resolve()
    head, _, rest = raw.partition(os.sep)
    alias = _ALIASES.get(head.lower())
    if alias:
        base = known_folder(alias)
        return (base / rest).resolve() if rest else base
    p = Path(raw)
    if not p.is_absolute():
        p = Path.home() / p
    return p.resolve()


def _protected_roots() -> list[Path]:
    roots = []
    for var in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramData", "ProgramW6432"):
        val = os.environ.get(var)
        if val:
            roots.append(Path(val).resolve())
    sysdrive = os.environ.get("SystemDrive", "C:") + os.sep
    roots += [Path(sysdrive, "$Recycle.Bin"), Path(sysdrive, "System Volume Information"),
              Path(sysdrive, "Recovery"), Path(sysdrive, "Boot")]
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata, "Microsoft", "Credentials"))
        roots.append(Path(appdata, "Microsoft", "Protect"))
    return roots


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_protected(path: Path) -> bool:
    path = path.resolve()
    if path.parent == path:  # a drive root like C:\
        return True
    if path == Path.home().resolve():
        return True
    return any(_is_under(path, r) for r in _protected_roots())


def write_allowed(path: Path) -> tuple[bool, str]:
    """May Jarvis create/change/delete things at this path?"""
    path = path.resolve()
    if is_protected(path):
        return False, f"{path} is a protected system location"
    allowed = [resolve(p) for p in (ctx.settings.get("allowed_write_dirs") or [])]
    if not allowed:
        allowed = [Path.home().resolve()]
    if any(_is_under(path, a) for a in allowed):
        return True, ""
    return False, f"{path} is outside the folders Jarvis may change (Settings → allowed folders)"
