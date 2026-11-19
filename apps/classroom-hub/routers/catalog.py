"""
📚 Κατάλογος μαθημάτων & σύνδεσμοι για τη ΣΥΝΘΕΤΗ ανακοίνωση (common.lessons).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from common.lessons import lessons_catalog

import state
from routers.commands import clean_links

router = APIRouter()


@router.get("/api/lessons-catalog")
def api_lessons_catalog(request: Request):
    """Read-only κατάλογος μαθημάτων (τίτλος/tags/favorite/τάξη) από τα front-matter
    του mkdocs-site — κοινή ελαφριά λογική με το Lesson Wizard (common.lessons)."""
    state.require_teacher(request)
    math_dir = state.PORTAL_DIR / "mkdocs-site" / "docs" / "mathimata"
    return {"lessons": lessons_catalog(math_dir),
            "apps": [{"title": m["title"], "url": m["url"]}
                     for m in state.CONFIG["menu"] if m["url"].startswith("/")],
            "custom_links": state.CONFIG.get("announce_links", [])}


@router.post("/api/announce-links")
async def api_announce_links(request: Request):
    """Διαμορφώσιμοι σύνδεσμοι ανακοινώσεων: {action: add|remove, title, url}."""
    state.require_teacher(request)
    body = await request.json()
    links = list(state.CONFIG.get("announce_links", []))
    action = str(body.get("action", "add"))
    if action == "add":
        new = clean_links([{"title": body.get("title", ""), "url": body.get("url", "")}])
        if not new:
            raise HTTPException(400, "Δώσε σχετικό URL πύλης (π.χ. /docs/…).")
        if not any(l["url"] == new[0]["url"] for l in links):
            links.append(new[0])
    elif action == "remove":
        url = str(body.get("url", ""))
        links = [l for l in links if l["url"] != url]
    else:
        raise HTTPException(400, "action: add | remove.")
    state.CONFIG["announce_links"] = links[:30]
    state.save_config(state.CONFIG)
    return {"ok": True, "links": state.CONFIG["announce_links"]}