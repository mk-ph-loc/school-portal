"""
Classroom Hub — ζωντανή παρουσία & WebSockets (Task 3: διάσπαση σε APIRouters).

Client/roster/broadcast + ο κεντρικός WS handler (/ws) που dispatchάρει στα
domain modules (polls/quizzes/chat_forum) + το background housekeeping loop
(φάσματα χωρίς heartbeat, λήξεις timers/polls/quizzes, γεγονότα ωραρίου).
Ένα event loop, ένας worker (βλ. systemd school-classroom.service).

Τα broadcast primitives ΔΕΝ εξαρτώνται από routers· οι domain handlers
γίνονται import ΤΕΜΠΕΛΙΚΑ μέσα στις συναρτήσεις (routers → presence μόνο),
ώστε να μην υπάρχουν κυκλικά imports.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from common.schedule import DAYS

import state
from store import db, active_mute, visible_announcements

log = logging.getLogger("classroom-hub")


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
    for c in list(state.CLIENTS.values()):
        if c.uid == exclude_uid:
            continue
        if audience_match(c, audience, tmima):
            await send_json(c.ws, payload)
            n += 1
    return n


async def send_to_uid(uid: str, payload: dict) -> None:
    for c in list(state.CLIENTS.values()):
        if c.uid == uid:
            await send_json(c.ws, payload)


def roster_payload() -> dict:
    return {"type": "roster", "clients": [c.public() for c in state.CLIENTS.values()],
            "server_now": time.time()}


async def push_roster() -> None:
    await broadcast(roster_payload(), audience="teachers")


def eligible_uids(audience: str, tmima: str) -> set[str]:
    """Μοναδικοί uid των συνδεδεμένων που ανήκουν στο κοινό (χωρίς καθηγητές)."""
    return {c.uid for c in state.CLIENTS.values()
            if c.role != "teacher" and audience_match(c, audience, tmima)}


# ---------------------------------------------------------------------------
# Background εργασία: sweeper παρουσίας + λήξη timers + γεγονότα ωραρίου
# ---------------------------------------------------------------------------
async def housekeeping() -> None:
    """Τρέχει κάθε δευτερόλεπτο: αποσύνδεση 'φαντασμάτων', λήξεις timers,
    γεγονότα τέλους ημέρας/ώρας από το Excel."""
    # Τεμπέλικα imports: τα routers κάνουν import το presence (broadcast) —
    # εδώ τα φορτώνουμε μόνο όταν ξεκινήσει το loop (όλα τα modules έτοιμα).
    from routers import polls as polls_mod
    from routers import quizzes as quizzes_mod
    from routers import timers as timers_mod
    while True:
        try:
            now = time.time()
            # 1) παρουσία: χωρίς heartbeat > HEARTBEAT_TIMEOUT → έξοδος
            stale = [k for k, c in state.CLIENTS.items()
                     if now - c.last_ping > state.HEARTBEAT_TIMEOUT]
            for k in stale:
                c = state.CLIENTS.pop(k, None)
                if c:
                    try:
                        await c.ws.close(code=4001)
                    except Exception:
                        pass
            if stale:
                await push_roster()
            # 2) λήξη χρονομετρητών
            for tid, t in list(state.ACTIVE_TIMERS.items()):
                if now >= t["ends_at"]:
                    state.ACTIVE_TIMERS.pop(tid, None)
                    payload = {"type": "timer_done", "id": tid, "label": t["label"],
                               "message": t.get("message", "")}
                    if t["visibility"] == "private":
                        await broadcast(payload, audience="teachers")
                    else:
                        await broadcast(payload, audience=t["audience"], tmima=t["tmima"])
            # 2β) λήξη polls/quizzes με χρονικό όριο (προαιρετικό duration_sec)
            for pid, p in list(state.ACTIVE_POLLS.items()):
                if p.get("ends_at") and now >= p["ends_at"]:
                    await polls_mod.close_poll_internal(pid)
            for qid, q in list(state.ACTIVE_QUIZZES.items()):
                if q.get("ends_at") and now >= q["ends_at"]:
                    await quizzes_mod.close_quiz_internal(qid)
            # 3) γεγονότα Excel (μία φορά ανά ημέρα & id, μόνο καθημερινές ή ορισμένες ημέρες)
            today = datetime.now().strftime("%Y-%m-%d")
            weekday = datetime.now().weekday()
            for ev in state.CONFIG["events"]:
                if not ev.get("enabled", True):
                    continue
                days = ev.get("days") or []
                if weekday >= 5 or (days and DAYS[weekday] not in days):
                    continue
                key = f"{ev['id']}:{today}"
                if key in state.EVENTS_FIRED:
                    continue
                dl = timers_mod.event_deadline(ev)
                if dl and now >= dl and now - dl < 3600:   # παράθυρο 1 ώρας (όχι μπαράζ σε restart)
                    state.EVENTS_FIRED.add(key)
                    await timers_mod.fire_event(ev.get("action", "announce"),
                                                ev.get("text", "Γεγονός ωραρίου"),
                                                ev.get("audience", "all"), ev.get("tmima", ""),
                                                ev.get("url", ""))
        except Exception:
            log.exception("housekeeping: απρόσμενο σφάλμα (το loop συνεχίζει)")
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# WebSocket — /ws (ταυτότητα από HMAC cookie· heartbeat ανά 15s από τον client)
# ---------------------------------------------------------------------------
async def hub_socket(ws: WebSocket) -> None:
    # Τεμπέλικα imports των domain handlers (routers → presence, όχι αντίστροφα)
    from routers import polls as polls_mod
    from routers import quizzes as quizzes_mod
    from routers import chat_forum
    ident = state.identity_from(ws)                     # τα cookies είναι διαθέσιμα στο WS
    teacher_cookie = state.token_payload(ws.cookies.get(state.COOKIE_NAME)) == "teacher"
    if not ident:
        await ws.close(code=4003)                       # πρώτα POST /api/join
        return
    if teacher_cookie:
        ident["role"] = "teacher"
    await ws.accept()
    c = Client(ws, ident)
    state.CLIENTS[id(ws)] = c
    # αρχική κατάσταση: timers/polls/quizzes σε εξέλιξη + πρόσφατες ανακοινώσεις.
    # Poll/quiz εμφανίζονται ΞΑΝΑ μόνο αν ο χρήστης ΔΕΝ έχει ήδη απαντήσει —
    # αλλιώς κάθε reconnect ξανάνοιγε τα modals ακόμα και μετά την υποβολή.
    with db() as conn:
        voted_polls = {r["poll_id"] for r in conn.execute(
            "SELECT poll_id FROM poll_votes WHERE uid=?", (c.uid,))}
        done_quizzes = {r["quiz_id"] for r in conn.execute(
            "SELECT quiz_id FROM quiz_results WHERE uid=?", (c.uid,))}
    pending_polls, pending_quizzes = [], []
    if c.role != "teacher":
        pending_polls = [p for p in state.ACTIVE_POLLS.values()
                         if audience_match(c, p["audience"], p["tmima"])
                         and p["id"] not in voted_polls]
        pending_quizzes = [{"id": q["id"], "title": q["title"],
                            "questions": [{"text": x["text"], "options": x["options"]}
                                          for x in q["questions"]]}
                           for q in state.ACTIVE_QUIZZES.values()
                           if audience_match(c, q["audience"], q["tmima"])
                           and q["id"] not in done_quizzes
                           and c.uid not in q.get("submitted", set())]
    mute = active_mute(c.uid)
    await send_json(ws, {"type": "welcome", "identity": c.public(),
                         "server_now": time.time(),
                         "announcements": visible_announcements(
                             {"uid": c.uid, "role": c.role, "tmima": c.tmima},
                             c.role == "teacher"),
                         "muted_until": mute["until_ts"] if mute else 0,
                         "timers": [t for t in state.ACTIVE_TIMERS.values()
                                    if t["visibility"] == "public" or c.role == "teacher"],
                         "polls": pending_polls,
                         "quizzes": pending_quizzes})
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
                await chat_forum.ws_chat(c, msg)
            elif mtype == "poll_vote":
                await polls_mod.ws_poll_vote(c, str(msg.get("id", "")), int(msg.get("choice", -1)))
            elif mtype == "quiz_submit":
                await quizzes_mod.ws_quiz_submit(c, str(msg.get("id", "")), msg.get("answers", []))
            elif mtype == "forum_post" and (c.role != "guest" or state.CONFIG["access"].get("guest_forum")):
                await chat_forum.ws_forum_post(c, msg)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        state.CLIENTS.pop(id(ws), None)
        await push_roster()