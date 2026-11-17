"""
Lesson Wizard — Οπτικός επεξεργαστής ημερήσιων μαθημάτων (Ψηφιακή Πύλη Σχολείου).

Περιβάλλον καθηγητή (κωδικός teacher2026, HMAC cookie όπως στο /app-builder/):
  * λίστα ημερήσιων μαθημάτων ανά τάξη/μάθημα (docs/mathimata/<τάξη>/<μάθημα>/),
  * visual editor διδακτικών φάσεων: drag & drop αναδιάταξη, προσθήκη από
    παλέτα τύπων, επεξεργασία markdown/τίτλου/διάρκειας, σημειώσεις καθηγητή,
  * upload υλικού (εικόνες/pdf/html/video) στον φάκελο του μαθήματος,
  * δημιουργία νέου ημερήσιου μαθήματος από template + αυτόματο nav,
  * ωράριο σχολείου από Excel (openpyxl) + χειροκίνητο «ενεργό μάθημα»,
  * /api/check για το nginx auth_request των σημειώσεων καθηγητή.

Τρέχει στο 127.0.0.1:8013 πίσω από τον Nginx στο /lesson-wizard/. Χωρίς Docker.
Το rebuild του static site γίνεται αυτόματα από το school-mkdocs.path/service.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent.parent                 # apps/lesson-wizard → /opt/school-portal
DOCS_DIR = PORTAL_DIR / "mkdocs-site" / "docs"
MATH_DIR = DOCS_DIR / "mathimata"
MKDOCS_YML = PORTAL_DIR / "mkdocs-site" / "mkdocs.yml"
BACKUP_DIR = BASE_DIR / "backups"
DATA_DIR = BASE_DIR / "data"
SCHEDULE_JSON = DATA_DIR / "schedule.json"
OVERRIDES_JSON = DATA_DIR / "active-overrides.json"
TEMPLATE_XLSX = DATA_DIR / "orari-protypo.xlsx"

TEACHER_CODE = "teacher2026"
COOKIE_NAME = "lessonwizard_teacher"
COOKIE_MAX_AGE = 8 * 3600                            # μία σχολική ημέρα

CLASS_GROUPS = [
    {"slug": "gymnasio-a", "label": "Α' Γυμνασίου"},
    {"slug": "gymnasio-b", "label": "Β' Γυμνασίου"},
    {"slug": "gymnasio-g", "label": "Γ' Γυμνασίου"},
    {"slug": "lykeio-a",   "label": "Α' Λυκείου"},
    {"slug": "lykeio-b",   "label": "Β' Λυκείου"},
    {"slug": "lykeio-g",   "label": "Γ' Λυκείου"},
]
CLASS_SLUGS = {c["slug"] for c in CLASS_GROUPS}
CLASS_LABELS = {c["slug"]: c["label"] for c in CLASS_GROUPS}

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")        # πεζά λατινικά/greeklish
PHASE_TYPES = {
    "aformisi":      {"icon": "🎯", "label": "Αφόρμηση",       "duration": 5},
    "syzitisi":      {"icon": "💬", "label": "Συζήτηση",       "duration": 6},
    "parousiasi":    {"icon": "📽️", "label": "Παρουσίαση",     "duration": 10},
    "drastiriotita": {"icon": "✍️", "label": "Δραστηριότητα",  "duration": 15},
    "aksiologisi":   {"icon": "✅", "label": "Αξιολόγηση",     "duration": 6},
    "kleisimo":      {"icon": "🧭", "label": "Κλείσιμο",       "duration": 3},
    "custom":        {"icon": "🧩", "label": "Ελεύθερη φάση",  "duration": 5},
}
UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf",
               ".html", ".mp4", ".webm", ".mp3", ".ogg", ".pptx", ".odp", ".zip"}
UPLOAD_MAX = 40 * 1024 * 1024                        # 40 MB ανά αρχείο

NAV_BEGIN = "# BEGIN AUTO-NAV MATHIMATA"
NAV_END = "# END AUTO-NAV MATHIMATA"

app = FastAPI(
    title="Lesson Wizard — Ημερήσια Μαθήματα",
    description="Οπτικός επεξεργαστής διδακτικών φάσεων & ωραρίου",
    docs_url=None, redoc_url=None, openapi_url=None,
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC), όχι απλό flag
# ---------------------------------------------------------------------------
def _secret_key() -> bytes:
    key_file = BASE_DIR / ".cookie-secret"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
        key_file.chmod(0o600)
    return key_file.read_text().strip().encode()


SECRET_KEY = _secret_key()


def make_token() -> str:
    expires = int(time.time()) + COOKIE_MAX_AGE
    payload = str(expires)
    sig = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def token_valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, _, sig = token.partition(".")
    expected = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return int(payload) > time.time()
    except ValueError:
        return False


def require_teacher(request: Request) -> None:
    if not token_valid(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(401, "Απαιτείται κωδικός καθηγητή.")
# ---------------------------------------------------------------------------
# Parsing / serialization μαθήματος (φάσεις με markers — ίδιο format με το hook)
# ---------------------------------------------------------------------------
PHASE_RE = re.compile(
    r"^<!--\s*phase:\s*([a-z0-9_-]+)([^\n]*?)-->\s*$(.*?)^<!--\s*/phase\s*-->\s*$",
    re.MULTILINE | re.DOTALL,
)
ATTR_RE = re.compile(r"\|\s*([a-z_]+):\s*([^|]*?)(?=\||$)")
TN_RE = re.compile(r"<!--\s*teacher-notes\s*-->(.*?)<!--\s*/teacher-notes\s*-->", re.DOTALL)
FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def parse_lesson(md: str) -> dict:
    """Χωρίζει το markdown σε front-matter, κεφαλίδα, φάσεις & σημειώσεις."""
    fm = ""
    m = FM_RE.match(md)
    if m:
        fm = m.group(1)
        md_rest = md[m.end():]
    else:
        md_rest = md
    tn = ""
    tnm = TN_RE.search(md_rest)
    if tnm:
        tn = tnm.group(1).strip()
        md_rest = TN_RE.sub("", md_rest)
    phases = []
    header_parts = []
    pos = 0
    for pm in PHASE_RE.finditer(md_rest):
        header_parts.append(md_rest[pos:pm.start()])
        attrs = dict((k.strip(), v.strip()) for k, v in ATTR_RE.findall(pm.group(2) or ""))
        ptype = pm.group(1)
        phases.append({
            "type": ptype,
            "title": attrs.get("title", PHASE_TYPES.get(ptype, {}).get("label", "Φάση")),
            "duration": int(attrs.get("duration", "0") or 0),
            "body": pm.group(3).strip("\n"),
        })
        pos = pm.end()
    header_parts.append(md_rest[pos:])
    return {
        "front_matter": fm,
        "header": "".join(header_parts).strip("\n"),
        "phases": phases,
        "teacher_notes": tn,
    }


def render_lesson(data: dict) -> str:
    """Συναρμολογεί το markdown από τα δομικά στοιχεία (στρογγυλοποίηση μορφής)."""
    out = []
    if data.get("front_matter"):
        out.append("---\n" + data["front_matter"].strip() + "\n---\n")
    out.append(data.get("header", "").strip() + "\n")
    for ph in data.get("phases", []):
        ptype = ph.get("type", "custom")
        title = ph.get("title") or PHASE_TYPES.get(ptype, {}).get("label", "Φάση")
        dur = int(ph.get("duration") or 0)
        out.append(
            f"\n<!-- phase: {ptype} | title: {title} | duration: {dur} -->\n"
            + ph.get("body", "").strip()
            + "\n<!-- /phase -->\n"
        )
    if data.get("teacher_notes", "").strip():
        out.append("\n<!-- teacher-notes -->\n" + data["teacher_notes"].strip() + "\n<!-- /teacher-notes -->\n")
    return "\n".join(out).replace("\n\n\n", "\n\n")


def lesson_dir(class_slug: str, subject: str, lesson: str) -> Path:
    """Έγκυρος φάκελος ημερήσιου μαθήματος (αυστηρή επαλήθευση διαδρομών)."""
    if not (SLUG_RE.match(class_slug) and class_slug in CLASS_SLUGS):
        raise HTTPException(400, "Μη έγκυρη τάξη.")
    if not SLUG_RE.match(subject) or not SLUG_RE.match(lesson):
        raise HTTPException(400, "Μη έγκυρο όνομα μαθήματος/ενότητας.")
    d = (MATH_DIR / class_slug / subject / lesson).resolve()
    if not str(d).startswith(str(MATH_DIR.resolve())):
        raise HTTPException(400, "Μη έγκυρη διαδρομή.")
    return d


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rel = path.relative_to(PORTAL_DIR).as_posix().replace("/", "__")
    shutil.copy2(path, BACKUP_DIR / f"{stamp}__{rel}.bak")


def list_all_lessons() -> list[dict]:
    """Όλα τα ημερήσια μαθήματα (φάκελοι με index.md κάτω από mathimata/)."""
    out = []
    if not MATH_DIR.is_dir():
        return out
    for cls_dir in sorted(MATH_DIR.iterdir()):
        if not cls_dir.is_dir() or cls_dir.name not in CLASS_SLUGS:
            continue
        for subj_dir in sorted(cls_dir.iterdir()):
            if not subj_dir.is_dir():
                continue
            for les_dir in sorted(subj_dir.iterdir()):
                idx = les_dir / "index.md"
                if not les_dir.is_dir() or not idx.is_file():
                    continue
                text = idx.read_text(encoding="utf-8", errors="ignore")
                parsed = parse_lesson(text)
                if not parsed["phases"]:
                    continue                      # index ενότητας, όχι μάθημα
                title = les_dir.name
                hm = re.search(r"^# (.+)$", parsed["header"], re.MULTILINE)
                if hm:
                    title = hm.group(1).strip()
                total = sum(p["duration"] for p in parsed["phases"])
                files = [p.name for p in sorted(les_dir.iterdir())
                         if p.is_file() and p.name != "index.md"]
                out.append({
                    "class_slug": cls_dir.name,
                    "class_label": CLASS_LABELS[cls_dir.name],
                    "subject": subj_dir.name,
                    "lesson": les_dir.name,
                    "title": title,
                    "phases": len(parsed["phases"]),
                    "duration": total,
                    "files": files,
                    "url": f"/docs/mathimata/{cls_dir.name}/{subj_dir.name}/{les_dir.name}/",
                })
    return out
# ---------------------------------------------------------------------------
# Αυτόματο nav στο mkdocs.yml (μεταξύ των δεικτών BEGIN/END AUTO-NAV)
# ---------------------------------------------------------------------------
def rebuild_nav() -> None:
    """Ξαναγράφει το μπλοκ Μαθήματα στο nav με βάση τους φακέλους."""
    text = MKDOCS_YML.read_text(encoding="utf-8")
    i = text.find(NAV_BEGIN)
    j = text.find(NAV_END)
    if i == -1 or j == -1:
        return                                    # χωρίς δείκτες δεν πειράζουμε
    j_end = text.find("\n", j)
    # Ο δείκτης BEGIN πρέπει να ξεκινά στην αρχή της γραμμής του (όχι μετά τα
    # κενά indent της προηγούμενης χρήσης — θα διπλασιάζονταν σε κάθε rebuild).
    i = text.rfind("\n", 0, i) + 1
    lines = ["  " + NAV_BEGIN + " (διαχειρίζεται το Lesson Wizard — μην επεξεργάζεστε χειροκίνητα)",
             "  - Μαθήματα:"]
    lessons = list_all_lessons()
    by_class: dict[str, dict[str, list]] = {}
    for les in lessons:
        by_class.setdefault(les["class_slug"], {}).setdefault(les["subject"], []).append(les)
    for cls in CLASS_GROUPS:
        subjects = by_class.get(cls["slug"])
        if not subjects:
            continue
        lines.append(f"      - {cls['label']}:")
        for subj, items in subjects.items():
            subj_label = subj.replace("-", " ").capitalize()
            idx_rel = f"mathimata/{cls['slug']}/{subj}/index.md"
            if (DOCS_DIR / idx_rel).is_file():
                # Προτίμηση του title από το front-matter του index (π.χ. «Πληροφορική Γ' Γυμνασίου»)
                fm = FM_RE.match((DOCS_DIR / idx_rel).read_text(encoding="utf-8", errors="ignore"))
                if fm:
                    tm = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", fm.group(1), re.MULTILINE)
                    if tm:
                        subj_label = tm.group(1).strip().replace("'", "''")
                lines.append(f"          - '{subj_label}': {idx_rel}")
            for les in items:
                title = les["title"].replace("'", "''")
                rel = f"mathimata/{cls['slug']}/{subj}/{les['lesson']}/index.md"
                lines.append(f"          - '{title}': {rel}")
    lines.append("  " + NAV_END)
    new_text = text[:i] + "\n".join(lines) + text[j_end:]
    if new_text != text:
        backup_file(MKDOCS_YML)
        MKDOCS_YML.write_text(new_text, encoding="utf-8")


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
# Ωράριο (Excel → JSON) & ενεργό μάθημα
# ---------------------------------------------------------------------------
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def make_template_xlsx() -> None:
    """Δημιουργεί το πρότυπο Excel ωραρίου (4 φύλλα, με οδηγίες & παράδειγμα)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="3F51B5")

    def style_header(ws):
        for c in ws[1]:
            c.font = head_font
            c.fill = head_fill

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

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(TEMPLATE_XLSX)


def parse_schedule_xlsx(path: Path) -> dict:
    """Μετατρέπει το Excel ωραρίου στο JSON που καταναλώνει το schedule.js."""
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    tmimata = []
    if "Τμήματα" in wb.sheetnames:
        for row in wb["Τμήματα"].iter_rows(min_row=2, values_only=True):
            if row and row[0]:
                tmimata.append({"name": str(row[0]).strip(),
                                "class_slug": str(row[1] or "").strip()})
    periods = []
    if "Ωρες" in wb.sheetnames:
        for row in wb["Ωρες"].iter_rows(min_row=2, values_only=True):
            if row and row[1] and row[2]:
                periods.append({"start": _hhmm(row[1]), "end": _hhmm(row[2])})
    timetable: dict = {}
    if "Ωραριο" in wb.sheetnames:
        for row in wb["Ωραριο"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0] or not row[1] or not row[2]:
                continue
            tm, day, period = str(row[0]).strip(), str(row[1]).strip(), str(int(row[2]))
            title = str(row[3] or "").strip()
            url = str(row[4] or "").strip()
            timetable.setdefault(tm, {}).setdefault(day, {})[period] = {"title": title, "url": url}
    wb.close()
    return {"tmimata": tmimata, "periods": periods, "timetable": timetable,
            "updated": datetime.now().isoformat(timespec="seconds")}


def _hhmm(v) -> str:
    """Δέχεται '8:15', datetime.time ή κλάσμα ημέρας του Excel."""
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    if isinstance(v, (int, float)):
        mins = round(float(v) * 24 * 60)
        return f"{mins // 60:02d}:{mins % 60:02d}"
    s = str(v).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else s
# ---------------------------------------------------------------------------
# Routes — σελίδες & auth
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/check")
def api_check(request: Request):
    """auth_request endpoint του Nginx για τα index.teacher.html (200/401)."""
    if token_valid(request.cookies.get(COOKIE_NAME)):
        return Response(status_code=200)
    return Response(status_code=401)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    authed = token_valid(request.cookies.get(COOKIE_NAME))
    return templates.TemplateResponse(request, "index.html", {
        "authed": authed,
        "classes": CLASS_GROUPS,
        "phase_types": PHASE_TYPES,
    })


@app.post("/api/login")
async def api_login(request: Request, response: Response):
    body = await request.json()
    if str(body.get("code", "")) != TEACHER_CODE:
        raise HTTPException(403, "Λάθος κωδικός καθηγητή.")
    response.set_cookie(COOKIE_NAME, make_token(), max_age=COOKIE_MAX_AGE,
                        httponly=True, samesite="lax", path="/")
    return {"ok": True}


@app.post("/api/logout")
def api_logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes — μαθήματα & φάσεις
# ---------------------------------------------------------------------------
@app.get("/api/lessons")
def api_lessons(request: Request):
    require_teacher(request)
    return {"lessons": list_all_lessons(), "classes": CLASS_GROUPS,
            "phase_types": PHASE_TYPES}


@app.get("/api/lesson/{class_slug}/{subject}/{lesson}")
def api_get_lesson(class_slug: str, subject: str, lesson: str, request: Request):
    require_teacher(request)
    d = lesson_dir(class_slug, subject, lesson)
    idx = d / "index.md"
    if not idx.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    data = parse_lesson(idx.read_text(encoding="utf-8"))
    files = [{"name": p.name, "size": p.stat().st_size}
             for p in sorted(d.iterdir()) if p.is_file() and p.name != "index.md"]
    return {**data, "files": files,
            "url": f"/docs/mathimata/{class_slug}/{subject}/{lesson}/"}


@app.post("/api/lesson/{class_slug}/{subject}/{lesson}")
async def api_save_lesson(class_slug: str, subject: str, lesson: str, request: Request):
    require_teacher(request)
    d = lesson_dir(class_slug, subject, lesson)
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
    backup_file(idx)
    idx.write_text(new_md, encoding="utf-8")
    rebuild_nav()
    return {"ok": True, "phases": len(phases),
            "duration": sum(int(p.get("duration") or 0) for p in phases)}
@app.post("/api/lesson-new")
async def api_new_lesson(request: Request):
    require_teacher(request)
    body = await request.json()
    cls = str(body.get("class_slug", "")).strip()
    subject = str(body.get("subject", "")).strip()
    slug = str(body.get("lesson", "")).strip()
    title = str(body.get("title", "")).strip() or slug
    book_url = str(body.get("book_url", "")).strip() or "#"
    d = lesson_dir(cls, subject, slug)
    if (d / "index.md").exists():
        raise HTTPException(409, "Υπάρχει ήδη μάθημα με αυτό το όνομα.")
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.md").write_text(
        NEW_LESSON_TEMPLATE.format(title=title, cls=cls, subject=subject, book_url=book_url),
        encoding="utf-8")
    rebuild_nav()
    return {"ok": True, "url": f"/docs/mathimata/{cls}/{subject}/{slug}/"}


@app.post("/api/upload/{class_slug}/{subject}/{lesson}")
async def api_upload(class_slug: str, subject: str, lesson: str, request: Request,
                     file: UploadFile = File(...)):
    require_teacher(request)
    d = lesson_dir(class_slug, subject, lesson)
    if not (d / "index.md").is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    name = PurePosixPath(file.filename or "").name
    if not name or name.startswith(".") or name == "index.md":
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
    ext = PurePosixPath(name).suffix.lower()
    if ext not in UPLOAD_EXTS:
        raise HTTPException(400, f"Μη επιτρεπτός τύπος αρχείου ({ext}).")
    content = await file.read()
    if len(content) > UPLOAD_MAX:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 40 MB.")
    dest = d / name
    if dest.exists():
        backup_file(dest)
    dest.write_bytes(content)
    return {"ok": True, "name": name, "size": len(content)}


@app.delete("/api/file/{class_slug}/{subject}/{lesson}/{filename}")
def api_delete_file(class_slug: str, subject: str, lesson: str, filename: str, request: Request):
    require_teacher(request)
    d = lesson_dir(class_slug, subject, lesson)
    name = PurePosixPath(filename).name
    if name in ("index.md", "") or name.startswith("."):
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
    target = d / name
    if not target.is_file():
        raise HTTPException(404, "Το αρχείο δεν βρέθηκε.")
    backup_file(target)
    target.unlink()
    return {"ok": True}
# ---------------------------------------------------------------------------
# Routes — ωράριο & ενεργό μάθημα
# ---------------------------------------------------------------------------
@app.get("/api/schedule/public")
def api_schedule_public():
    """Δημόσιο JSON για το schedule.js των μαθητών (χωρίς ευαίσθητα δεδομένα)."""
    data = load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    overrides = load_json(OVERRIDES_JSON, {})
    now = time.time()
    active = {k: v for k, v in overrides.items() if v.get("until", 0) > now}
    return {**data, "overrides": active}


@app.get("/api/schedule/template")
def api_schedule_template(request: Request):
    from fastapi.responses import FileResponse
    require_teacher(request)
    if not TEMPLATE_XLSX.exists():
        make_template_xlsx()
    return FileResponse(TEMPLATE_XLSX, filename="orari-protypo.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/schedule/upload")
async def api_schedule_upload(request: Request, file: UploadFile = File(...)):
    require_teacher(request)
    name = PurePosixPath(file.filename or "").name
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Απαιτείται αρχείο Excel (.xlsx).")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / "orari-upload.xlsx"
    tmp.write_bytes(await file.read())
    try:
        data = parse_schedule_xlsx(tmp)
    except Exception as exc:
        raise HTTPException(400, f"Σφάλμα ανάγνωσης Excel: {exc}")
    if not data["tmimata"]:
        raise HTTPException(400, "Δεν βρέθηκαν τμήματα στο φύλλο 'Τμήματα'.")
    if SCHEDULE_JSON.exists():
        backup_file(SCHEDULE_JSON)
    save_json(SCHEDULE_JSON, data)
    return {"ok": True, "tmimata": len(data["tmimata"]),
            "periods": len(data["periods"]),
            "entries": sum(len(p) for t in data["timetable"].values() for p in t.values())}


@app.get("/api/schedule")
def api_schedule_get(request: Request):
    require_teacher(request)
    return load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})


@app.post("/api/active")
async def api_set_active(request: Request):
    """Χειροκίνητο 'ενεργό μάθημα τώρα' ανά τμήμα (override του ωραρίου)."""
    require_teacher(request)
    body = await request.json()
    tmima = str(body.get("tmima", "")).strip()
    if not tmima:
        raise HTTPException(400, "Δώσε τμήμα.")
    overrides = load_json(OVERRIDES_JSON, {})
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
    save_json(OVERRIDES_JSON, overrides)
    return {"ok": True, "overrides": overrides}