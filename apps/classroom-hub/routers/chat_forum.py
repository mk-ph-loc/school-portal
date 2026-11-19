"""
Chat τάξης & Forum νημάτων — REST (ιστορικό, διαγραφή, bulk, mutes, νήματα)
και WS handlers (ws_chat/ws_forum_post) που καλούνται από το presence.
Η σιωπή (mute) ισχύει ΠΑΝΤΟΥ: WS chat, WS forum και REST δημιουργία νήματος.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

import state
from store import db, active_mute
from presence import broadcast, send_json, send_to_uid, roster_payload

router = APIRouter()


# ---------------------------------------------------------------------------
# REST — chat ιστορικό & διαγραφή μηνυμάτων (καθηγητής)
# ---------------------------------------------------------------------------
@router.get("/api/chat/history")
def api_chat_history(request: Request, limit: int = 100, before_id: int = 0):
    if not state.identity_from(request):
        raise HTTPException(401, "Συνδέσου πρώτα.")
    limit = max(1, min(int(limit), 500))
    with db() as conn:
        if before_id > 0:
            rows = conn.execute("SELECT * FROM chat WHERE id < ? ORDER BY id DESC LIMIT ?",
                                (before_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"messages": [dict(r) for r in reversed(rows)]}


@router.delete("/api/chat/messages/{mid}")
async def api_chat_delete(mid: int, request: Request):
    """🗑 Διαγραφή ανάρμοστου μηνύματος — αφαιρείται ζωντανά από όλους."""
    state.require_teacher(request)
    with db() as conn:
        cur = conn.execute("DELETE FROM chat WHERE id=?", (mid,))
        if not cur.rowcount:
            raise HTTPException(404, "Το μήνυμα δεν βρέθηκε.")
    await broadcast({"type": "chat_deleted", "ids": [mid]})
    return {"ok": True}


@router.post("/api/chat/bulk")
async def api_chat_bulk(request: Request):
    """Μαζικός καθαρισμός chat: {ids: [...]} ή {clear_all: true} ή {older_than_days: N}."""
    state.require_teacher(request)
    body = await request.json()
    with db() as conn:
        if body.get("ids"):
            ids = [int(i) for i in body["ids"]][:1000]
            qmarks = ",".join("?" * len(ids)) or "NULL"
            rows = conn.execute(f"SELECT id FROM chat WHERE id IN ({qmarks})", ids).fetchall()
            conn.execute(f"DELETE FROM chat WHERE id IN ({qmarks})", ids)
        elif body.get("clear_all"):
            rows = conn.execute("SELECT id FROM chat").fetchall()
            conn.execute("DELETE FROM chat")
        elif float(body.get("older_than_days", 0) or 0) > 0:
            cutoff = time.time() - float(body["older_than_days"]) * 86400
            rows = conn.execute("SELECT id FROM chat WHERE ts < ?", (cutoff,)).fetchall()
            conn.execute("DELETE FROM chat WHERE ts < ?", (cutoff,))
        else:
            raise HTTPException(400, "Δώσε ids, clear_all=true ή older_than_days.")
        deleted = [r["id"] for r in rows]
    if deleted:
        await broadcast({"type": "chat_deleted", "ids": deleted})
    return {"ok": True, "affected": len(deleted)}


# ---------------------------------------------------------------------------
# 🔇 Chat moderation — σιωπή (mute) ανά χρήστη, μόνο καθηγητής
# ---------------------------------------------------------------------------
@router.get("/api/mutes")
def api_mutes(request: Request):
    state.require_teacher(request)
    now = time.time()
    with db() as conn:
        conn.execute("DELETE FROM chat_mutes WHERE until_ts <= ?", (now,))
        rows = conn.execute("SELECT * FROM chat_mutes ORDER BY until_ts").fetchall()
    return {"mutes": [dict(r) for r in rows]}


@router.post("/api/mutes")
async def api_mute_set(request: Request):
    """🔇 Σιωπή: {uid, minutes} (0 ή αρνητικό = άρση). Ισχύει για chat & forum."""
    state.require_teacher(request)
    ident = state.identity_from(request)
    body = await request.json()
    uid = str(body.get("uid", "")).strip()
    if not uid:
        raise HTTPException(400, "Χρειάζεται uid χρήστη.")
    minutes = float(body.get("minutes", 15))
    target = next((c for c in state.CLIENTS.values() if c.uid == uid), None)
    if target and target.role == "teacher":
        raise HTTPException(400, "Δεν επιβάλλεται σιωπή σε καθηγητή.")
    name = str(body.get("name", "") or (target.name if target else ""))[:40]
    by_name = ident["name"] if ident else "Καθηγητής"
    if minutes <= 0:
        with db() as conn:
            conn.execute("DELETE FROM chat_mutes WHERE uid=?", (uid,))
        await send_to_uid(uid, {"type": "unmuted"})
        await broadcast({"type": "mute_changed", "uid": uid, "until_ts": 0}, audience="teachers")
        return {"ok": True, "muted": False}
    until = time.time() + min(minutes, 24 * 60) * 60
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO chat_mutes (uid, name, until_ts, by_name) VALUES (?,?,?,?)",
                     (uid, name, until, by_name))
    await send_to_uid(uid, {"type": "muted", "until_ts": until, "by": by_name})
    await broadcast({"type": "mute_changed", "uid": uid, "name": name, "until_ts": until},
                    audience="teachers")
    return {"ok": True, "muted": True, "until_ts": until}


# ---------------------------------------------------------------------------
# REST — forum νήματα & roster (καθηγητής)
# ---------------------------------------------------------------------------
@router.get("/api/forum/threads")
def api_forum_threads(request: Request):
    ident = state.identity_from(request)
    if not ident:
        raise HTTPException(401, "Συνδέσου πρώτα.")
    if ident["role"] == "guest" and not state.CONFIG["access"].get("guest_forum"):
        raise HTTPException(403, "Το forum δεν είναι διαθέσιμο στους επισκέπτες.")
    with db() as conn:
        rows = conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM forum_posts p WHERE p.thread_id=t.id) AS posts "
            "FROM forum_threads t ORDER BY t.id DESC LIMIT 50").fetchall()
    return {"threads": [dict(r) for r in rows]}


@router.post("/api/forum/threads")
async def api_forum_new_thread(request: Request):
    ident = state.identity_from(request)
    if not ident:
        raise HTTPException(401, "Συνδέσου πρώτα.")
    if ident["role"] == "guest" and not state.CONFIG["access"].get("guest_forum"):
        raise HTTPException(403, "Το forum δεν είναι διαθέσιμο στους επισκέπτες.")
    mute = active_mute(ident["uid"])            # 🔇 η σιωπή ισχύει και στο REST forum
    if mute and ident["role"] != "teacher":
        raise HTTPException(403, "Έχεις προσωρινή σιωπή (mute) από τον καθηγητή.")
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


@router.get("/api/forum/threads/{tid}")
def api_forum_thread(tid: int, request: Request):
    ident = state.identity_from(request)
    if not ident:
        raise HTTPException(401, "Συνδέσου πρώτα.")
    if ident["role"] == "guest" and not state.CONFIG["access"].get("guest_forum"):
        raise HTTPException(403, "Το forum δεν είναι διαθέσιμο στους επισκέπτες.")
    with db() as conn:
        th = conn.execute("SELECT * FROM forum_threads WHERE id=?", (tid,)).fetchone()
        if not th:
            raise HTTPException(404, "Το νήμα δεν βρέθηκε.")
        posts = conn.execute("SELECT * FROM forum_posts WHERE thread_id=? ORDER BY id", (tid,)).fetchall()
    return {"thread": dict(th), "posts": [dict(p) for p in posts]}


@router.post("/api/forum/threads/{tid}/lock")
async def api_forum_lock(tid: int, request: Request):
    state.require_teacher(request)
    body = await request.json()
    locked = 1 if body.get("locked", True) else 0
    with db() as conn:
        conn.execute("UPDATE forum_threads SET locked=? WHERE id=?", (locked, tid))
    await broadcast({"type": "forum_lock", "thread_id": tid, "locked": bool(locked)})
    return {"ok": True}


@router.delete("/api/forum/threads/{tid}")
async def api_forum_delete(tid: int, request: Request):
    state.require_teacher(request)
    with db() as conn:
        conn.execute("DELETE FROM forum_posts WHERE thread_id=?", (tid,))
        conn.execute("DELETE FROM forum_threads WHERE id=?", (tid,))
    await broadcast({"type": "forum_deleted", "thread_id": tid})
    return {"ok": True}


@router.get("/api/roster")
def api_roster(request: Request):
    state.require_teacher(request)
    return roster_payload()


# ---------------------------------------------------------------------------
# WS handlers — καλούνται από το presence.hub_socket (chat / forum_post)
# ---------------------------------------------------------------------------
async def ws_chat(c, msg: dict) -> None:
    if c.role == "guest" and not state.CONFIG["access"].get("guest_chat", True):
        return
    mute = active_mute(c.uid)                   # 🔇 σιωπή από τον καθηγητή
    if mute and c.role != "teacher":
        await send_json(c.ws, {"type": "muted", "until_ts": mute["until_ts"],
                               "by": mute["by_name"]})
        return
    text = str(msg.get("text", "")).strip()[:500]
    if not text:
        return
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO chat (ts, uid, name, role, tmima, text) VALUES (?,?,?,?,?,?)",
            (time.time(), c.uid, c.name, c.role, c.tmima, text))
        mid = cur.lastrowid
    await broadcast({"type": "chat", "id": mid, "ts": time.time(),
                     "uid": c.uid, "name": c.name, "role": c.role,
                     "tmima": c.tmima, "emoji": c.emoji, "color": c.color,
                     "text": text})


async def ws_forum_post(c, msg: dict) -> None:
    mute = active_mute(c.uid)                   # η σιωπή ισχύει και στο forum
    if mute and c.role != "teacher":
        await send_json(c.ws, {"type": "muted", "until_ts": mute["until_ts"],
                               "by": mute["by_name"]})
        return
    tid = int(msg.get("thread_id", 0))
    text = str(msg.get("text", "")).strip()[:2000]
    if not text:
        return
    with db() as conn:
        th = conn.execute("SELECT locked FROM forum_threads WHERE id=?", (tid,)).fetchone()
        if not th or (th["locked"] and c.role != "teacher"):
            return
        cur = conn.execute(
            "INSERT INTO forum_posts (thread_id, ts, uid, name, role, text) "
            "VALUES (?,?,?,?,?,?)", (tid, time.time(), c.uid, c.name, c.role, text))
        pid = cur.lastrowid
    await broadcast({"type": "forum_post", "thread_id": tid, "id": pid,
                     "ts": time.time(), "uid": c.uid, "name": c.name,
                     "role": c.role, "text": text})