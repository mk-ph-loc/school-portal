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
BROADCAST_JSON = DATA_DIR / "broadcast.json"
BOOKS_JSON = DATA_DIR / "books.json"
TEMPLATE_XLSX = DATA_DIR / "orari-protypo.xlsx"
LIBRARY_DIR = DOCS_DIR / "vivliothiki"

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή"]

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
# Γενικός file browser: επιπλέον τύποι για υλικό μαθημάτων (md/css/js/data).
FS_UPLOAD_EXTS = UPLOAD_EXTS | {".md", ".txt", ".css", ".js", ".json", ".csv",
                                ".docx", ".odt", ".xlsx", ".ipynb", ".py"}
NAME_RE = re.compile(r"^[^/\\\x00-\x1f]+$")          # όνομα αρχείου/φακέλου χωρίς διαδρομές

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


def fm_meta(fm: str) -> dict:
    """Ελαφρύ διάβασμα μεταδεδομένων front-matter (tags/favorite/unit/book).

    Δεν απαιτεί PyYAML — καλύπτει τις μορφές που γράφει το wizard:
      tags: [a, b]  ή  tags:\n    - a\n    - b
      favorite: true
    """
    meta: dict = {"tags": [], "favorite": False}
    m = re.search(r"^tags:\s*\[(.*?)\]\s*$", fm, re.MULTILINE)
    if m:
        meta["tags"] = [t.strip().strip("'\"") for t in m.group(1).split(",") if t.strip()]
    else:
        m = re.search(r"^tags:\s*\n((?:\s+-\s+.+\n?)+)", fm, re.MULTILINE)
        if m:
            meta["tags"] = [x.strip().lstrip("-").strip().strip("'\"")
                            for x in m.group(1).strip().splitlines() if x.strip()]
    m = re.search(r"^favorite:\s*(true|yes|1)\s*$", fm, re.MULTILINE | re.IGNORECASE)
    meta["favorite"] = bool(m)
    m = re.search(r"^\s+unit:\s*['\"]?(.*?)['\"]?\s*$", fm, re.MULTILINE)
    if m:
        meta["unit"] = m.group(1).strip()
    m = re.search(r"^\s+book_pages:\s*['\"]?(.*?)['\"]?\s*$", fm, re.MULTILINE)
    if m:
        meta["book_pages"] = m.group(1).strip()
    return meta


def set_fm_meta(fm: str, tags: list[str] | None, favorite: bool | None) -> str:
    """Γράφει/αντικαθιστά τα tags & favorite στο front-matter (χωρίς YAML lib)."""
    lines = fm.splitlines()
    out: list[str] = []
    skip_block = False
    for ln in lines:
        if skip_block:
            if re.match(r"^\s+-\s+", ln):
                continue                          # γραμμές παλιάς λίστας tags
            skip_block = False
        if re.match(r"^tags:", ln):
            if not re.match(r"^tags:\s*\[", ln):
                skip_block = True                 # block-style λίστα → αφαίρεση
            continue
        if re.match(r"^favorite:", ln):
            continue
        out.append(ln)
    if tags is not None:
        clean = [re.sub(r"[\[\],#'\"\n]", "", str(t)).strip() for t in tags]
        clean = [t for t in clean if t][:12]
        if clean:
            out.append("tags: [" + ", ".join(clean) + "]")
    if favorite:
        out.append("favorite: true")
    return "\n".join(out).strip("\n")


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
                meta = fm_meta(parsed["front_matter"])
                out.append({
                    "class_slug": cls_dir.name,
                    "class_label": CLASS_LABELS[cls_dir.name],
                    "subject": subj_dir.name,
                    "lesson": les_dir.name,
                    "title": title,
                    "phases": len(parsed["phases"]),
                    "duration": total,
                    "files": files,
                    "tags": meta["tags"],
                    "favorite": meta["favorite"],
                    "unit": meta.get("unit", ""),
                    "book_pages": meta.get("book_pages", ""),
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
    lines = ["  " + NAV_BEGIN + " (διαχειρίζεται το Lesson Wizard — μην επεξεργάζεστε χειροκίνητα)"]
    if LIBRARY_DIR.is_dir() and any(LIBRARY_DIR.glob("*.pdf")):
        lines.append("  - 📖 Βιβλιοθήκη: vivliothiki/index.md")
    lines.append("  - Μαθήματα:")
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


@app.post("/api/meta/{class_slug}/{subject}/{lesson}")
async def api_set_meta(class_slug: str, subject: str, lesson: str, request: Request):
    """Tags & ⭐ αγαπημένο στο front-matter του μαθήματος (χωρίς αλλαγή φάσεων)."""
    require_teacher(request)
    d = lesson_dir(class_slug, subject, lesson)
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
    backup_file(idx)
    idx.write_text(render_lesson(parsed), encoding="utf-8")
    meta = fm_meta(new_fm)
    return {"ok": True, "tags": meta["tags"], "favorite": meta["favorite"]}


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
    bc = load_json(BROADCAST_JSON, {})
    broadcast = bc if bc.get("until", 0) > now else None
    return {**data, "overrides": active, "broadcast": broadcast}


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


@app.post("/api/broadcast")
async def api_broadcast(request: Request):
    """📡 Μετάδοση μαθήματος: banner σε ΟΛΟΥΣ τους μαθητές (ή επιλεγμένο τμήμα)."""
    require_teacher(request)
    body = await request.json()
    if body.get("clear"):
        save_json(BROADCAST_JSON, {})
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
    save_json(BROADCAST_JSON, bc)
    return {"ok": True, "broadcast": bc}


# ---------------------------------------------------------------------------
# Routes — πλέγμα ωραρίου (edit / drag & drop χωρίς Excel)
# ---------------------------------------------------------------------------
def _validate_cell(body: dict) -> tuple[str, str, str]:
    tmima = str(body.get("tmima", "")).strip()
    day = str(body.get("day", "")).strip()
    period = str(body.get("period", "")).strip()
    data = load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    if tmima not in {t["name"] for t in data["tmimata"]}:
        raise HTTPException(400, "Άγνωστο τμήμα.")
    if day not in DAYS:
        raise HTTPException(400, "Άγνωστη ημέρα.")
    if not period.isdigit() or not (1 <= int(period) <= len(data["periods"])):
        raise HTTPException(400, "Άγνωστη διδακτική ώρα.")
    return tmima, day, period


@app.post("/api/schedule/cell")
async def api_schedule_cell(request: Request):
    """Επεξεργασία/καθαρισμός ενός κελιού του πλέγματος ωραρίου."""
    require_teacher(request)
    body = await request.json()
    tmima, day, period = _validate_cell(body)
    data = load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    tt = data.setdefault("timetable", {}).setdefault(tmima, {}).setdefault(day, {})
    if body.get("clear"):
        tt.pop(period, None)
    else:
        title = str(body.get("title", "")).strip()
        if not title:
            raise HTTPException(400, "Δώσε μάθημα για το κελί.")
        tt[period] = {"title": title, "url": str(body.get("url", "")).strip()}
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    backup_file(SCHEDULE_JSON)
    save_json(SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}


@app.post("/api/schedule/tmima")
async def api_schedule_tmima(request: Request):
    """Προσθήκη/αφαίρεση τμήματος απευθείας από το UI (χωρίς Excel)."""
    require_teacher(request)
    body = await request.json()
    name = str(body.get("name", "")).strip()[:20]
    cls = str(body.get("class_slug", "")).strip()
    if not name or not NAME_RE.match(name):
        raise HTTPException(400, "Μη έγκυρο όνομα τμήματος.")
    data = load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
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
    backup_file(SCHEDULE_JSON)
    save_json(SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}


@app.post("/api/schedule/periods")
async def api_schedule_periods(request: Request):
    """Ενημέρωση ζωνών διδακτικών ωρών από το UI."""
    require_teacher(request)
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
    data = load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    old_n = len(data.get("periods", []))
    data["periods"] = clean
    if len(clean) < old_n:                        # καθάρισμα κελιών εκτός νέων ωρών
        for tm in data.get("timetable", {}).values():
            for day in tm.values():
                for k in list(day.keys()):
                    if k.isdigit() and int(k) > len(clean):
                        day.pop(k)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    backup_file(SCHEDULE_JSON)
    save_json(SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}


# ---------------------------------------------------------------------------
# Routes — γενικός file browser του docs/ (μαθήματα, φάκελοι, υλικό)
# ---------------------------------------------------------------------------
def fs_path(rel: str) -> Path:
    """Αυστηρή επαλήθευση: η διαδρομή μένει εντός docs/ (όχι κρυφά αρχεία).

    Δέχεται ΜΟΝΟ σχετικές διαδρομές — απόλυτες (/etc/…) απορρίπτονται, γιατί
    το pathlib θα αγνοούσε το DOCS_DIR prefix.
    """
    rel = (rel or "").strip()
    if (rel.startswith("/") or ".." in rel.strip("/").split("/")
            or "\\" in rel or "\x00" in rel):
        raise HTTPException(400, "Μη έγκυρη διαδρομή.")
    rel = rel.strip("/")
    base = DOCS_DIR.resolve()
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise HTTPException(400, "Μη έγκυρη διαδρομή.")
    for part in p.relative_to(base).parts:
        if part.startswith("."):
            raise HTTPException(403, "Κρυφά αρχεία δεν επιτρέπονται.")
    return p


FS_EDITABLE_EXTS = {".md", ".txt", ".css", ".js", ".json", ".csv", ".html", ".py"}
FS_EDIT_MAX = 2 * 1024 * 1024                        # 2 MB ανά αρχείο κειμένου


@app.get("/api/fs/list")
def api_fs_list(request: Request, path: str = ""):
    require_teacher(request)
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
    rel = d.relative_to(DOCS_DIR.resolve()).as_posix()
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


@app.get("/api/fs/read")
def api_fs_read(request: Request, path: str):
    require_teacher(request)
    p = fs_path(path)
    if not p.is_file():
        raise HTTPException(404, "Το αρχείο δεν βρέθηκε.")
    if p.suffix.lower() not in FS_EDITABLE_EXTS:
        raise HTTPException(400, "Ο τύπος αρχείου δεν υποστηρίζει επεξεργασία κειμένου.")
    if p.stat().st_size > FS_EDIT_MAX:
        raise HTTPException(413, "Το αρχείο είναι πολύ μεγάλο για επεξεργασία (>2 MB).")
    return {"path": path, "content": p.read_text(encoding="utf-8", errors="replace"),
            "view_url": "/docs/" + p.relative_to(DOCS_DIR.resolve()).as_posix()}


@app.post("/api/fs/save")
async def api_fs_save(request: Request):
    require_teacher(request)
    body = await request.json()
    p = fs_path(str(body.get("path", "")))
    if not p.is_file() or p.suffix.lower() not in FS_EDITABLE_EXTS:
        raise HTTPException(400, "Μη επεξεργάσιμο αρχείο.")
    content = str(body.get("content", ""))
    if len(content.encode("utf-8")) > FS_EDIT_MAX:
        raise HTTPException(413, "Πολύ μεγάλο περιεχόμενο (>2 MB).")
    backup_file(p)
    p.write_text(content, encoding="utf-8")
    if p.name == "index.md" and "mathimata" in p.parts:
        rebuild_nav()
    return {"ok": True}


@app.post("/api/fs/upload")
async def api_fs_upload(request: Request, path: str = "", file: UploadFile = File(...)):
    require_teacher(request)
    d = fs_path(path)
    if not d.is_dir():
        raise HTTPException(404, "Ο φάκελος δεν βρέθηκε.")
    name = PurePosixPath(file.filename or "").name
    if not name or name.startswith(".") or not NAME_RE.match(name):
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
    ext = PurePosixPath(name).suffix.lower()
    if ext not in FS_UPLOAD_EXTS:
        raise HTTPException(400, f"Μη επιτρεπτός τύπος αρχείου ({ext}).")
    content = await file.read()
    if len(content) > UPLOAD_MAX:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 40 MB.")
    dest = d / name
    if dest.exists():
        backup_file(dest)
    dest.write_bytes(content)
    return {"ok": True, "name": name, "size": len(content)}


@app.post("/api/fs/mkdir")
async def api_fs_mkdir(request: Request):
    require_teacher(request)
    body = await request.json()
    parent = fs_path(str(body.get("path", "")))
    name = str(body.get("name", "")).strip()
    if not name or name.startswith(".") or not NAME_RE.match(name):
        raise HTTPException(400, "Μη έγκυρο όνομα φακέλου.")
    if not parent.is_dir():
        raise HTTPException(404, "Ο γονικός φάκελος δεν βρέθηκε.")
    target = parent / name
    if target.exists():
        raise HTTPException(409, "Υπάρχει ήδη φάκελος/αρχείο με αυτό το όνομα.")
    target.mkdir()
    return {"ok": True}


@app.delete("/api/fs/delete")
def api_fs_delete(request: Request, path: str):
    require_teacher(request)
    p = fs_path(path)
    if p == DOCS_DIR.resolve() or not p.is_file():
        raise HTTPException(400, "Επιτρέπεται μόνο διαγραφή αρχείων (όχι φακέλων).")
    backup_file(p)
    p.unlink()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Routes — 📖 Βιβλιοθήκη βιβλίων (PDF στο docs/vivliothiki/, links με #page=N)
# ---------------------------------------------------------------------------
def rebuild_library_page() -> None:
    """Παράγει το vivliothiki/index.md από τα metadata των βιβλίων."""
    books = load_json(BOOKS_JSON, [])
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "title: '📖 Βιβλιοθήκη Βιβλίων'",
        "---",
        "",
        "# 📖 Βιβλιοθήκη Βιβλίων",
        "",
        "Τα σχολικά βιβλία (PDF) που χρησιμοποιούμε στα μαθήματα. Κάθε σύνδεσμος",
        "«σελ. Ν» ανοίγει το βιβλίο **κατευθείαν στη σελίδα Ν** (`#page=N`).",
        "",
        '!!! tip "Πώς μπαίνει link σε συγκεκριμένη σελίδα μέσα σε μάθημα"',
        "    Από το [Lesson Wizard → Βιβλία](/lesson-wizard/){target=_blank} πάτα",
        "    **🔗 Link σε μάθημα**, ή γράψε απευθείας markdown:",
        "    `[📖 Βιβλίο, σελ. 10](/docs/vivliothiki/ΟΝΟΜΑ.pdf#page=10){target=_blank}`",
        "",
    ]
    if not books:
        lines.append("*Δεν έχουν ανέβει βιβλία ακόμη — ο καθηγητής τα προσθέτει από το Lesson Wizard → 📖 Βιβλία.*")
    for b in books:
        cls_label = CLASS_LABELS.get(b.get("class_slug", ""), "")
        meta_bits = [x for x in (cls_label, b.get("subject", ""),
                                 (str(b["pages"]) + " σελίδες") if b.get("pages") else "") if x]
        lines += [
            f"## {b['title']}",
            "",
            (" · ".join(meta_bits) + "  ") if meta_bits else "",
            f"[📕 Άνοιγμα βιβλίου]({b['file']}){{target=_blank}} · "
            f"[Σελ. 1]({b['file']}#page=1){{target=_blank}}",
            "",
            f'<object data="{b["file"]}#page=1" type="application/pdf" width="100%" height="520px">',
            f'<p>📄 <a href="{b["file"]}" target="_blank">Λήψη/Άνοιγμα PDF</a></p>',
            "</object>",
            "",
        ]
    idx = LIBRARY_DIR / "index.md"
    new_md = "\n".join(lines) + "\n"
    if not idx.exists() or idx.read_text(encoding="utf-8") != new_md:
        backup_file(idx)
        idx.write_text(new_md, encoding="utf-8")


@app.get("/api/books")
def api_books(request: Request):
    require_teacher(request)
    return {"books": load_json(BOOKS_JSON, []), "classes": CLASS_GROUPS}


@app.post("/api/books/upload")
async def api_books_upload(request: Request, file: UploadFile = File(...),
                           title: str = Form(""), slug: str = Form(""),
                           class_slug: str = Form(""), subject: str = Form("")):
    require_teacher(request)
    name = PurePosixPath(file.filename or "").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Απαιτείται αρχείο PDF.")
    slug = (slug or PurePosixPath(name).stem).strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    if not SLUG_RE.match(slug):
        raise HTTPException(400, "Μη έγκυρο slug βιβλίου (πεζά λατινικά/greeklish).")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(413, "Το βιβλίο ξεπερνά τα 100 MB.")
    pages = 0
    try:
        import io
        from pypdf import PdfReader
        pages = len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        pass                                       # μη αναγνώσιμο PDF → χωρίς πλήθος σελίδων
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    dest = LIBRARY_DIR / f"{slug}.pdf"
    if dest.exists():
        backup_file(dest)
    dest.write_bytes(content)
    books = load_json(BOOKS_JSON, [])
    entry = {"slug": slug, "title": title.strip() or slug,
             "file": f"/docs/vivliothiki/{slug}.pdf",
             "class_slug": class_slug if class_slug in CLASS_SLUGS else "",
             "subject": subject.strip(), "pages": pages,
             "size": len(content),
             "added": datetime.now().isoformat(timespec="seconds")}
    books = [b for b in books if b["slug"] != slug] + [entry]
    save_json(BOOKS_JSON, books)
    rebuild_library_page()
    rebuild_nav()
    return {"ok": True, "book": entry}


@app.delete("/api/books/{slug}")
def api_books_delete(slug: str, request: Request):
    require_teacher(request)
    if not SLUG_RE.match(slug):
        raise HTTPException(400, "Μη έγκυρο slug.")
    books = load_json(BOOKS_JSON, [])
    if slug not in {b["slug"] for b in books}:
        raise HTTPException(404, "Το βιβλίο δεν βρέθηκε.")
    pdf = LIBRARY_DIR / f"{slug}.pdf"
    if pdf.is_file():
        backup_file(pdf)
        pdf.unlink()
    save_json(BOOKS_JSON, [b for b in books if b["slug"] != slug])
    rebuild_library_page()
    rebuild_nav()
    return {"ok": True}


@app.post("/api/books/link")
async def api_books_link(request: Request):
    """Εισαγωγή link βιβλίου με #page=N στο τέλος της κεφαλίδας ενός μαθήματος."""
    require_teacher(request)
    body = await request.json()
    slug = str(body.get("slug", "")).strip()
    page = int(body.get("page", 1))
    key = str(body.get("lesson_key", "")).split("/")
    if len(key) != 3:
        raise HTTPException(400, "Δώσε μάθημα (τάξη/μάθημα/φάκελος).")
    d = lesson_dir(*key)
    idx = d / "index.md"
    if not idx.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    book = next((b for b in load_json(BOOKS_JSON, []) if b["slug"] == slug), None)
    if not book:
        raise HTTPException(404, "Το βιβλίο δεν βρέθηκε.")
    max_p = book.get("pages") or 10000
    if not (1 <= page <= max_p):
        raise HTTPException(400, f"Η σελίδα πρέπει να είναι 1–{max_p}.")
    parsed = parse_lesson(idx.read_text(encoding="utf-8"))
    link = f"[📖 {book['title']}, σελ. {page}]({book['file']}#page={page}){{target=_blank}}"
    if link in parsed["header"]:
        return {"ok": True, "link": link, "already": True}
    parsed["header"] = parsed["header"].rstrip() + "\n\n" + link
    backup_file(idx)
    idx.write_text(render_lesson(parsed), encoding="utf-8")
    return {"ok": True, "link": link}


@app.post("/api/schedule/move")
async def api_schedule_move(request: Request):
    """Drag & drop κελιού: μετακίνηση (ή αντιγραφή με copy=true)."""
    require_teacher(request)
    body = await request.json()
    src = body.get("from", {}) or {}
    dst = body.get("to", {}) or {}
    s_tm, s_day, s_per = _validate_cell(src)
    d_tm, d_day, d_per = _validate_cell(dst)
    data = load_json(SCHEDULE_JSON, {"tmimata": [], "periods": [], "timetable": {}})
    entry = data["timetable"].get(s_tm, {}).get(s_day, {}).get(s_per)
    if not entry:
        raise HTTPException(400, "Το κελί προέλευσης είναι κενό.")
    data["timetable"].setdefault(d_tm, {}).setdefault(d_day, {})[d_per] = dict(entry)
    if not body.get("copy"):
        data["timetable"][s_tm][s_day].pop(s_per, None)
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    backup_file(SCHEDULE_JSON)
    save_json(SCHEDULE_JSON, data)
    return {"ok": True, "schedule": data}