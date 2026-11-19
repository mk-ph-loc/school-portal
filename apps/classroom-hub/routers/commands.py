"""
Εντολές τάξης (μόνο καθηγητής) — ανακοινώσεις/συγχαρητήρια/βραβεία, τυχαία
επιλογή μαθητή, υποχρεωτική πλοήγηση + διαχείριση μόνιμων ανακοινώσεων.
"""
from __future__ import annotations

import json
import random
import secrets
import time

from fastapi import APIRouter, HTTPException, Request

import state
from store import db, store_announcement, recent_announcements, bulk_ids
from presence import broadcast, send_to_uid, audience_match

router = APIRouter()


def clean_links(raw) -> list[dict]:
    """Σύνδεσμοι σύνθετης ανακοίνωσης: [{title, url}] — μόνο σχετικά URLs πύλης."""
    out = []
    for l in raw or []:
        if not isinstance(l, dict):
            continue
        url = str(l.get("url", "")).strip()
        if not url.startswith("/") or url.startswith("//"):
            continue
        out.append({"title": str(l.get("title", "")).strip()[:80] or url, "url": url[:300]})
    return out[:8]


@router.post("/api/cmd/announce")
async def cmd_announce(request: Request):
    """📣 Ανακοίνωση / 🎉 συγχαρητήρια / 🏆 βραβείο (kind: announce|congrats|award)."""
    state.require_teacher(request)
    body = await request.json()
    kind = str(body.get("kind", "announce"))
    if kind not in ("announce", "congrats", "award"):
        raise HTTPException(400, "kind: announce | congrats | award.")
    text = str(body.get("text", "")).strip()[:500]
    if not text:
        raise HTTPException(400, "Γράψε το μήνυμα.")
    aud, tmima = state.audience_of(body)
    target_uid = str(body.get("target_uid", ""))
    links = clean_links(body.get("links"))
    msg = {"id": secrets.token_hex(6), "kind": kind, "text": text,
           "ts": time.time(), "audience": aud, "tmima": tmima,
           "target_uid": target_uid,
           "target_name": next((c.name for c in state.CLIENTS.values() if c.uid == target_uid), ""),
           "links": links}
    store_announcement(msg)
    payload = {"type": "announcement", **msg}
    if target_uid:
        await send_to_uid(target_uid, payload)          # προσωπικό (π.χ. βραβείο)
        await broadcast(payload, audience="teachers")   # ο καθηγητής βλέπει τι στάλθηκε
        sent = 1
    else:
        sent = await broadcast(payload, audience=aud, tmima=tmima)
    # Σύνθετη ανακοίνωση: προαιρετική άμεση μετάβαση στον 1ο σύνδεσμο
    if links and body.get("navigate") and not target_uid:
        nav_aud = "students" if aud == "all" else aud   # ποτέ δεν σπρώχνουμε άλλον καθηγητή
        await broadcast({"type": "navigate", "url": links[0]["url"],
                         "title": links[0]["title"] or text[:80], "ts": time.time()},
                        audience=nav_aud, tmima=tmima)
    return {"ok": True, "sent": sent, "announcement": msg}


@router.post("/api/cmd/random-pick")
async def cmd_random_pick(request: Request):
    """🎲 Τυχαία επιλογή από τους συνδεδεμένους (με φίλτρο ρόλου/τμήματος)."""
    state.require_teacher(request)
    body = await request.json()
    aud, tmima = state.audience_of(body)
    pool, seen = [], set()
    for c in state.CLIENTS.values():
        if c.uid not in seen and audience_match(c, aud or "students", tmima):
            pool.append(c)
            seen.add(c.uid)
    if not pool:
        raise HTTPException(404, "Δεν υπάρχει κανείς συνδεδεμένος με αυτά τα κριτήρια.")
    pick = random.choice(pool)
    payload = {"type": "random_pick", "uid": pick.uid, "name": pick.name,
               "emoji": pick.emoji, "tmima": pick.tmima,
               "celebrate": bool(body.get("celebrate", True)), "ts": time.time()}
    await broadcast(payload)                            # όλοι βλέπουν την κλήρωση
    return {"ok": True, "picked": payload, "pool_size": len(pool)}


@router.post("/api/cmd/navigate")
async def cmd_navigate(request: Request):
    """➡️ Υποχρεωτική μετάβαση μαθητών & guests σε συγκεκριμένη σελίδα της πύλης."""
    state.require_teacher(request)
    body = await request.json()
    url = str(body.get("url", "")).strip()
    if not url.startswith("/") or url.startswith("//"):
        raise HTTPException(400, "Δώσε σχετικό URL της πύλης (π.χ. /docs/ ή /live-quiz/).")
    aud, tmima = state.audience_of(body)
    if aud == "all":
        aud = "students"                                # ποτέ δεν σπρώχνουμε άλλον καθηγητή
    sent = await broadcast({"type": "navigate", "url": url,
                            "title": str(body.get("title", ""))[:80],
                            "ts": time.time()}, audience=aud, tmima=tmima)
    return {"ok": True, "sent": sent}


# ---------------------------------------------------------------------------
# 🗄️ Διαχείριση ανακοινώσεων (μόνιμη αποθήκευση + edit/delete/bulk)
# ---------------------------------------------------------------------------
@router.get("/api/announcements")
def api_announcements(request: Request, limit: int = 100):
    state.require_teacher(request)
    return {"announcements": recent_announcements(max(1, min(int(limit), 500)))}


@router.put("/api/announcements/{aid}")
async def api_announcement_update(aid: str, request: Request):
    """✏️ Επεξεργασία κειμένου/kind/συνδέσμων — ενημερώνεται ζωντανά σε όλους."""
    state.require_teacher(request)
    body = await request.json()
    with db() as conn:
        row = conn.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone()
        if not row:
            raise HTTPException(404, "Η ανακοίνωση δεν βρέθηκε.")
        kind = str(body.get("kind", row["kind"]))
        if kind not in ("announce", "congrats", "award"):
            raise HTTPException(400, "kind: announce | congrats | award.")
        text = str(body.get("text", row["text"])).strip()[:500] or row["text"]
        links = clean_links(body["links"]) if "links" in body else json.loads(row["links"] or "[]")
        conn.execute("UPDATE announcements SET kind=?, text=?, links=? WHERE id=?",
                     (kind, text, json.dumps(links, ensure_ascii=False), aid))
    msg = {"id": aid, "ts": row["ts"], "kind": kind, "text": text,
           "audience": row["audience"], "tmima": row["tmima"],
           "target_uid": row["target_uid"], "target_name": row["target_name"], "links": links}
    await broadcast({"type": "announcement_updated", **msg})
    return {"ok": True, "announcement": msg}


@router.delete("/api/announcements/{aid}")
async def api_announcement_delete(aid: str, request: Request):
    state.require_teacher(request)
    with db() as conn:
        cur = conn.execute("DELETE FROM announcements WHERE id=?", (aid,))
        if not cur.rowcount:
            raise HTTPException(404, "Η ανακοίνωση δεν βρέθηκε.")
    await broadcast({"type": "announcement_deleted", "id": aid})
    return {"ok": True}


@router.post("/api/announcements/bulk")
async def api_announcements_bulk(request: Request):
    """Μαζική διαγραφή: {ids | all | older_than_days}."""
    state.require_teacher(request)
    body = await request.json()
    if str(body.get("action", "delete")) != "delete":
        raise HTTPException(400, "Για ανακοινώσεις υποστηρίζεται μόνο action=delete.")
    ids = bulk_ids("announcements", body)
    n = 0
    with db() as conn:
        for aid in ids:
            n += conn.execute("DELETE FROM announcements WHERE id=?", (aid,)).rowcount
    if ids:
        await broadcast({"type": "announcements_bulk_deleted", "ids": ids})
    return {"ok": True, "affected": n}