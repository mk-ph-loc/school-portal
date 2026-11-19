"""
Lesson Wizard — Γενικός file browser του docs/ (Task 3: APIRouters).

Λίστα φακέλων/αρχείων, επεξεργασία κειμένου (md/css/js/…), upload/mkdir/
delete με αυστηρή επαλήθευση διαδρομών (fs_path — μόνο εντός docs/,
χωρίς κρυφά αρχεία) και .bak πριν από κάθε εγγραφή (state.backup_file).
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from common.lessons import parse_lesson

import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Routes — γενικός file browser του docs/ (μαθήματα, φάκελοι, υλικό)
# ---------------------------------------------------------------------------
def fs_path(rel: str) -> Path:
    """Αυστηρή επαλήθευση: η διαδρομή μένει εντός docs/ (όχι κρυφά αρχεία).

    Δέχεται ΜΟΝΟ σχετικές διαδρομές — απόλυτες (/etc/…) απορρίπτονται, γιατί
    το pathlib θα αγνοούσε το state.DOCS_DIR prefix.
    """
    rel = (rel or "").strip()
    if (rel.startswith("/") or ".." in rel.strip("/").split("/")
            or "\\" in rel or "\x00" in rel):
        raise HTTPException(400, "Μη έγκυρη διαδρομή.")
    rel = rel.strip("/")
    base = state.DOCS_DIR.resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise HTTPException(400, "Μη έγκυρη διαδρομή.")
    for part in p.relative_to(base).parts:
        if part.startswith("."):
            raise HTTPException(403, "Κρυφά αρχεία δεν επιτρέπονται.")
    return p


FS_EDITABLE_EXTS = {".md", ".txt", ".css", ".js", ".json", ".csv", ".html", ".py"}
FS_EDIT_MAX = 2 * 1024 * 1024                        # 2 MB ανά αρχείο κειμένου


@router.get("/api/fs/list")
def api_fs_list(request: Request, path: str = ""):
    state.require_teacher(request)
    d = fs_path(path)
    if not d.is_dir():
        raise HTTPException(404, "Ο φάκελος δεν βρέθηκε.")
    dirs, files = [], []
    for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if p.name.startswith("."):
            continue
        if p.is_dir():
            dirs.append({"name": p.name,
                         "children": sum(1 for c in p.iterdir() if not c.name.startswith("."))})
        elif p.is_file():
            st = p.stat()
            files.append({"name": p.name, "size": st.st_size,
                          "mtime": int(st.st_mtime),
                          "editable": p.suffix.lower() in FS_EDITABLE_EXTS and st.st_size <= FS_EDIT_MAX})
    rel = d.relative_to(state.DOCS_DIR.resolve()).as_posix()
    rel = "" if rel == "." else rel
    # Αν ο φάκελος είναι ημερήσιο μάθημα (index.md με φάσεις) → άνοιγμα στον visual editor
    lesson_key = None
    idx = d / "index.md"
    parts = PurePosixPath(rel).parts
    if len(parts) == 4 and parts[0] == "mathimata" and idx.is_file():
        if parse_lesson(idx.read_text(encoding="utf-8", errors="ignore"))["phases"]:
            lesson_key = "/".join(parts[1:])
    return {"path": rel, "dirs": dirs, "files": files,
            "view_url": f"/docs/{rel}/" if rel else "/docs/",
            "lesson_key": lesson_key}


@router.get("/api/fs/read")
def api_fs_read(request: Request, path: str):
    state.require_teacher(request)
    p = fs_path(path)
    if not p.is_file():
        raise HTTPException(404, "Το αρχείο δεν βρέθηκε.")
    if p.suffix.lower() not in FS_EDITABLE_EXTS:
        raise HTTPException(400, "Ο τύπος αρχείου δεν υποστηρίζει επεξεργασία κειμένου.")
    if p.stat().st_size > FS_EDIT_MAX:
        raise HTTPException(413, "Το αρχείο είναι πολύ μεγάλο για επεξεργασία (>2 MB).")
    return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace"),
            "view_url": "/docs/" + p.relative_to(state.DOCS_DIR.resolve()).as_posix()}


@router.post("/api/fs/save")
async def api_fs_save(request: Request):
    state.require_teacher(request)
    body = await request.json()
    p = fs_path(str(body.get("path", "")))
    if not p.is_file() or p.suffix.lower() not in FS_EDITABLE_EXTS:
        raise HTTPException(400, "Μη επεξεργάσιμο αρχείο.")
    content = str(body.get("content", ""))
    if len(content.encode("utf-8")) > FS_EDIT_MAX:
        raise HTTPException(413, "Πολύ μεγάλο περιεχόμενο (>2 MB).")
    state.backup_file(p)
    p.write_text(content, encoding="utf-8")
    if p.name == "index.md" and "mathimata" in p.parts:
        state.rebuild_nav()
    return {"ok": True}


@router.post("/api/fs/upload")
async def api_fs_upload(request: Request, path: str = "", file: UploadFile = File(...)):
    state.require_teacher(request)
    d = fs_path(path)
    if not d.is_dir():
        raise HTTPException(404, "Ο φάκελος δεν βρέθηκε.")
    name = PurePosixPath(file.filename or "").name
    if not name or name.startswith(".") or not state.NAME_RE.match(name):
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
    ext = PurePosixPath(name).suffix.lower()
    if ext not in state.FS_UPLOAD_EXTS:
        raise HTTPException(400, f"Μη επιτρεπτός τύπος αρχείου ({ext}).")
    content = await file.read()
    if len(content) > state.UPLOAD_MAX:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 40 MB.")
    dest = d / name
    if dest.exists():
        state.backup_file(dest)
    dest.write_bytes(content)
    return {"ok": True, "name": name, "size": len(content)}


@router.post("/api/fs/mkdir")
async def api_fs_mkdir(request: Request):
    state.require_teacher(request)
    body = await request.json()
    parent = fs_path(str(body.get("path", "")))
    name = str(body.get("name", "")).strip()
    if not name or name.startswith(".") or not state.NAME_RE.match(name):
        raise HTTPException(400, "Μη έγκυρο όνομα φακέλου.")
    if not parent.is_dir():
        raise HTTPException(404, "Ο γονικός φάκελος δεν βρέθηκε.")
    target = parent / name
    if target.exists():
        raise HTTPException(409, "Υπάρχει ήδη φάκελος/αρχείο με αυτό το όνομα.")
    target.mkdir()
    return {"ok": True}


@router.delete("/api/fs/delete")
def api_fs_delete(request: Request, path: str):
    state.require_teacher(request)
    p = fs_path(path)
    if p == state.DOCS_DIR.resolve() or not p.is_file():
        raise HTTPException(400, "Επιτρέπεται μόνο διαγραφή αρχείων (όχι φακέλων).")
    state.backup_file(p)
    p.unlink()
    return {"ok": True}
