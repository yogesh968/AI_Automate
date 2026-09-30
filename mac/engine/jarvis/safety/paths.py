"""Path helpers: friendly names -> real macOS folders, and protected-path checks."""

from __future__ import annotations

import os
from pathlib import Path

from ..context import ctx

_ALIASES = {
    "desktop": "Desktop", "डेस्कटॉप": "Desktop",
    "documents": "Documents", "document": "Documents", "docs": "Documents",
    "downloads": "Downloads", "download": "Downloads",
    "pictures": "Pictures", "photos": "Pictures", "images": "Pictures",
    "music": "Music", "songs": "Music",
    "videos": "Movies", "video": "Movies", "movies": "Movies",
    "icloud": "Library/Mobile Documents/com~apple~CloudDocs", "icloud drive": "Library/Mobile Documents/com~apple~CloudDocs",
}


def known_folder(key: str) -> Path:
    sub = _ALIASES.get(key.lower(), key.capitalize())
    return Path.home() / sub


def resolve(path: str | None) -> Path:
    """Turn 'downloads/report.pdf', '~/x', '$HOME/y' or a full path into an absolute Path."""
    if not path or not str(path).strip():
        return Path.home()
    raw = os.path.expandvars(str(path).strip().strip('"').strip("'"))
    if raw.startswith("~"):
        return Path(os.path.expanduser(raw)).resolve()
    head, _, rest = raw.partition("/")
    alias = _ALIASES.get(head.lower())
    if alias and not raw.startswith("/"):
        base = Path.home() / alias
        return (base / rest).resolve() if rest else base
    p = Path(raw)
    if not p.is_absolute():
        p = Path.home() / p
    return p.resolve()


def _protected_roots() -> list[Path]:
    home = Path.home()
    return [Path(p) for p in ("/System", "/Library", "/bin", "/sbin", "/usr", "/private", "/etc", "/var",
                              "/Applications", "/cores", "/opt", "/Volumes/Macintosh HD")] + [
        home / "Library" / "Keychains",
        home / "Library" / "Application Support" / "com.apple.TCC",
        home / "Library" / "Mail",
        home / "Library" / "Messages",
        home / ".ssh",
    ]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_protected(path: Path) -> bool:
    path = path.resolve()
    if path == Path("/") or path == Path.home().resolve() or path == Path("/Users"):
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
