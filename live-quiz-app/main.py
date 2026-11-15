"""
Ζωντανό Παιχνίδι Τάξης (Live Quiz) — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

Ελαφριά εφαρμογή ζωντανών κουίζ πραγματικού χρόνου (τύπου Kahoot) για το
τοπικό δίκτυο της τάξης. FastAPI + WebSockets + SQLite:
  * Οθόνη καθηγητή/προτζέκτορα (κωδικός teacher2026): δημιουργία κουίζ
    (χειροκίνητα, εισαγωγή JSON/CSV ή έτοιμα ελληνικά παραδείγματα),
    έναρξη live session με 4-ψήφιο PIN, ροή ερωτήσεων με αντίστροφη
    μέτρηση, γράφημα απαντήσεων και Top-5 leaderboard.
  * Οθόνη μαθητή (χωρίς κωδικό): PIN + όνομα, 4 χρωματιστά κουμπιά
    απαντήσεων, άμεση ανατροφοδότηση ορθότητας/πόντων/κατάταξης.
  * Βαθμολογία τύπου Kahoot: 500–1000 πόντοι ανά σωστή απάντηση,
    ανάλογα με την ταχύτητα (0 για λάθος).

Τρέχει στο 127.0.0.1:8005 πίσω από τον Nginx στο /live-quiz/ (WebSockets).
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "livequiz.db"

TEACHER_CODE = "teacher2026"
COOKIE_NAME = "livequiz_teacher"
COOKIE_MAX_AGE = 8 * 3600            # μία σχολική ημέρα
MAX_PLAYERS = 60                     # ένα εργαστήριο/τμήμα
MAX_QUESTIONS = 50
SESSION_TTL = 12 * 3600              # αυτόματος καθαρισμός ανενεργών sessions
REVEAL_SECONDS = 6                   # διάρκεια προβολής αποτελεσμάτων στον προτζέκτορα

app = FastAPI(
    title="Ζωντανό Παιχνίδι Τάξης (Live Quiz)",
    description="Ζωντανά κουίζ πραγματικού χρόνου για το LAN της τάξης",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/live-quiz) ορίζεται στο uvicorn μέσω του systemd
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
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quizzes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                questions   TEXT NOT NULL DEFAULT '[]',   -- JSON λίστα ερωτήσεων
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                pin         TEXT PRIMARY KEY,             -- 4-ψήφιο PIN δωματίου
                quiz_id     INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
                state       TEXT NOT NULL DEFAULT 'lobby',-- lobby|question|reveal|leaderboard|finished
                q_index     INTEGER NOT NULL DEFAULT -1,  -- τρέχουσα ερώτηση (-1 = καμία)
                deadline    REAL NOT NULL DEFAULT 0,      -- epoch λήξης αντίστροφης μέτρησης
                created_at  REAL NOT NULL,
                finished_at REAL
            );
            CREATE TABLE IF NOT EXISTS players (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pin         TEXT NOT NULL REFERENCES sessions(pin) ON DELETE CASCADE,
                token       TEXT NOT NULL UNIQUE,         -- μυστικό επανασύνδεσης μαθητή
                name        TEXT NOT NULL,
                score       INTEGER NOT NULL DEFAULT 0,
                joined_at   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS answers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pin         TEXT NOT NULL REFERENCES sessions(pin) ON DELETE CASCADE,
                player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                q_index     INTEGER NOT NULL,
                choice      INTEGER NOT NULL,             -- 0..3
                correct     INTEGER NOT NULL,             -- 0/1
                points      INTEGER NOT NULL DEFAULT 0,
                elapsed     REAL NOT NULL,                -- δευτερόλεπτα από την έναρξη
                answered_at REAL NOT NULL,
                UNIQUE (player_id, q_index)               -- μία απάντηση ανά ερώτηση
            );
            CREATE INDEX IF NOT EXISTS idx_players_pin ON players(pin);
            CREATE INDEX IF NOT EXISTS idx_answers_pin_q ON answers(pin, q_index);
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
# Έτοιμα ελληνικά παραδείγματα κουίζ
# ---------------------------------------------------------------------------
SAMPLE_QUIZZES: list[dict[str, Any]] = [
    {
        "title": "Πληροφορική Α' Γυμνασίου — Βασικές Έννοιες",
        "questions": [
            {"text": "Ποιο από τα παρακάτω είναι συσκευή ΕΙΣΟΔΟΥ;",
             "options": ["Οθόνη", "Πληκτρολόγιο", "Εκτυπωτής", "Ηχεία"], "correct": 1, "time": 20},
            {"text": "Τι σημαίνει η συντομογραφία CPU;",
             "options": ["Κεντρική Μονάδα Επεξεργασίας", "Κεντρική Μνήμη Υπολογιστή",
                         "Μονάδα Αποθήκευσης Δεδομένων", "Κάρτα Γραφικών"], "correct": 0, "time": 20},
            {"text": "Πόσα bit αποτελούν ένα byte;",
             "options": ["4", "8", "16", "32"], "correct": 1, "time": 15},
            {"text": "Ποιο πρόγραμμα χρησιμοποιούμε για περιήγηση στο Διαδίκτυο;",
             "options": ["Επεξεργαστή κειμένου", "Πρόγραμμα περιήγησης (browser)",
                         "Υπολογιστικό φύλλο", "Πρόγραμμα ζωγραφικής"], "correct": 1, "time": 20},
            {"text": "Ποια μνήμη χάνει τα δεδομένα της όταν σβήσει ο υπολογιστής;",
             "options": ["Σκληρός δίσκος", "RAM", "USB flash", "DVD"], "correct": 1, "time": 20},
        ],
    },
    {
        "title": "Δυαδικό Σύστημα & Μετατροπές",
        "questions": [
            {"text": "Πόσο είναι το δυαδικό 1010 στο δεκαδικό;",
             "options": ["8", "10", "12", "5"], "correct": 1, "time": 25},
            {"text": "Πόσο είναι το δεκαδικό 7 στο δυαδικό;",
             "options": ["101", "110", "111", "1000"], "correct": 2, "time": 25},
            {"text": "Πόσους διαφορετικούς αριθμούς αναπαριστούμε με 3 bit;",
             "options": ["3", "6", "8", "9"], "correct": 2, "time": 20},
            {"text": "Ποιος είναι ο μεγαλύτερος αριθμός με 4 bit;",
             "options": ["4", "8", "15", "16"], "correct": 2, "time": 20},
            {"text": "Το δυαδικό σύστημα χρησιμοποιεί τα ψηφία…",
             "options": ["0 και 1", "0 έως 9", "1 και 2", "0 έως 7"], "correct": 0, "time": 15},
        ],
    },
    {
        "title": "Ασφάλεια στο Διαδίκτυο",
        "questions": [
            {"text": "Ποιος είναι ο πιο ασφαλής κωδικός πρόσβασης;",
             "options": ["123456", "το όνομά μου", "K9#mP2$vL8!q", "password"], "correct": 2, "time": 20},
            {"text": "Τι είναι το phishing;",
             "options": ["Ιός υπολογιστή", "Απάτη με ψεύτικα μηνύματα/ιστοσελίδες",
                         "Πρόγραμμα antivirus", "Τρόπος backup"], "correct": 1, "time": 25},
            {"text": "Λαμβάνεις email που ζητά τον κωδικό σου. Τι κάνεις;",
             "options": ["Τον στέλνω αμέσως", "Απαντώ και ρωτάω γιατί",
                         "Δεν τον δίνω ποτέ και το αναφέρω", "Τον δίνω μόνο σε φίλους"], "correct": 2, "time": 25},
            {"text": "Τι προστατεύει το HTTPS σε μια ιστοσελίδα;",
             "options": ["Την ταχύτητα φόρτωσης", "Την κρυπτογράφηση της σύνδεσης",
                         "Τα χρώματα της σελίδας", "Τις διαφημίσεις"], "correct": 1, "time": 20},
            {"text": "Πού είναι ασφαλές να αποθηκεύουμε αντίγραφα ασφαλείας;",
             "options": ["Μόνο στον ίδιο δίσκο", "Σε εξωτερικό δίσκο ή έμπιστο cloud",
                         "Πουθενά, δεν χρειάζονται", "Στον κάδο ανακύκλωσης"], "correct": 1, "time": 25},
        ],
    },
]


# ---------------------------------------------------------------------------
# Επικύρωση ερωτήσεων & εισαγωγή JSON/CSV
# ---------------------------------------------------------------------------
class QuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    options: list[str] = Field(min_length=4, max_length=4)
    correct: int = Field(ge=0, le=3)
    time: int = Field(default=20, ge=5, le=120)   # χρονικό όριο σε δευτερόλεπτα


class QuizIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    questions: list[QuestionIn] = Field(min_length=1, max_length=MAX_QUESTIONS)


def clean_questions(raw: list[dict]) -> list[dict]:
    """Καθαρίζει/επικυρώνει λίστα ερωτήσεων από οποιαδήποτε πηγή (JSON/CSV/form)."""
    out: list[dict] = []
    for i, q in enumerate(raw[:MAX_QUESTIONS], start=1):
        try:
            opts = [str(o).strip()[:200] for o in q.get("options", [])]
            if len(opts) != 4 or not all(opts):
                raise ValueError("χρειάζονται ακριβώς 4 μη κενές απαντήσεις")
            item = QuestionIn(
                text=str(q.get("text", "")).strip(),
                options=opts,
                correct=int(q.get("correct", -1)),
                time=int(q.get("time", 20)),
            )
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, f"Ερώτηση {i}: {exc}") from exc
        out.append(item.model_dump())
    if not out:
        raise HTTPException(422, "Δεν βρέθηκαν έγκυρες ερωτήσεις.")
    return out


def parse_import(text: str, filename: str) -> dict[str, Any]:
    """Εισαγωγή κουίζ από JSON ή CSV.

    JSON: {"title": "...", "questions": [{"text","options"[4],"correct"(0-3),"time"}]}
          ή απλή λίστα ερωτήσεων.
    CSV:  κεφαλίδα text,option1,option2,option3,option4,correct,time
          (το correct είναι 1-4 για ευκολία στο Excel· το time προαιρετικό).
    """
    text = text.strip().lstrip("\ufeff")
    if not text:
        raise HTTPException(422, "Το αρχείο είναι κενό.")
    is_csv = filename.lower().endswith(".csv") or (
        not text.startswith(("{", "[")) and "," in text.splitlines()[0]
    )
    if is_csv:
        delimiter = ";" if ";" in text.splitlines()[0] else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        fields = {(f or "").strip().lower() for f in (reader.fieldnames or [])}
        if not {"text", "option1", "option4", "correct"} <= fields:
            raise HTTPException(
                422, "Το CSV χρειάζεται κεφαλίδα: text,option1,option2,option3,option4,correct[,time]"
            )
        questions = []
        for row in reader:
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not row.get("text"):
                continue
            try:
                correct = int(row["correct"])
                correct = correct - 1 if 1 <= correct <= 4 else correct  # 1-4 → 0-3
                questions.append({
                    "text": row["text"],
                    "options": [row.get(f"option{i}", "") for i in range(1, 5)],
                    "correct": correct,
                    "time": int(row.get("time") or 20),
                })
            except (ValueError, KeyError) as exc:
                raise HTTPException(422, f"Σφάλμα στη γραμμή «{row['text'][:40]}»: {exc}") from exc
        return {"title": Path(filename).stem or "Εισαγωγή CSV", "questions": clean_questions(questions)}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"Μη έγκυρο JSON: {exc.msg}") from exc
    if isinstance(data, list):
        data = {"title": Path(filename).stem or "Εισαγωγή JSON", "questions": data}
    if not isinstance(data, dict) or "questions" not in data:
        raise HTTPException(422, 'Το JSON πρέπει να έχει τη μορφή {"title": ..., "questions": [...]}')
    return {
        "title": str(data.get("title") or "Εισαγωγή JSON")[:200],
        "questions": clean_questions(data["questions"]),
    }


# ---------------------------------------------------------------------------
# Βοηθητικές συναρτήσεις βάσης / βαθμολογίας
# ---------------------------------------------------------------------------
def get_quiz(conn: sqlite3.Connection, quiz_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Το κουίζ δεν βρέθηκε.")
    return row


def get_session(conn: sqlite3.Connection, pin: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM sessions WHERE pin=?", (pin,)).fetchone()
    if row is None:
        raise HTTPException(404, "Το δωμάτιο δεν βρέθηκε — έλεγξε το PIN.")
    return row


def session_questions(conn: sqlite3.Connection, sess: sqlite3.Row) -> list[dict]:
    return json.loads(get_quiz(conn, sess["quiz_id"])["questions"])


def leaderboard(conn: sqlite3.Connection, pin: str, limit: int | None = None) -> list[dict]:
    sql = ("SELECT id, name, score FROM players WHERE pin=? "
           "ORDER BY score DESC, joined_at ASC")
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql, (pin,)).fetchall()
    return [{"rank": i, "id": r["id"], "name": r["name"], "score": r["score"]}
            for i, r in enumerate(rows, start=1)]


def player_rank(conn: sqlite3.Connection, pin: str, player_id: int) -> int:
    for entry in leaderboard(conn, pin):
        if entry["id"] == player_id:
            return entry["rank"]
    return 0


def kahoot_points(elapsed: float, limit: int) -> int:
    """500–1000 πόντοι για σωστή απάντηση, γραμμικά με την ταχύτητα."""
    frac = max(0.0, min(1.0, elapsed / max(1, limit)))
    return int(round(1000 * (1 - frac / 2)))


def answer_counts(conn: sqlite3.Connection, pin: str, q_index: int) -> list[int]:
    counts = [0, 0, 0, 0]
    for row in conn.execute(
        "SELECT choice, COUNT(*) AS n FROM answers WHERE pin=? AND q_index=? GROUP BY choice",
        (pin, q_index),
    ):
        counts[row["choice"]] = row["n"]
    return counts


# ---------------------------------------------------------------------------
# Ζωντανή κατάσταση & WebSockets (ένα event loop, ένας worker — βλ. systemd)
# ---------------------------------------------------------------------------
class Room:
    """Ενεργές συνδέσεις ενός δωματίου + εργασία αυτόματης λήξης ερώτησης."""

    def __init__(self) -> None:
        self.sockets: set[WebSocket] = set()
        self.timer: asyncio.Task | None = None


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


async def broadcast(pin: str, payload: dict) -> None:
    for ws in list(room(pin).sockets):
        await send_json(ws, payload)


def lobby_payload(conn: sqlite3.Connection, sess: sqlite3.Row) -> dict:
    quiz = get_quiz(conn, sess["quiz_id"])
    players = conn.execute(
        "SELECT name FROM players WHERE pin=? ORDER BY joined_at ASC", (sess["pin"],)
    ).fetchall()
    return {
        "type": "lobby",
        "pin": sess["pin"],
        "title": quiz["title"],
        "total_questions": len(json.loads(quiz["questions"])),
        "players": [p["name"] for p in players],
    }


def question_payload(sess: sqlite3.Row, questions: list[dict], *, with_correct: bool) -> dict:
    q = questions[sess["q_index"]]
    payload = {
        "type": "question",
        "q_index": sess["q_index"],
        "total": len(questions),
        "text": q["text"],
        "options": q["options"],
        "time": q["time"],
        "deadline": sess["deadline"],
        "server_now": time.time(),   # αντιστάθμιση ρολογιού πελάτη
    }
    if with_correct:                 # ΜΟΝΟ προς τον καθηγητή/προτζέκτορα
        payload["correct"] = q["correct"]
    return payload


def reveal_payload(conn: sqlite3.Connection, sess: sqlite3.Row, questions: list[dict]) -> dict:
    q = questions[sess["q_index"]]
    total_players = conn.execute(
        "SELECT COUNT(*) AS n FROM players WHERE pin=?", (sess["pin"],)
    ).fetchone()["n"]
    answered = sum(answer_counts(conn, sess["pin"], sess["q_index"]))
    return {
        "type": "reveal",
        "q_index": sess["q_index"],
        "total": len(questions),
        "text": q["text"],
        "options": q["options"],
        "correct": q["correct"],
        "counts": answer_counts(conn, sess["pin"], sess["q_index"]),
        "answered": answered,
        "players": total_players,
        "top5": leaderboard(conn, sess["pin"], limit=5),
    }


def leaderboard_payload(conn: sqlite3.Connection, sess: sqlite3.Row, questions: list[dict]) -> dict:
    return {
        "type": "leaderboard",
        "q_index": sess["q_index"],
        "total": len(questions),
        "top5": leaderboard(conn, sess["pin"], limit=5),
        "is_last": sess["q_index"] >= len(questions) - 1,
    }


def finished_payload(conn: sqlite3.Connection, sess: sqlite3.Row) -> dict:
    return {
        "type": "finished",
        "pin": sess["pin"],
        "top5": leaderboard(conn, sess["pin"], limit=5),
        "final": leaderboard(conn, sess["pin"]),
    }


async def reveal_question(pin: str) -> None:
    """Λήξη αντίστροφης μέτρησης → αποτελέσματα + αυτόματο Top-5 leaderboard."""
    with db() as conn:
        sess = get_session(conn, pin)
        if sess["state"] != "question":
            return
        questions = session_questions(conn, sess)
        conn.execute("UPDATE sessions SET state='reveal' WHERE pin=?", (pin,))
        sess = get_session(conn, pin)
        await broadcast(pin, reveal_payload(conn, sess, questions))
        await push_personal(conn, pin, -1)
    await asyncio.sleep(REVEAL_SECONDS)
    with db() as conn:
        sess = get_session(conn, pin)
        if sess["state"] != "reveal":   # ο καθηγητής προχώρησε ήδη χειροκίνητα
            return
        questions = session_questions(conn, sess)
        conn.execute("UPDATE sessions SET state='leaderboard' WHERE pin=?", (pin,))
        sess = get_session(conn, pin)
        await broadcast(pin, leaderboard_payload(conn, sess, questions))


def schedule_reveal(pin: str, delay: float) -> None:
    r = room(pin)
    if r.timer and not r.timer.done():
        r.timer.cancel()
    r.timer = asyncio.create_task(_delayed_reveal(pin, delay))


async def _delayed_reveal(pin: str, delay: float) -> None:
    try:
        await asyncio.sleep(max(0.0, delay))
        await reveal_question(pin)
    except asyncio.CancelledError:
        pass


async def push_personal(conn: sqlite3.Connection, pin: str, player_id: int) -> None:
    """Στέλνει σε κάθε μαθητή τη δική του ορθότητα/πόντους/κατάταξη."""
    sess = get_session(conn, pin)
    rows = conn.execute(
        "SELECT p.id, p.score, a.choice, a.correct, a.points FROM players p "
        "LEFT JOIN answers a ON a.player_id=p.id AND a.q_index=? WHERE p.pin=?",
        (sess["q_index"], pin),
    ).fetchall()
    board = leaderboard(conn, pin)
    ranks = {e["id"]: e["rank"] for e in board}
    for ws in list(room(pin).sockets):
        pid = getattr(ws.state, "player_id", None)
        if pid is None:
            continue
        row = next((r for r in rows if r["id"] == pid), None)
        if row is None:
            continue
        await send_json(ws, {
            "type": "result",
            "q_index": sess["q_index"],
            "answered": row["choice"] is not None,
            "choice": row["choice"],
            "correct": bool(row["correct"]) if row["choice"] is not None else False,
            "points": row["points"] or 0,
            "score": row["score"],
            "rank": ranks.get(pid, 0),
            "players": len(board),
        })


async def snapshot_for(ws: WebSocket, conn: sqlite3.Connection, sess: sqlite3.Row) -> None:
    """Πλήρης τρέχουσα κατάσταση προς μία νέα/επανασυνδεόμενη σύνδεση."""
    pin = sess["pin"]
    questions = session_questions(conn, sess)
    is_teacher = getattr(ws.state, "is_teacher", False)
    state = sess["state"]
    if state == "lobby":
        await send_json(ws, lobby_payload(conn, sess))
    elif state == "question":
        await send_json(ws, question_payload(sess, questions, with_correct=is_teacher))
        await send_json(ws, {"type": "progress",
                             "answered": sum(answer_counts(conn, pin, sess["q_index"])),
                             "players": len(leaderboard(conn, pin))})
    elif state == "reveal":
        await send_json(ws, reveal_payload(conn, sess, questions))
        await push_personal(conn, pin, getattr(ws.state, "player_id", -1))
    elif state == "leaderboard":
        await send_json(ws, leaderboard_payload(conn, sess, questions))
        await push_personal(conn, pin, getattr(ws.state, "player_id", -1))
    elif state == "finished":
        await send_json(ws, finished_payload(conn, sess))
        await push_personal(conn, pin, getattr(ws.state, "player_id", -1))


# ---------------------------------------------------------------------------
# Σελίδες (HTML)
# ---------------------------------------------------------------------------
def page_base(request: Request) -> str:
    """Base URL για τα σχετικά fetch/WebSocket URLs (/live-quiz/ ή /live-quiz/teacher/).

    ΣΗΜΕΙΩΣΗ: Με --root-path /live-quiz και proxy_pass που αφαιρεί το prefix,
    το request.url.path περιέχει ήδη το πλήρες εξωτερικό μονοπάτι, οπότε ΔΕΝ
    προσθέτουμε ξανά το root_path (θα διπλασιαζόταν).
    """
    path = request.url.path.rstrip("/")
    return f"{path}/" if path else "/"


@app.get("/", response_class=HTMLResponse)
def student_page(request: Request):
    return templates.TemplateResponse(request, "student.html", {"base": page_base(request)})


@app.get("/teacher", response_class=HTMLResponse)
def teacher_page(request: Request):
    return templates.TemplateResponse(
        request,
        "teacher.html",
        {
            "logged_in": token_valid(request.cookies.get(COOKIE_NAME)),
            "base": page_base(request),
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "school-livequiz"}


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


@app.get("/api/teacher/quizzes")
def list_quizzes(request: Request):
    require_teacher(request)
    with db() as conn:
        rows = conn.execute("SELECT * FROM quizzes ORDER BY id DESC").fetchall()
        active = conn.execute(
            "SELECT pin, quiz_id, state FROM sessions WHERE finished_at IS NULL"
        ).fetchall()
    active_by_quiz = {a["quiz_id"]: {"pin": a["pin"], "state": a["state"]} for a in active}
    return {"quizzes": [
        {"id": r["id"], "title": r["title"],
         "questions": json.loads(r["questions"]),
         "created_at": r["created_at"],
         "live": active_by_quiz.get(r["id"])}
        for r in rows
    ]}


@app.post("/api/teacher/quizzes")
def create_quiz(payload: QuizIn, request: Request):
    require_teacher(request)
    questions = clean_questions([q.model_dump() for q in payload.questions])
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO quizzes (title, questions, created_at) VALUES (?,?,?)",
            (payload.title.strip(), json.dumps(questions, ensure_ascii=False), time.time()),
        )
        quiz_id = cur.lastrowid
    return {"id": quiz_id}


@app.delete("/api/teacher/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, request: Request):
    require_teacher(request)
    with db() as conn:
        get_quiz(conn, quiz_id)
        live = conn.execute(
            "SELECT pin FROM sessions WHERE quiz_id=? AND finished_at IS NULL", (quiz_id,)
        ).fetchall()
        if live:
            raise HTTPException(409, "Το κουίζ έχει ενεργό παιχνίδι — τερμάτισέ το πρώτα.")
        conn.execute("DELETE FROM quizzes WHERE id=?", (quiz_id,))
    return {"ok": True}


@app.get("/api/teacher/samples")
def sample_quizzes(request: Request):
    """Έτοιμα ελληνικά παραδείγματα (επιστρέφονται για προεπισκόπηση/εισαγωγή)."""
    require_teacher(request)
    return {"samples": SAMPLE_QUIZZES}


@app.post("/api/teacher/samples/{index}")
def import_sample(index: int, request: Request):
    require_teacher(request)
    if not 0 <= index < len(SAMPLE_QUIZZES):
        raise HTTPException(404, "Το παράδειγμα δεν βρέθηκε.")
    sample = SAMPLE_QUIZZES[index]
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO quizzes (title, questions, created_at) VALUES (?,?,?)",
            (sample["title"], json.dumps(sample["questions"], ensure_ascii=False), time.time()),
        )
    return {"id": cur.lastrowid}


class ImportIn(BaseModel):
    filename: str = Field(default="import.json", max_length=200)
    content: str = Field(min_length=1, max_length=500_000)


@app.post("/api/teacher/import")
def import_quiz(payload: ImportIn, request: Request):
    """Εισαγωγή ερωτήσεων από JSON/CSV (το περιεχόμενο έρχεται ως κείμενο)."""
    require_teacher(request)
    data = parse_import(payload.content, payload.filename)
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO quizzes (title, questions, created_at) VALUES (?,?,?)",
            (data["title"], json.dumps(data["questions"], ensure_ascii=False), time.time()),
        )
    return {"id": cur.lastrowid, "title": data["title"], "count": len(data["questions"])}


# ---------------------------------------------------------------------------
# Έλεγχος ζωντανού παιχνιδιού (καθηγητής) — η κατάσταση μεταδίδεται με WS
# ---------------------------------------------------------------------------
class StartIn(BaseModel):
    quiz_id: int


@app.post("/api/teacher/start")
async def start_session(payload: StartIn, request: Request):
    """Δημιουργεί live session με μοναδικό 4-ψήφιο PIN."""
    require_teacher(request)
    with db() as conn:
        get_quiz(conn, payload.quiz_id)
        existing = conn.execute(
            "SELECT pin FROM sessions WHERE quiz_id=? AND finished_at IS NULL",
            (payload.quiz_id,),
        ).fetchone()
        if existing:
            return {"pin": existing["pin"], "resumed": True}
        for _ in range(100):
            pin = f"{secrets.randbelow(9000) + 1000}"   # 1000–9999
            clash = conn.execute("SELECT 1 FROM sessions WHERE pin=?", (pin,)).fetchone()
            if clash is None:
                break
        else:
            raise HTTPException(503, "Δεν βρέθηκε διαθέσιμο PIN — δοκίμασε ξανά.")
        conn.execute(
            "INSERT INTO sessions (pin, quiz_id, created_at) VALUES (?,?,?)",
            (pin, payload.quiz_id, time.time()),
        )
    return {"pin": pin, "resumed": False}


@app.post("/api/teacher/{pin}/next")
async def next_step(pin: str, request: Request):
    """Ροή: lobby → ερώτηση 1 → reveal → leaderboard → ερώτηση 2 → … → finished.

    Ο καθηγητής πατάει «Επόμενη Ερώτηση»· η λήξη του χρόνου εμφανίζει αυτόματα
    τα αποτελέσματα και μετά το Top-5 (βλ. reveal_question).
    """
    require_teacher(request)
    with db() as conn:
        sess = get_session(conn, pin)
        questions = session_questions(conn, sess)
        state = sess["state"]
        r = room(pin)
        if state == "finished":
            raise HTTPException(409, "Το παιχνίδι έχει ολοκληρωθεί.")
        if state == "question":
            # Πρόωρη εμφάνιση αποτελεσμάτων (πριν λήξει ο χρόνος)
            if r.timer and not r.timer.done():
                r.timer.cancel()
            await reveal_question(pin)   # στέλνει και τα προσωπικά αποτελέσματα
            return {"ok": True, "state": "reveal"}
        if state == "reveal":
            if r.timer and not r.timer.done():
                r.timer.cancel()
            conn.execute("UPDATE sessions SET state='leaderboard' WHERE pin=?", (pin,))
            sess = get_session(conn, pin)
            await broadcast(pin, leaderboard_payload(conn, sess, questions))
            return {"ok": True, "state": "leaderboard"}
        # lobby ή leaderboard → επόμενη ερώτηση (ή τέλος)
        next_index = sess["q_index"] + 1
        if next_index >= len(questions):
            conn.execute(
                "UPDATE sessions SET state='finished', finished_at=? WHERE pin=?",
                (time.time(), pin),
            )
            sess = get_session(conn, pin)
            await broadcast(pin, finished_payload(conn, sess))
            await push_personal(conn, pin, -1)
            return {"ok": True, "state": "finished"}
        limit = questions[next_index]["time"]
        deadline = time.time() + limit
        conn.execute(
            "UPDATE sessions SET state='question', q_index=?, deadline=? WHERE pin=?",
            (next_index, deadline, pin),
        )
        sess = get_session(conn, pin)
        for ws in list(r.sockets):
            is_teacher = getattr(ws.state, "is_teacher", False)
            await send_json(ws, question_payload(sess, questions, with_correct=is_teacher))
        await broadcast(pin, {"type": "progress", "answered": 0,
                              "players": len(leaderboard(conn, pin))})
        schedule_reveal(pin, limit)
    return {"ok": True, "state": "question", "q_index": next_index}


@app.post("/api/teacher/{pin}/end")
async def end_session(pin: str, request: Request):
    """Πρόωρος τερματισμός παιχνιδιού από τον καθηγητή."""
    require_teacher(request)
    with db() as conn:
        sess = get_session(conn, pin)
        if sess["state"] == "finished":
            return {"ok": True}
        r = room(pin)
        if r.timer and not r.timer.done():
            r.timer.cancel()
        conn.execute(
            "UPDATE sessions SET state='finished', finished_at=? WHERE pin=?",
            (time.time(), pin),
        )
        sess = get_session(conn, pin)
        await broadcast(pin, finished_payload(conn, sess))
        await push_personal(conn, pin, -1)
    return {"ok": True}


@app.get("/api/teacher/{pin}/results")
def session_results(pin: str, request: Request):
    """Πλήρης κατάταξη + αναλυτικά αποτελέσματα (για εξαγωγή CSV στον browser)."""
    require_teacher(request)
    with db() as conn:
        sess = get_session(conn, pin)
        quiz = get_quiz(conn, sess["quiz_id"])
        board = leaderboard(conn, pin)
        answers = conn.execute(
            "SELECT player_id, q_index, choice, correct, points, elapsed "
            "FROM answers WHERE pin=?", (pin,)
        ).fetchall()
    per_player: dict[int, list] = {e["id"]: [] for e in board}
    for a in answers:
        per_player[a["player_id"]].append(dict(a))
    return {"title": quiz["title"], "pin": pin, "state": sess["state"],
            "board": board, "answers": per_player}


# ---------------------------------------------------------------------------
# API Μαθητή — είσοδος με PIN + όνομα (χωρίς κωδικό)
# ---------------------------------------------------------------------------
class JoinIn(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")
    name: str = Field(min_length=1, max_length=40)
    token: str | None = Field(default=None, max_length=64)  # επανασύνδεση


@app.post("/api/join")
def join_session(payload: JoinIn):
    name = " ".join(payload.name.split())[:40]
    if not name:
        raise HTTPException(422, "Γράψε το όνομά σου.")
    with db() as conn:
        sess = get_session(conn, payload.pin)
        if sess["state"] == "finished":
            raise HTTPException(409, "Το παιχνίδι σε αυτό το PIN έχει ολοκληρωθεί.")
        # Επανασύνδεση με υπάρχον token (π.χ. refresh/αλλαγή συσκευής δικτύου)
        if payload.token:
            row = conn.execute(
                "SELECT * FROM players WHERE token=? AND pin=?", (payload.token, payload.pin)
            ).fetchone()
            if row:
                return {"token": row["token"], "name": row["name"],
                        "player_id": row["id"], "resumed": True}
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE pin=?", (payload.pin,)
        ).fetchone()["n"]
        if count >= MAX_PLAYERS:
            raise HTTPException(409, "Το δωμάτιο είναι γεμάτο.")
        # Μοναδικό εμφανιζόμενο όνομα (π.χ. «Γιώργος», «Γιώργος 2»)
        taken = {r["name"] for r in conn.execute(
            "SELECT name FROM players WHERE pin=?", (payload.pin,))}
        unique, suffix = name, 2
        while unique in taken:
            unique = f"{name} {suffix}"
            suffix += 1
        token = secrets.token_urlsafe(24)
        cur = conn.execute(
            "INSERT INTO players (pin, token, name, joined_at) VALUES (?,?,?,?)",
            (payload.pin, token, unique, time.time()),
        )
        player_id = cur.lastrowid
    return {"token": token, "name": unique, "player_id": player_id, "resumed": False}


# ---------------------------------------------------------------------------
# WebSocket — /ws/{pin}?token=… (μαθητής) ή ?teacher=… (καθηγητής/προτζέκτορας)
# ---------------------------------------------------------------------------
async def handle_answer(ws: WebSocket, pin: str, choice: int) -> None:
    player_id = getattr(ws.state, "player_id", None)
    if player_id is None or choice not in (0, 1, 2, 3):
        return
    with db() as conn:
        sess = get_session(conn, pin)
        if sess["state"] != "question":
            await send_json(ws, {"type": "error", "message": "Η ερώτηση δεν δέχεται πλέον απαντήσεις."})
            return
        questions = session_questions(conn, sess)
        q = questions[sess["q_index"]]
        now = time.time()
        elapsed = max(0.0, now - (sess["deadline"] - q["time"]))
        if now > sess["deadline"] + 0.5:   # μικρή ανοχή δικτύου
            await send_json(ws, {"type": "error", "message": "Ο χρόνος έληξε!"})
            return
        correct = int(choice == q["correct"])
        points = kahoot_points(elapsed, q["time"]) if correct else 0
        try:
            conn.execute(
                "INSERT INTO answers (pin, player_id, q_index, choice, correct, points,"
                " elapsed, answered_at) VALUES (?,?,?,?,?,?,?,?)",
                (pin, player_id, sess["q_index"], choice, correct, points, elapsed, now),
            )
        except sqlite3.IntegrityError:
            await send_json(ws, {"type": "error", "message": "Έχεις ήδη απαντήσει σε αυτή την ερώτηση."})
            return
        if points:
            conn.execute("UPDATE players SET score=score+? WHERE id=?", (points, player_id))
        rank = player_rank(conn, pin, player_id)
        total_players = conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE pin=?", (pin,)
        ).fetchone()["n"]
        answered = sum(answer_counts(conn, pin, sess["q_index"]))
        # Άμεση προσωπική ανατροφοδότηση: ορθότητα + πόντοι + θέση
        await send_json(ws, {
            "type": "answer_ack", "q_index": sess["q_index"], "choice": choice,
            "correct": bool(correct), "points": points, "rank": rank,
            "players": total_players,
            "score": conn.execute("SELECT score FROM players WHERE id=?",
                                  (player_id,)).fetchone()["score"],
        })
        await broadcast(pin, {"type": "progress", "answered": answered, "players": total_players})
        # Όλοι απάντησαν → αυτόματη λήξη χωρίς αναμονή του χρονόμετρου
        if answered >= total_players and total_players > 0:
            schedule_reveal(pin, 0.5)


@app.websocket("/ws/{pin}")
async def game_socket(ws: WebSocket, pin: str):
    teacher_cookie = ws.cookies.get(COOKIE_NAME)
    is_teacher = token_valid(teacher_cookie)
    player_token = ws.query_params.get("token", "")
    with db() as conn:
        row = conn.execute("SELECT 1 FROM sessions WHERE pin=?", (pin,)).fetchone()
        if row is None:
            await ws.close(code=4404)
            return
        player = None
        if not is_teacher:
            if not player_token:
                await ws.close(code=4401)
                return
            player = conn.execute(
                "SELECT * FROM players WHERE token=? AND pin=?", (player_token, pin)
            ).fetchone()
            if player is None:
                await ws.close(code=4401)
                return
    await ws.accept()
    ws.state.is_teacher = is_teacher
    ws.state.player_id = player["id"] if player else None
    r = room(pin)
    r.sockets.add(ws)
    try:
        with db() as conn:
            sess = get_session(conn, pin)
            await snapshot_for(ws, conn, sess)
            if not is_teacher and sess["state"] == "lobby":
                await broadcast(pin, lobby_payload(conn, sess))   # live ονόματα στον προτζέκτορα
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "answer" and not is_teacher:
                try:
                    await handle_answer(ws, pin, int(msg.get("choice", -1)))
                except (TypeError, ValueError):
                    pass
            elif msg.get("type") == "ping":
                await send_json(ws, {"type": "pong"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        pass  # μη έγκυρο JSON κ.λπ. — η σύνδεση κλείνει καθαρά
    finally:
        r.sockets.discard(ws)


# ---------------------------------------------------------------------------
# Εκκίνηση / περιοδικός καθαρισμός
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup() -> None:
    init_db()
    asyncio.create_task(_cleanup_loop())


async def _cleanup_loop() -> None:
    """Κλείνει/σβήνει πολύ παλιά sessions ώστε το PIN pool να μένει διαθέσιμο."""
    while True:
        try:
            cutoff = time.time() - SESSION_TTL
            with db() as conn:
                old = conn.execute(
                    "SELECT pin FROM sessions WHERE created_at<?", (cutoff,)
                ).fetchall()
                for row in old:
                    r = ROOMS.get(row["pin"])
                    if r and r.timer and not r.timer.done():
                        r.timer.cancel()
                    conn.execute("DELETE FROM sessions WHERE pin=?", (row["pin"],))
                    ROOMS.pop(row["pin"], None)
        except Exception:
            pass
        await asyncio.sleep(600)
