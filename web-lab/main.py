"""
Εργαστήριο Web (HTML / CSS / JS) — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

Διαδραστικό, συνεργατικό περιβάλλον εκμάθησης ανάπτυξης ιστοσελίδων για το
τοπικό δίκτυο της τάξης. FastAPI + WebSockets + SQLite (χωρίς Docker):
  * Editor 3 πάνελ (HTML/CSS/JS, CodeMirror τοπικά — 100% offline) με ζωντανή
    προεπισκόπηση <iframe> και ενσωματωμένη κονσόλα (console.log / σφάλματα).
  * Ατομική λειτουργία (Solo): αυτόματη αποθήκευση στο localStorage του browser.
  * Δωμάτια συνεργασίας ομάδας με 4-ψήφιο PIN: ζωντανός συγχρονισμός κώδικα
    μέσω WebSockets + μόνιμη αποθήκευση στη weblab.db (επιβιώνει refresh).
  * Λειτουργία καθηγητή (κωδικός teacher2026, HMAC cookie όπως στο /exams/):
    «Αποστολή Κώδικα σε Όλους» (broadcast) & «Μόνο Ανάγνωση» (κλείδωμα τάξης).
  * Δημοσίευση project στα custom-apps/<id>/ + build-apps-manifest.py ώστε να
    εμφανίζεται αμέσως ως κάρτα στο κεντρικό Dashboard (/apps/<id>/).

Τρέχει στο 127.0.0.1:8011 πίσω από τον Nginx στο /web-lab/ (WebSockets).
ΣΗΜΕΙΩΣΗ: Η θύρα 8010 χρησιμοποιείται ήδη από το excalidraw-room (/board-ws/).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "weblab.db"
APPS_DIR = PORTAL_DIR / "custom-apps"
MANIFEST_SCRIPT = PORTAL_DIR / "scripts" / "build-apps-manifest.py"

TEACHER_CODE = "teacher2026"
COOKIE_NAME = "weblab_teacher"
COOKIE_MAX_AGE = 8 * 3600            # μία σχολική ημέρα
MAX_ROOM_MEMBERS = 60                # ένα εργαστήριο/τμήμα
MAX_CODE_CHARS = 200_000             # ανά πάνελ (HTML/CSS/JS)
ROOM_TTL = 7 * 24 * 3600             # καθαρισμός δωματίων ανενεργών για 7 ημέρες
PIN_RE = re.compile(r"^\d{4}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")   # ίδιο με το build-apps-manifest.py
VALID_ACCESS = {"all", "teachers"}

app = FastAPI(
    title="Εργαστήριο Web (HTML / CSS / JS)",
    description="Συνεργατικός editor ανάπτυξης ιστοσελίδων για το LAN της τάξης",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/web-lab) ορίζεται στο uvicorn μέσω του systemd
# unit, ώστε τα url_for() των templates να παράγουν σωστό πρόθεμα πίσω από
# τον Nginx.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Βάση δεδομένων (SQLite — ενσωματωμένη στην Python, χωρίς επιπλέον πακέτα)
# ---------------------------------------------------------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                pin         TEXT PRIMARY KEY,             -- 4-ψήφιος κωδικός δωματίου
                name        TEXT NOT NULL DEFAULT '',
                html        TEXT NOT NULL DEFAULT '',
                css         TEXT NOT NULL DEFAULT '',
                js          TEXT NOT NULL DEFAULT '',
                locked      INTEGER NOT NULL DEFAULT 0,   -- 1 = Μόνο Ανάγνωση (καθηγητής)
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC), όχι απλό flag
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Βοηθητικά δωματίων & δημοσίευσης
# ---------------------------------------------------------------------------
def get_room(conn: sqlite3.Connection, pin: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM rooms WHERE pin=?", (pin,)).fetchone()
    if row is None:
        raise HTTPException(404, "Το δωμάτιο δεν βρέθηκε — έλεγξε τον 4-ψήφιο κωδικό.")
    return row


def room_code(row: sqlite3.Row) -> dict:
    return {"html": row["html"], "css": row["css"], "js": row["js"]}


def clean_code(value: str, label: str) -> str:
    value = value or ""
    if len(value) > MAX_CODE_CHARS:
        raise HTTPException(400, f"Το {label} είναι πολύ μεγάλο (> {MAX_CODE_CHARS} χαρακτήρες).")
    return value


def new_pin(conn: sqlite3.Connection) -> str:
    for _ in range(100):
        pin = f"{secrets.randbelow(9000) + 1000}"
        if conn.execute("SELECT 1 FROM rooms WHERE pin=?", (pin,)).fetchone() is None:
            return pin
    raise HTTPException(503, "Δεν υπάρχει διαθέσιμος κωδικός δωματίου — δοκίμασε ξανά.")


def rebuild_manifest() -> None:
    """Εκτελεί το build-apps-manifest.py ώστε το Dashboard να ενημερωθεί άμεσα."""
    proc = subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise HTTPException(500, "Αποτυχία ενημέρωσης manifest: " + (proc.stderr or proc.stdout).strip())


def fix_permissions(app_dir: Path) -> None:
    """Φάκελοι 755, αρχεία 644 — όπως ορίζει ο CUSTOM-APPS-GUIDE.md."""
    for p in sorted(app_dir.rglob("*"), reverse=True):
        p.chmod(0o755 if p.is_dir() else 0o644)
    app_dir.chmod(0o755)


def merge_document(title: str, html: str, css: str, js: str) -> str:
    """Ενώνει HTML + <style> + <script> σε ΕΝΑ αυτόνομο αρχείο .html.

    Λειτουργεί τόσο με πλήρη έγγραφα (<!DOCTYPE html>…) όσο και με σκέτο
    περιεχόμενο <body>. Το CSS μπαίνει στο τέλος της <head> (ώστε να υπερισχύει)
    και η JS πριν το </body> (ώστε να βρίσκει τα στοιχεία της σελίδας).
    """
    title = (title or "Η Ιστοσελίδα μου").strip() or "Η Ιστοσελίδα μου"
    doc = (html or "").strip()
    style = f"<style>\n{css.strip()}\n</style>" if css.strip() else ""
    script = f"<script>\n{js.strip()}\n</script>" if js.strip() else ""

    if not re.search(r"<html\b", doc, re.IGNORECASE):
        parts = ["<!DOCTYPE html>", '<html lang="el">', "<head>",
                 '<meta charset="utf-8">',
                 '<meta name="viewport" content="width=device-width, initial-scale=1">',
                 f"<title>{title}</title>"]
        if style:
            parts.append(style)
        parts += ["</head>", "<body>", doc]
        if script:
            parts.append(script)
        parts += ["</body>", "</html>"]
        return "\n".join(parts) + "\n"

    # Πλήρες έγγραφο: αντικατάσταση τίτλου & εισαγωγή style/script στα σωστά σημεία
    if re.search(r"<title>.*?</title>", doc, re.IGNORECASE | re.DOTALL):
        doc = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", doc,
                     count=1, flags=re.IGNORECASE | re.DOTALL)
    if style:
        if re.search(r"</head>", doc, re.IGNORECASE):
            doc = re.sub(r"</head>", style + "\n</head>", doc, count=1, flags=re.IGNORECASE)
        else:
            doc = style + "\n" + doc
    if script:
        if re.search(r"</body>", doc, re.IGNORECASE):
            doc = re.sub(r"</body>", script + "\n</body>", doc, count=1, flags=re.IGNORECASE)
        else:
            doc += "\n" + script
    return doc + "\n"


# ---------------------------------------------------------------------------
# Ζωντανή κατάσταση & WebSockets (ένα event loop, ένας worker — βλ. systemd)
# ---------------------------------------------------------------------------
class Room:
    """Ενεργές συνδέσεις ενός δωματίου συνεργασίας."""

    def __init__(self) -> None:
        self.sockets: set[WebSocket] = set()


ROOMS: dict[str, Room] = {}


def room(pin: str) -> Room:
    if pin not in ROOMS:
        ROOMS[pin] = Room()
    return ROOMS[pin]


async def send_json(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except Exception:
        pass  # η σύνδεση θα καθαριστεί στο receive loop


async def broadcast(pin: str, payload: dict, exclude: WebSocket | None = None) -> None:
    for ws in list(room(pin).sockets):
        if ws is not exclude:
            await send_json(ws, payload)


def members_payload(pin: str) -> dict:
    members = []
    for ws in room(pin).sockets:
        members.append({
            "name": getattr(ws.state, "member_name", "Ανώνυμος"),
            "teacher": bool(getattr(ws.state, "is_teacher", False)),
        })
    members.sort(key=lambda m: (not m["teacher"], m["name"].casefold()))
    return {"type": "members", "members": members}


def state_payload(row: sqlite3.Row) -> dict:
    return {"type": "state", "pin": row["pin"], "name": row["name"],
            "locked": bool(row["locked"]), "code": room_code(row)}


# ---------------------------------------------------------------------------
# Σελίδα (HTML) & health check
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def editor_page(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"logged_in": token_valid(request.cookies.get(COOKIE_NAME))},
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "school-weblab"}


# ---------------------------------------------------------------------------
# API Καθηγητή — προστατευμένο με κωδικό teacher2026 (HMAC cookie)
# ---------------------------------------------------------------------------
class Login(BaseModel):
    password: str


@app.post("/api/teacher/login")
def teacher_login(payload: Login, response: Response):
    # encode() ώστε να υποστηρίζονται και μη-ASCII (λανθασμένοι) κωδικοί
    if not hmac.compare_digest(payload.password.encode(), TEACHER_CODE.encode()):
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


# ---------------------------------------------------------------------------
# API Δωματίων Συνεργασίας (Team Rooms)
# ---------------------------------------------------------------------------
class RoomIn(BaseModel):
    name: str = Field("", max_length=80)
    html: str = ""
    css: str = ""
    js: str = ""


@app.post("/api/rooms")
def create_room(payload: RoomIn):
    """Δημιουργία δωματίου από ομάδα μαθητών ή καθηγητή → 4-ψήφιο PIN."""
    now = time.time()
    with db() as conn:
        pin = new_pin(conn)
        conn.execute(
            "INSERT INTO rooms (pin, name, html, css, js, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (pin, payload.name.strip()[:80],
             clean_code(payload.html, "HTML"), clean_code(payload.css, "CSS"),
             clean_code(payload.js, "JavaScript"), now, now),
        )
    return {"ok": True, "pin": pin}


@app.get("/api/rooms/{pin}")
def read_room(pin: str):
    """Snapshot δωματίου (φόρτωση μετά από refresh / είσοδος με PIN)."""
    if not PIN_RE.match(pin):
        raise HTTPException(400, "Ο κωδικός δωματίου πρέπει να είναι 4 ψηφία (π.χ. 7342).")
    with db() as conn:
        row = get_room(conn, pin)
        return {"pin": row["pin"], "name": row["name"], "locked": bool(row["locked"]),
                "code": room_code(row), "updated_at": row["updated_at"]}


# ---------------------------------------------------------------------------
# Δημοσίευση στα Custom Apps του Portal (μόνο καθηγητής)
# ---------------------------------------------------------------------------
class PublishIn(BaseModel):
    id: str
    title: str
    description: str = ""
    icon: str = "🌐"
    access: str = "all"
    replace: bool = False
    html: str = ""
    css: str = ""
    js: str = ""


@app.post("/api/publish")
def publish_app(payload: PublishIn, request: Request):
    require_teacher(request)

    app_id = (payload.id or "").strip()
    if app_id.startswith(("_", ".")) or not ID_RE.match(app_id):
        raise HTTPException(400, "Το id επιτρέπεται να περιέχει μόνο πεζά λατινικά, ψηφία και παύλες (π.χ. class-site).")
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "Ο τίτλος είναι υποχρεωτικός.")
    if len(title) > 200:
        raise HTTPException(400, "Ο τίτλος είναι πολύ μεγάλος (> 200 χαρακτήρες).")
    access = payload.access.strip()
    if access not in VALID_ACCESS:
        raise HTTPException(400, "Το access πρέπει να είναι 'all' ή 'teachers'.")
    if not any((payload.html.strip(), payload.css.strip(), payload.js.strip())):
        raise HTTPException(400, "Το project είναι άδειο — γράψε πρώτα κάποιον κώδικα.")

    dest = APPS_DIR / app_id
    if dest.exists() and not payload.replace:
        raise HTTPException(409, f"Η εφαρμογή '{app_id}' υπάρχει ήδη. Τσέκαρε την «Αντικατάσταση υπάρχουσας» για αντικατάσταση.")
    if dest.is_symlink():
        raise HTTPException(400, "Μη επιτρεπτός φάκελος προορισμού (symlink).")

    index_html = merge_document(
        title,
        clean_code(payload.html, "HTML"),
        clean_code(payload.css, "CSS"),
        clean_code(payload.js, "JavaScript"),
    )
    meta = {
        "id": app_id, "title": title,
        "description": payload.description.strip()[:300] or "Δημιουργία της τάξης από το Εργαστήριο Web.",
        "category": "Εργαστήριο Web / Δημιουργίες Τάξης",
        "icon": payload.icon.strip() or "🌐",
        "access": access,
    }

    # --- Κατασκευή σε προσωρινό φάκελο & ατομική αντικατάσταση (όπως ο App Builder) ---
    staging = APPS_DIR / f".staging-{app_id}-{secrets.token_hex(4)}"
    staging.mkdir(parents=True)
    backup = None
    try:
        (staging / "index.html").write_text(index_html, encoding="utf-8")
        (staging / "app.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fix_permissions(staging)
        if dest.exists():
            backup = APPS_DIR / f".backup-{app_id}-{secrets.token_hex(4)}"
            dest.rename(backup)
        try:
            staging.rename(dest)
        except OSError:
            if backup:
                backup.rename(dest)
            raise
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        rebuild_manifest()
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {"ok": True, "url": f"/apps/{app_id}/", "title": title}


# ---------------------------------------------------------------------------
# WebSocket δωματίου — ζωντανός συγχρονισμός HTML/CSS/JS
# ---------------------------------------------------------------------------
@app.websocket("/ws/{pin}")
async def room_socket(ws: WebSocket, pin: str):
    is_teacher = token_valid(ws.cookies.get(COOKIE_NAME))
    member_name = (ws.query_params.get("name") or "").strip()[:40] or "Μαθητής"
    if not PIN_RE.match(pin):
        await ws.close(code=4400)
        return
    with db() as conn:
        row = conn.execute("SELECT * FROM rooms WHERE pin=?", (pin,)).fetchone()
        if row is None:
            await ws.close(code=4404)
            return
    if len(room(pin).sockets) >= MAX_ROOM_MEMBERS:
        await ws.close(code=4429)
        return
    await ws.accept()
    ws.state.is_teacher = is_teacher
    ws.state.member_name = ("👩‍🏫 " if is_teacher else "") + member_name
    r = room(pin)
    r.sockets.add(ws)
    try:
        with db() as conn:
            row = get_room(conn, pin)
            await send_json(ws, state_payload(row))       # πλήρες snapshot (refresh-safe)
        await broadcast(pin, members_payload(pin))
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")

            if kind == "ping":
                await send_json(ws, {"type": "pong"})

            elif kind == "edit":
                # Ζωντανή πληκτρολόγηση: ενημέρωση ενός πάνελ (html|css|js)
                panel = msg.get("panel")
                if panel not in ("html", "css", "js"):
                    continue
                with db() as conn:
                    row = get_room(conn, pin)
                    if row["locked"] and not is_teacher:
                        await send_json(ws, {"type": "denied",
                                             "reason": "Το δωμάτιο είναι σε «Μόνο Ανάγνωση» από τον καθηγητή."})
                        await send_json(ws, state_payload(row))
                        continue
                    code = clean_code(str(msg.get("code", "")), panel.upper())
                    conn.execute(
                        f"UPDATE rooms SET {panel}=?, updated_at=? WHERE pin=?",
                        (code, time.time(), pin),
                    )
                await broadcast(pin, {"type": "code", "panel": panel, "code": code,
                                      "by": ws.state.member_name}, exclude=ws)

            elif kind == "broadcast" and is_teacher:
                # «Αποστολή Κώδικα σε Όλους» — αντικαθιστά και τα 3 πάνελ
                html = clean_code(str(msg.get("html", "")), "HTML")
                css = clean_code(str(msg.get("css", "")), "CSS")
                js = clean_code(str(msg.get("js", "")), "JavaScript")
                with db() as conn:
                    get_room(conn, pin)
                    conn.execute(
                        "UPDATE rooms SET html=?, css=?, js=?, updated_at=? WHERE pin=?",
                        (html, css, js, time.time(), pin),
                    )
                await broadcast(pin, {"type": "full", "code": {"html": html, "css": css, "js": js},
                                      "by": ws.state.member_name, "announce": True})

            elif kind == "lock" and is_teacher:
                # «Μόνο Ανάγνωση (Προβολή στον Πίνακα)» — κλείδωμα/ξεκλείδωμα
                locked = 1 if msg.get("locked") else 0
                with db() as conn:
                    get_room(conn, pin)
                    conn.execute("UPDATE rooms SET locked=?, updated_at=? WHERE pin=?",
                                 (locked, time.time(), pin))
                await broadcast(pin, {"type": "lock", "locked": bool(locked),
                                      "by": ws.state.member_name})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except HTTPException as exc:
        await send_json(ws, {"type": "error", "message": str(exc.detail)})
    except Exception:
        pass  # μη έγκυρο JSON κ.λπ. — η σύνδεση κλείνει καθαρά
    finally:
        r.sockets.discard(ws)
        if not r.sockets:
            ROOMS.pop(pin, None)
        else:
            await broadcast(pin, members_payload(pin))


# ---------------------------------------------------------------------------
# Εκκίνηση / περιοδικός καθαρισμός
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup() -> None:
    init_db()
    asyncio.create_task(_cleanup_loop())


async def _cleanup_loop() -> None:
    """Σβήνει δωμάτια ανενεργά για > ROOM_TTL ώστε το PIN pool να μένει διαθέσιμο."""
    while True:
        try:
            cutoff = time.time() - ROOM_TTL
            with db() as conn:
                old = conn.execute(
                    "SELECT pin FROM rooms WHERE updated_at<?", (cutoff,)
                ).fetchall()
                for row in old:
                    if not ROOMS.get(row["pin"]):     # όχι ενεργό μάθημα
                        conn.execute("DELETE FROM rooms WHERE pin=?", (row["pin"],))
        except Exception:
            pass
        await asyncio.sleep(3600)