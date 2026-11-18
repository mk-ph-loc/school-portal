"""
Classroom Hub — Ζωντανή Τάξη (Ψηφιακή Πύλη Σχολείου).

Κεντρικό παράθυρο (/classroom/) με μόνιμο μενού (Μαθήματα, Ανακοινώσεις, Chat,
Forum, Βοήθεια — διαμορφώσιμα ανά ρόλο από Excel) όπου ΟΛΕΣ οι εφαρμογές της
πύλης ανοίγουν μέσα σε iframe. Ο server παρακολουθεί συνεχώς ποιος είναι
συνδεδεμένος (guest / μαθητής / καθηγητής) μέσω WebSocket heartbeat και
ανταλλάσσει εντολές:

  * ανακοινώσεις / συγχαρητήρια / βραβεία (και τυχαία επιλογή μαθητή),
  * δημοσκοπήσεις (poll) με επιλογή «βλέπουν όλοι τα αποτελέσματα»,
  * υποχρεωτική μετάβαση μαθητών & guests σε συγκεκριμένη σελίδα,
  * αποστολή quiz — στους μαθητές ΚΑΤΑΓΡΑΦΕΤΑΙ το αποτέλεσμα (SQLite),
    στους guests γίνεται μόνο εξάσκηση (χωρίς καταγραφή),
  * χρονομετρητές ιδιωτικοί ή δημόσιοι, συγχρονισμένοι με το ωράριο του
    σχολείου (anchor σε διδακτική ώρα + offset ±λεπτών),
  * γεγονότα στο τέλος ημέρας/ώρας, chat τάξης & forum νημάτων.

Οι guests παίρνουν παιχνιδιάρικα ονόματα τύπου Google Docs («Γενναίος
Πάνθηρας»…) από τις λίστες του Excel. Όλες οι ρυθμίσεις περνούν από ΕΝΙΑΙΟ
πρότυπο Excel (rythmiseis-protypo.xlsx, 12 καρτέλες με χρωματικούς κώδικες)
που περιλαμβάνει ΑΥΤΟΥΣΙΟ το πρότυπο ωραρίου του Lesson Wizard (Τμήματα /
Ωρες / Ωραριο) — το ίδιο αρχείο ανεβαίνει και στα δύο apps.

Τρέχει στο 127.0.0.1:8014 πίσω από τον Nginx στο /classroom/ (WebSockets).
Χωρίς Docker· ένας worker (βλ. systemd school-classroom.service).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import random
import re
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent.parent                    # apps/classroom-hub → /opt/school-portal
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "classroom.db"
CONFIG_JSON = DATA_DIR / "config.json"                 # αποτέλεσμα του Excel upload
TEMPLATE_XLSX = DATA_DIR / "rythmiseis-protypo.xlsx"   # ενιαίο πρότυπο όλων των ρυθμίσεων
LW_SCHEDULE_JSON = PORTAL_DIR / "apps" / "lesson-wizard" / "data" / "schedule.json"

TEACHER_CODE = "teacher2026"                           # ίδιος κωδικός με όλη την πύλη
COOKIE_NAME = "classroom_teacher"
IDENT_COOKIE = "classroom_ident"                       # HttpOnly HMAC ταυτότητα σύνδεσης
COOKIE_MAX_AGE = 8 * 3600                              # μία σχολική ημέρα

HEARTBEAT_TIMEOUT = 45                                 # χωρίς ping τόσο → αποσύνδεση
DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή"]
ROLES = ("guest", "student", "teacher")
NAME_RE = re.compile(r"^[\w\u0370-\u03ff\u1f00-\u1fff .'-]{1,40}$")

app = FastAPI(
    title="Classroom Hub — Ζωντανή Τάξη",
    description="Παρουσία, εντολές τάξης, timers ωραρίου & ενιαίες ρυθμίσεις Excel",
    docs_url=None, redoc_url=None, openapi_url=None,
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση: HMAC cookies (ίδιο μοτίβο με lesson-wizard / live-quiz)
# ---------------------------------------------------------------------------
def _secret_key() -> bytes:
    key_file = BASE_DIR / ".cookie-secret"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
        key_file.chmod(0o600)
    return key_file.read_text().strip().encode()


SECRET_KEY = _secret_key()


def make_token(payload: str, max_age: int = COOKIE_MAX_AGE) -> str:
    # base64url: τα ονόματα είναι ελληνικά — τα cookies πρέπει να είναι latin-1 safe
    expires = int(time.time()) + max_age
    b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    body = f"{expires}:{b64}"
    sig = hmac.new(SECRET_KEY, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def token_payload(token: str | None) -> str | None:
    """Επιστρέφει το payload αν η υπογραφή & η λήξη είναι έγκυρες, αλλιώς None."""
    if not token or "." not in token:
        return None
    body, _, sig = token.rpartition(".")
    expected = hmac.new(SECRET_KEY, body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    exp, _, b64 = body.partition(":")
    try:
        if int(exp) <= time.time():
            return None
        return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def is_teacher(request: Request) -> bool:
    return token_payload(request.cookies.get(COOKIE_NAME)) == "teacher"


def require_teacher(request: Request) -> None:
    if not is_teacher(request):
        raise HTTPException(401, "Απαιτείται κωδικός καθηγητή.")


def identity_from(request: Request) -> dict | None:
    """Ταυτότητα σύνδεσης από το HMAC ident cookie (uid|role|name|tmima)."""
    payload = token_payload(request.cookies.get(IDENT_COOKIE))
    if not payload:
        return None
    parts = payload.split("|")
    if len(parts) != 4 or parts[1] not in ROLES:
        return None
    return {"uid": parts[0], "role": parts[1], "name": parts[2], "tmima": parts[3]}


def set_identity(response: Response, uid: str, role: str, name: str, tmima: str) -> None:
    response.set_cookie(IDENT_COOKIE, make_token(f"{uid}|{role}|{name}|{tmima}"),
                        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/")


# ---------------------------------------------------------------------------
# SQLite — chat, forum, polls, quiz & αποτελέσματα (μόνο μαθητών)
# ---------------------------------------------------------------------------
def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL, uid TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL, tmima TEXT NOT NULL DEFAULT '', text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS forum_threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL, uid TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL, title TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS forum_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER NOT NULL REFERENCES forum_threads(id) ON DELETE CASCADE,
            ts REAL NOT NULL, uid TEXT NOT NULL, name TEXT NOT NULL,
            role TEXT NOT NULL, text TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_posts_thread ON forum_posts(thread_id);
        CREATE TABLE IF NOT EXISTS polls (
            id TEXT PRIMARY KEY, ts REAL NOT NULL, question TEXT NOT NULL,
            options TEXT NOT NULL, show_results INTEGER NOT NULL DEFAULT 1,
            audience TEXT NOT NULL DEFAULT 'all', closed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS poll_votes (
            poll_id TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            uid TEXT NOT NULL, choice INTEGER NOT NULL,
            PRIMARY KEY (poll_id, uid)
        );
        CREATE TABLE IF NOT EXISTS quizzes (
            id TEXT PRIMARY KEY, ts REAL NOT NULL, title TEXT NOT NULL,
            questions TEXT NOT NULL, audience TEXT NOT NULL DEFAULT 'all',
            closed INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id TEXT NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
            ts REAL NOT NULL, uid TEXT NOT NULL, name TEXT NOT NULL,
            tmima TEXT NOT NULL DEFAULT '', score INTEGER NOT NULL,
            total INTEGER NOT NULL, answers TEXT NOT NULL,
            UNIQUE (quiz_id, uid)
        );
        """)


init_db()




# ---------------------------------------------------------------------------
# Προεπιλεγμένες ρυθμίσεις — αντικαθίστανται/εμπλουτίζονται από το Excel
# ---------------------------------------------------------------------------
DEFAULT_ADJ = ["Γενναίος", "Χαμογελαστός", "Περιπετειώδης", "Έξυπνος", "Τολμηρός",
               "Φιλικός", "Αστραφτερός", "Ήρεμος", "Δημιουργικός", "Παιχνιδιάρης",
               "Λαμπερός", "Γρήγορος", "Σοφός", "Καλοσυνάτος", "Μυστηριώδης"]
DEFAULT_NOUNS = [("Πάνθηρας", "🐆"), ("Αστροναύτης", "🚀"), ("Δελφίνι", "🐬"),
                 ("Αλεπού", "🦊"), ("Κουκουβάγια", "🦉"), ("Πιγκουίνος", "🐧"),
                 ("Δράκος", "🐉"), ("Ρομπότ", "🤖"), ("Εξερευνητής", "🧭"),
                 ("Γάτος", "🐱"), ("Πάντα", "🐼"), ("Χταπόδι", "🐙"),
                 ("Μονόκερος", "🦄"), ("Αετός", "🦅"), ("Χελώνα", "🐢")]
GUEST_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6",
                "#3b82f6", "#8b5cf6", "#ec4899", "#0ea5e9", "#84cc16"]

DEFAULT_CONFIG: dict = {
    "schedule": {"tmimata": [], "periods": [], "timetable": {}},
    "menu": [
        {"id": "mathimata", "title": "Μαθήματα", "icon": "📚", "url": "/docs/",
         "order": 1, "guest": True, "student": True, "teacher": True},
        {"id": "anakoinoseis", "title": "Ανακοινώσεις", "icon": "📣", "url": "#announcements",
         "order": 2, "guest": True, "student": True, "teacher": True},
        {"id": "chat", "title": "Chat", "icon": "💬", "url": "#chat",
         "order": 3, "guest": True, "student": True, "teacher": True},
        {"id": "forum", "title": "Forum", "icon": "🗂️", "url": "#forum",
         "order": 4, "guest": False, "student": True, "teacher": True},
        {"id": "voitheia", "title": "Βοήθεια", "icon": "❓", "url": "#help",
         "order": 5, "guest": True, "student": True, "teacher": True},
    ],
    "toolbars": [
        {"id": "roster", "title": "👥 Συνδεδεμένοι", "mode": "dock", "x": 20, "y": 90,
         "w": 300, "h": 380, "guest": False, "student": False, "teacher": True},
        {"id": "commands", "title": "🎛️ Εντολές Τάξης", "mode": "dock", "x": 20, "y": 90,
         "w": 340, "h": 480, "guest": False, "student": False, "teacher": True},
        {"id": "timer", "title": "⏱️ Χρονομετρητής", "mode": "float", "x": 60, "y": 120,
         "w": 280, "h": 200, "guest": True, "student": True, "teacher": True},
        {"id": "chat", "title": "💬 Chat Τάξης", "mode": "dock", "x": 20, "y": 90,
         "w": 320, "h": 420, "guest": True, "student": True, "teacher": True},
    ],
    "access": {"student_code": "", "guest_chat": True, "guest_forum": False,
               "allowed_apps": {"guest": "*", "student": "*", "teacher": "*"}},
    "guest_names": {"adjectives": DEFAULT_ADJ,
                    "nouns": [{"name": n, "emoji": e} for n, e in DEFAULT_NOUNS],
                    "colors": GUEST_COLORS},
    "timers": [],       # ορίζονται από Excel ή ζωντανά από τον καθηγητή
    "events": [],       # γεγονότα τέλους ημέρας/ώρας από Excel
    "messages": [],     # πρότυπα ανακοινώσεων/συγχαρητηρίων/βραβείων
    "polls_bank": [],   # έτοιμες δημοσκοπήσεις
    "quizzes_bank": [], # τράπεζα quiz για γρήγορη αποστολή
    "updated": None,
}



def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))       # deep copy
    if CONFIG_JSON.exists():
        try:
            saved = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
            for k, v in saved.items():
                if v not in (None, [], {}, ""):
                    cfg[k] = v
        except (OSError, ValueError):
            pass
    # Αν δεν υπάρχει δικό μας ωράριο, δανειζόμαστε του Lesson Wizard (ίδιο JSON)
    if not cfg["schedule"]["tmimata"] and LW_SCHEDULE_JSON.exists():
        try:
            cfg["schedule"] = json.loads(LW_SCHEDULE_JSON.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg["updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = CONFIG_JSON.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_JSON)


CONFIG = load_config()


def guest_name() -> dict:
    """Παιχνιδιάρικο όνομα τύπου Google Docs: επίθετο + ζώο/ρόλος + emoji."""
    gn = CONFIG["guest_names"]
    adj = random.choice(gn["adjectives"] or DEFAULT_ADJ)
    noun = random.choice(gn["nouns"] or [{"name": n, "emoji": e} for n, e in DEFAULT_NOUNS])
    return {"name": f"{adj} {noun['name']}", "emoji": noun.get("emoji", "🎲"),
            "color": random.choice(gn["colors"] or GUEST_COLORS)}



# ---------------------------------------------------------------------------
# Ζωντανή παρουσία & WebSockets (ένα event loop, ένας worker — βλ. systemd)
# ---------------------------------------------------------------------------
class Client:
    """Μία ενεργή σύνδεση shell (browser καρτέλα)."""

    def __init__(self, ws: WebSocket, ident: dict) -> None:
        self.ws = ws
        self.uid = ident["uid"]
        self.role = ident["role"]
        self.name = ident["name"]
        self.tmima = ident.get("tmima", "")
        self.emoji = ident.get("emoji", {"guest": "🎲", "student": "👨‍🎓", "teacher": "🧑‍🏫"}[ident["role"]])
        self.color = ident.get("color", "#3b82f6")
        self.page = ""                                  # ποια εφαρμογή βλέπει τώρα
        self.last_ping = time.time()
        self.connected_at = time.time()

    def public(self) -> dict:
        return {"uid": self.uid, "role": self.role, "name": self.name,
                "tmima": self.tmima, "emoji": self.emoji, "color": self.color,
                "page": self.page, "connected_at": self.connected_at}


CLIENTS: dict[int, Client] = {}                         # key = id(ws)
ANNOUNCEMENTS: list[dict] = []                          # τελευταίες ανακοινώσεις (μνήμη)
ACTIVE_TIMERS: dict[str, dict] = {}                     # id → {label, ends_at, audience, tmima}
ACTIVE_POLLS: dict[str, dict] = {}                      # id → κατάσταση poll
ACTIVE_QUIZZES: dict[str, dict] = {}                    # id → κατάσταση quiz


async def send_json(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        pass  # η σύνδεση θα καθαριστεί στο receive loop / sweeper


def audience_match(c: Client, audience: str, tmima: str = "") -> bool:
    """audience: all | students (μαθητές+guests) | guests | teachers | role:X· + φίλτρο τμήματος."""
    if tmima and c.tmima != tmima:
        return False
    if audience == "all":
        return True
    if audience == "students":
        return c.role in ("student", "guest")
    if audience == "guests":
        return c.role == "guest"
    if audience == "teachers":
        return c.role == "teacher"
    if audience.startswith("role:"):
        return c.role == audience[5:]
    return True


async def broadcast(payload: dict, audience: str = "all", tmima: str = "",
                    exclude_uid: str = "") -> int:
    n = 0
    for c in list(CLIENTS.values()):
        if c.uid == exclude_uid:
            continue
        if audience_match(c, audience, tmima):
            await send_json(c.ws, payload)
            n += 1
    return n


async def send_to_uid(uid: str, payload: dict) -> None:
    for c in list(CLIENTS.values()):
        if c.uid == uid:
            await send_json(c.ws, payload)


def roster_payload() -> dict:
    return {"type": "roster", "clients": [c.public() for c in CLIENTS.values()],
            "server_now": time.time()}


async def push_roster() -> None:
    await broadcast(roster_payload(), audience="teachers")


def clean_name(v: str) -> str:
    v = str(v or "").strip()
    if not NAME_RE.match(v):
        raise HTTPException(400, "Μη έγκυρο όνομα (έως 40 χαρακτήρες, γράμματα/ψηφία).")
    return v


# ---------------------------------------------------------------------------
# Routes — σελίδα, είσοδος ανά ρόλο, δημόσια ρυθμίσεις
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"status": "ok", "clients": len(CLIENTS)}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/me")
def api_me(request: Request):
    ident = identity_from(request)
    if ident and is_teacher(request):
        ident["role"] = "teacher"                       # ο κωδικός καθηγητή υπερισχύει
    return {"identity": ident, "teacher": is_teacher(request)}


@app.post("/api/join")
async def api_join(request: Request, response: Response):
    """Είσοδος: role=guest (τυχαίο όνομα), student (όνομα+τμήμα+κωδικός τάξης),
    teacher (κωδικός teacher2026). Εκδίδει HMAC ident cookie για το WebSocket."""
    body = await request.json()
    role = str(body.get("role", "guest")).strip()
    uid = secrets.token_hex(8)
    if role == "teacher":
        if str(body.get("code", "")) != TEACHER_CODE:
            raise HTTPException(403, "Λάθος κωδικός καθηγητή.")
        name = clean_name(body.get("name") or "Καθηγητής")
        ident = {"uid": uid, "role": "teacher", "name": name, "tmima": "",
                 "emoji": "🧑‍🏫", "color": "#10b981"}
        response.set_cookie(COOKIE_NAME, make_token("teacher"), max_age=COOKIE_MAX_AGE,
                            httponly=True, samesite="lax", path="/")
    elif role == "student":
        name = clean_name(body.get("name"))
        tmima = str(body.get("tmima", "")).strip()
        known = {t["name"] for t in CONFIG["schedule"]["tmimata"]}
        if known and tmima not in known:
            raise HTTPException(400, f"Άγνωστο τμήμα '{tmima}'. Διάλεξε από τη λίστα.")
        code_needed = CONFIG["access"].get("student_code", "")
        if code_needed and str(body.get("code", "")) != code_needed:
            raise HTTPException(403, "Λάθος κωδικός τάξης.")
        ident = {"uid": uid, "role": "student", "name": name, "tmima": tmima,
                 "emoji": "👨‍🎓", "color": random.choice(GUEST_COLORS)}
    else:
        role = "guest"
        gn = guest_name()
        ident = {"uid": uid, "role": "guest", "name": gn["name"], "tmima": "",
                 "emoji": gn["emoji"], "color": gn["color"]}
    set_identity(response, ident["uid"], ident["role"], ident["name"], ident["tmima"])
    return {"ok": True, "identity": ident}


@app.post("/api/leave")
def api_leave(request: Request, response: Response):
    response.delete_cookie(IDENT_COOKIE, path="/")
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/config/public")
def api_config_public(request: Request):
    """Ρυθμίσεις φιλτραρισμένες ΑΝΑ ΡΟΛΟ (μενού, εργαλειοθήκες, πρόσβαση)."""
    ident = identity_from(request)
    role = "teacher" if is_teacher(request) else (ident["role"] if ident else "guest")
    menu = sorted([m for m in CONFIG["menu"] if m.get(role)], key=lambda m: m.get("order", 99))
    toolbars = [t for t in CONFIG["toolbars"] if t.get(role)]
    acc = CONFIG["access"]
    return {
        "role": role,
        "menu": menu,
        "toolbars": toolbars,
        "tmimata": CONFIG["schedule"]["tmimata"],
        "periods": CONFIG["schedule"]["periods"],
        "timetable": CONFIG["schedule"]["timetable"],
        "guest_chat": acc.get("guest_chat", True),
        "guest_forum": acc.get("guest_forum", False),
        "allowed_apps": acc.get("allowed_apps", {}).get(role, "*"),
        "messages": CONFIG["messages"] if role == "teacher" else [],
        "polls_bank": CONFIG["polls_bank"] if role == "teacher" else [],
        "quizzes_bank": [{"id": q["id"], "title": q["title"], "count": len(q["questions"])}
                         for q in CONFIG["quizzes_bank"]] if role == "teacher" else [],
        "timers_cfg": CONFIG["timers"] if role == "teacher" else [],
        "events_cfg": CONFIG["events"] if role == "teacher" else [],
        "announcements": ANNOUNCEMENTS[-20:],
        "server_now": time.time(),
    }




# ---------------------------------------------------------------------------
# Εντολές τάξης (μόνο καθηγητής) — ανακοινώσεις, βραβεία, πλοήγηση, poll, quiz
# ---------------------------------------------------------------------------
def _audience(body: dict) -> tuple[str, str]:
    aud = str(body.get("audience", "all"))
    if aud not in ("all", "students", "guests", "teachers") and not aud.startswith("role:"):
        raise HTTPException(400, "Μη έγκυρο κοινό (all/students/guests/teachers).")
    return aud, str(body.get("tmima", "")).strip()


@app.post("/api/cmd/announce")
async def cmd_announce(request: Request):
    """📣 Ανακοίνωση / 🎉 συγχαρητήρια / 🏆 βραβείο (kind: announce|congrats|award)."""
    require_teacher(request)
    body = await request.json()
    kind = str(body.get("kind", "announce"))
    if kind not in ("announce", "congrats", "award"):
        raise HTTPException(400, "kind: announce | congrats | award.")
    text = str(body.get("text", "")).strip()[:500]
    if not text:
        raise HTTPException(400, "Γράψε το μήνυμα.")
    aud, tmima = _audience(body)
    target_uid = str(body.get("target_uid", ""))
    msg = {"id": secrets.token_hex(6), "kind": kind, "text": text,
           "ts": time.time(), "audience": aud, "tmima": tmima,
           "target_uid": target_uid,
           "target_name": next((c.name for c in CLIENTS.values() if c.uid == target_uid), "")}
    ANNOUNCEMENTS.append(msg)
    del ANNOUNCEMENTS[:-50]
    payload = {"type": "announcement", **msg}
    if target_uid:
        await send_to_uid(target_uid, payload)          # προσωπικό (π.χ. βραβείο)
        await broadcast(payload, audience="teachers")   # ο καθηγητής βλέπει τι στάλθηκε
        sent = 1
    else:
        sent = await broadcast(payload, audience=aud, tmima=tmima)
    return {"ok": True, "sent": sent, "announcement": msg}


@app.post("/api/cmd/random-pick")
async def cmd_random_pick(request: Request):
    """🎲 Τυχαία επιλογή από τους συνδεδεμένους (με φίλτρο ρόλου/τμήματος)."""
    require_teacher(request)
    body = await request.json()
    aud, tmima = _audience(body)
    pool, seen = [], set()
    for c in CLIENTS.values():
        if c.uid not in seen and audience_match(c, aud or "students", tmima):
            pool.append(c)
            seen.add(c.uid)
    if not pool:
        raise HTTPException(404, "Δεν υπάρχει κανείς συνδεδεμένος με αυτά τα κριτήρια.")
    pick = random.choice(pool)
    payload = {"type": "random_pick", "uid": pick.uid, "name": pick.name,
               "emoji": pick.emoji, "tmima": pick.tmima,
               "celebrate": bool(body.get("celebrate", True)), "ts": time.time()}
    await broadcast(payload)                            # όλοι βλέπουν την κλήρωση
    return {"ok": True, "picked": payload, "pool_size": len(pool)}


@app.post("/api/cmd/navigate")
async def cmd_navigate(request: Request):
    """➡️ Υποχρεωτική μετάβαση μαθητών & guests σε συγκεκριμένη σελίδα της πύλης."""
    require_teacher(request)
    body = await request.json()
    url = str(body.get("url", "")).strip()
    if not url.startswith("/") or url.startswith("//"):
        raise HTTPException(400, "Δώσε σχετικό URL της πύλης (π.χ. /docs/ ή /live-quiz/).")
    aud, tmima = _audience(body)
    if aud == "all":
        aud = "students"                                # ποτέ δεν σπρώχνουμε άλλον καθηγητή
    sent = await broadcast({"type": "navigate", "url": url,
                            "title": str(body.get("title", ""))[:80],
                            "ts": time.time()}, audience=aud, tmima=tmima)
    return {"ok": True, "sent": sent}


@app.post("/api/cmd/poll")
async def cmd_poll(request: Request):
    """📊 Δημοσκόπηση· show_results=1 → όλοι βλέπουν ζωντανά τα αποτελέσματα."""
    require_teacher(request)
    body = await request.json()
    question = str(body.get("question", "")).strip()[:300]
    options = [str(o).strip()[:120] for o in body.get("options", []) if str(o).strip()]
    if not question or len(options) < 2:
        raise HTTPException(400, "Χρειάζεται ερώτηση και τουλάχιστον 2 επιλογές.")
    aud, tmima = _audience(body)
    pid = secrets.token_hex(6)
    show = 1 if body.get("show_results", True) else 0
    with db() as conn:
        conn.execute("INSERT INTO polls VALUES (?,?,?,?,?,?,0)",
                     (pid, time.time(), question, json.dumps(options, ensure_ascii=False),
                      show, f"{aud}|{tmima}"))
    ACTIVE_POLLS[pid] = {"id": pid, "question": question, "options": options,
                         "show_results": bool(show), "audience": aud, "tmima": tmima,
                         "closed": False}
    await broadcast({"type": "poll", "id": pid, "question": question, "options": options,
                     "show_results": bool(show), "ts": time.time()},
                    audience=aud, tmima=tmima)
    return {"ok": True, "id": pid}



def poll_results(conn: sqlite3.Connection, pid: str) -> dict:
    row = conn.execute("SELECT * FROM polls WHERE id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "Η δημοσκόπηση δεν βρέθηκε.")
    options = json.loads(row["options"])
    counts = [0] * len(options)
    for v in conn.execute("SELECT choice, COUNT(*) n FROM poll_votes WHERE poll_id=? GROUP BY choice", (pid,)):
        if 0 <= v["choice"] < len(counts):
            counts[v["choice"]] = v["n"]
    return {"type": "poll_results", "id": pid, "question": row["question"],
            "options": options, "counts": counts, "total": sum(counts),
            "show_results": bool(row["show_results"]), "closed": bool(row["closed"])}


@app.post("/api/cmd/poll/{pid}/close")
async def cmd_poll_close(pid: str, request: Request):
    require_teacher(request)
    with db() as conn:
        conn.execute("UPDATE polls SET closed=1 WHERE id=?", (pid,))
        res = poll_results(conn, pid)
    ACTIVE_POLLS.pop(pid, None)
    await broadcast({**res, "closed": True})            # στο κλείσιμο όλοι βλέπουν το τελικό αποτέλεσμα
    return {"ok": True, "results": res}


@app.get("/api/polls")
def api_polls(request: Request):
    require_teacher(request)
    with db() as conn:
        rows = conn.execute("SELECT id FROM polls ORDER BY ts DESC LIMIT 30").fetchall()
        return {"polls": [poll_results(conn, r["id"]) for r in rows]}


# ---------------------------------------------------------------------------
# Quiz — αποστολή σε μαθητές (καταγραφή) & guests (μόνο εξάσκηση)
# ---------------------------------------------------------------------------
def clean_questions(raw) -> list[dict]:
    questions = []
    for q in raw or []:
        text = str(q.get("text", "")).strip()[:300]
        options = [str(o).strip()[:120] for o in q.get("options", []) if str(o).strip()]
        correct = int(q.get("correct", -1))
        if text and len(options) >= 2 and 0 <= correct < len(options):
            questions.append({"text": text, "options": options, "correct": correct})
    if not questions:
        raise HTTPException(400, "Χρειάζεται τουλάχιστον 1 έγκυρη ερώτηση (text/options/correct).")
    return questions[:30]


@app.post("/api/cmd/quiz")
async def cmd_quiz(request: Request):
    """📝 Αποστολή quiz (inline ερωτήσεις ή bank_id από το Excel)."""
    require_teacher(request)
    body = await request.json()
    bank_id = str(body.get("bank_id", ""))
    if bank_id:
        bank = next((q for q in CONFIG["quizzes_bank"] if q["id"] == bank_id), None)
        if not bank:
            raise HTTPException(404, "Δεν βρέθηκε quiz με αυτό το id στην τράπεζα Excel.")
        title, questions = bank["title"], bank["questions"]
    else:
        title = str(body.get("title", "Quiz Τάξης")).strip()[:120]
        questions = clean_questions(body.get("questions"))
    aud, tmima = _audience(body)
    qid = secrets.token_hex(6)
    with db() as conn:
        conn.execute("INSERT INTO quizzes VALUES (?,?,?,?,?,0)",
                     (qid, time.time(), title, json.dumps(questions, ensure_ascii=False),
                      f"{aud}|{tmima}"))
    ACTIVE_QUIZZES[qid] = {"id": qid, "title": title, "questions": questions,
                           "audience": aud, "tmima": tmima, "closed": False}
    # Στους πελάτες ΔΕΝ στέλνουμε το correct — η βαθμολόγηση γίνεται στον server.
    public_qs = [{"text": q["text"], "options": q["options"]} for q in questions]
    await broadcast({"type": "quiz", "id": qid, "title": title, "questions": public_qs,
                     "ts": time.time()}, audience=aud, tmima=tmima)
    return {"ok": True, "id": qid, "count": len(questions)}



@app.get("/api/quizzes")
def api_quizzes(request: Request):
    require_teacher(request)
    with db() as conn:
        rows = conn.execute("SELECT id, ts, title, closed FROM quizzes ORDER BY ts DESC LIMIT 30").fetchall()
        out = []
        for r in rows:
            results = conn.execute(
                "SELECT name, tmima, score, total, ts FROM quiz_results "
                "WHERE quiz_id=? ORDER BY score DESC, ts ASC", (r["id"],)).fetchall()
            out.append({"id": r["id"], "ts": r["ts"], "title": r["title"],
                        "closed": bool(r["closed"]), "results": [dict(x) for x in results]})
        return {"quizzes": out}


@app.post("/api/cmd/quiz/{qid}/close")
async def cmd_quiz_close(qid: str, request: Request):
    require_teacher(request)
    with db() as conn:
        conn.execute("UPDATE quizzes SET closed=1 WHERE id=?", (qid,))
    ACTIVE_QUIZZES.pop(qid, None)
    await broadcast({"type": "quiz_closed", "id": qid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Timers — ιδιωτικοί/δημόσιοι, με anchor στο ωράριο + offset ±λεπτών
# ---------------------------------------------------------------------------
def schedule_deadline(tmima: str, day: str, period: int, edge: str, offset_min: float) -> float | None:
    """Υπολογίζει epoch deadline από διδακτική ώρα του ωραρίου + offset.
    edge: start|end· day='' → σημερινή ημέρα."""
    periods = CONFIG["schedule"]["periods"]
    if not (1 <= period <= len(periods)):
        return None
    day_idx = DAYS.index(day) if day in DAYS else datetime.now().weekday()
    hhmm = periods[period - 1]["start" if edge == "start" else "end"]
    try:
        h, m = map(int, str(hhmm).split(":"))
    except ValueError:
        return None
    now = datetime.now()
    base = now.replace(hour=h, minute=m, second=0, microsecond=0)
    # μεταφορά στη σωστή ημέρα της εβδομάδας (ίδια εβδομάδα)
    return base.timestamp() + (day_idx - now.weekday()) * 86400 + offset_min * 60


@app.post("/api/cmd/timer")
async def cmd_timer(request: Request):
    """⏱️ Χρονομετρητής: duration_sec Ή anchor ωραρίου (tmima/day/period/edge/offset).
    visibility: private (μόνο καθηγητής) | public (όλοι ή επιλεγμένο κοινό)."""
    require_teacher(request)
    body = await request.json()
    label = str(body.get("label", "Χρονομετρητής")).strip()[:80] or "Χρονομετρητής"
    visibility = str(body.get("visibility", "public"))
    if visibility not in ("private", "public"):
        raise HTTPException(400, "visibility: private | public.")
    aud, tmima = _audience(body)
    if body.get("period"):
        ends = schedule_deadline(str(body.get("anchor_tmima", tmima)),
                                 str(body.get("day", "")), int(body["period"]),
                                 str(body.get("edge", "end")), float(body.get("offset_min", 0)))
        if not ends or ends <= time.time():
            raise HTTPException(400, "Η στιγμή του ωραρίου (+offset) έχει ήδη περάσει για αυτή την ημέρα.")
    else:
        dur = float(body.get("duration_sec", 300))
        if not (5 <= dur <= 4 * 3600):
            raise HTTPException(400, "Διάρκεια 5 δευτ. έως 4 ώρες.")
        ends = time.time() + dur
    tid = secrets.token_hex(6)
    timer = {"id": tid, "label": label, "ends_at": ends, "server_now": time.time(),
             "visibility": visibility, "audience": aud, "tmima": tmima,
             "message": str(body.get("message", ""))[:200]}
    ACTIVE_TIMERS[tid] = timer
    payload = {"type": "timer", **timer}
    if visibility == "private":
        await broadcast(payload, audience="teachers")
    else:
        await broadcast(payload, audience=aud, tmima=tmima)
    return {"ok": True, "id": tid, "ends_at": ends}



@app.post("/api/cmd/timer/{tid}/stop")
async def cmd_timer_stop(tid: str, request: Request):
    require_teacher(request)
    ACTIVE_TIMERS.pop(tid, None)
    await broadcast({"type": "timer_stop", "id": tid})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Background εργασία: sweeper παρουσίας + λήξη timers + γεγονότα ωραρίου
# ---------------------------------------------------------------------------
EVENTS_FIRED: set[str] = set()                          # "event_id:YYYY-MM-DD" (μία φορά/ημέρα)


def event_deadline(ev: dict) -> float | None:
    """trigger: day_end (τέλος τελευταίας ώρας), period_end (συγκεκριμένη ώρα),
    time (συγκεκριμένη HH:MM) — πάντα με offset ±λεπτών."""
    trigger = ev.get("trigger", "day_end")
    offset = float(ev.get("offset_min", 0))
    periods = CONFIG["schedule"]["periods"]
    now = datetime.now()
    if trigger == "day_end" and periods:
        hhmm = periods[-1]["end"]
    elif trigger == "period_end":
        p = int(ev.get("period", 0))
        if not (1 <= p <= len(periods)):
            return None
        hhmm = periods[p - 1]["end"]
    elif trigger == "time":
        hhmm = str(ev.get("time", ""))
    else:
        return None
    try:
        h, m = map(int, hhmm.split(":"))
    except ValueError:
        return None
    return now.replace(hour=h, minute=m, second=0, microsecond=0).timestamp() + offset * 60


async def fire_event(kind: str, text: str, audience: str = "all", tmima: str = "",
                     url: str = "") -> None:
    msg = {"id": secrets.token_hex(6), "kind": kind, "text": text,
           "ts": time.time(), "audience": audience, "tmima": tmima,
           "target_uid": "", "target_name": ""}
    ANNOUNCEMENTS.append(msg)
    del ANNOUNCEMENTS[:-50]
    await broadcast({"type": "announcement", **msg}, audience=audience, tmima=tmima)
    if url:
        await broadcast({"type": "navigate", "url": url, "title": text[:80],
                         "ts": time.time()}, audience="students", tmima=tmima)


async def housekeeping() -> None:
    """Τρέχει κάθε δευτερόλεπτο: αποσύνδεση 'φαντασμάτων', λήξεις timers,
    γεγονότα τέλους ημέρας/ώρας από το Excel."""
    while True:
        try:
            now = time.time()
            # 1) παρουσία: χωρίς heartbeat > HEARTBEAT_TIMEOUT → έξοδος
            stale = [k for k, c in CLIENTS.items() if now - c.last_ping > HEARTBEAT_TIMEOUT]
            for k in stale:
                c = CLIENTS.pop(k, None)
                if c:
                    try:
                        await c.ws.close(code=4001)
                    except Exception:
                        pass
            if stale:
                await push_roster()
            # 2) λήξη χρονομετρητών
            for tid, t in list(ACTIVE_TIMERS.items()):
                if now >= t["ends_at"]:
                    ACTIVE_TIMERS.pop(tid, None)
                    payload = {"type": "timer_done", "id": tid, "label": t["label"],
                               "message": t.get("message", "")}
                    if t["visibility"] == "private":
                        await broadcast(payload, audience="teachers")
                    else:
                        await broadcast(payload, audience=t["audience"], tmima=t["tmima"])
            # 3) γεγονότα Excel (μία φορά ανά ημέρα & id, μόνο καθημερινές ή ορισμένες ημέρες)
            today = datetime.now().strftime("%Y-%m-%d")
            weekday = datetime.now().weekday()
            for ev in CONFIG["events"]:
                if not ev.get("enabled", True):
                    continue
                days = ev.get("days") or []
                if weekday >= 5 or (days and DAYS[weekday] not in days):
                    continue
                key = f"{ev['id']}:{today}"
                if key in EVENTS_FIRED:
                    continue
                dl = event_deadline(ev)
                if dl and now >= dl and now - dl < 3600:   # παράθυρο 1 ώρας (όχι μπαράζ σε restart)
                    EVENTS_FIRED.add(key)
                    await fire_event(ev.get("action", "announce"),
                                     ev.get("text", "Γεγονός ωραρίου"),
                                     ev.get("audience", "all"), ev.get("tmima", ""),
                                     ev.get("url", ""))
        except Exception:
            pass                                        # ποτέ δεν σκοτώνει το loop
        await asyncio.sleep(1)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(housekeeping())



# ---------------------------------------------------------------------------
# WebSocket — /ws (ταυτότητα από HMAC cookie· heartbeat ανά 15s από τον client)
# ---------------------------------------------------------------------------
async def ws_poll_vote(c: Client, pid: str, choice: int) -> None:
    poll = ACTIVE_POLLS.get(pid)
    if not poll or poll["closed"] or not audience_match(c, poll["audience"], poll["tmima"]):
        return
    if not (0 <= choice < len(poll["options"])):
        return
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO poll_votes VALUES (?,?,?)", (pid, c.uid, choice))
        res = poll_results(conn, pid)
    await send_to_uid(c.uid, {"type": "poll_voted", "id": pid, "choice": choice})
    if res["show_results"]:
        await broadcast(res, audience=poll["audience"], tmima=poll["tmima"])
    await broadcast(res, audience="teachers")           # ο καθηγητής βλέπει ΠΑΝΤΑ


async def ws_quiz_submit(c: Client, qid: str, answers: list) -> None:
    quiz = ACTIVE_QUIZZES.get(qid)
    if not quiz or quiz["closed"] or not audience_match(c, quiz["audience"], quiz["tmima"]):
        return
    questions = quiz["questions"]
    answers = [int(a) if str(a).lstrip("-").isdigit() else -1 for a in answers][:len(questions)]
    answers += [-1] * (len(questions) - len(answers))
    score = sum(1 for q, a in zip(questions, answers) if a == q["correct"])
    feedback = [{"correct": q["correct"], "chosen": a, "ok": a == q["correct"]}
                for q, a in zip(questions, answers)]
    recorded = False
    if c.role == "student":
        # ΜΟΝΟ οι μαθητές καταγράφονται· οι guests κάνουν απλή εξάσκηση.
        with db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO quiz_results "
                "(quiz_id, ts, uid, name, tmima, score, total, answers) VALUES (?,?,?,?,?,?,?,?)",
                (qid, time.time(), c.uid, c.name, c.tmima, score, len(questions),
                 json.dumps(answers)))
        recorded = True
        await broadcast({"type": "quiz_progress", "id": qid, "uid": c.uid, "name": c.name,
                         "tmima": c.tmima, "score": score, "total": len(questions)},
                        audience="teachers")
    await send_json(c.ws, {"type": "quiz_result", "id": qid, "score": score,
                           "total": len(questions), "feedback": feedback,
                           "recorded": recorded,
                           "note": "Το αποτέλεσμά σου καταγράφηκε." if recorded
                                   else "Εξάσκηση επισκέπτη — δεν καταγράφεται."})



@app.websocket("/ws")
async def hub_socket(ws: WebSocket):
    ident = identity_from(ws)                           # τα cookies είναι διαθέσιμα στο WS
    teacher_cookie = token_payload(ws.cookies.get(COOKIE_NAME)) == "teacher"
    if not ident:
        await ws.close(code=4003)                       # πρώτα POST /api/join
        return
    if teacher_cookie:
        ident["role"] = "teacher"
    await ws.accept()
    c = Client(ws, ident)
    CLIENTS[id(ws)] = c
    # αρχική κατάσταση: timers/polls/quizzes σε εξέλιξη + πρόσφατες ανακοινώσεις
    await send_json(ws, {"type": "welcome", "identity": c.public(),
                         "server_now": time.time(),
                         "announcements": ANNOUNCEMENTS[-20:],
                         "timers": [t for t in ACTIVE_TIMERS.values()
                                    if t["visibility"] == "public" or c.role == "teacher"],
                         "polls": [p for p in ACTIVE_POLLS.values()
                                   if audience_match(c, p["audience"], p["tmima"])],
                         "quizzes": [{"id": q["id"], "title": q["title"],
                                      "questions": [{"text": x["text"], "options": x["options"]}
                                                    for x in q["questions"]]}
                                     for q in ACTIVE_QUIZZES.values()
                                     if audience_match(c, q["audience"], q["tmima"])]})
    await push_roster()
    try:
        while True:
            msg = await ws.receive_json()
            c.last_ping = time.time()
            mtype = str(msg.get("type", ""))
            if mtype == "ping":
                page = str(msg.get("page", ""))[:200]
                if page != c.page:
                    c.page = page
                    await push_roster()
                await send_json(ws, {"type": "pong", "server_now": time.time()})
            elif mtype == "chat":
                if c.role == "guest" and not CONFIG["access"].get("guest_chat", True):
                    continue
                text = str(msg.get("text", "")).strip()[:500]
                if not text:
                    continue
                with db() as conn:
                    cur = conn.execute(
                        "INSERT INTO chat (ts, uid, name, role, tmima, text) VALUES (?,?,?,?,?,?)",
                        (time.time(), c.uid, c.name, c.role, c.tmima, text))
                    mid = cur.lastrowid
                await broadcast({"type": "chat", "id": mid, "ts": time.time(),
                                 "uid": c.uid, "name": c.name, "role": c.role,
                                 "tmima": c.tmima, "emoji": c.emoji, "color": c.color,
                                 "text": text})
            elif mtype == "poll_vote":
                await ws_poll_vote(c, str(msg.get("id", "")), int(msg.get("choice", -1)))
            elif mtype == "quiz_submit":
                await ws_quiz_submit(c, str(msg.get("id", "")), msg.get("answers", []))
            elif mtype == "forum_post" and (c.role != "guest" or CONFIG["access"].get("guest_forum")):
                tid = int(msg.get("thread_id", 0))
                text = str(msg.get("text", "")).strip()[:2000]
                if not text:
                    continue
                with db() as conn:
                    th = conn.execute("SELECT locked FROM forum_threads WHERE id=?", (tid,)).fetchone()
                    if not th or (th["locked"] and c.role != "teacher"):
                        continue
                    cur = conn.execute(
                        "INSERT INTO forum_posts (thread_id, ts, uid, name, role, text) "
                        "VALUES (?,?,?,?,?,?)", (tid, time.time(), c.uid, c.name, c.role, text))
                    pid = cur.lastrowid
                await broadcast({"type": "forum_post", "thread_id": tid, "id": pid,
                                 "ts": time.time(), "uid": c.uid, "name": c.name,
                                 "role": c.role, "text": text})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        CLIENTS.pop(id(ws), None)
        await push_roster()



# ---------------------------------------------------------------------------
# REST — chat ιστορικό, forum νήματα, roster (καθηγητής)
# ---------------------------------------------------------------------------
@app.get("/api/chat/history")
def api_chat_history(request: Request):
    if not identity_from(request):
        raise HTTPException(401, "Συνδέσου πρώτα.")
    with db() as conn:
        rows = conn.execute("SELECT * FROM chat ORDER BY id DESC LIMIT 100").fetchall()
    return {"messages": [dict(r) for r in reversed(rows)]}


@app.get("/api/forum/threads")
def api_forum_threads(request: Request):
    ident = identity_from(request)
    if not ident:
        raise HTTPException(401, "Συνδέσου πρώτα.")
    if ident["role"] == "guest" and not CONFIG["access"].get("guest_forum"):
        raise HTTPException(403, "Το forum δεν είναι διαθέσιμο στους επισκέπτες.")
    with db() as conn:
        rows = conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM forum_posts p WHERE p.thread_id=t.id) AS posts "
            "FROM forum_threads t ORDER BY t.id DESC LIMIT 50").fetchall()
    return {"threads": [dict(r) for r in rows]}


@app.post("/api/forum/threads")
async def api_forum_new_thread(request: Request):
    ident = identity_from(request)
    if not ident:
        raise HTTPException(401, "Συνδέσου πρώτα.")
    if ident["role"] == "guest" and not CONFIG["access"].get("guest_forum"):
        raise HTTPException(403, "Το forum δεν είναι διαθέσιμο στους επισκέπτες.")
    body = await request.json()
    title = str(body.get("title", "")).strip()[:150]
    text = str(body.get("text", "")).strip()[:2000]
    if not title or not text:
        raise HTTPException(400, "Χρειάζεται τίτλος και κείμενο.")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO forum_threads (ts, uid, name, role, title) VALUES (?,?,?,?,?)",
            (time.time(), ident["uid"], ident["name"], ident["role"], title))
        tid = cur.lastrowid
        conn.execute(
            "INSERT INTO forum_posts (thread_id, ts, uid, name, role, text) VALUES (?,?,?,?,?,?)",
            (tid, time.time(), ident["uid"], ident["name"], ident["role"], text))
    await broadcast({"type": "forum_thread", "id": tid, "title": title,
                     "name": ident["name"], "ts": time.time()})
    return {"ok": True, "id": tid}



@app.get("/api/forum/threads/{tid}")
def api_forum_thread(tid: int, request: Request):
    ident = identity_from(request)
    if not ident:
        raise HTTPException(401, "Συνδέσου πρώτα.")
    if ident["role"] == "guest" and not CONFIG["access"].get("guest_forum"):
        raise HTTPException(403, "Το forum δεν είναι διαθέσιμο στους επισκέπτες.")
    with db() as conn:
        th = conn.execute("SELECT * FROM forum_threads WHERE id=?", (tid,)).fetchone()
        if not th:
            raise HTTPException(404, "Το νήμα δεν βρέθηκε.")
        posts = conn.execute("SELECT * FROM forum_posts WHERE thread_id=? ORDER BY id", (tid,)).fetchall()
    return {"thread": dict(th), "posts": [dict(p) for p in posts]}


@app.post("/api/forum/threads/{tid}/lock")
async def api_forum_lock(tid: int, request: Request):
    require_teacher(request)
    body = await request.json()
    locked = 1 if body.get("locked", True) else 0
    with db() as conn:
        conn.execute("UPDATE forum_threads SET locked=? WHERE id=?", (locked, tid))
    await broadcast({"type": "forum_lock", "thread_id": tid, "locked": bool(locked)})
    return {"ok": True}


@app.delete("/api/forum/threads/{tid}")
async def api_forum_delete(tid: int, request: Request):
    require_teacher(request)
    with db() as conn:
        conn.execute("DELETE FROM forum_posts WHERE thread_id=?", (tid,))
        conn.execute("DELETE FROM forum_threads WHERE id=?", (tid,))
    await broadcast({"type": "forum_deleted", "thread_id": tid})
    return {"ok": True}


@app.get("/api/roster")
def api_roster(request: Request):
    require_teacher(request)
    return roster_payload()



# ---------------------------------------------------------------------------
# Ενιαίο πρότυπο Excel — δημιουργία (12 καρτέλες, χρωματικοί κώδικες, οδηγίες)
# ---------------------------------------------------------------------------
# Χρωματικός κώδικας (ίδιος σε όλες τις καρτέλες — εξηγείται στο φύλλο Οδηγίες):
TAB_COLORS = {"Οδηγίες": "9E9E9E", "Τμήματα": "1E88E5", "Ωρες": "1E88E5",
              "Ωραριο": "1E88E5", "Μενού": "8E24AA", "Εργαλειοθήκες": "8E24AA",
              "Ρόλοι": "FB8C00", "Ονόματα Guest": "43A047", "Timers": "FDD835",
              "Γεγονότα": "FDD835", "Μηνύματα": "E53935", "Poll-Quiz": "E53935"}
HEAD_FILL = "3F51B5"      # 🟦 κεφαλίδες — ΜΗΝ τις αλλάζετε
REQ_FILL = "FFF9C4"       # 🟨 υποχρεωτικά πεδία
OPT_FILL = "E8F5E9"       # 🟩 προαιρετικά πεδία
WARN_FILL = "FFEBEE"      # 🟥 ευαίσθητα (κωδικοί) — προσοχή


def _style_sheet(ws, headers: list[str], widths: list[int], req_cols: set[int],
                 warn_cols: set[int] | None = None):
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    ws.append(headers)
    for i, cell in enumerate(ws[1], 1):
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=HEAD_FILL)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1] if i <= len(widths) else 18
    ws.freeze_panes = "A2"
    ws.sheet_properties.tabColor = TAB_COLORS.get(ws.title, "607D8B")
    # χρωματισμός περιοχής εισαγωγής (πρώτες 60 γραμμές) ανά τύπο πεδίου
    for r in range(2, 62):
        for i in range(1, len(headers) + 1):
            fill = WARN_FILL if (warn_cols and i in warn_cols) else (
                REQ_FILL if i in req_cols else OPT_FILL)
            ws.cell(row=r, column=i).fill = PatternFill("solid", fgColor=fill)


def _yesno_validation(ws, cols: list[int]):
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
    dv = DataValidation(type="list", formula1='"ΝΑΙ,ΟΧΙ"', allow_blank=True)
    ws.add_data_validation(dv)
    for col in cols:
        letter = get_column_letter(col)
        dv.add(f"{letter}2:{letter}200")


def make_template_xlsx() -> None:
    """Ενιαίο πρότυπο ΟΛΩΝ των ρυθμίσεων· οι 3 καρτέλες ωραρίου είναι ΑΥΤΟΥΣΙΕΣ
    με το πρότυπο του Lesson Wizard ώστε το ίδιο αρχείο να ανεβαίνει παντού."""
    from openpyxl import Workbook

    wb = Workbook()

    # --- 1. Οδηγίες (γκρι) ---------------------------------------------------
    ws = wb.active
    ws.title = "Οδηγίες"
    _style_sheet(ws, ["Ενιαίο Πρότυπο Ρυθμίσεων — Ζωντανή Τάξη (/classroom/)"], [110], set())
    rows = [
        "",
        "🎨 ΧΡΩΜΑΤΙΚΟΣ ΚΩΔΙΚΑΣ",
        "🟦 Μπλε κεφαλίδα (γραμμή 1): τίτλοι στηλών — ΜΗΝ τους αλλάξετε/μετονομάσετε.",
        "🟨 Κίτρινο κελί: ΥΠΟΧΡΕΩΤΙΚΟ πεδίο — συμπληρώστε το.",
        "🟩 Πράσινο κελί: προαιρετικό πεδίο — αφήστε το κενό αν δεν χρειάζεται.",
        "🟥 Κόκκινο κελί: ΕΥΑΙΣΘΗΤΟ (κωδικοί πρόσβασης) — προσοχή, φαίνεται σε όποιον έχει το αρχείο.",
        "",
        "🗂️ ΚΑΡΤΕΛΕΣ (χρώμα tab = θεματική ομάδα)",
        "🔵 Τμήματα / Ωρες / Ωραριο → το ΩΡΑΡΙΟ του σχολείου (ίδια δομή με το Lesson Wizard·",
        "     το ίδιο αρχείο μπορεί να ανέβει και στο /lesson-wizard/ → καρτέλα Ωράριο).",
        "🟣 Μενού / Εργαλειοθήκες → τι βλέπει κάθε ρόλος στο κεντρικό παράθυρο.",
        "🟠 Ρόλοι → κωδικός τάξης & δικαιώματα επισκεπτών (guests).",
        "🟢 Ονόματα Guest → παιχνιδιάρικα ονόματα τύπου Google Docs (Επίθετο + Όνομα).",
        "🟡 Timers / Γεγονότα → χρονομετρητές & αυτόματα γεγονότα δεμένα με το ωράριο (±offset λεπτά).",
        "🔴 Μηνύματα / Poll-Quiz → έτοιμες ανακοινώσεις, δημοσκοπήσεις & τράπεζα quiz.",
        "",
        "📤 ΡΟΗ ΕΡΓΑΣΙΑΣ",
        "1. Συμπληρώνετε τις καρτέλες (κάθε γραμμή = μία εγγραφή· τα παραδείγματα μπορείτε να τα σβήσετε).",
        "2. Αποθήκευση ως .xlsx και ανέβασμα: /classroom/ → ⚙️ Ρυθμίσεις (καθηγητής, κωδικός teacher2026).",
        "3. Οι ρυθμίσεις εφαρμόζονται ΖΩΝΑΝΑ σε όλους τους συνδεδεμένους — χωρίς επανεκκίνηση.",
        "4. Μπορείτε να επεκτείνετε το αρχείο αργότερα: άγνωστες καρτέλες αγνοούνται με ασφάλεια.",
        "",
        "⚠️ ΣΗΜΑΝΤΙΚΑ",
        "• ΝΑΙ/ΟΧΙ: διαλέξτε από το αναδυόμενο μενού του κελιού (όχι ελεύθερο κείμενο).",
        "• Ώρες σε 24ωρη μορφή HH:MM (π.χ. 08:15). Offset σε λεπτά: -5 = πέντε λεπτά ΝΩΡΙΤΕΡΑ.",
        "• URL εφαρμογών: σχετικά με την πύλη (π.χ. /docs/, /live-quiz/, /apps/my-app/).",
        "• Τα αποτελέσματα quiz καταγράφονται ΜΟΝΟ για μαθητές· οι guests κάνουν εξάσκηση.",
    ]
    for r in rows:
        ws.append([r])

    # --- 2-4. Ωράριο (μπλε — ΙΔΙΑ ΔΟΜΗ με lesson-wizard) ----------------------
    ws = wb.create_sheet("Τμήματα")
    _style_sheet(ws, ["Τμήμα", "Τάξη (slug)", "Σημείωση"], [14, 20, 40], {1, 2})
    ws.append(["Γ1", "gymnasio-g", "Πληροφορική Γ' Γυμνασίου"])
    ws.append(["Γ2", "gymnasio-g", ""])
    ws.append(["Β1", "gymnasio-b", ""])

    ws = wb.create_sheet("Ωρες")
    _style_sheet(ws, ["Ωρα", "Εναρξη", "Ληξη"], [10, 14, 14], {1, 2, 3})
    for i, (s, e) in enumerate([("08:15", "09:00"), ("09:10", "09:55"), ("10:05", "10:50"),
                                 ("11:10", "11:55"), ("12:05", "12:50"), ("13:00", "13:45"),
                                 ("13:55", "14:40")], 1):
        ws.append([i, s, e])

    ws = wb.create_sheet("Ωραριο")
    _style_sheet(ws, ["Τμήμα", "Ημέρα", "Ωρα", "Μάθημα", "URL μαθήματος (προαιρετικό)"],
                 [12, 14, 8, 30, 46], {1, 2, 3, 4})
    ws.append(["Γ1", "Δευτέρα", 3, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    ws.append(["Γ1", "Τετάρτη", 5, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    ws.append(["Γ2", "Τρίτη", 2, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])



    # --- 5. Μενού (μωβ) -------------------------------------------------------
    ws = wb.create_sheet("Μενού")
    _style_sheet(ws, ["id", "Τίτλος", "Emoji", "URL ή #panel", "Σειρά",
                      "Guest", "Μαθητής", "Καθηγητής"],
                 [16, 22, 8, 34, 8, 10, 10, 12], {1, 2, 4})
    _yesno_validation(ws, [6, 7, 8])
    for row in [["mathimata", "Μαθήματα", "📚", "/docs/", 1, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["anakoinoseis", "Ανακοινώσεις", "📣", "#announcements", 2, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["chat", "Chat", "💬", "#chat", 3, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["forum", "Forum", "🗂️", "#forum", 4, "ΟΧΙ", "ΝΑΙ", "ΝΑΙ"],
                ["voitheia", "Βοήθεια", "❓", "#help", 5, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["live-quiz", "Live Quiz", "🎮", "/live-quiz/", 6, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"]]:
        ws.append(row)

    # --- 6. Εργαλειοθήκες (μωβ) ----------------------------------------------
    ws = wb.create_sheet("Εργαλειοθήκες")
    _style_sheet(ws, ["id", "Τίτλος", "Τύπος (dock/float)", "X", "Y", "Πλάτος", "Ύψος",
                      "Guest", "Μαθητής", "Καθηγητής"],
                 [14, 24, 18, 8, 8, 10, 10, 10, 10, 12], {1, 2, 3})
    _yesno_validation(ws, [8, 9, 10])
    from openpyxl.worksheet.datavalidation import DataValidation
    dv = DataValidation(type="list", formula1='"dock,float"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("C2:C200")
    for row in [["roster", "👥 Συνδεδεμένοι", "dock", 20, 90, 300, 380, "ΟΧΙ", "ΟΧΙ", "ΝΑΙ"],
                ["commands", "🎛️ Εντολές Τάξης", "dock", 20, 90, 340, 480, "ΟΧΙ", "ΟΧΙ", "ΝΑΙ"],
                ["timer", "⏱️ Χρονομετρητής", "float", 60, 120, 280, 200, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["chat", "💬 Chat Τάξης", "dock", 20, 90, 320, 420, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"]]:
        ws.append(row)

    # --- 7. Ρόλοι (πορτοκαλί) -----------------------------------------------
    ws = wb.create_sheet("Ρόλοι")
    _style_sheet(ws, ["Ρύθμιση", "Τιμή", "Εξήγηση"], [24, 24, 66], {1}, warn_cols={2})
    for row in [["student_code", "", "Προαιρετικός κωδικός τάξης για είσοδο ως μαθητής (κενό = χωρίς κωδικό)."],
                ["guest_chat", "ΝΑΙ", "Επιτρέπεται στους guests το chat τάξης;"],
                ["guest_forum", "ΟΧΙ", "Επιτρέπεται στους guests το forum;"],
                ["allowed_guest", "*", "Εφαρμογές για guests: * = όλες, ή λίστα με κόμμα (/docs/,/live-quiz/)"],
                ["allowed_student", "*", "Εφαρμογές για μαθητές: * = όλες, ή λίστα με κόμμα."],
                ["allowed_teacher", "*", "Εφαρμογές για καθηγητές: * = όλες."]]:
        ws.append(row)

    # --- 8. Ονόματα Guest (πράσινο) ------------------------------------------
    ws = wb.create_sheet("Ονόματα Guest")
    _style_sheet(ws, ["Επίθετα", "Ονόματα (ζώα/ρόλοι)", "Emoji", "Χρώματα (hex)"],
                 [24, 26, 10, 16], set())
    examples = list(zip(DEFAULT_ADJ, [n for n, _ in DEFAULT_NOUNS],
                        [e for _, e in DEFAULT_NOUNS], GUEST_COLORS + [""] * 5))
    for adj, noun, emoji, color in examples[:15]:
        ws.append([adj, noun, emoji, color])

    # --- 9. Timers (κίτρινο) --------------------------------------------------
    ws = wb.create_sheet("Timers")
    _style_sheet(ws, ["id", "Ετικέτα", "Ορατότητα (private/public)", "Διάρκεια (δευτ.)",
                      "Τμήμα ωραρίου", "Ημέρα", "Ωρα (#)", "Άκρη (start/end)",
                      "Offset (±λεπτά)", "Μήνυμα λήξης", "Κοινό", "Ενεργό"],
                 [12, 24, 22, 14, 14, 12, 8, 14, 14, 30, 12, 10], {1, 2, 3})
    _yesno_validation(ws, [12])
    dv = DataValidation(type="list", formula1='"private,public"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("C2:C200")
    dv2 = DataValidation(type="list", formula1='"start,end"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add("H2:H200")
    ws.append(["break", "Διάλειμμα", "public", "", "Γ1", "Δευτέρα", 2, "end", -2,
               "Σε 2 λεπτά τελειώνει η ώρα!", "all", "ΝΑΙ"])
    ws.append(["focus", "Χρόνος εργασίας", "public", 600, "", "", "", "", 0,
               "Ο χρόνος τελείωσε — αποθηκεύστε!", "students", "ΝΑΙ"])


    # --- 10. Γεγονότα (κίτρινο) ----------------------------------------------
    ws = wb.create_sheet("Γεγονότα")
    _style_sheet(ws, ["id", "Trigger (day_end/period_end/time)", "Ωρα (#)", "Ώρα HH:MM",
                      "Offset (±λεπτά)", "Ημέρες (κενό=καθημερινές)", "Ενέργεια (announce/congrats/award/navigate)",
                      "Μήνυμα", "URL (για navigate)", "Κοινό", "Τμήμα", "Ενεργό"],
                 [12, 30, 8, 12, 14, 26, 34, 36, 30, 12, 10, 10], {1, 2, 7, 8})
    _yesno_validation(ws, [12])
    dv = DataValidation(type="list", formula1='"day_end,period_end,time"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("B2:B200")
    dv2 = DataValidation(type="list", formula1='"announce,congrats,award,navigate"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add("G2:G200")
    ws.append(["telos-imeras", "day_end", "", "", -5, "", "congrats",
               "Μπράβο παιδιά! Τελειώσαμε για σήμερα 🎉", "", "all", "", "ΝΑΙ"])
    ws.append(["anafora", "period_end", 4, "", 0, "Παρασκευή", "announce",
               "Μην ξεχάσετε την εβδομαδιαία αναφορά στο /exams/", "/exams/", "students", "", "ΝΑΙ"])

    # --- 11. Μηνύματα (κόκκινο) ----------------------------------------------
    ws = wb.create_sheet("Μηνύματα")
    _style_sheet(ws, ["id", "Είδος (announce/congrats/award)", "Κείμενο"],
                 [14, 28, 80], {1, 2, 3})
    dv = DataValidation(type="list", formula1='"announce,congrats,award"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("B2:B200")
    for row in [["kalimera", "announce", "Καλημέρα! Ξεκινάμε σε 2 λεπτά — ανοίξτε το μάθημα."],
                ["bravo", "congrats", "Συγχαρητήρια {name}! Εξαιρετική προσπάθεια 👏"],
                ["vraveio", "award", "🏆 Βραβείο ημέρας απονέμεται στον/στη {name}!"],
                ["swsti-apantisi", "congrats", "Μπράβο {name}, σωστή απάντηση! ⭐"]]:
        ws.append(row)

    # --- 12. Poll-Quiz (κόκκινο) ---------------------------------------------
    ws = wb.create_sheet("Poll-Quiz")
    _style_sheet(ws, ["Τύπος (poll/quiz)", "id", "Τίτλος/Ερώτηση", "Επιλογή 1", "Επιλογή 2",
                      "Επιλογή 3", "Επιλογή 4", "Σωστή (1-4, μόνο quiz)",
                      "Ορατά αποτελέσματα (poll)", "Ομάδα quiz (ίδιο id = ίδιο quiz)"],
                 [16, 14, 44, 22, 22, 22, 22, 20, 24, 28], {1, 2, 3, 4, 5})
    _yesno_validation(ws, [9])
    dv = DataValidation(type="list", formula1='"poll,quiz"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("A2:A200")
    ws.append(["poll", "diathesi", "Πώς νιώθετε σήμερα;", "😀 Τέλεια", "🙂 Καλά",
               "😐 Έτσι κι έτσι", "😴 Κουρασμένοι", "", "ΝΑΙ", ""])
    ws.append(["quiz", "dyadiko-1", "Πόσα bits έχει ένα byte;", "4", "8", "16", "32", 2, "", "dyadiko"])
    ws.append(["quiz", "dyadiko-1", "Το 1010 (δυαδικό) σε δεκαδικό είναι:", "8", "10", "12", "14", 2, "", "dyadiko"])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(TEMPLATE_XLSX)



# ---------------------------------------------------------------------------
# Parser ενιαίου Excel → config.json (δέχεται και το παλιό 4-φυλλο ωράριο)
# ---------------------------------------------------------------------------
def _hhmm(v) -> str:
    """Δέχεται '8:15', datetime.time ή κλάσμα ημέρας του Excel (όπως lesson-wizard)."""
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    if isinstance(v, (int, float)):
        mins = round(float(v) * 24 * 60)
        return f"{mins // 60:02d}:{mins % 60:02d}"
    s = str(v).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else s


def _bool(v, default=False) -> bool:
    s = str(v or "").strip().upper()
    if s in ("ΝΑΙ", "NAI", "YES", "TRUE", "1"):
        return True
    if s in ("ΟΧΙ", "OXI", "NO", "FALSE", "0"):
        return False
    return default


def parse_config_xlsx(path: Path) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))

    # --- Ωράριο: ΙΔΙΑ λογική με parse_schedule_xlsx του Lesson Wizard ---------
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
            if row and row[0] and row[1] and row[2]:
                tm, day, per = str(row[0]).strip(), str(row[1]).strip(), str(int(row[2]))
                timetable.setdefault(tm, {}).setdefault(day, {})[per] = {
                    "title": str(row[3] or "").strip(),
                    "url": str(row[4] or "").strip() if len(row) > 4 else ""}
    if tmimata:
        cfg["schedule"] = {"tmimata": tmimata, "periods": periods, "timetable": timetable}

    # --- Μενού ---------------------------------------------------------------
    if "Μενού" in wb.sheetnames:
        menu = []
        for row in wb["Μενού"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                menu.append({"id": str(row[0]).strip(), "title": str(row[1]).strip(),
                             "icon": str(row[2] or "🔗").strip(),
                             "url": str(row[3] or "").strip(),
                             "order": int(row[4] or 99),
                             "guest": _bool(row[5], True), "student": _bool(row[6], True),
                             "teacher": _bool(row[7], True)})
        if menu:
            cfg["menu"] = sorted(menu, key=lambda m: m["order"])


    # --- Εργαλειοθήκες ---------------------------------------------------------
    if "Εργαλειοθήκες" in wb.sheetnames:
        toolbars = []
        for row in wb["Εργαλειοθήκες"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                mode = str(row[2] or "dock").strip().lower()
                toolbars.append({"id": str(row[0]).strip(), "title": str(row[1]).strip(),
                                 "mode": mode if mode in ("dock", "float") else "dock",
                                 "x": int(row[3] or 40), "y": int(row[4] or 100),
                                 "w": int(row[5] or 300), "h": int(row[6] or 360),
                                 "guest": _bool(row[7]), "student": _bool(row[8]),
                                 "teacher": _bool(row[9], True)})
        if toolbars:
            cfg["toolbars"] = toolbars

    # --- Ρόλοι & πρόσβαση ------------------------------------------------------
    if "Ρόλοι" in wb.sheetnames:
        acc = cfg["access"]
        for row in wb["Ρόλοι"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            key, val = str(row[0]).strip(), str(row[1] or "").strip()
            if key == "student_code":
                acc["student_code"] = val
            elif key == "guest_chat":
                acc["guest_chat"] = _bool(val, True)
            elif key == "guest_forum":
                acc["guest_forum"] = _bool(val, False)
            elif key in ("allowed_guest", "allowed_student", "allowed_teacher"):
                role = key.split("_", 1)[1]
                acc["allowed_apps"][role] = (
                    "*" if val in ("", "*") else [u.strip() for u in val.split(",") if u.strip()])

    # --- Ονόματα guest ---------------------------------------------------------
    if "Ονόματα Guest" in wb.sheetnames:
        adjs, nouns, colors = [], [], []
        for row in wb["Ονόματα Guest"].iter_rows(min_row=2, values_only=True):
            if not row:
                continue
            if row[0]:
                adjs.append(str(row[0]).strip())
            if row[1]:
                nouns.append({"name": str(row[1]).strip(),
                              "emoji": str(row[2] or "🎲").strip()})
            if len(row) > 3 and row[3] and re.match(r"^#[0-9a-fA-F]{6}$", str(row[3]).strip()):
                colors.append(str(row[3]).strip())
        if adjs and nouns:
            cfg["guest_names"] = {"adjectives": adjs, "nouns": nouns,
                                  "colors": colors or GUEST_COLORS}

    # --- Timers ----------------------------------------------------------------
    if "Timers" in wb.sheetnames:
        timers = []
        for row in wb["Timers"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                vis = str(row[2] or "public").strip().lower()
                timers.append({"id": str(row[0]).strip(), "label": str(row[1]).strip(),
                               "visibility": vis if vis in ("private", "public") else "public",
                               "duration_sec": int(row[3]) if row[3] else None,
                               "anchor_tmima": str(row[4] or "").strip(),
                               "day": str(row[5] or "").strip(),
                               "period": int(row[6]) if row[6] else None,
                               "edge": str(row[7] or "end").strip(),
                               "offset_min": float(row[8] or 0),
                               "message": str(row[9] or "").strip(),
                               "audience": str(row[10] or "all").strip(),
                               "enabled": _bool(row[11], True)})
        cfg["timers"] = timers


    # --- Γεγονότα ---------------------------------------------------------------
    if "Γεγονότα" in wb.sheetnames:
        events = []
        for row in wb["Γεγονότα"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                trig = str(row[1]).strip()
                action = str(row[6] or "announce").strip()
                events.append({"id": str(row[0]).strip(),
                               "trigger": trig if trig in ("day_end", "period_end", "time") else "day_end",
                               "period": int(row[2]) if row[2] else None,
                               "time": _hhmm(row[3]) if row[3] else "",
                               "offset_min": float(row[4] or 0),
                               "days": [d.strip() for d in str(row[5] or "").split(",") if d.strip()],
                               "action": action if action in ("announce", "congrats", "award", "navigate") else "announce",
                               "text": str(row[7] or "").strip(),
                               "url": str(row[8] or "").strip(),
                               "audience": str(row[9] or "all").strip(),
                               "tmima": str(row[10] or "").strip(),
                               "enabled": _bool(row[11], True)})
        cfg["events"] = events

    # --- Μηνύματα ----------------------------------------------------------------
    if "Μηνύματα" in wb.sheetnames:
        messages = []
        for row in wb["Μηνύματα"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[2]:
                kind = str(row[1] or "announce").strip()
                messages.append({"id": str(row[0]).strip(),
                                 "kind": kind if kind in ("announce", "congrats", "award") else "announce",
                                 "text": str(row[2]).strip()})
        cfg["messages"] = messages

    # --- Poll & Quiz τράπεζες ------------------------------------------------------
    if "Poll-Quiz" in wb.sheetnames:
        polls, quiz_groups = [], {}
        for row in wb["Poll-Quiz"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0] or not row[2]:
                continue
            typ = str(row[0]).strip().lower()
            options = [str(o).strip() for o in row[3:7] if o]
            if typ == "poll" and len(options) >= 2:
                polls.append({"id": str(row[1] or secrets.token_hex(4)).strip(),
                              "question": str(row[2]).strip(), "options": options,
                              "show_results": _bool(row[8], True)})
            elif typ == "quiz" and len(options) >= 2 and row[7]:
                gid = str(row[9] or row[1] or "quiz").strip()
                group = quiz_groups.setdefault(gid, {"id": gid, "title": gid, "questions": []})
                group["questions"].append({"text": str(row[2]).strip(), "options": options,
                                           "correct": int(row[7]) - 1})
        cfg["polls_bank"] = polls
        cfg["quizzes_bank"] = [g for g in quiz_groups.values()
                               if all(0 <= q["correct"] < len(q["options"]) for q in g["questions"])]

    wb.close()
    return cfg



# ---------------------------------------------------------------------------
# Routes — ρυθμίσεις Excel (καθηγητής) & εκκίνηση timers από το config
# ---------------------------------------------------------------------------
@app.get("/api/config/template")
def api_config_template(request: Request):
    require_teacher(request)
    if not TEMPLATE_XLSX.exists():
        make_template_xlsx()
    return FileResponse(TEMPLATE_XLSX, filename="rythmiseis-protypo.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/config/upload")
async def api_config_upload(request: Request, file: UploadFile = File(...)):
    global CONFIG
    require_teacher(request)
    name = PurePosixPath(file.filename or "").name
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Απαιτείται αρχείο Excel (.xlsx).")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_DIR / "rythmiseis-upload.xlsx"
    tmp.write_bytes(await file.read())
    try:
        cfg = parse_config_xlsx(tmp)
    except Exception as exc:
        raise HTTPException(400, f"Σφάλμα ανάγνωσης Excel: {exc}")
    save_config(cfg)
    CONFIG = load_config()
    EVENTS_FIRED.clear()                                # νέο config → ξανα-οπλισμός γεγονότων
    await broadcast({"type": "config_updated"})         # όλοι ξαναφορτώνουν το μενού τους
    return {"ok": True,
            "summary": {"tmimata": len(CONFIG["schedule"]["tmimata"]),
                        "menu": len(CONFIG["menu"]), "toolbars": len(CONFIG["toolbars"]),
                        "timers": len(CONFIG["timers"]), "events": len(CONFIG["events"]),
                        "messages": len(CONFIG["messages"]),
                        "polls": len(CONFIG["polls_bank"]), "quizzes": len(CONFIG["quizzes_bank"])}}


@app.get("/api/config")
def api_config_get(request: Request):
    require_teacher(request)
    return CONFIG


@app.post("/api/cmd/timer-from-config/{cfg_id}")
async def cmd_timer_from_config(cfg_id: str, request: Request):
    """Εκκινεί timer ορισμένο στο Excel (id από την καρτέλα Timers)."""
    require_teacher(request)
    t = next((x for x in CONFIG["timers"] if x["id"] == cfg_id), None)
    if not t:
        raise HTTPException(404, "Δεν βρέθηκε timer με αυτό το id στο Excel.")
    if t.get("period"):
        ends = schedule_deadline(t.get("anchor_tmima", ""), t.get("day", ""),
                                 int(t["period"]), t.get("edge", "end"),
                                 float(t.get("offset_min", 0)))
        if not ends or ends <= time.time():
            raise HTTPException(400, "Η στιγμή του ωραρίου (+offset) έχει ήδη περάσει σήμερα.")
    else:
        ends = time.time() + float(t.get("duration_sec") or 300)
    tid = secrets.token_hex(6)
    timer = {"id": tid, "label": t["label"], "ends_at": ends, "server_now": time.time(),
             "visibility": t.get("visibility", "public"),
             "audience": t.get("audience", "all"), "tmima": "",
             "message": t.get("message", "")}
    ACTIVE_TIMERS[tid] = timer
    aud = "teachers" if timer["visibility"] == "private" else timer["audience"]
    await broadcast({"type": "timer", **timer}, audience=aud)
    return {"ok": True, "id": tid, "ends_at": ends}

