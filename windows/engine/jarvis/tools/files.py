"""File and folder tools. Deletes go to the Recycle Bin; changes outside allowed folders are refused."""

from __future__ import annotations

import datetime as dt
import os
import shutil
from pathlib import Path

from ..safety.paths import resolve, write_allowed
from ._win import clip
from .base import AUTO, BLOCKED, CONFIRM, B, I, S, tool

CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".ico", ".tiff"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".flv", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".xls", ".xlsx", ".csv",
                  ".ppt", ".pptx", ".odp", ".ods", ".epub"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"},
    "Installers": {".exe", ".msi", ".msix", ".appx", ".bat", ".cmd"},
    "Code": {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".java", ".c", ".cpp", ".cs",
             ".go", ".rs", ".php", ".rb", ".sh", ".ps1", ".ipynb", ".sql", ".yml", ".yaml", ".xml"},
}


def _check_write(*paths: Path) -> None:
    for p in paths:
        ok, why = write_allowed(p)
        if not ok:
            raise PermissionError(why)


def _write_level(*keys: str, base: str = CONFIRM):
    """Level function: BLOCKED if any path arg is not writable, else `base`."""

    def level(args):
        for k in keys:
            if args.get(k):
                ok, why = write_allowed(resolve(args[k]))
                if not ok:
                    raise PermissionError(why)
        return base

    return level


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


@tool("list_folder", "List what's inside a folder. Accepts names like 'downloads', 'desktop', 'documents/projects'.",
      {"path": S("folder path or name"), "show_hidden": B("include hidden files")}, ["path"])
def list_folder(path: str, show_hidden: bool = False):
    p = resolve(path)
    if not p.is_dir():
        return f"not a folder: {p}"
    items = []
    for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        if not show_hidden and entry.name.startswith("."):
            continue
        try:
            st = entry.stat()
            items.append({"name": entry.name + ("/" if entry.is_dir() else ""),
                          "size": "" if entry.is_dir() else _human(st.st_size),
                          "modified": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
        except OSError:
            continue
        if len(items) >= 200:
            break
    return {"folder": str(p), "count": len(items), "items": items}


@tool("search_files", "Find files/folders by name (and optionally extension) under a folder, newest first.",
      {"query": S("part of the file name (can be empty)"), "folder": S("where to search, default home"),
       "extension": S("optional like '.pdf'"), "max_results": I("default 30")})
def search_files(query: str = "", folder: str = "", extension: str = "", max_results: int = 30):
    root = resolve(folder or "~")
    q = query.lower().strip()
    ext = extension.lower().strip()
    if ext and not ext.startswith("."):
        ext = "." + ext
    skip = {"node_modules", ".git", "AppData", "$Recycle.Bin", ".venv", "__pycache__", "Windows"}
    found = []
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for name in filenames + dirnames:
            scanned += 1
            low = name.lower()
            if (not q or q in low) and (not ext or low.endswith(ext)):
                full = Path(dirpath, name)
                try:
                    found.append((full.stat().st_mtime, full))
                except OSError:
                    pass
        if scanned > 300_000:
            break
    found.sort(reverse=True)
    return [str(p) for _, p in found[: max(1, min(int(max_results), 200))]] or "nothing found"


@tool("read_file", "Read a text/code/PDF/Word file so you can answer questions or summarize it.",
      {"path": S("file path"), "max_chars": I("default 15000")}, ["path"])
def read_file(path: str, max_chars: int = 15000):
    p = resolve(path)
    if not p.is_file():
        return f"file not found: {p}"
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:60])
    elif suffix == ".docx":
        import docx

        text = "\n".join(par.text for par in docx.Document(str(p)).paragraphs)
    else:
        if p.stat().st_size > 20 * 2**20:
            return "file is too large to read (over 20MB)"
        text = p.read_text(encoding="utf-8", errors="replace")
    return clip(text, int(max_chars))


@tool("file_info", "Size, dates and type of a file or folder.", {"path": S("path")}, ["path"])
def file_info(path: str):
    p = resolve(path)
    if not p.exists():
        return f"not found: {p}"
    st = p.stat()
    size = st.st_size
    if p.is_dir():
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return {"path": str(p), "type": "folder" if p.is_dir() else (p.suffix or "file"), "size": _human(size),
            "created": dt.datetime.fromtimestamp(st.st_ctime).isoformat(timespec="minutes"),
            "modified": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")}


@tool("open_path", "Open a file with its default app, or open a folder in File Explorer.",
      {"path": S("file or folder")}, ["path"])
def open_path(path: str):
    p = resolve(path)
    if not p.exists():
        return f"not found: {p}"
    os.startfile(str(p))
    return f"opened {p}"


def _write_file_level(args):
    p = resolve(args.get("path", ""))
    ok, why = write_allowed(p)
    if not ok:
        raise PermissionError(why)
    return CONFIRM if p.exists() else AUTO


@tool("write_file", "Create a new text file, or overwrite/append to an existing one.",
      {"path": S("file path"), "content": S("text to write"), "append": B("append instead of overwrite")},
      ["path", "content"], level=_write_file_level,
      describe=lambda a: f"{'Append to' if a.get('append') else 'Overwrite'} {resolve(a.get('path', ''))}")
def write_file(path: str, content: str, append: bool = False):
    p = resolve(path)
    _check_write(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if append else "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"wrote {len(content)} characters to {p}"


@tool("create_folder", "Create a folder (and parents).", {"path": S("folder path")}, ["path"],
      level=_write_level("path", base=AUTO))
def create_folder(path: str):
    p = resolve(path)
    _check_write(p)
    p.mkdir(parents=True, exist_ok=True)
    return f"created {p}"


@tool("move_path", "Move or rename a file/folder.", {"source": S("from"), "destination": S("to (folder or new name)")},
      ["source", "destination"], level=_write_level("source", "destination"),
      describe=lambda a: f"Move {resolve(a.get('source', ''))} → {resolve(a.get('destination', ''))}")
def move_path(source: str, destination: str):
    src, dst = resolve(source), resolve(destination)
    _check_write(src, dst)
    if not src.exists():
        return f"not found: {src}"
    if dst.is_dir():
        dst = dst / src.name
    if dst.exists():
        return f"destination already exists: {dst}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"moved to {dst}"


def _copy_level(args):
    dst = resolve(args.get("destination", ""))
    ok, why = write_allowed(dst)
    if not ok:
        raise PermissionError(why)
    src = resolve(args.get("source", ""))
    target = dst / src.name if dst.is_dir() else dst
    return CONFIRM if target.exists() else AUTO


@tool("copy_path", "Copy a file or folder.", {"source": S("from"), "destination": S("to (folder or new name)")},
      ["source", "destination"], level=_copy_level,
      describe=lambda a: f"Copy {a.get('source')} → {a.get('destination')} (will overwrite)")
def copy_path(source: str, destination: str):
    src, dst = resolve(source), resolve(destination)
    _check_write(dst)
    if not src.exists():
        return f"not found: {src}"
    if dst.is_dir():
        dst = dst / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return f"copied to {dst}"


@tool("delete_path", "Delete files/folders (they go to the Recycle Bin, so they can be restored).",
      {"paths": {"type": "array", "items": {"type": "string"}, "description": "paths to delete"}}, ["paths"],
      level=lambda a: _delete_level(a),
      describe=lambda a: "Move to Recycle Bin: " + ", ".join(str(resolve(p)) for p in a.get("paths", [])[:8]))
def delete_path(paths: list[str]):
    from send2trash import send2trash

    done = []
    for raw in paths:
        p = resolve(raw)
        _check_write(p)
        if p.exists():
            send2trash(str(p))
            done.append(p.name)
    return f"moved {len(done)} item(s) to the Recycle Bin: {', '.join(done)}" if done else "nothing to delete"


def _delete_level(args):
    for raw in args.get("paths", []):
        ok, why = write_allowed(resolve(raw))
        if not ok:
            raise PermissionError(why)
    return CONFIRM


def _plan_organize(folder: Path) -> dict[str, list[str]]:
    plan: dict[str, list[str]] = {}
    for entry in folder.iterdir():
        if entry.is_file() and not entry.name.startswith(".") and not entry.name.endswith((".crdownload", ".part", ".tmp")):
            cat = next((c for c, exts in CATEGORIES.items() if entry.suffix.lower() in exts), "Others")
            plan.setdefault(cat, []).append(entry.name)
    return plan


def _organize_describe(args):
    folder = resolve(args.get("path", "downloads"))
    plan = _plan_organize(folder) if folder.is_dir() else {}
    parts = [f"{cat}: {len(files)}" for cat, files in plan.items()]
    return f"Sort {sum(len(f) for f in plan.values())} files in {folder} into folders ({', '.join(parts)})"


@tool("organize_folder", "Tidy a folder by moving files into sub-folders by type (Images, Videos, Documents, "
      "Audio, Archives, Installers, Code, Others). Use preview=true to only show the plan.",
      {"path": S("folder, e.g. 'downloads' or 'desktop'"), "preview": B("only show what would happen")},
      ["path"],
      level=lambda a: AUTO if a.get("preview") else _write_level("path")(a),
      describe=_organize_describe)
def organize_folder(path: str, preview: bool = False):
    folder = resolve(path)
    if not folder.is_dir():
        return f"not a folder: {folder}"
    plan = _plan_organize(folder)
    if preview:
        return {cat: {"count": len(files), "examples": files[:5]} for cat, files in plan.items()} or "already tidy"
    _check_write(folder)
    moved = 0
    for cat, files in plan.items():
        target = folder / cat
        target.mkdir(exist_ok=True)
        for name in files:
            src = folder / name
            dst = target / name
            stem, suffix, n = dst.stem, dst.suffix, 1
            while dst.exists():
                dst = target / f"{stem} ({n}){suffix}"
                n += 1
            try:
                shutil.move(str(src), str(dst))
                moved += 1
            except OSError:
                continue
    return f"moved {moved} files into {len(plan)} folders"


@tool("folder_size", "Show how much space a folder uses and its biggest items.",
      {"path": S("folder"), "top": I("how many biggest items, default 10")}, ["path"])
def folder_size(path: str, top: int = 10):
    root = resolve(path)
    if not root.is_dir():
        return f"not a folder: {root}"
    sizes: dict[str, int] = {}
    total = 0
    for child in root.iterdir():
        try:
            if child.is_file():
                s = child.stat().st_size
            else:
                s = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
        except OSError:
            continue
        sizes[child.name] = s
        total += s
    biggest = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[: max(1, int(top))]
    return {"folder": str(root), "total": _human(total), "biggest": [{n: _human(s)} for n, s in biggest]}
