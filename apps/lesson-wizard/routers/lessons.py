"""
Lesson Wizard — Μαθήματα & διδακτικές φάσεις (Task 3: APIRouters).

Σελίδα wizard, login/logout, auth_request check του Nginx, λίστα μαθημάτων,
visual editor (get/save φάσεων), tags/⭐ front-matter, νέο μάθημα από
template + αυτόματο nav, upload/delete υλικού στον φάκελο του μαθήματος.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from common.auth import TEACHER_CODE, COOKIE_MAX_AGE
from common.classes import CLASS_GROUPS
from common.lessons import PHASE_TYPES, parse_lesson, render_lesson, fm_meta, set_fm_meta

import state

router = APIRouter()
templates = Jinja2Templates(directory=str(state.BASE_DIR / "templates"))


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/api/check")
def api_check(request: Request):
    """auth_request endpoint του Nginx για τα index.teacher.html (200/401)."""
    if state.token_valid(request.cookies.get(state.COOKIE_NAME)):
        return Response(status_code=200)
    return Response(status_code=401)


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    authed = state.token_valid(request.cookies.get(state.COOKIE_NAME))
    return templates.TemplateResponse(request, "index.html", {
        "authed": authed,
        "classes": CLASS_GROUPS,
        "phase_types": PHASE_TYPES,
    })


@router.post("/api/login")
async def api_login(request: Request, response: Response):
    body = await request.json()
    if str(body.get("code", "")) != TEACHER_CODE:
        raise HTTPException(403, "Λάθος κωδικός καθηγητή.")
    response.set_cookie(state.COOKIE_NAME, state.make_token(), max_age=COOKIE_MAX_AGE,
                        httponly=True, samesite="lax", path="/")
    return {"ok": True}


@router.post("/api/logout")
def api_logout(response: Response):
    response.delete_cookie(state.COOKIE_NAME, path="/")
    return {"ok": True}


NEW_LESSON_TEMPLATE = """---
title: '{title}'
lesson:
  class: {cls}
  subject: {subject}
  unit: ''
  book_pages: ''
  duration: 45
---

# {title}

📖 **Βιβλίο:** [Άνοιγμα στο βιβλίο (PDF)]({book_url}){{target=_blank}}

<!-- phase: aformisi | title: Αφόρμηση | duration: 5 -->
## 🎯 Ας ξεκινήσουμε!

![Εικόνα αφόρμησης](aformisi.png)

Γράψε εδώ 2-3 περιεκτικές προτάσεις που συνδέουν την εικόνα με το θέμα.
<!-- /phase -->

<!-- phase: syzitisi | title: Μικρή Συζήτηση | duration: 6 -->
## 💬 Η γνώμη σας μετράει

!!! question "Συζητάμε σε ζευγάρια και μετά στην τάξη"
    1. Ερώτηση προβληματισμού 1;
    2. Ερώτηση προβληματισμού 2;
<!-- /phase -->

<!-- phase: parousiasi | title: Παρουσίαση | duration: 10 -->
## 📽️ Παρουσίαση

<object data="slides.pdf" type="application/pdf" width="100%" height="480px">
<p>📄 <a href="slides.pdf" target="_blank">Άνοιγμα της παρουσίασης (PDF)</a></p>
</object>
<!-- /phase -->

<!-- phase: drastiriotita | title: Δραστηριότητα | duration: 15 -->
## ✍️ Δραστηριότητα

Οδηγίες ομαδικής/ατομικής εργασίας. **Παραδοτέο:** [📤 Παράδοση Εργασιών](/exams/){{target=_blank}}.
<!-- /phase -->

<!-- phase: aksiologisi | title: Διαμορφωτική Αξιολόγηση | duration: 6 -->
## ✅ Έλεγξε τι έμαθες

<div class="quiz" data-quiz='[
 {{"q":"Ερώτηση;","options":["Επιλογή Α","Επιλογή Β"],"answer":0,"explain":"Επεξήγηση."}}
]'></div>
<!-- /phase -->

<!-- phase: kleisimo | title: Κλείσιμο & Αναστοχασμός | duration: 3 -->
## 🧭 Τι κρατάμε σήμερα

- Κύριο σημείο 1
- Κύριο σημείο 2
<!-- /phase -->

<!-- teacher-notes -->
**Διδακτικοί στόχοι:** …
**Ροή & χρόνοι:** …
**Λύσεις / αναμενόμενες δυσκολίες:** …
<!-- /teacher-notes -->
"""


# ---------------------------------------------------------------------------
# Routes — μαθήματα & φάσεις
# ---------------------------------------------------------------------------
@router.get("/api/lessons")
def api_lessons(request: Request):
    state.require_teacher(request)
    return {"lessons": state.list_all_lessons(), "classes": CLASS_GROUPS,
            "phase_types": PHASE_TYPES}


@router.post("/api/meta/{class_slug}/{subject}/{lesson}")
async def api_set_meta(class_slug: str, subject: str, lesson: str, request: Request):
    """Tags & ⭐ αγαπημένο στο front-matter του μαθήματος (χωρίς αλλαγή φάσεων)."""
    state.require_teacher(request)
    d = state.lesson_dir(class_slug, subject, lesson)
    idx = d / "index.md"
    if not idx.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    body = await request.json()
    text = idx.read_text(encoding="utf-8")
    parsed = parse_lesson(text)
    tags = body.get("tags")
    favorite = body.get("favorite")
    if tags is not None and not isinstance(tags, list):
        raise HTTPException(400, "Μη έγκυρα tags.")
    new_fm = set_fm_meta(parsed["front_matter"], tags,
                         bool(favorite) if favorite is not None else fm_meta(parsed["front_matter"])["favorite"])
    parsed["front_matter"] = new_fm
    state.backup_file(idx)
    idx.write_text(render_lesson(parsed), encoding="utf-8")
    meta = fm_meta(new_fm)
    return {"ok": True, "tags": meta["tags"], "favorite": meta["favorite"]}


@router.get("/api/lesson/{class_slug}/{subject}/{lesson}")
def api_get_lesson(class_slug: str, subject: str, lesson: str, request: Request):
    state.require_teacher(request)
    d = state.lesson_dir(class_slug, subject, lesson)
    idx = d / "index.md"
    if not idx.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    data = parse_lesson(idx.read_text(encoding="utf-8"))
    files = [{"name": p.name, "size": p.stat().st_size}
             for p in sorted(d.iterdir()) if p.is_file() and p.name != "index.md"]
    return {**data, "files": files,
            "url": f"/docs/mathimata/{class_slug}/{subject}/{lesson}/"}


@router.post("/api/lesson/{class_slug}/{subject}/{lesson}")
async def api_save_lesson(class_slug: str, subject: str, lesson: str, request: Request):
    state.require_teacher(request)
    d = state.lesson_dir(class_slug, subject, lesson)
    idx = d / "index.md"
    if not idx.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    body = await request.json()
    phases = body.get("phases", [])
    if not isinstance(phases, list):
        raise HTTPException(400, "Μη έγκυρες φάσεις.")
    for ph in phases:
        if ph.get("type") not in PHASE_TYPES:
            raise HTTPException(400, f"Άγνωστος τύπος φάσης: {ph.get('type')}")
    data = {
        "front_matter": str(body.get("front_matter", "")),
        "header": str(body.get("header", "")),
        "phases": phases,
        "teacher_notes": str(body.get("teacher_notes", "")),
    }
    new_md = render_lesson(data)
    # Στρογγυλοποίηση: parse(render(x)) πρέπει να δίνει ίδιο πλήθος φάσεων
    check = parse_lesson(new_md)
    if len(check["phases"]) != len(phases):
        raise HTTPException(400, "Σφάλμα μορφής: κάποια φάση περιέχει markers που μπερδεύουν τη δομή.")
    state.backup_file(idx)
    idx.write_text(new_md, encoding="utf-8")
    state.rebuild_nav()
    return {"ok": True, "phases": len(phases),
            "duration": sum(int(p.get("duration") or 0) for p in phases)}
@router.post("/api/lesson-new")
async def api_new_lesson(request: Request):
    state.require_teacher(request)
    body = await request.json()
    cls = str(body.get("class_slug", "")).strip()
    subject = str(body.get("subject", "")).strip()
    slug = str(body.get("lesson", "")).strip()
    title = str(body.get("title", "")).strip() or slug
    book_url = str(body.get("book_url", "")).strip() or "#"
    d = state.lesson_dir(cls, subject, slug)
    if (d / "index.md").exists():
        raise HTTPException(409, "Υπάρχει ήδη μάθημα με αυτό το όνομα.")
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(
        NEW_LESSON_TEMPLATE.format(title=title, cls=cls, subject=subject, book_url=book_url),
        encoding="utf-8")
    state.rebuild_nav()
    return {"ok": True, "url": f"/docs/mathimata/{cls}/{subject}/{slug}/"}


@router.post("/api/upload/{class_slug}/{subject}/{lesson}")
async def api_upload(class_slug: str, subject: str, lesson: str, request: Request,
                     file: UploadFile = File(...)):
    state.require_teacher(request)
    d = state.lesson_dir(class_slug, subject, lesson)
    if not (d / "index.md").is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    name = PurePosixPath(file.filename or "").name
    if not name or name.startswith(".") or name == "index.md":
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
    ext = PurePosixPath(name).suffix.lower()
    if ext not in state.UPLOAD_EXTS:
        raise HTTPException(400, f"Μη επιτρεπτός τύπος αρχείου ({ext}).")
    content = await file.read()
    if len(content) > state.UPLOAD_MAX:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 40 MB.")
    dest = d / name
    if dest.exists():
        state.backup_file(dest)
    dest.write_bytes(content)
    return {"ok": True, "name": name, "size": len(content)}


@router.delete("/api/file/{class_slug}/{subject}/{lesson}/{filename}")
def api_delete_file(class_slug: str, subject: str, lesson: str, filename: str, request: Request):
    state.require_teacher(request)
    d = state.lesson_dir(class_slug, subject, lesson)
    name = PurePosixPath(filename).name
    if name in ("index.md", "") or name.startswith("."):
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
    target = d / name
    if not target.is_file():
        raise HTTPException(404, "Το αρχείο δεν βρέθηκε.")
    state.backup_file(target)
    target.unlink()
    return {"ok": True}
