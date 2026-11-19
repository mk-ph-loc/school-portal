"""
H5P Studio — Ενσωμάτωση σε μάθημα MkDocs (Task 3: APIRouters).

Λίστα μαθημάτων (mathimata/ + _paradeigma/ — common.lessons), κώδικας iframe
και «1 κλικ» append στο τέλος υπάρχοντος .md με .bak backup + ιστορικό
(common.fs) και άμεσο rebuild του static site (build-docs.sh).
"""
from __future__ import annotations

import subprocess
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from common.classes import CLASS_SLUGS
from common.fs import backup_beside, backup_history
from common.lessons import list_lessons_grouped

import state
import content

router = APIRouter()


def list_lessons() -> list[dict]:
    """Όλα τα .md μαθήματα ανά τάξη (όπως στο apps/hedgedoc-bridge).

    mathimata/ + _paradeigma/ fallback — common.lessons (single source of truth).
    """
    return list_lessons_grouped(state.DOCS_DIR)


@router.get("/api/lessons")
def api_lessons(request: Request):
    state.require_teacher(request)
    return {"groups": list_lessons()}


def iframe_code(aid: str, title: str, height: int = 600) -> str:
    safe = title.replace('"', "'")
    return (f'<iframe src="/h5p-studio/play/{aid}/?embed=1" width="100%" '
            f'height="{height}" frameborder="0" allowfullscreen="allowfullscreen" '
            f'allow="autoplay; fullscreen; encrypted-media" '
            f'title="{safe}" style="border:0;border-radius:12px"></iframe>')


@router.get("/api/embed-code/{aid}")
def api_embed_code(request: Request, aid: str, height: int = 600):
    row = content.get_activity_row(aid)
    height = max(200, min(2000, height))
    return {"code": iframe_code(aid, row["title"], height),
            "play_url": f"/h5p-studio/play/{aid}/"}


class EmbedRequest(BaseModel):
    lesson: str
    height: int = 600
    heading: str = ""


@router.post("/api/embed/{aid}")
def api_embed(request: Request, aid: str, body: EmbedRequest):
    """1 κλικ: append του iframe στο τέλος υπάρχοντος .md (+ .bak backup)."""
    state.require_teacher(request)
    row = content.get_activity_row(aid)
    lesson = body.lesson.strip().replace("\\", "/").lstrip("/")
    parts = PurePosixPath(lesson).parts
    # Νέα δομή: mathimata/<τάξη>/… ή _paradeigma/<τάξη>/… (παλιό υλικό).
    slug = parts[1] if len(parts) > 1 and parts[0] in ("mathimata", "_paradeigma") else (
        parts[0] if parts else "")
    if (not lesson.endswith(".md") or not parts
            or any(p in ("..", "") for p in parts)
            or slug not in CLASS_SLUGS):
        raise HTTPException(400, "Μη έγκυρη διαδρομή μαθήματος (μόνο φάκελοι τάξεων).")
    target = (state.DOCS_DIR / lesson).resolve()
    if not str(target).startswith(str(state.DOCS_DIR.resolve()) + "/") or not target.is_file():
        raise HTTPException(400, "Το μάθημα δεν βρέθηκε.")
    text = target.read_text(encoding="utf-8")
    marker = f"/h5p-studio/play/{aid}/"
    if marker in text:
        raise HTTPException(409, "Η δραστηριότητα είναι ήδη ενσωματωμένη σε αυτό το μάθημα.")
    # Backup: .bak δίπλα + ιστορικό στο backups/ (όπως το md-publish bridge — common.fs)
    backup_beside(target)
    backup_history(target, state.BACKUP_DIR, relative_to=state.DOCS_DIR, mirror_tree=True)
    heading = body.heading.strip() or f"🎮 Διαδραστική Άσκηση: {row['title']}"
    height = max(200, min(2000, body.height))
    section = (f"\n\n## {heading}\n\n"
               f"{iframe_code(aid, row['title'], height)}\n")
    target.write_text(text.rstrip() + section, encoding="utf-8")
    try:
        target.chmod(0o664)
    except OSError:
        pass
    # Άμεσο rebuild (το school-mkdocs.path θα το έκανε έτσι κι αλλιώς)
    subprocess.Popen(["/bin/bash", str(state.BUILD_DOCS_SCRIPT)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # use_directory_urls: index.md → /docs/<dir>/, αλλιώς /docs/<dir>/<stem>/
    docs_url = "/docs/" + (lesson[:-8] if lesson.endswith("/index.md") else lesson[:-3] + "/")
    return {"ok": True, "lesson": lesson, "docs_url": docs_url}
