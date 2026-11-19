"""
Χρονομετρητές — ιδιωτικοί/δημόσιοι, με anchor στο ωράριο + offset ±λεπτών,
και γεγονότα τέλους ημέρας/ώρας από το Excel (fire_event/event_deadline).
Οι λήξεις των ACTIVE_TIMERS γίνονται στο presence.housekeeping.
"""
from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, HTTPException, Request

from common.schedule import (schedule_deadline as _schedule_deadline,
                             event_deadline as _event_deadline)

import state
from store import store_announcement
from presence import broadcast

router = APIRouter()


def schedule_deadline(tmima: str, day: str, period: int, edge: str, offset_min: float) -> float | None:
    """Υπολογίζει epoch deadline από διδακτική ώρα του ωραρίου + offset (common.schedule).
    edge: start|end· day='' → σημερινή ημέρα."""
    return _schedule_deadline(state.CONFIG["schedule"]["periods"], day, period, edge, offset_min)


def event_deadline(ev: dict) -> float | None:
    """trigger: day_end (τέλος τελευταίας ώρας), period_end (συγκεκριμένη ώρα),
    time (συγκεκριμένη HH:MM) — πάντα με offset ±λεπτών (common.schedule)."""
    return _event_deadline(ev, state.CONFIG["schedule"]["periods"])


async def fire_event(kind: str, text: str, audience: str = "all", tmima: str = "",
                     url: str = "") -> None:
    msg = {"id": secrets.token_hex(6), "kind": kind, "text": text,
           "ts": time.time(), "audience": audience, "tmima": tmima,
           "target_uid": "", "target_name": "",
           "links": [{"title": text[:80], "url": url}] if url else []}
    store_announcement(msg)
    await broadcast({"type": "announcement", **msg}, audience=audience, tmima=tmima)
    if url:
        await broadcast({"type": "navigate", "url": url, "title": text[:80],
                         "ts": time.time()}, audience="students", tmima=tmima)


@router.post("/api/cmd/timer")
async def cmd_timer(request: Request):
    """⏱️ Χρονομετρητής: duration_sec Ή anchor ωραρίου (tmima/day/period/edge/offset).
    visibility: private (μόνο καθηγητής) | public (όλοι ή επιλεγμένο κοινό)."""
    state.require_teacher(request)
    body = await request.json()
    label = str(body.get("label", "Χρονομετρητής")).strip()[:80] or "Χρονομετρητής"
    visibility = str(body.get("visibility", "public"))
    if visibility not in ("private", "public"):
        raise HTTPException(400, "visibility: private | public.")
    aud, tmima = state.audience_of(body)
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
    state.ACTIVE_TIMERS[tid] = timer
    payload = {"type": "timer", **timer}
    if visibility == "private":
        await broadcast(payload, audience="teachers")
    else:
        await broadcast(payload, audience=aud, tmima=tmima)
    return {"ok": True, "id": tid, "ends_at": ends}


@router.post("/api/cmd/timer/{tid}/stop")
async def cmd_timer_stop(tid: str, request: Request):
    state.require_teacher(request)
    state.ACTIVE_TIMERS.pop(tid, None)
    await broadcast({"type": "timer_stop", "id": tid})
    return {"ok": True}


@router.post("/api/cmd/timer-from-config/{cfg_id}")
async def cmd_timer_from_config(cfg_id: str, request: Request):
    """Εκκινεί timer ορισμένο στο Excel (id από την καρτέλα Timers)."""
    state.require_teacher(request)
    t = next((x for x in state.CONFIG["timers"] if x["id"] == cfg_id), None)
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
    state.ACTIVE_TIMERS[tid] = timer
    aud = "teachers" if timer["visibility"] == "private" else timer["audience"]
    await broadcast({"type": "timer", **timer}, audience=aud)
    return {"ok": True, "id": tid, "ends_at": ends}