"""
Quiz τάξης — αποστολή σε μαθητές (καταγραφή στη SQLite) & guests (μόνο
εξάσκηση), server-side βαθμολόγηση (το correct ΔΕΝ φεύγει στον client),
CRUD, αποτελέσματα & bulk διαχείριση. WS handler: ws_quiz_submit.
"""
from __future__ import annotations

import json
import secrets
import time

from fastapi import APIRouter, HTTPException, Request

import state
from store import db, bulk_ids
from presence import broadcast, send_json, audience_match, eligible_uids

router = APIRouter()


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


@router.post("/api/cmd/quiz")
async def cmd_quiz(request: Request):
    """📝 Αποστολή quiz (inline ερωτήσεις ή bank_id από το Excel)."""
    state.require_teacher(request)
    body = await request.json()
    bank_id = str(body.get("bank_id", ""))
    if bank_id:
        bank = next((q for q in state.CONFIG["quizzes_bank"] if q["id"] == bank_id), None)
        if not bank:
            raise HTTPException(404, "Δεν βρέθηκε quiz με αυτό το id στην τράπεζα Excel.")
        title, questions = bank["title"], bank["questions"]
    else:
        title = str(body.get("title", "Quiz Τάξης")).strip()[:120]
        questions = clean_questions(body.get("questions"))
    aud, tmima = state.audience_of(body)
    qid = secrets.token_hex(6)
    auto = 1 if body.get("auto_close", True) else 0
    dur = float(body.get("duration_sec", 0) or 0)
    ends = time.time() + dur if dur > 0 else 0.0
    with db() as conn:
        conn.execute("INSERT INTO quizzes (id, ts, title, questions, audience, closed,"
                     " auto_close, ends_at) VALUES (?,?,?,?,?,0,?,?)",
                     (qid, time.time(), title, json.dumps(questions, ensure_ascii=False),
                      f"{aud}|{tmima}", auto, ends))
    state.ACTIVE_QUIZZES[qid] = {"id": qid, "title": title, "questions": questions,
                                 "audience": aud, "tmima": tmima, "closed": False,
                                 "auto_close": bool(auto), "ends_at": ends}
    # Στους πελάτες ΔΕΝ στέλνουμε το correct — η βαθμολόγηση γίνεται στον server.
    public_qs = [{"text": q["text"], "options": q["options"]} for q in questions]
    await broadcast({"type": "quiz", "id": qid, "title": title, "questions": public_qs,
                     "ts": time.time()}, audience=aud, tmima=tmima)
    return {"ok": True, "id": qid, "count": len(questions)}


@router.get("/api/quizzes")
def api_quizzes(request: Request):
    state.require_teacher(request)
    with db() as conn:
        rows = conn.execute("SELECT id, ts, title, closed FROM quizzes ORDER BY ts DESC LIMIT 100").fetchall()
        out = []
        for r in rows:
            results = conn.execute(
                "SELECT id, uid, name, tmima, score, total, ts FROM quiz_results "
                "WHERE quiz_id=? ORDER BY score DESC, ts ASC", (r["id"],)).fetchall()
            out.append({"id": r["id"], "ts": r["ts"], "title": r["title"],
                        "closed": bool(r["closed"]), "results": [dict(x) for x in results]})
        return {"quizzes": out}


async def close_quiz_internal(qid: str) -> bool:
    """Κλείσιμο quiz (χειροκίνητο ή αυτόματο όταν υποβάλουν όλοι)."""
    with db() as conn:
        cur = conn.execute("UPDATE quizzes SET closed=1 WHERE id=?", (qid,))
        if not cur.rowcount:
            return False
    state.ACTIVE_QUIZZES.pop(qid, None)
    await broadcast({"type": "quiz_closed", "id": qid})
    return True


@router.post("/api/cmd/quiz/{qid}/close")
async def cmd_quiz_close(qid: str, request: Request):
    state.require_teacher(request)
    if not await close_quiz_internal(qid):
        raise HTTPException(404, "Το quiz δεν βρέθηκε.")
    return {"ok": True}


@router.put("/api/quizzes/{qid}")
async def api_quiz_update(qid: str, request: Request):
    """✏️ Επεξεργασία quiz (τίτλος· ερωτήσεις μόνο όσο δεν έχει αποτελέσματα)."""
    state.require_teacher(request)
    body = await request.json()
    with db() as conn:
        row = conn.execute("SELECT * FROM quizzes WHERE id=?", (qid,)).fetchone()
        if not row:
            raise HTTPException(404, "Το quiz δεν βρέθηκε.")
        title = str(body.get("title", row["title"])).strip()[:120] or row["title"]
        questions = json.loads(row["questions"])
        if "questions" in body:
            n = conn.execute("SELECT COUNT(*) n FROM quiz_results WHERE quiz_id=?", (qid,)).fetchone()["n"]
            if n:
                raise HTTPException(400, "Το quiz έχει ήδη αποτελέσματα — οι ερωτήσεις δεν αλλάζουν (μόνο ο τίτλος).")
            questions = clean_questions(body["questions"])
        conn.execute("UPDATE quizzes SET title=?, questions=? WHERE id=?",
                     (title, json.dumps(questions, ensure_ascii=False), qid))
    if qid in state.ACTIVE_QUIZZES:
        state.ACTIVE_QUIZZES[qid].update(title=title, questions=questions)
        public_qs = [{"text": q["text"], "options": q["options"]} for q in questions]
        await broadcast({"type": "quiz", "id": qid, "title": title, "questions": public_qs,
                         "ts": row["ts"], "updated": True},
                        audience=state.ACTIVE_QUIZZES[qid]["audience"], tmima=state.ACTIVE_QUIZZES[qid]["tmima"])
    await broadcast({"type": "quiz_updated", "id": qid}, audience="teachers")
    return {"ok": True}


@router.delete("/api/quizzes/{qid}")
async def api_quiz_delete(qid: str, request: Request):
    state.require_teacher(request)
    with db() as conn:
        conn.execute("DELETE FROM quiz_results WHERE quiz_id=?", (qid,))
        conn.execute("DELETE FROM quizzes WHERE id=?", (qid,))
    state.ACTIVE_QUIZZES.pop(qid, None)
    await broadcast({"type": "quiz_deleted", "id": qid})
    return {"ok": True}


@router.post("/api/quizzes/bulk")
async def api_quizzes_bulk(request: Request):
    """Μαζικές ενέργειες: {action: close|delete, ids | all | older_than_days}."""
    state.require_teacher(request)
    body = await request.json()
    action = str(body.get("action", ""))
    if action not in ("close", "delete"):
        raise HTTPException(400, "action: close | delete.")
    ids = bulk_ids("quizzes", body)
    n = 0
    for qid in ids:
        if action == "close":
            if await close_quiz_internal(qid):
                n += 1
        else:
            with db() as conn:
                conn.execute("DELETE FROM quiz_results WHERE quiz_id=?", (qid,))
                cur = conn.execute("DELETE FROM quizzes WHERE id=?", (qid,))
                n += cur.rowcount
            state.ACTIVE_QUIZZES.pop(qid, None)
            await broadcast({"type": "quiz_deleted", "id": qid})
    return {"ok": True, "affected": n}


@router.delete("/api/quiz-results/{rid}")
def api_quiz_result_delete(rid: int, request: Request):
    """Διαγραφή μεμονωμένου αποτελέσματος μαθητή (π.χ. άκυρη υποβολή)."""
    state.require_teacher(request)
    with db() as conn:
        cur = conn.execute("DELETE FROM quiz_results WHERE id=?", (rid,))
        if not cur.rowcount:
            raise HTTPException(404, "Το αποτέλεσμα δεν βρέθηκε.")
    return {"ok": True}


@router.post("/api/quiz-results/bulk-delete")
async def api_quiz_results_bulk_delete(request: Request):
    """Μαζική διαγραφή αποτελεσμάτων: {ids: [...]} ή {quiz_id, all: true}."""
    state.require_teacher(request)
    body = await request.json()
    with db() as conn:
        if body.get("ids"):
            ids = [int(i) for i in body["ids"]][:500]
            qmarks = ",".join("?" * len(ids)) or "NULL"
            cur = conn.execute(f"DELETE FROM quiz_results WHERE id IN ({qmarks})", ids)
        elif body.get("quiz_id") and body.get("all"):
            cur = conn.execute("DELETE FROM quiz_results WHERE quiz_id=?", (str(body["quiz_id"]),))
        else:
            raise HTTPException(400, "Δώσε ids ή quiz_id με all=true.")
        return {"ok": True, "affected": cur.rowcount}


# ---------------------------------------------------------------------------
# WS handler — καλείται από το presence.hub_socket (type: quiz_submit)
# ---------------------------------------------------------------------------
async def ws_quiz_submit(c, qid: str, answers: list) -> None:
    quiz = state.ACTIVE_QUIZZES.get(qid)
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
    # 🔚 Αυτόματο κλείσιμο όταν έχουν υποβάλει ΟΛΟΙ οι συνδεδεμένοι του κοινού.
    # Οι guests δεν καταγράφονται στη βάση → παρακολουθούνται σε μνήμη ανά quiz.
    submitted = quiz.setdefault("submitted", set())
    submitted.add(c.uid)
    if quiz.get("auto_close") and eligible_uids(quiz["audience"], quiz["tmima"]) <= submitted:
        await close_quiz_internal(qid)