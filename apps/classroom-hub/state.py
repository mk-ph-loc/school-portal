"""
Classroom Hub — κοινό state & αυθεντικοποίηση (Task 3: διάσπαση σε APIRouters).

Εδώ ζουν ΟΛΑ τα globals που μοιράζονται οι routers (CONFIG, CLIENTS, ACTIVE_*),
ώστε να μην υπάρχουν κυκλικά imports: κάθε router κάνει `import state` και
διαβάζει/γράφει `state.CONFIG` κ.λπ. ΠΟΤΕ `from state import CONFIG` — το
Excel upload αντικαθιστά ολόκληρο το dict (state.CONFIG = load_config()).

Περιεχόμενο: διαδρομές/σταθερές, TeacherAuth + ident cookie helpers,
προεπιλεγμένες ρυθμίσεις & load/save του config.json, παιχνιδιάρικα ονόματα
guests και validation ονομάτων/κοινού. Καμία ενέργεια πέρα από το φόρτωμα
του config κατά το import (όπως στον παλιό μονόλιθο app.py).
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request, Response

from common.auth import TeacherAuth, COOKIE_MAX_AGE

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

COOKIE_NAME = "classroom_teacher"
IDENT_COOKIE = "classroom_ident"                       # HttpOnly HMAC ταυτότητα σύνδεσης

HEARTBEAT_TIMEOUT = 45                                 # χωρίς ping τόσο → αποσύνδεση
ROLES = ("guest", "student", "teacher")
NAME_RE = re.compile(r"^[\w\u0370-\u03ff\u1f00-\u1fff .'-]{1,40}$")


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση: HMAC cookies (common.auth — ίδιο μοτίβο με όλη την πύλη)
# ---------------------------------------------------------------------------
auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
make_token = auth.signed_token                         # payload μορφή (ελληνικά ονόματα)
token_payload = auth.token_payload


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


def clean_name(v: str) -> str:
    v = str(v or "").strip()
    if not NAME_RE.match(v):
        raise HTTPException(400, "Μη έγκυρο όνομα (έως 40 χαρακτήρες, γράμματα/ψηφία).")
    return v


def audience_of(body: dict) -> tuple[str, str]:
    """Κοινό εντολής: audience all/students/guests/teachers/role:X + τμήμα."""
    aud = str(body.get("audience", "all"))
    if aud not in ("all", "students", "guests", "teachers") and not aud.startswith("role:"):
        raise HTTPException(400, "Μη έγκυρο κοινό (all/students/guests/teachers).")
    return aud, str(body.get("tmima", "")).strip()


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
        {"id": "manage", "title": "Διαχείριση", "icon": "🗄️", "url": "#manage",
         "order": 6, "guest": False, "student": False, "teacher": True},
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
    "announce_links": [],  # διαμορφώσιμοι σύνδεσμοι για τη σύνθετη ανακοίνωση
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
            # Νέα built-in panels προστίθενται αυτόματα σε παλαιότερα uploads
            # (π.χ. 🗄️ Διαχείριση) — δεν χάνονται οι ρυθμίσεις του χρήστη.
            known = {m["id"] for m in cfg["menu"]}
            for m in DEFAULT_CONFIG["menu"]:
                if m["id"] not in known:
                    cfg["menu"].append(dict(m))
            cfg["menu"].sort(key=lambda m: m.get("order", 99))
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
# Ζωντανή κατάσταση (ένα event loop, ένας worker — βλ. systemd).
# Τα dicts γεμίζουν από presence.py/routers· εδώ μόνο οι αρχικές δηλώσεις.
# ---------------------------------------------------------------------------
CLIENTS: dict = {}                                      # id(ws) → presence.Client
ACTIVE_TIMERS: dict[str, dict] = {}                     # id → {label, ends_at, audience, tmima}
ACTIVE_POLLS: dict[str, dict] = {}                      # id → κατάσταση poll
ACTIVE_QUIZZES: dict[str, dict] = {}                    # id → κατάσταση quiz
EVENTS_FIRED: set[str] = set()                          # "event_id:YYYY-MM-DD" (μία φορά/ημέρα)
# Οι ανακοινώσεις αποθηκεύονται ΜΟΝΙΜΑ στη SQLite (πίνακας announcements).