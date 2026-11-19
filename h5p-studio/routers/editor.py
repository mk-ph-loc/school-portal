"""
H5P Studio — Editor & Βιβλιοθήκη δραστηριοτήτων (Task 3: APIRouters).

Σελίδες index/edit, login/logout καθηγητή, CRUD δραστηριοτήτων, ζωντανή
προεπισκόπηση (preview-tmp) και ανέβασμα/επιλογή media (εικόνες/βίντεο).
Το κοινό state ζει στο state.py· η δομή H5P χτίζεται στο content.py.
"""
from __future__ import annotations

import hmac
import io
import json
import re
import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from common.auth import TEACHER_CODE, COOKIE_MAX_AGE
from common.classes import CLASS_GROUPS, CLASS_LABELS

import state
import store
import content

router = APIRouter()
templates = Jinja2Templates(directory=str(state.BASE_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "logged_in": state.token_valid(request.cookies.get(state.COOKIE_NAME)),
        "classes": CLASS_GROUPS, "subjects": state.SUBJECTS,
        "type_labels": state.TYPE_LABELS, "type_icons": state.TYPE_ICONS,
    })


@router.get("/edit/{aid}", response_class=HTMLResponse)
def edit_page(request: Request, aid: str):
    if not state.token_valid(request.cookies.get(state.COOKIE_NAME)):
        return templates.TemplateResponse(request, "index.html", {
            "logged_in": False, "classes": CLASS_GROUPS, "subjects": state.SUBJECTS,
            "type_labels": state.TYPE_LABELS, "type_icons": state.TYPE_ICONS,
            "login_hint": "Συνδέσου με τον κωδικό καθηγητή για επεξεργασία.",
        })
    if aid == "new":
        # Νέα δραστηριότητα από draft (AI wizard / hotspots / video) —
        # τα δεδομένα έρχονται από το sessionStorage του browser.
        title, atype = "Νέα Δραστηριότητα", ""
    else:
        row = content.get_activity_row(aid)
        title, atype = row["title"], row["type"]
    return templates.TemplateResponse(request, "editor.html", {
        "activity_id": aid, "title": title, "atype": atype,
        "classes": CLASS_GROUPS, "subjects": state.SUBJECTS,
        "type_labels": state.TYPE_LABELS,
    })


class Login(BaseModel):
    password: str


@router.post("/api/login")
def login(body: Login, response: Response):
    # Σύγκριση σε bytes ώστε να λειτουργεί και με μη-ASCII (ελληνικούς) κωδικούς
    if not hmac.compare_digest(body.password.encode("utf-8"), TEACHER_CODE.encode("utf-8")):
        raise HTTPException(401, "Λάθος κωδικός καθηγητή.")
    response.set_cookie(state.COOKIE_NAME, state.make_token(), max_age=COOKIE_MAX_AGE,
                        httponly=True, samesite="lax", path="/")
    return {"ok": True}


@router.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(state.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/api/activities")
def api_activities(request: Request, class_slug: str = "", subject: str = ""):
    sql = "SELECT * FROM activities WHERE 1=1"
    args: list = []
    if class_slug:
        sql += " AND class_slug=?"
        args.append(class_slug)
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    sql += " ORDER BY updated_at DESC"
    with store.db() as conn:
        rows = conn.execute(sql, args).fetchall()
    teacher = state.token_valid(request.cookies.get(state.COOKIE_NAME))
    out = []
    for r in rows:
        d = dict(r)
        d["type_label"] = state.TYPE_LABELS.get(r["type"], r["type"])
        d["type_icon"] = state.TYPE_ICONS.get(r["type"], "📦")
        d["class_label"] = CLASS_LABELS.get(r["class_slug"], "")
        d["editable"] = teacher and r["type"] != "external"
        out.append(d)
    return {"activities": out, "teacher": teacher}


class CreateActivity(BaseModel):
    type: str
    title: str = Field(min_length=1, max_length=200)
    class_slug: str = ""
    subject: str = ""
    chapter: str = ""
    goal: str = ""
    difficulty: str = ""
    data: dict = Field(default_factory=dict)


@router.post("/api/activities")
def api_create(request: Request, body: CreateActivity):
    state.require_teacher(request)
    if body.type not in state.TYPE_LIBS:
        raise HTTPException(400, "Άγνωστος τύπος δραστηριότητας.")
    aid = content.new_activity_id()
    data = dict(body.data)
    data["type"] = body.type
    data.setdefault("title", body.title)
    # Νέα δραστηριότητα από τον editor: τα media ανέβηκαν στο preview-tmp/ —
    # μεταφέρονται στον μόνιμο φάκελο πριν το χτίσιμο του content.json.
    content.transfer_preview_media(aid, data)
    atype, params, extra = content.build_content(data)
    main_folder = state.TYPE_LIBS[atype]
    content.save_activity_files(aid, body.title, main_folder, params, extra)
    content.save_editor_state(aid, data)
    lj = content.lib_json(main_folder)
    content.upsert_activity(aid, body.title, atype,
                    f"{lj['machineName']} {lj['majorVersion']}.{lj['minorVersion']}",
                    body.model_dump())
    return {"ok": True, "id": aid}


@router.get("/api/activities/{aid}")
def api_get_activity(request: Request, aid: str):
    state.require_teacher(request)
    if aid == state.PREVIEW_ID:
        raise HTTPException(400, "Χρησιμοποίησε το /api/preview.")
    row = content.get_activity_row(aid)
    state = content.read_editor_state(aid)
    if state is None:
        cpath = content.activity_dir(aid) / "content" / "content.json"
        params = json.loads(cpath.read_text(encoding="utf-8"))
        state = content.editor_state_from_content(row["type"], params, row["title"])
    return {"meta": dict(row), "data": state}


class UpdateActivity(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    class_slug: str = ""
    subject: str = ""
    chapter: str = ""
    goal: str = ""
    difficulty: str = ""
    data: dict


@router.put("/api/activities/{aid}")
def api_update(request: Request, aid: str, body: UpdateActivity):
    state.require_teacher(request)
    row = content.get_activity_row(aid)
    if row["type"] == "external":
        raise HTTPException(400, "Τα εξωτερικά .h5p δεν επεξεργάζονται στον Visual Editor "
                                 "(μόνο αναπαραγωγή/export).")
    data = dict(body.data)
    data["type"] = row["type"]
    data.setdefault("title", body.title)
    atype, params, extra = content.build_content(data)
    content.save_activity_files(aid, body.title, state.TYPE_LIBS[atype], params, extra)
    content.save_editor_state(aid, data)
    content.upsert_activity(aid, body.title, atype, row["main_lib"], body.model_dump())
    return {"ok": True, "id": aid}


@router.delete("/api/activities/{aid}")
def api_delete(request: Request, aid: str):
    state.require_teacher(request)
    if aid == state.PREVIEW_ID:
        raise HTTPException(400, "Δεν διαγράφεται η προσωρινή προεπισκόπηση.")
    content.get_activity_row(aid)
    adir = content.activity_dir(aid)
    shutil.rmtree(adir, ignore_errors=True)
    with store.db() as conn:
        conn.execute("DELETE FROM activities WHERE id=?", (aid,))
    return {"ok": True}


# ---------------------------------------------------------------------------
# API — Preview (προσωρινή δραστηριότητα για ζωντανή προεπισκόπηση editor)
# ---------------------------------------------------------------------------
@router.post("/api/preview")
def api_preview(request: Request, body: dict):
    """Χτίζει content.json σε library/preview-tmp/ για το iframe προεπισκόπησης.
    Τα media πρέπει να έχουν ανέβει ήδη μέσω /api/upload (στο ίδιο tmp folder)."""
    state.require_teacher(request)
    data = dict(body.get("data") or {})
    title = body.get("title") or "Προεπισκόπηση"
    atype, params, extra = content.build_content(data)
    content.save_activity_files(state.PREVIEW_ID, title, state.TYPE_LIBS[atype], params, extra)
    return {"ok": True, "id": state.PREVIEW_ID}


# ---------------------------------------------------------------------------
# API — Ανέβασμα media (εικόνες/βίντεο) σε δραστηριότητα ή στο preview-tmp
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}
VIDEO_EXTS = {".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg"}


@router.post("/api/upload/{aid}")
async def api_upload(request: Request, aid: str, file: UploadFile = File(...)):
    state.require_teacher(request)
    if aid != state.PREVIEW_ID:
        content.get_activity_row(aid)
    name = Path(file.filename or "file").name
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTS:
        subdir, mime = "images", IMAGE_EXTS[ext]
    elif ext in VIDEO_EXTS:
        subdir, mime = "videos", VIDEO_EXTS[ext]
    else:
        raise HTTPException(400, "Επιτρέπονται μόνο εικόνες (png/jpg/gif/svg/webp) "
                                 "και βίντεο (mp4/webm/ogv).")
    raw = await file.read(state.MAX_UPLOAD_BYTES + 1)
    if len(raw) > state.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 100 MB.")
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", Path(name).stem)[:40] or "media"
    rel = f"{subdir}/{safe}-{secrets.token_hex(4)}{ext}"
    dest = content.activity_dir(aid) / "content" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    result = {"ok": True, "path": rel, "mime": mime}
    if ext in IMAGE_EXTS and ext != ".svg":
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                result["width"], result["height"] = im.size
        except Exception:
            pass
    return result


@router.get("/api/videos")
def api_videos(request: Request):
    """Λίστα υπαρχόντων βίντεο στα docs/assets/videos/ & docs/videos/ του MkDocs."""
    state.require_teacher(request)
    out = []
    for vdir in state.VIDEOS_DIRS:
        if vdir.is_dir():
            for p in sorted(vdir.rglob("*")):
                if p.suffix.lower() in VIDEO_EXTS and p.is_file():
                    rel = p.relative_to(state.DOCS_DIR).as_posix()
                    out.append({"path": rel, "name": p.name,
                                "size_mb": round(p.stat().st_size / 1048576, 1),
                                "docs_url": "/docs/" + rel})
    return {"videos": out}


class PickVideo(BaseModel):
    docs_path: str


@router.post("/api/pick-video/{aid}")
def api_pick_video(request: Request, aid: str, body: PickVideo):
    """Αντιγραφή υπάρχοντος βίντεο από τα docs/ στη δραστηριότητα (offline player)."""
    state.require_teacher(request)
    if aid != state.PREVIEW_ID:
        content.get_activity_row(aid)
    rel = body.docs_path.strip().lstrip("/")
    src = (state.DOCS_DIR / rel).resolve()
    if (not str(src).startswith(str(state.DOCS_DIR.resolve()) + "/")
            or src.suffix.lower() not in VIDEO_EXTS or not src.is_file()):
        raise HTTPException(400, "Μη έγκυρη διαδρομή βίντεο.")
    dest_rel = f"videos/{src.stem[:40]}-{secrets.token_hex(4)}{src.suffix.lower()}"
    dest = content.activity_dir(aid) / "content" / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {"ok": True, "path": dest_rel,
            "mime": VIDEO_EXTS[src.suffix.lower()]}
