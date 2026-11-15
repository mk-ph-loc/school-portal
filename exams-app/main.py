"""
Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

FastAPI εφαρμογή με SQLite για:
  * Παράδοση αρχείων εργασιών από μαθητές (χωρίς εγγραφή/login).
  * Ηλεκτρονικά τεστ/διαγωνίσματα με χρονόμετρο και αυτόματη υποβολή.
  * Περιβάλλον καθηγητή (κωδικός teacher2026): δημιουργία δραστηριοτήτων,
    διακόπτης Ενεργό/Κλειστό, βαθμολόγηση, λήψη ZIP αρχείων και CSV βαθμολογίας.

Τρέχει στο 127.0.0.1:8004 πίσω από τον Nginx στο /exams/.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "exams.db"
SUBMISSIONS_DIR = BASE_DIR / "submissions"
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)

TEACHER_CODE = "teacher2026"
COOKIE_NAME = "exams_teacher"
COOKIE_MAX_AGE = 8 * 3600            # μία σχολική ημέρα
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # ευθυγραμμισμένο με client_max_body_size 50M
ALLOWED_EXTENSIONS = {".py", ".docx", ".pdf", ".zip", ".txt", ".sb3", ".glo"}

CLASSES = [
    {"slug": "gymnasio-a", "label": "Α' Γυμνασίου"},
    {"slug": "gymnasio-b", "label": "Β' Γυμνασίου"},
    {"slug": "gymnasio-g", "label": "Γ' Γυμνασίου"},
    {"slug": "lykeio-a", "label": "Α' Λυκείου"},
    {"slug": "lykeio-b", "label": "Β' Λυκείου"},
    {"slug": "lykeio-g", "label": "Γ' Λυκείου"},
]
CLASS_SLUGS = {c["slug"] for c in CLASSES}
CLASS_LABELS = {c["slug"]: c["label"] for c in CLASSES}

# Αλφάβητο κωδικού επιβεβαίωσης χωρίς διφορούμενους χαρακτήρες (0/O, 1/I)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

app = FastAPI(
    title="Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα",
    description="Υποβολές εργασιών και ηλεκτρονικά διαγωνίσματα Πληροφορικής",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/exams) ορίζεται στο uvicorn μέσω του systemd unit,
# ώστε τα url_for() των templates να παράγουν σωστό πρόθεμα πίσω από τον Nginx.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Βάση δεδομένων (SQLite — ενσωματωμένη στην Python, χωρίς επιπλέον πακέτα)
# ---------------------------------------------------------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                class_slug  TEXT NOT NULL,
                kind        TEXT NOT NULL CHECK (kind IN ('assignment','test')),
                duration    INTEGER NOT NULL DEFAULT 0,   -- λεπτά (μόνο για test)
                questions   TEXT NOT NULL DEFAULT '[]',   -- JSON λίστα ερωτήσεων
                active      INTEGER NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id  INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
                code         TEXT NOT NULL UNIQUE,        -- κωδικός επιβεβαίωσης
                fullname     TEXT NOT NULL,
                section      TEXT NOT NULL,               -- τμήμα, π.χ. Α2
                comment      TEXT NOT NULL DEFAULT '',
                filename     TEXT NOT NULL DEFAULT '',    -- αποθηκευμένο όνομα στο δίσκο
                orig_name    TEXT NOT NULL DEFAULT '',    -- αρχικό όνομα αρχείου μαθητή
                answers      TEXT NOT NULL DEFAULT '{}',  -- JSON απαντήσεις τεστ
                mc_score     REAL,                        -- αυτόματη βαθμολογία MC
                mc_max       REAL,
                essay_scores TEXT NOT NULL DEFAULT '{}',  -- JSON βαθμοί ανάπτυξης
                total_score  REAL,
                max_score    REAL,
                started_at   REAL,                        -- έναρξη χρονόμετρου (test)
                deadline     REAL,                        -- λήξη χρονόμετρου (test)
                submitted_at REAL NOT NULL,
                auto_submit  INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_sub_activity ON submissions(activity_id);
            """
        )


init_db()


# ---------------------------------------------------------------------------
# Βοηθητικές συναρτήσεις
# ---------------------------------------------------------------------------
def greek_slug(text: str) -> str:
    """Μετατρέπει ελληνικό/λατινικό κείμενο σε ασφαλές όνομα αρχείου (Greeklish)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    greek_map = {
        "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
        "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
        "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
        "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
    }
    text = "".join(greek_map.get(ch, ch) for ch in text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "mathitis"


def new_code() -> str:
    """Μοναδικός κωδικός επιβεβαίωσης παράδοσης, π.χ. K7M2-9QXD."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def clean_name(value: str, limit: int = 120) -> str:
    """Καθαρίζει ονοματεπώνυμο/τμήμα από control χαρακτήρες και υπερβολικά κενά."""
    value = re.sub(r"\s+", " ", value).strip()
    value = "".join(ch for ch in value if ch.isprintable())
    return value[:limit]


def safe_upload_name(orig: str) -> str:
    """Επιστρέφει ασφαλές όνομα αρχείου με επιτρεπτή κατάληξη (αποτροπή traversal)."""
    base = Path(orig or "").name.strip()
    ext = Path(base).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "Επιτρέπονται μόνο αρχεία: " + ", ".join(sorted(ALLOWED_EXTENSIONS)),
        )
    stem = greek_slug(Path(base).stem)
    return f"{stem}{ext}"


# --- Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC), όχι απλό flag ---
def _secret_key() -> bytes:
    """Σταθερό μυστικό ανά εγκατάσταση (δημιουργείται μία φορά, εκτός git)."""
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


def activity_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "class_slug": row["class_slug"],
        "class_label": CLASS_LABELS.get(row["class_slug"], row["class_slug"]),
        "kind": row["kind"],
        "duration": row["duration"],
        "questions": json.loads(row["questions"]),
        "active": bool(row["active"]),
        "created_at": row["created_at"],
    }


def get_activity(conn: sqlite3.Connection, activity_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM activities WHERE id=?", (activity_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Η δραστηριότητα δεν βρέθηκε.")
    return row


def grade_submission(questions: list[dict], answers: dict, essay_scores: dict) -> dict:
    """Υπολογίζει αυτόματα τη βαθμολογία MC και αθροίζει τους βαθμούς ανάπτυξης."""
    mc_score = 0.0
    mc_max = 0.0
    essay_total = 0.0
    essay_max = 0.0
    for i, q in enumerate(questions):
        qid = str(i)
        points = float(q.get("points", 1))
        if q.get("type") == "mc":
            mc_max += points
            chosen = answers.get(qid)
            if chosen is not None and str(chosen) == str(q.get("correct")):
                mc_score += points
        else:
            essay_max += points
            try:
                val = float(essay_scores.get(qid, 0) or 0)
            except (TypeError, ValueError):
                val = 0.0
            essay_total += max(0.0, min(points, val))
    return {
        "mc_score": mc_score,
        "mc_max": mc_max,
        "total_score": mc_score + essay_total,
        "max_score": mc_max + essay_max,
    }


# ---------------------------------------------------------------------------
# Σελίδες (HTML)
# ---------------------------------------------------------------------------
def page_base(request: Request) -> str:
    """Base URL για τα σχετικά fetch URLs των σελίδων (/exams/ ή /exams/teacher/).

    ΣΗΜΕΙΩΣΗ: Με --root-path /exams και proxy_pass που αφαιρεί το prefix,
    το request.url.path περιέχει ήδη το πλήρες εξωτερικό μονοπάτι (/exams/…),
    οπότε ΔΕΝ προσθέτουμε ξανά το root_path (θα διπλασιαζόταν).
    """
    path = request.url.path.rstrip("/")
    return f"{path}/" if path else "/"


@app.get("/", response_class=HTMLResponse)
def student_page(request: Request):
    return templates.TemplateResponse(
        request, "student.html", {"classes": CLASSES, "base": page_base(request)}
    )


@app.get("/teacher", response_class=HTMLResponse)
def teacher_page(request: Request):
    return templates.TemplateResponse(
        request,
        "teacher.html",
        {
            "classes": CLASSES,
            "logged_in": token_valid(request.cookies.get(COOKIE_NAME)),
            "base": page_base(request),
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "school-exams"}


# ---------------------------------------------------------------------------
# API Μαθητή — ελεύθερο, χωρίς εγγραφή
# ---------------------------------------------------------------------------
@app.get("/api/activities")
def list_active_activities(class_slug: str = ""):
    """Ενεργές δραστηριότητες, φιλτραρισμένες ανά τάξη (χωρίς τις σωστές απαντήσεις)."""
    if class_slug and class_slug not in CLASS_SLUGS:
        raise HTTPException(400, "Άγνωστη τάξη.")
    with db() as conn:
        if class_slug:
            rows = conn.execute(
                "SELECT * FROM activities WHERE active=1 AND class_slug=? ORDER BY id DESC",
                (class_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM activities WHERE active=1 ORDER BY id DESC"
            ).fetchall()
    out = []
    for row in rows:
        a = activity_row(row)
        # Ο μαθητής ΔΕΝ βλέπει ποτέ το πεδίο correct των MC ερωτήσεων.
        a["questions"] = [
            {k: v for k, v in q.items() if k != "correct"} for q in a["questions"]
        ]
        a["question_count"] = len(a["questions"])
        out.append(a)
    return {"activities": out}


class StartTest(BaseModel):
    fullname: str = Field(min_length=3, max_length=120)
    section: str = Field(min_length=1, max_length=20)


@app.post("/api/activities/{activity_id}/start")
def start_test(activity_id: int, payload: StartTest):
    """Έναρξη διαγωνίσματος: ο server ορίζει τη λήξη (αξιόπιστο χρονόμετρο)."""
    fullname = clean_name(payload.fullname)
    section = clean_name(payload.section, 20).upper()
    if len(fullname) < 3 or not section:
        raise HTTPException(400, "Συμπλήρωσε ονοματεπώνυμο και τμήμα.")
    with db() as conn:
        row = get_activity(conn, activity_id)
        if not row["active"]:
            raise HTTPException(403, "Η δραστηριότητα είναι κλειστή.")
        if row["kind"] != "test":
            raise HTTPException(400, "Η δραστηριότητα δεν είναι διαγώνισμα.")
        a = activity_row(row)
        now = time.time()
        deadline = now + max(1, row["duration"]) * 60
        code = new_code()
        cur = conn.execute(
            """INSERT INTO submissions
               (activity_id, code, fullname, section, started_at, deadline, submitted_at)
               VALUES (?,?,?,?,?,?,0)""",
            (activity_id, code, fullname, section, now, deadline),
        )
        sub_id = cur.lastrowid
    questions = [{k: v for k, v in q.items() if k != "correct"} for q in a["questions"]]
    return {
        "submission_id": sub_id,
        "code": code,
        "deadline": deadline,
        "server_now": now,
        "duration": a["duration"],
        "title": a["title"],
        "questions": questions,
    }


class SubmitTest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    auto: bool = False


@app.post("/api/submissions/{submission_id}/submit-test")
def submit_test(submission_id: int, payload: SubmitTest):
    """Οριστική υποβολή διαγωνίσματος (χειροκίνητη ή αυτόματη στο μηδενισμό)."""
    with db() as conn:
        sub = conn.execute(
            "SELECT * FROM submissions WHERE id=?", (submission_id,)
        ).fetchone()
        if sub is None:
            raise HTTPException(404, "Η υποβολή δεν βρέθηκε.")
        if sub["submitted_at"]:
            # Ήδη υποβλήθηκε (π.χ. διπλό κλικ / auto+manual): επέστρεψε τον ίδιο κωδικό.
            return {"code": sub["code"], "already": True}
        row = get_activity(conn, sub["activity_id"])
        questions = json.loads(row["questions"])
        now = time.time()
        # Περιθώριο 30s για latency δικτύου· πέρα από αυτό θεωρείται εκπρόθεσμη-auto.
        expired = sub["deadline"] and now > sub["deadline"] + 30
        auto = bool(payload.auto or expired)
        answers = {str(k): v for k, v in payload.answers.items()}
        grades = grade_submission(questions, answers, {})
        conn.execute(
            """UPDATE submissions
               SET answers=?, mc_score=?, mc_max=?, total_score=?, max_score=?,
                   submitted_at=?, auto_submit=?
               WHERE id=?""",
            (
                json.dumps(answers, ensure_ascii=False),
                grades["mc_score"], grades["mc_max"],
                grades["total_score"], grades["max_score"],
                now, int(auto), submission_id,
            ),
        )
    return {"code": sub["code"], "auto": auto}


@app.post("/api/activities/{activity_id}/submit-file")
async def submit_file(
    activity_id: int,
    fullname: str = Form(...),
    section: str = Form(...),
    comment: str = Form(""),
    file: UploadFile = File(...),
):
    """Παράδοση αρχείου εργασίας με μοναδικό κωδικό επιβεβαίωσης."""
    fullname = clean_name(fullname)
    section = clean_name(section, 20).upper()
    comment = clean_name(comment, 1000)
    if len(fullname) < 3 or not section:
        raise HTTPException(400, "Συμπλήρωσε ονοματεπώνυμο και τμήμα.")

    safe_name = safe_upload_name(file.filename or "")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το αρχείο υπερβαίνει τα 50 MB.")
    if not data:
        raise HTTPException(400, "Το αρχείο είναι κενό.")

    with db() as conn:
        row = get_activity(conn, activity_id)
        if not row["active"]:
            raise HTTPException(403, "Η δραστηριότητα είναι κλειστή.")
        if row["kind"] != "assignment":
            raise HTTPException(400, "Η δραστηριότητα δεν είναι παράδοση εργασίας.")
        code = new_code()
        # Αποθήκευση: submissions/<activity_id>/<code>_<ασφαλές όνομα>
        act_dir = SUBMISSIONS_DIR / str(activity_id)
        act_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{code}_{safe_name}"
        target = (act_dir / stored_name).resolve()
        if act_dir.resolve() not in target.parents:
            raise HTTPException(400, "Μη έγκυρο όνομα αρχείου.")
        target.write_bytes(data)
        conn.execute(
            """INSERT INTO submissions
               (activity_id, code, fullname, section, comment, filename, orig_name,
                submitted_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (activity_id, code, fullname, section, comment,
             stored_name, Path(file.filename or "").name[:200], time.time()),
        )
    return {"code": code, "filename": Path(file.filename or "").name}


# ---------------------------------------------------------------------------
# API Καθηγητή — προστατευμένο με κωδικό teacher2026 (HMAC cookie)
# ---------------------------------------------------------------------------
class Login(BaseModel):
    password: str


@app.post("/api/teacher/login")
def teacher_login(payload: Login, response: Response):
    if not hmac.compare_digest(payload.password, TEACHER_CODE):
        raise HTTPException(401, "Λανθασμένος κωδικός καθηγητή.")
    response.set_cookie(
        COOKIE_NAME, make_token(),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
    )
    return {"ok": True}


@app.post("/api/teacher/logout")
def teacher_logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


class QuestionIn(BaseModel):
    type: str = Field(pattern="^(mc|essay)$")
    text: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(default_factory=list)
    correct: int | None = None
    points: float = Field(default=1, ge=0, le=100)


class ActivityIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    class_slug: str
    kind: str = Field(pattern="^(assignment|test)$")
    duration: int = Field(default=0, ge=0, le=300)
    questions: list[QuestionIn] = Field(default_factory=list)
    active: bool = False


def validate_activity(payload: ActivityIn) -> list[dict]:
    if payload.class_slug not in CLASS_SLUGS:
        raise HTTPException(400, "Άγνωστη τάξη.")
    questions: list[dict] = []
    if payload.kind == "test":
        if payload.duration < 1:
            raise HTTPException(400, "Το διαγώνισμα απαιτεί διάρκεια ≥ 1 λεπτό.")
        if not payload.questions:
            raise HTTPException(400, "Το διαγώνισμα απαιτεί τουλάχιστον μία ερώτηση.")
        for q in payload.questions:
            item = {
                "type": q.type,
                "text": q.text.strip(),
                "points": q.points,
            }
            if q.type == "mc":
                opts = [o.strip() for o in q.options if o.strip()]
                if len(opts) < 2:
                    raise HTTPException(400, "Κάθε ερώτηση πολλαπλής επιλογής χρειάζεται ≥ 2 επιλογές.")
                if q.correct is None or not (0 <= q.correct < len(opts)):
                    raise HTTPException(400, "Όρισε τη σωστή επιλογή για κάθε ερώτηση πολλαπλής επιλογής.")
                item["options"] = opts[:8]
                item["correct"] = q.correct
            questions.append(item)
    return questions


@app.get("/api/teacher/activities")
def teacher_activities(request: Request):
    require_teacher(request)
    with db() as conn:
        rows = conn.execute("SELECT * FROM activities ORDER BY id DESC").fetchall()
        counts = dict(conn.execute(
            "SELECT activity_id, COUNT(*) FROM submissions WHERE submitted_at>0 GROUP BY activity_id"
        ).fetchall())
    out = []
    for row in rows:
        a = activity_row(row)
        a["submission_count"] = counts.get(a["id"], 0)
        out.append(a)
    return {"activities": out}


@app.post("/api/teacher/activities")
def create_activity(payload: ActivityIn, request: Request):
    require_teacher(request)
    questions = validate_activity(payload)
    with db() as conn:
        cur = conn.execute(
            """INSERT INTO activities (title, class_slug, kind, duration, questions, active, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (payload.title.strip(), payload.class_slug, payload.kind,
             payload.duration if payload.kind == "test" else 0,
             json.dumps(questions, ensure_ascii=False),
             int(payload.active), time.time()),
        )
        row = get_activity(conn, cur.lastrowid)
    return activity_row(row)


class ToggleIn(BaseModel):
    active: bool


@app.patch("/api/teacher/activities/{activity_id}")
def toggle_activity(activity_id: int, payload: ToggleIn, request: Request):
    """Διακόπτης Ενεργό/Κλειστό — ανοίγει μόνο την ώρα του μαθήματος."""
    require_teacher(request)
    with db() as conn:
        get_activity(conn, activity_id)
        conn.execute(
            "UPDATE activities SET active=? WHERE id=?", (int(payload.active), activity_id)
        )
    return {"ok": True, "active": payload.active}


@app.delete("/api/teacher/activities/{activity_id}")
def delete_activity(activity_id: int, request: Request):
    require_teacher(request)
    with db() as conn:
        get_activity(conn, activity_id)
        conn.execute("DELETE FROM submissions WHERE activity_id=?", (activity_id,))
        conn.execute("DELETE FROM activities WHERE id=?", (activity_id,))
    act_dir = SUBMISSIONS_DIR / str(activity_id)
    if act_dir.is_dir():
        for f in act_dir.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
        act_dir.rmdir()
    return {"ok": True}


@app.get("/api/teacher/activities/{activity_id}/submissions")
def list_submissions(activity_id: int, request: Request):
    """Πίνακας υποβολών με αυτόματη βαθμολογία MC και απαντήσεις ανάπτυξης."""
    require_teacher(request)
    with db() as conn:
        row = get_activity(conn, activity_id)
        subs = conn.execute(
            """SELECT * FROM submissions
               WHERE activity_id=? AND submitted_at>0
               ORDER BY section, fullname""",
            (activity_id,),
        ).fetchall()
    a = activity_row(row)
    out = []
    for s in subs:
        out.append({
            "id": s["id"],
            "code": s["code"],
            "fullname": s["fullname"],
            "section": s["section"],
            "comment": s["comment"],
            "orig_name": s["orig_name"],
            "has_file": bool(s["filename"]),
            "answers": json.loads(s["answers"]),
            "mc_score": s["mc_score"],
            "mc_max": s["mc_max"],
            "essay_scores": json.loads(s["essay_scores"]),
            "total_score": s["total_score"],
            "max_score": s["max_score"],
            "submitted_at": s["submitted_at"],
            "auto_submit": bool(s["auto_submit"]),
        })
    return {"activity": a, "submissions": out}


class GradeIn(BaseModel):
    essay_scores: dict[str, float] = Field(default_factory=dict)


@app.post("/api/teacher/submissions/{submission_id}/grade")
def grade_essay(submission_id: int, payload: GradeIn, request: Request):
    """Βαθμολόγηση ερωτήσεων ανάπτυξης/κώδικα από τον καθηγητή."""
    require_teacher(request)
    with db() as conn:
        sub = conn.execute(
            "SELECT * FROM submissions WHERE id=?", (submission_id,)
        ).fetchone()
        if sub is None:
            raise HTTPException(404, "Η υποβολή δεν βρέθηκε.")
        row = get_activity(conn, sub["activity_id"])
        questions = json.loads(row["questions"])
        answers = json.loads(sub["answers"])
        scores = {str(k): v for k, v in payload.essay_scores.items()}
        grades = grade_submission(questions, answers, scores)
        conn.execute(
            """UPDATE submissions
               SET essay_scores=?, mc_score=?, mc_max=?, total_score=?, max_score=?
               WHERE id=?""",
            (json.dumps(scores), grades["mc_score"], grades["mc_max"],
             grades["total_score"], grades["max_score"], submission_id),
        )
    return {"ok": True, **grades}


def zip_entry_name(sub: sqlite3.Row) -> str:
    """Τμήμα_Ονοματεπώνυμο_αρχείο — Greeklish για συμβατότητα με κάθε unzip."""
    ext = Path(sub["orig_name"] or sub["filename"]).suffix.lower() or ".txt"
    section = greek_slug(sub["section"])
    name = greek_slug(sub["fullname"])
    stem = greek_slug(Path(sub["orig_name"] or "ergasia").stem)
    return f"{section}_{name}_{stem}{ext}"


@app.get("/api/teacher/submissions/{submission_id}/file")
def download_submission_file(submission_id: int, request: Request):
    """Λήψη μεμονωμένου αρχείου μαθητή (μόνο καθηγητής)."""
    require_teacher(request)
    with db() as conn:
        sub = conn.execute(
            "SELECT * FROM submissions WHERE id=?", (submission_id,)
        ).fetchone()
    if sub is None or not sub["filename"]:
        raise HTTPException(404, "Δεν υπάρχει αρχείο για αυτή την υποβολή.")
    path = (SUBMISSIONS_DIR / str(sub["activity_id"]) / sub["filename"]).resolve()
    if not path.is_file():
        raise HTTPException(404, "Το αρχείο δεν βρέθηκε στον δίσκο.")
    nice = zip_entry_name(sub)
    return StreamingResponse(
        io.BytesIO(path.read_bytes()),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nice)}"},
    )


@app.get("/api/teacher/activities/{activity_id}/zip")
def download_zip(activity_id: int, request: Request):
    """Λήψη όλων των αρχείων της δραστηριότητας σε ένα ZIP (Τμήμα_Ονοματεπώνυμο_αρχείο)."""
    require_teacher(request)
    with db() as conn:
        row = get_activity(conn, activity_id)
        subs = conn.execute(
            """SELECT * FROM submissions
               WHERE activity_id=? AND submitted_at>0 AND filename!=''
               ORDER BY section, fullname""",
            (activity_id,),
        ).fetchall()
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for s in subs:
            path = SUBMISSIONS_DIR / str(activity_id) / s["filename"]
            if not path.is_file():
                continue
            entry = zip_entry_name(s)
            # Αποφυγή συνωνυμιών (ίδιο τμήμα/όνομα): πρόσθεσε τον κωδικό υποβολής.
            if entry in used:
                entry = f"{Path(entry).stem}_{s['code']}{Path(entry).suffix}"
            used.add(entry)
            zf.write(path, entry)
    if not used:
        raise HTTPException(404, "Δεν υπάρχουν αρχεία προς λήψη για αυτή τη δραστηριότητα.")
    buf.seek(0)
    fname = f"{greek_slug(row['title'])}_arxeia.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


def fmt_num(value: Any) -> str:
    """Ελληνικό δεκαδικό κόμμα για το CSV· κενό για μη βαθμολογημένα."""
    if value is None or value == "":
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{num:g}".replace(".", ",")


@app.get("/api/teacher/activities/{activity_id}/csv")
def export_csv(activity_id: int, request: Request):
    """Εξαγωγή βαθμολογίας σε CSV (UTF-8 με BOM για σωστά ελληνικά στο Excel)."""
    require_teacher(request)
    with db() as conn:
        row = get_activity(conn, activity_id)
        subs = conn.execute(
            """SELECT * FROM submissions
               WHERE activity_id=? AND submitted_at>0
               ORDER BY section, fullname""",
            (activity_id,),
        ).fetchall()
    a = activity_row(row)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    header = ["Κωδικός", "Τμήμα", "Ονοματεπώνυμο", "Ημ/νία Υποβολής", "Αυτόματη Υποβολή"]
    if a["kind"] == "test":
        header += ["Βαθμός MC", "Μέγιστο MC", "Βαθμός Ανάπτυξης", "Σύνολο", "Μέγιστο"]
        for i, q in enumerate(a["questions"], 1):
            label = "Πολλαπλής" if q["type"] == "mc" else "Ανάπτυξης"
            header.append(f"Ε{i} ({label})")
    else:
        header += ["Αρχείο", "Σχόλιο"]
    writer.writerow(header)
    for s in subs:
        when = time.strftime("%d/%m/%Y %H:%M", time.localtime(s["submitted_at"]))
        base = [s["code"], s["section"], s["fullname"], when,
                "ΝΑΙ" if s["auto_submit"] else "ΟΧΙ"]
        if a["kind"] == "test":
            answers = json.loads(s["answers"])
            essay_scores = json.loads(s["essay_scores"])
            essay_total = (s["total_score"] or 0) - (s["mc_score"] or 0)
            base += [fmt_num(s["mc_score"]), fmt_num(s["mc_max"]),
                     fmt_num(essay_total), fmt_num(s["total_score"]),
                     fmt_num(s["max_score"])]
            for i, q in enumerate(a["questions"]):
                qid = str(i)
                if q["type"] == "mc":
                    chosen = answers.get(qid)
                    if chosen is None or chosen == "":
                        base.append("(κενό)")
                    else:
                        idx = int(chosen)
                        opts = q.get("options", [])
                        base.append(opts[idx] if 0 <= idx < len(opts) else str(chosen))
                else:
                    base.append(fmt_num(essay_scores.get(qid, "")))
        else:
            base += [s["orig_name"], s["comment"]]
        writer.writerow(base)
    data = "\ufeff" + buf.getvalue()  # BOM ώστε το Excel να αναγνωρίζει UTF-8
    fname = f"{greek_slug(row['title'])}_vathmologia.csv"
    return Response(
        content=data.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )