"""
H5P Studio — Αναπαραγωγή & Import/Export .h5p (Task 3: APIRouters).

Σελίδες play (ανοιχτές στους μαθητές, embed=1 για iframe) + preview,
import επίσημων πακέτων .h5p (Lumi/Φωτόδεντρο/h5p.org) με επικύρωση δομής
και export με ΟΛΕΣ τις απαιτούμενες βιβλιοθήκες μέσα (όπως του Lumi).
"""
from __future__ import annotations

import io
import json
import re
import secrets
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

import state
import content

router = APIRouter()
templates = Jinja2Templates(directory=str(state.BASE_DIR / "templates"))


@router.get("/play/preview-tmp/", response_class=HTMLResponse)
def preview_page(request: Request):
    """Προσωρινή προεπισκόπηση του Visual Editor — μόνο για καθηγητή."""
    state.require_teacher(request)
    if not (content.activity_dir(state.PREVIEW_ID) / "h5p.json").is_file():
        raise HTTPException(404, "Δεν υπάρχει προεπισκόπηση ακόμη.")
    return templates.TemplateResponse(request, "play.html", {
        "activity_id": state.PREVIEW_ID, "title": "Προεπισκόπηση", "embed": True,
        "type_label": "Προεπισκόπηση",
    })


@router.get("/play/{aid}/", response_class=HTMLResponse)
def play_page(request: Request, aid: str):
    row = content.get_activity_row(aid)
    adir = content.activity_dir(aid)
    if not (adir / "h5p.json").is_file():
        raise HTTPException(404, "Η δραστηριότητα δεν βρέθηκε στο δίσκο.")
    # embed=1 → καθαρή σελίδα για <iframe> (χωρίς μπάρα επιστροφής)
    embed = request.query_params.get("embed") == "1"
    return templates.TemplateResponse(request, "play.html", {
        "activity_id": aid, "title": row["title"], "embed": embed,
        "type_label": state.TYPE_LABELS.get(row["type"], row["type"]),
    })


def validate_h5p_zip(zf: zipfile.ZipFile) -> dict:
    """Επικύρωση δομής: h5p.json + content/content.json + βιβλιοθήκες."""
    names = zf.namelist()
    if any(n.startswith("/") or ".." in PurePosixPath(n).parts for n in names):
        raise HTTPException(400, "Μη ασφαλές αρχείο .h5p (path traversal).")
    if "h5p.json" not in names:
        raise HTTPException(400, "Μη έγκυρο .h5p: λείπει το h5p.json στη ρίζα.")
    try:
        h5pj = json.loads(zf.read("h5p.json").decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Μη έγκυρο h5p.json (σφάλμα JSON).")
    main = h5pj.get("mainLibrary", "")
    deps = h5pj.get("preloadedDependencies", [])
    if not main or not isinstance(deps, list) or not deps:
        raise HTTPException(400, "Μη έγκυρο h5p.json: λείπει mainLibrary/preloadedDependencies.")
    if not any(d.get("machineName") == main for d in deps):
        raise HTTPException(400, "Η κύρια βιβλιοθήκη δεν υπάρχει στα preloadedDependencies.")
    if "content/content.json" not in names:
        raise HTTPException(400, "Μη έγκυρο .h5p: λείπει το content/content.json.")
    try:
        json.loads(zf.read("content/content.json").decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Μη έγκυρο content/content.json (σφάλμα JSON).")
    # Κάθε preloaded βιβλιοθήκη πρέπει να υπάρχει είτε στο πακέτο είτε τοπικά
    local = {d.name for d in state.H5P_LIBS_DIR.iterdir() if d.is_dir()}
    missing = []
    for d in deps:
        folder = f"{d.get('machineName')}-{d.get('majorVersion')}.{d.get('minorVersion')}"
        if f"{folder}/library.json" not in names and folder not in local:
            missing.append(folder)
    if missing:
        raise HTTPException(400, "Λείπουν βιβλιοθήκες από το πακέτο: "
                                 + ", ".join(missing[:5]))
    return h5pj


@router.post("/api/import")
async def api_import(request: Request, file: UploadFile = File(...),
                     class_slug: str = Form(""), subject: str = Form("")):
    state.require_teacher(request)
    if not (file.filename or "").lower().endswith(".h5p"):
        raise HTTPException(400, "Επίλεξε αρχείο με κατάληξη .h5p")
    raw = await file.read(state.MAX_UPLOAD_BYTES + 1)
    if len(raw) > state.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 100 MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Το αρχείο δεν είναι έγκυρο ZIP/.h5p.")
    with zf:
        h5pj = validate_h5p_zip(zf)
        aid = content.new_activity_id()
        adir = content.activity_dir(aid)
        adir.mkdir(parents=True, exist_ok=True)
        try:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = (adir / info.filename).resolve()
                if not str(target).startswith(str(adir.resolve()) + "/"):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
        except Exception:
            shutil.rmtree(adir, ignore_errors=True)
            raise
    title = h5pj.get("title") or Path(file.filename).stem
    main = h5pj["mainLibrary"]
    dep = next(d for d in h5pj["preloadedDependencies"]
               if d.get("machineName") == main)
    main_lib = f"{main} {dep.get('majorVersion')}.{dep.get('minorVersion')}"
    atype = state.LIB_TYPE.get(main, "external")
    content.upsert_activity(aid, title, atype if atype != "external" else "external",
                    main_lib, {"class_slug": class_slug, "subject": subject})
    return {"ok": True, "id": aid, "title": title, "type": atype,
            "play_url": f"/h5p-studio/play/{aid}/"}


# ---------------------------------------------------------------------------
# API — Export σε επίσημο .h5p (με όλες τις βιβλιοθήκες μέσα, όπως του Lumi)
# ---------------------------------------------------------------------------
@router.get("/api/export/{aid}")
def api_export(request: Request, aid: str):
    row = content.get_activity_row(aid)
    adir = content.activity_dir(aid)
    h5pj = json.loads((adir / "h5p.json").read_text(encoding="utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) Περιεχόμενο δραστηριότητας (χωρίς editor-state & τυχόν τοπικές βιβλ.)
        for p in sorted(adir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(adir).as_posix()
            if rel == "content/editor-state.json":
                continue
            if state.LIBDIR_RE.match(rel.split("/")[0]):
                continue                      # οι βιβλιοθήκες μπαίνουν παρακάτω
            zf.write(p, rel)
        # 2) Όλες οι απαιτούμενες βιβλιοθήκες (από το πακέτο ή τα τοπικά assets)
        added: set[str] = set()
        for dep in h5pj.get("preloadedDependencies", []):
            folder = content.dep_folder(dep)
            src = adir / folder
            if not src.is_dir():
                src = state.H5P_LIBS_DIR / folder
            if not src.is_dir():
                continue
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    arc = f"{folder}/{p.relative_to(src).as_posix()}"
                    if arc not in added:
                        zf.write(p, arc)
                        added.add(arc)
    safe_title = re.sub(r"[^A-Za-z0-9Α-Ωα-ωά-ώ_-]+", "-", row["title"])[:60] or aid
    from starlette.background import BackgroundTask
    tmp = state.BASE_DIR / f".export-{secrets.token_hex(4)}.h5p"
    tmp.write_bytes(buf.getvalue())
    return FileResponse(tmp, media_type="application/zip",
                        filename=f"{safe_title}.h5p",
                        background=BackgroundTask(tmp.unlink, missing_ok=True))
