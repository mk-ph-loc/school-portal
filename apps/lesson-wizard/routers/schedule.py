"""
Lesson Wizard — Ωράριο & ενεργό μάθημα (Task 3: APIRouters).

Πρότυπο Excel (4 φύλλα) + upload → schedule.json (δέχεται και το ΕΝΙΑΙΟ
Excel του Classroom Hub — common.schedule), δημόσιο JSON για τους μαθητές,
χειροκίνητο «ενεργό μάθημα τώρα» & 📡 μετάδοση, πλέγμα ωραρίου από το UI
(κελιά/τμήματα/ώρες/drag & drop χωρίς Excel).
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request, UploadFile, File

from common.classes import CLASS_SLUGS
from common.schedule import DAYS, hhmm as _hhmm, load_json, save_json, parse_schedule_xlsx
from common.xlsx import style_header

import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Ωράριο (Excel → JSON) & ενεργό μάθημα — parsing/JSON helpers: common.schedule
# Styling κεφαλίδων: common.xlsx (κοινό με το ενιαίο πρότυπο του Classroom Hub).
# ---------------------------------------------------------------------------
def make_template_xlsx() -> None:
    """Δημιουργεί το πρότυπο Excel ωραρίου (4 φύλλα, με οδηγίες & παράδειγμα)."""
    from openpyxl import Workbook

    wb = Workbook()

    ws = wb.active
    ws.title = "Τμήματα"
    ws.append(["Τμήμα", "Τάξη (slug)", "Σημείωση"])
    ws.append(["Γ1", "gymnasio-g", "Πληροφορική Γ' Γυμνασίου"])
    ws.append(["Γ2", "gymnasio-g", ""])
    ws.append(["Β1", "gymnasio-b", ""])
    style_header(ws)

    ws = wb.create_sheet("Ωρες")
    ws.append(["Ωρα", "Εναρξη", "Ληξη"])
    for i, (s, e) in enumerate([("08:15", "09:00"), ("09:10", "09:55"), ("10:05", "10:50"),
                                 ("11:10", "11:55"), ("12:05", "12:50"), ("13:00", "13:45"),
                                 ("13:55", "14:40")], 1):
        ws.append([i, s, e])
    style_header(ws)

    ws = wb.create_sheet("Ωραριο")
    ws.append(["Τμήμα", "Ημέρα", "Ωρα", "Μάθημα", "URL μαθήματος (προαιρετικό)"])
    ws.append(["Γ1", "Δευτέρα", 3, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    ws.append(["Γ1", "Τετάρτη", 5, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    ws.append(["Γ2", "Τρίτη", 2, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    style_header(ws)

    ws = wb.create_sheet("Οδηγίες")
    ws.append(["Πώς συμπληρώνω το ωράριο"])
    ws.append(["1. Φύλλο 'Τμήματα': ένα ανά γραμμή. Τάξη (slug): gymnasio-a/b/g, lykeio-a/b/g."])
    ws.append(["2. Φύλλο 'Ωρες': οι διδακτικές ώρες του σχολείου (24ωρη μορφή HH:MM)."])
    ws.append(["3. Φύλλο 'Ωραριο': Τμήμα + Ημέρα (Δευτέρα..Παρασκευή) + αριθμός Ωρας + τίτλος Μαθήματος."])
    ws.append(["   Το URL είναι προαιρετικό· αν δοθεί, ο μαθητής μεταβαίνει κατευθείαν στο μάθημα."])
    ws.append(["4. Ανέβασε το αρχείο στο Lesson Wizard → καρτέλα 'Ωράριο'."])
    ws.append(["5. Κατά τη διάρκεια της ημέρας μπορείς να ορίσεις χειροκίνητα 'Ενεργό μάθημα τώρα'"])
    ws.append(["   ανά τμήμα — υπερισχύει του ωραρίου για όσο διάστημα ορίσεις."])
    style_header(ws)

    state.DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(state.TEMPLATE_XLSX)


# parse_schedule_xlsx/_hhmm: common.schedule (δέχεται και το ενιαίο Excel του
# Classroom Hub — οι 3 καρτέλες ωραρίου είναι ΑΥΤΟΥΣΙΕΣ με αυτό το πρότυπο).


# ---------------------------------------------------------------------------
# Routes — ωράριο & ενεργό μάθημα
# ---------------------------------------------------------------------------
@router.get("/api/schedule/public")
def api_schedule_public():
    """Δημόσιο JSON για το schedule.js των μαθητών (χωρίς ευαίσθητα δεδομένα)."""
    data = load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    overrides = load_json(state.OVERRIDES_JSON, {})
    now = time.time()
    active = {k: v for k, v in overrides.items() if v.get("until", 0) > now}
    bc = load_json(state.BROADCAST_JSON, {})
    broadcast = bc if bc.get("until", 0) > now else None
    return {**data, "overrides": active, "broadcast": broadcast}


@router.get("/api/schedule/template")
def api_schedule_template(request: Request):
    from fastapi.responses import FileResponse
    state.require_teacher(request)
    if not state.TEMPLATE_XLSX.exists():
        make_template_xlsx()
    return FileResponse(state.TEMPLATE_XLSX, filename="orari-protypo.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/api/schedule/upload")
async def api_schedule_upload(request: Request, file: UploadFile = File(...)):
    state.require_teacher(request)
    name = PurePosixPath(file.filename or "").name
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Απαιτείται αρχείο Excel (.xlsx).")
    state.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = state.DATA_DIR / "orari-upload.xlsx"
    tmp.write_bytes(await file.read())
    try:
        data = parse_schedule_xlsx(tmp)
    except Exception as exc:
        raise HTTPException(400, f"Σφάλμα ανάγνωσης Excel: {exc}")
    if not data["tmimata"]:
        raise HTTPException(400, "Δεν βρέθηκαν τμήματα στο φύλλο 'Τμήματα'.")
    if state.SCHEDULE_JSON.exists():
        state.backup_file(state.SCHEDULE_JSON)
    save_json(state.SCHEDULE_JSON, data)
    return {"ok": True, "tmimata": len(data["tmimata"]),
            "periods": len(data["periods"]),
            "entries": sum(len(p) for t in data["timetable"].values() for p in t.values())}


@router.get("/api/schedule")
def api_schedule_get(request: Request):
    state.require_teacher(request)
    return load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})


@router.post("/api/active")
async def api_set_active(request: Request):
    """Χειροκίνητο 'ενεργό μάθημα τώρα' ανά τμήμα (override του ωραρίου)."""
    state.require_teacher(request)
    body = await request.json()
    tmima = str(body.get("tmima", "")).strip()
    if not tmima:
        raise HTTPException(400, "Δώσε τμήμα.")
    overrides = load_json(state.OVERRIDES_JSON, {})
    minutes = int(body.get("minutes", 45))
    if body.get("clear"):
        overrides.pop(tmima, None)
    else:
        title = str(body.get("title", "")).strip()
        url = str(body.get("url", "")).strip()
        if not title:
            raise HTTPException(400, "Δώσε τίτλο μαθήματος.")
        overrides[tmima] = {"title": title, "url": url,
                            "until": time.time() + max(5, min(minutes, 180)) * 60}
    save_json(state.OVERRIDES_JSON, overrides)
    return {"ok": True, "overrides": overrides}


@router.post("/api/broadcast")
async def api_broadcast(request: Request):
    """📡 Μετάδοση μαθήματος: banner σε ΟΛΟΥΣ τους μαθητές (ή επιλεγμένο τμήμα)."""
    state.require_teacher(request)
    body = await request.json()
    if body.get("clear"):
        save_json(state.BROADCAST_JSON, {})
        return {"ok": True, "broadcast": None}
    title = str(body.get("title", "")).strip()
    url = str(body.get("url", "")).strip()
    if not title:
        raise HTTPException(400, "Δώσε τίτλο μαθήματος για μετάδοση.")
    minutes = max(1, min(int(body.get("minutes", 45)), 180))
    bc = {"title": title, "url": url,
          "message": str(body.get("message", "")).strip()[:200],
          "tmima": str(body.get("tmima", "")).strip(),   # κενό = όλα τα τμήματα
          "until": time.time() + minutes * 60}
    save_json(state.BROADCAST_JSON, bc)
    return {"ok": True, "broadcast": bc}


# ---------------------------------------------------------------------------
# Routes — πλέγμα ωραρίου (edit / drag & drop χωρίς Excel)
# ---------------------------------------------------------------------------
def _validate_cell(body: dict) -> tuple[str, str, str]:
    tmima = str(body.get("tmima", "")).strip()
    day = str(body.get("day", "")).strip()
    period = str(body.get("period", "")).strip()
    data = load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    if tmima not in {t["name"] for t in data["tmimata"]}:
        raise HTTPException(400, "Άγνωστο τμήμα.")
    if day not in DAYS:
        raise HTTPException(400, "Άγνωστη ημέρα.")
    if not period.isdigit() or not (1 <= int(period) <= len(data["periods"])):
        raise HTTPException(400, "Άγνωστη διδακτική ώρα.")
    return tmima, day, period


@router.post("/api/schedule/cell")
async def api_schedule_cell(request: Request):
    """Επεξεργασία/καθαρισμός ενός κελιού του πλέγματος ωραρίου."""
    state.require_teacher(request)
    body = await request.json()
    tmima, day, period = _validate_cell(body)
    data = load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    tt = data.setdefault("timetable", {}).setdefault(tmima, {}).setdefault(day, {})
    if body.get("clear"):
        tt.pop(period, None)
    else:
        title = str(body.get("title", "")).strip()
        if not title:
            raise HTTPException(400, "Δώσε μάθημα για το κελί.")
        tt[period] = {"title": title, "url": str(body.get("url", "")).strip()}
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    state.backup_file(state.SCHEDULE_JSON)
    save_json(state.SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}


@router.post("/api/schedule/tmima")
async def api_schedule_tmima(request: Request):
    """Προσθήκη/αφαίρεση τμήματος απευθείας από το UI (χωρίς Excel)."""
    state.require_teacher(request)
    body = await request.json()
    name = str(body.get("name", "")).strip()[:20]
    cls = str(body.get("class_slug", "")).strip()
    if not name or not state.NAME_RE.match(name):
        raise HTTPException(400, "Μη έγκυρο όνομα τμήματος.")
    data = load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    names = {t["name"] for t in data["tmimata"]}
    if body.get("remove"):
        data["tmimata"] = [t for t in data["tmimata"] if t["name"] != name]
        data.get("timetable", {}).pop(name, None)
    else:
        if cls not in CLASS_SLUGS:
            raise HTTPException(400, "Μη έγκυρη τάξη.")
        if name in names:
            raise HTTPException(409, "Το τμήμα υπάρχει ήδη.")
        data["tmimata"].append({"name": name, "class_slug": cls})
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    state.backup_file(state.SCHEDULE_JSON)
    save_json(state.SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}


@router.post("/api/schedule/periods")
async def api_schedule_periods(request: Request):
    """Ενημέρωση ζωνών διδακτικών ωρών από το UI."""
    state.require_teacher(request)
    body = await request.json()
    periods = body.get("periods", [])
    if not isinstance(periods, list) or not (1 <= len(periods) <= 10):
        raise HTTPException(400, "Δώσε 1–10 διδακτικές ώρες.")
    clean = []
    for p in periods:
        s, e = _hhmm(p.get("start", "")), _hhmm(p.get("end", ""))
        if not re.match(r"^\d{2}:\d{2}$", s) or not re.match(r"^\d{2}:\d{2}$", e) or s >= e:
            raise HTTPException(400, f"Μη έγκυρη ζώνη ώρας: {s}–{e}")
        clean.append({"start": s, "end": e})
    data = load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    old_n = len(data.get("periods", []))
    data["periods"] = clean
    if len(clean) < old_n:                        # καθάρισμα κελιών εκτός νέων ωρών
        for tm in data.get("timetable", {}).values():
            for day in tm.values():
                for k in list(day.keys()):
                    if k.isdigit() and int(k) > len(clean):
                        day.pop(k)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    state.backup_file(state.SCHEDULE_JSON)
    save_json(state.SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}


@router.post("/api/schedule/move")
async def api_schedule_move(request: Request):
    """Drag & drop κελιού: μετακίνηση (ή αντιγραφή με copy=true)."""
    state.require_teacher(request)
    body = await request.json()
    src = body.get("from", {}) or {}
    dst = body.get("to", {}) or {}
    s_tm, s_day, s_per = _validate_cell(src)
    d_tm, d_day, d_per = _validate_cell(dst)
    data = load_json(state.SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    entry = data["timetable"].get(s_tm, {}).get(s_day, {}).get(s_per)
    if not entry:
        raise HTTPException(400, "Το κελί προέλευσης είναι κενό.")
    data["timetable"].setdefault(d_tm, {}).setdefault(d_day, {})[d_per] = dict(entry)
    if not body.get("copy"):
        data["timetable"][s_tm][s_day].pop(s_per, None)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    state.backup_file(state.SCHEDULE_JSON)
    save_json(state.SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}
