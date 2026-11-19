"""
Classroom Hub — SQLite schema & queries (Task 3: διάσπαση σε APIRouters).

Chat, forum, polls, quiz & αποτελέσματα (μόνο μαθητών), μόνιμες ανακοινώσεις
και σιωπές (mutes). Οι συνδέσεις περνούν από το common.db (WAL/Row/FK,
timeout 15s)· η βάση μένει στο data/classroom.db όπως πάντα.
"""
from __future__ import annotations

import json
import time

from fastapi import HTTPException

from common.db import session, add_columns

import state


def db():
    """Context manager σύνδεσης: commit/rollback ΚΑΙ close (common.db.session)."""
    return session(state.DB_PATH, create_parent=True)


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
        CREATE TABLE IF NOT EXISTS announcements (
            id TEXT PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,
            text TEXT NOT NULL, audience TEXT NOT NULL DEFAULT 'all',
            tmima TEXT NOT NULL DEFAULT '', target_uid TEXT NOT NULL DEFAULT '',
            target_name TEXT NOT NULL DEFAULT '', links TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS chat_mutes (
            uid TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
            until_ts REAL NOT NULL, by_name TEXT NOT NULL DEFAULT ''
        );
        """)
        # --- Ήπιες migrations για υπάρχουσες βάσεις (νέες στήλες lifecycle) ---
        add_columns(conn, (
            ("polls", "auto_close", "INTEGER NOT NULL DEFAULT 0"),
            ("polls", "ends_at", "REAL NOT NULL DEFAULT 0"),
            ("quizzes", "auto_close", "INTEGER NOT NULL DEFAULT 0"),
            ("quizzes", "ends_at", "REAL NOT NULL DEFAULT 0"),
        ))


def recent_announcements(limit: int = 20) -> list[dict]:
    """Τελευταίες ανακοινώσεις από τη SQLite (επιβιώνουν restart)."""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in reversed(rows):
        d = dict(r)
        try:
            d["links"] = json.loads(d.get("links") or "[]")
        except ValueError:
            d["links"] = []
        out.append(d)
    return out


def visible_announcements(ident: dict | None, teacher: bool, limit: int = 20) -> list[dict]:
    """Ανακοινώσεις ΟΡΑΤΕΣ στον συγκεκριμένο χρήστη (όχι προσωπικά ξένων).

    Τα προσωπικά βραβεία/συγχαρητήρια (target_uid) και οι στοχευμένες
    ανακοινώσεις (audience/tmima) δεν πρέπει να διαρρέουν σε άλλους μέσω
    του /api/config/public ή του WS welcome μετά από reconnect.
    """
    out = []
    for a in recent_announcements(limit):
        if teacher:
            out.append(a)                       # ο καθηγητής βλέπει τα πάντα
            continue
        target = a.get("target_uid", "")
        if target and (not ident or ident["uid"] != target):
            continue                            # προσωπικό μήνυμα ΑΛΛΟΥ χρήστη
        role = ident["role"] if ident else "guest"
        tmima = ident.get("tmima", "") if ident else ""
        aud = a.get("audience", "all")
        ok = (aud == "all"
              or (aud == "students" and role in ("student", "guest"))
              or (aud == "guests" and role == "guest")
              or (aud == "teachers" and False)
              or (aud.startswith("role:") and aud[5:] == role))
        if ok and a.get("tmima") and a["tmima"] != tmima:
            ok = False                          # φίλτρο τμήματος
        if ok:
            out.append(a)
    return out


def store_announcement(msg: dict) -> None:
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO announcements "
            "(id, ts, kind, text, audience, tmima, target_uid, target_name, links) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (msg["id"], msg["ts"], msg["kind"], msg["text"], msg.get("audience", "all"),
             msg.get("tmima", ""), msg.get("target_uid", ""), msg.get("target_name", ""),
             json.dumps(msg.get("links", []), ensure_ascii=False)))


def active_mute(uid: str) -> dict | None:
    """Ενεργή σιωπή (mute) για τον uid — ληγμένες καθαρίζονται τεμπέλικα."""
    with db() as conn:
        row = conn.execute("SELECT * FROM chat_mutes WHERE uid=?", (uid,)).fetchone()
        if not row:
            return None
        if row["until_ts"] <= time.time():
            conn.execute("DELETE FROM chat_mutes WHERE uid=?", (uid,))
            return None
        return dict(row)


def bulk_ids(table: str, body: dict) -> list[str]:
    """Κοινή λογική επιλογής ids για bulk (ρητή λίστα / όλα / παλαιότερα των N ημερών)."""
    if table not in ("polls", "quizzes", "announcements"):
        raise HTTPException(400, "Άγνωστος πίνακας.")
    with db() as conn:
        if body.get("ids"):
            return [str(i) for i in body["ids"]][:500]
        days = float(body.get("older_than_days", 0) or 0)
        if days > 0:
            cutoff = time.time() - days * 86400
            rows = conn.execute(f"SELECT id FROM {table} WHERE ts < ?", (cutoff,)).fetchall()
        elif body.get("all"):
            rows = conn.execute(f"SELECT id FROM {table}").fetchall()
        else:
            raise HTTPException(400, "Δώσε ids, all=true ή older_than_days.")
        return [r["id"] for r in rows]