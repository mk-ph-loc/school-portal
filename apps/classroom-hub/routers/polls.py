"""
Δημοσκοπήσεις (polls) — αποστολή, ζωντανές ψήφοι (WS), CRUD & bulk διαχείριση.
Το auto-close (όλοι ψήφισαν / χρονικό όριο) καλείται από εδώ και από το
presence.housekeeping — ποτέ αντίστροφα (χωρίς κυκλικά imports).
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time

from fastapi import APIRouter, HTTPException, Request

import state
from store import db, bulk_ids
from presence import broadcast, send_to_uid, audience_match, eligible_uids

router = APIRouter()


@router.post("/api/cmd/poll")
async def cmd_poll(request: Request):
    """📊 Δημοσκόπηση· show_results=1 → όλοι βλέπουν ζωντανά τα αποτελέσματα."""
    state.require_teacher(request)
    body = await request.json()
    question = str(body.get("question", "")).strip()[:300]
    options = [str(o).strip()[:120] for o in body.get("options", []) if str(o).strip()]
    if not question or len(options) < 2:
        raise HTTPException(400, "Χρειάζεται ερώτηση και τουλάχιστον 2 επιλογές.")
    aud, tmima = state.audience_of(body)
    pid = secrets.token_hex(6)
    show = 1 if body.get("show_results", True) else 0
    auto = 1 if body.get("auto_close", True) else 0
    dur = float(body.get("duration_sec", 0) or 0)
    ends = time.time() + dur if dur > 0 else 0.0
    with db() as conn:
        conn.execute("INSERT INTO polls (id, ts, question, options, show_results, audience,"
                     " closed, auto_close, ends_at) VALUES (?,?,?,?,?,?,0,?,?)",
                     (pid, time.time(), question, json.dumps(options, ensure_ascii=False),
                      show, f"{aud}|{tmima}", auto, ends))
    state.ACTIVE_POLLS[pid] = {"id": pid, "question": question, "options": options,
                               "show_results": bool(show), "audience": aud, "tmima": tmima,
                               "closed": False, "auto_close": bool(auto), "ends_at": ends}
    await broadcast({"type": "poll", "id": pid, "question": question, "options": options,
                     "show_results": bool(show), "ts": time.time()},
                    audience=aud, tmima=tmima)
    return {"ok": True, "id": pid}


async def close_poll_internal(pid: str) -> dict | None:
    """Κλείσιμο poll (χειροκίνητο ή αυτόματο) — όλοι βλέπουν το τελικό αποτέλεσμα."""
    state.ACTIVE_POLLS.pop(pid, None)
    with db() as conn:
        conn.execute("UPDATE polls SET closed=1 WHERE id=?", (pid,))
        try:
            res = poll_results(conn, pid)
        except HTTPException:
            return None
    await broadcast({**res, "closed": True})
    return res


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


@router.post("/api/cmd/poll/{pid}/close")
async def cmd_poll_close(pid: str, request: Request):
    state.require_teacher(request)
    res = await close_poll_internal(pid)                # στο κλείσιμο όλοι βλέπουν το τελικό αποτέλεσμα
    if res is None:
        raise HTTPException(404, "Η δημοσκόπηση δεν βρέθηκε.")
    return {"ok": True, "results": res}


@router.get("/api/polls")
def api_polls(request: Request):
    state.require_teacher(request)
    with db() as conn:
        rows = conn.execute("SELECT id FROM polls ORDER BY ts DESC LIMIT 100").fetchall()
        out = []
        for r in rows:
            res = poll_results(conn, r["id"])
            voters = conn.execute(
                "SELECT uid, choice FROM poll_votes WHERE poll_id=?", (r["id"],)).fetchall()
            res["voters"] = [dict(v) for v in voters]
            out.append(res)
        return {"polls": out}


@router.put("/api/polls/{pid}")
async def api_poll_update(pid: str, request: Request):
    """✏️ Επεξεργασία δημοσκόπησης (ερώτηση/επιλογές/ορατότητα αποτελεσμάτων)."""
    state.require_teacher(request)
    body = await request.json()
    with db() as conn:
        row = conn.execute("SELECT * FROM polls WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Η δημοσκόπηση δεν βρέθηκε.")
        question = str(body.get("question", row["question"])).strip()[:300] or row["question"]
        options = ([str(o).strip()[:120] for o in body["options"] if str(o).strip()]
                   if "options" in body else json.loads(row["options"]))
        if len(options) < 2:
            raise HTTPException(400, "Χρειάζονται τουλάχιστον 2 επιλογές.")
        show = 1 if body.get("show_results", bool(row["show_results"])) else 0
        conn.execute("UPDATE polls SET question=?, options=?, show_results=? WHERE id=?",
                     (question, json.dumps(options, ensure_ascii=False), show, pid))
    if pid in state.ACTIVE_POLLS:                       # ζωντανή ενημέρωση ενεργού poll
        state.ACTIVE_POLLS[pid].update(question=question, options=options, show_results=bool(show))
        await broadcast({"type": "poll", "id": pid, "question": question, "options": options,
                         "show_results": bool(show), "ts": row["ts"], "updated": True},
                        audience=state.ACTIVE_POLLS[pid]["audience"], tmima=state.ACTIVE_POLLS[pid]["tmima"])
    await broadcast({"type": "poll_updated", "id": pid}, audience="teachers")
    return {"ok": True}


@router.delete("/api/polls/{pid}")
async def api_poll_delete(pid: str, request: Request):
    state.require_teacher(request)
    with db() as conn:
        conn.execute("DELETE FROM poll_votes WHERE poll_id=?", (pid,))
        conn.execute("DELETE FROM polls WHERE id=?", (pid,))
    state.ACTIVE_POLLS.pop(pid, None)
    await broadcast({"type": "poll_deleted", "id": pid})
    return {"ok": True}


@router.post("/api/polls/bulk")
async def api_polls_bulk(request: Request):
    """Μαζικές ενέργειες: {action: close|delete, ids: [...] | all: true, older_than_days: N}."""
    state.require_teacher(request)
    body = await request.json()
    action = str(body.get("action", ""))
    if action not in ("close", "delete"):
        raise HTTPException(400, "action: close | delete.")
    ids = bulk_ids("polls", body)
    n = 0
    for pid in ids:
        if action == "close":
            if await close_poll_internal(pid) is not None:
                n += 1
        else:
            with db() as conn:
                conn.execute("DELETE FROM poll_votes WHERE poll_id=?", (pid,))
                cur = conn.execute("DELETE FROM polls WHERE id=?", (pid,))
                n += cur.rowcount
            state.ACTIVE_POLLS.pop(pid, None)
            await broadcast({"type": "poll_deleted", "id": pid})
    return {"ok": True, "affected": n}


# ---------------------------------------------------------------------------
# WS handler — καλείται από το presence.hub_socket (type: poll_vote)
# ---------------------------------------------------------------------------
async def ws_poll_vote(c, pid: str, choice: int) -> None:
    poll = state.ACTIVE_POLLS.get(pid)
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
    # 🔚 Αυτόματο κλείσιμο όταν έχουν ψηφίσει ΟΛΟΙ οι συνδεδεμένοι του κοινού
    if poll.get("auto_close"):
        with db() as conn:
            voted = {v["uid"] for v in conn.execute(
                "SELECT uid FROM poll_votes WHERE poll_id=?", (pid,))}
        if eligible_uids(poll["audience"], poll["tmima"]) <= voted:
            await close_poll_internal(pid)