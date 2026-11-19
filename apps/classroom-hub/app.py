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

Δομή (Task 3 architecture review — διάσπαση μονόλιθου σε APIRouters):
  app.py            wiring: FastAPI, lifespan, mounts, σελίδα/join/config-public
  state.py          κοινό state (CONFIG/CLIENTS/ACTIVE_*), auth & ident cookies
  store.py          SQLite schema + queries (chat/forum/polls/quizzes/mutes)
  presence.py       Client, broadcast, roster, housekeeping, WS handler /ws
  routers/          commands · polls · quizzes · timers · chat_forum ·
                    config_xlsx · catalog

Τρέχει στο 127.0.0.1:8014 πίσω από τον Nginx στο /classroom/ (WebSockets).
Χωρίς Docker· ένας worker (βλ. systemd school-classroom.service).
"""
from __future__ import annotations

import asyncio
import random
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from common.auth import TEACHER_CODE, COOKIE_MAX_AGE

import state
import store
import presence
from routers import commands, polls, quizzes, timers, chat_forum, config_xlsx, catalog

store.init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(presence.housekeeping())
    yield
    task.cancel()


app = FastAPI(
    title="Classroom Hub — Ζωντανή Τάξη",
    description="Παρουσία, εντολές τάξης, timers ωραρίου & ενιαίες ρυθμίσεις Excel",
    docs_url=None, redoc_url=None, openapi_url=None,
    lifespan=lifespan,
)
templates = Jinja2Templates(directory=str(state.BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(state.BASE_DIR / "static")), name="static")

for module in (commands, polls, quizzes, timers, chat_forum, config_xlsx, catalog):
    app.include_router(module.router)


# ---------------------------------------------------------------------------
# Routes — σελίδα, είσοδος ανά ρόλο, δημόσια ρυθμίσεις
# ---------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"status": "ok", "clients": len(state.CLIENTS)}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/me")
def api_me(request: Request):
    ident = state.identity_from(request)
    if ident and state.is_teacher(request):
        ident["role"] = "teacher"                       # ο κωδικός καθηγητή υπερισχύει
    return {"identity": ident, "teacher": state.is_teacher(request)}


@app.post("/api/join")
async def api_join(request: Request, response: Response):
    """Είσοδος: role=guest (τυχαίο όνομα), student (όνομα+τμήμα+κωδικός τάξης),
    teacher (κοινόχρηστος κωδικός πύλης). Εκδίδει HMAC ident cookie για το WebSocket."""
    body = await request.json()
    role = str(body.get("role", "guest")).strip()
    uid = secrets.token_hex(8)
    if role == "teacher":
        if str(body.get("code", "")) != TEACHER_CODE:
            raise HTTPException(403, "Λάθος κωδικός καθηγητή.")
        name = state.clean_name(body.get("name") or "Καθηγητής")
        ident = {"uid": uid, "role": "teacher", "name": name, "tmima": "",
                 "emoji": "🧑‍🏫", "color": "#10b981"}
        response.set_cookie(state.COOKIE_NAME, state.make_token("teacher"), max_age=COOKIE_MAX_AGE,
                            httponly=True, samesite="lax", path="/")
    elif role == "student":
        name = state.clean_name(body.get("name"))
        tmima = str(body.get("tmima", "")).strip()
        known = {t["name"] for t in state.CONFIG["schedule"]["tmimata"]}
        if known and tmima not in known:
            raise HTTPException(400, f"Άγνωστο τμήμα '{tmima}'. Διάλεξε από τη λίστα.")
        code_needed = state.CONFIG["access"].get("student_code", "")
        if code_needed and str(body.get("code", "")) != code_needed:
            raise HTTPException(403, "Λάθος κωδικός τάξης.")
        ident = {"uid": uid, "role": "student", "name": name, "tmima": tmima,
                 "emoji": "👨‍🎓", "color": random.choice(state.GUEST_COLORS)}
    else:
        role = "guest"
        gn = state.guest_name()
        ident = {"uid": uid, "role": "guest", "name": gn["name"], "tmima": "",
                 "emoji": gn["emoji"], "color": gn["color"]}
    state.set_identity(response, ident["uid"], ident["role"], ident["name"], ident["tmima"])
    return {"ok": True, "identity": ident}


@app.post("/api/leave")
def api_leave(request: Request, response: Response):
    response.delete_cookie(state.IDENT_COOKIE, path="/")
    response.delete_cookie(state.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/config/public")
def api_config_public(request: Request):
    """Ρυθμίσεις φιλτραρισμένες ΑΝΑ ΡΟΛΟ (μενού, εργαλειοθήκες, πρόσβαση)."""
    ident = state.identity_from(request)
    role = "teacher" if state.is_teacher(request) else (ident["role"] if ident else "guest")
    menu = sorted([m for m in state.CONFIG["menu"] if m.get(role)], key=lambda m: m.get("order", 99))
    toolbars = [t for t in state.CONFIG["toolbars"] if t.get(role)]
    acc = state.CONFIG["access"]
    return {
        "role": role,
        "menu": menu,
        "toolbars": toolbars,
        "tmimata": state.CONFIG["schedule"]["tmimata"],
        "periods": state.CONFIG["schedule"]["periods"],
        "timetable": state.CONFIG["schedule"]["timetable"],
        "guest_chat": acc.get("guest_chat", True),
        "guest_forum": acc.get("guest_forum", False),
        "allowed_apps": acc.get("allowed_apps", {}).get(role, "*"),
        "messages": state.CONFIG["messages"] if role == "teacher" else [],
        "polls_bank": state.CONFIG["polls_bank"] if role == "teacher" else [],
        "quizzes_bank": [{"id": q["id"], "title": q["title"], "count": len(q["questions"])}
                         for q in state.CONFIG["quizzes_bank"]] if role == "teacher" else [],
        "timers_cfg": state.CONFIG["timers"] if role == "teacher" else [],
        "events_cfg": state.CONFIG["events"] if role == "teacher" else [],
        "announce_links": state.CONFIG.get("announce_links", []) if role == "teacher" else [],
        "announcements": store.visible_announcements(ident, role == "teacher"),
        "server_now": time.time(),
    }


# ---------------------------------------------------------------------------
# WebSocket — ο handler ζει στο presence.py (dispatch σε poll/quiz/chat/forum)
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def hub_socket(ws: WebSocket):
    await presence.hub_socket(ws)


# Συμβατότητα με scripts/classroom-test.py (import app as hub → parse_config_xlsx)
parse_config_xlsx = config_xlsx.parse_config_xlsx
make_template_xlsx = config_xlsx.make_template_xlsx