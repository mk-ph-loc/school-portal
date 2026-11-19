"""
Lesson Wizard — 📖 Βιβλιοθήκη βιβλίων (Task 3: APIRouters).

PDF στο docs/vivliothiki/ + metadata στο data/books.json, αυτόματη σελίδα
vivliothiki/index.md, links «σελ. Ν» (#page=N) στην κεφαλίδα μαθήματος.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form

from common.classes import CLASS_GROUPS, CLASS_SLUGS, CLASS_LABELS, SLUG_RE
from common.lessons import parse_lesson, render_lesson
from common.schedule import load_json, save_json

import state

router = APIRouter()


# ---------------------------------------------------------------------------
# Routes — 📖 Βιβλιοθήκη βιβλίων (PDF στο docs/vivliothiki/, links με #page=N)
# ---------------------------------------------------------------------------
def rebuild_library_page() -> None:
    """Παράγει το vivliothiki/index.md από τα metadata των βιβλίων."""
    books = load_json(state.BOOKS_JSON, [])
    state.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "title: '📖 Βιβλιοθήκη Βιβλίων'",
        "---",
        "",
        "# 📖 Βιβλιοθήκη Βιβλίων",
        "",
        "Τα σχολικά βιβλία (PDF) που χρησιμοποιούμε στα μαθήματα. Κάθε σύνδεσμος",
        "«σελ. Ν» ανοίγει το βιβλίο **κατευθείαν στη σελίδα Ν** (`#page=N`).",
        "",
        '!!! tip "Πώς μπαίνει link σε συγκεκριμένη σελίδα μέσα σε μάθημα"',
        "    Από το [Lesson Wizard → Βιβλία](/lesson-wizard/){target=_blank} πάτα",
        "    **🔗 Link σε μάθημα**, ή γράψε απευθείας markdown:",
        "    `[📖 Βιβλίο, σελ. 10](/docs/vivliothiki/ΟΝΟΜΑ.pdf#page=10){target=_blank}`",
        "",
    ]
    if not books:
        lines.append("*Δεν έχουν ανέβει βιβλία ακόμη — ο καθηγητής τα προσθέτει από το Lesson Wizard → 📖 Βιβλία.*")
    for b in books:
        cls_label = CLASS_LABELS.get(b.get("class_slug", ""), "")
        meta_bits = [x for x in (cls_label, b.get("subject", ""),
                                 (str(b["pages"]) + " σελίδες") if b.get("pages") else "") if x]
        lines += [
            f"## {b['title']}",
            "",
            (" · ".join(meta_bits) + "  ") if meta_bits else "",
            f"[📕 Άνοιγμα βιβλίου]({b['file']}){{target=_blank}} · "
            f"[Σελ. 1]({b['file']}#page=1){{target=_blank}}",
            "",
            f'<object data="{b["file"]}#page=1" type="application/pdf" width="100%" height="520px">',
            f'<p>📄 <a href="{b["file"]}" target="_blank">Λήψη/Άνοιγμα PDF</a></p>',
            "</object>",
            "",
        ]
    idx = state.LIBRARY_DIR / "index.md"
    new_md = "\n".join(lines) + "\n"
    if not idx.exists() or idx.read_text(encoding="utf-8") != new_md:
        state.backup_file(idx)
        idx.write_text(new_md, encoding="utf-8")


@router.get("/api/books")
def api_books(request: Request):
    state.require_teacher(request)
    return {"books": load_json(state.BOOKS_JSON, []), "classes": CLASS_GROUPS}


@router.post("/api/books/upload")
async def api_books_upload(request: Request, file: UploadFile = File(...),
                           title: str = Form(""), slug: str = Form(""),
                           class_slug: str = Form(""), subject: str = Form("")):
    state.require_teacher(request)
    name = PurePosixPath(file.filename or "").name
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Απαιτείται αρχείο PDF.")
    slug = (slug or PurePosixPath(name).stem).strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    if not SLUG_RE.match(slug):
        raise HTTPException(400, "Μη έγκυρο slug βιβλίου (πεζά λατινικά/greeklish).")
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(413, "Το βιβλίο ξεπερνά τα 100 MB.")
    pages = 0
    try:
        import io
        from pypdf import PdfReader
        pages = len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        pass                                       # μη αναγνώσιμο PDF → χωρίς πλήθος σελίδων
    state.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    dest = state.LIBRARY_DIR / f"{slug}.pdf"
    if dest.exists():
        state.backup_file(dest)
    dest.write_bytes(content)
    books = load_json(state.BOOKS_JSON, [])
    entry = {"slug": slug, "title": title.strip() or slug,
             "file": f"/docs/vivliothiki/{slug}.pdf",
             "class_slug": class_slug if class_slug in CLASS_SLUGS else "",
             "subject": subject.strip(), "pages": pages,
             "size": len(content),
             "added": datetime.now().isoformat(timespec="seconds")}
    books = [b for b in books if b["slug"] != slug] + [entry]
    save_json(state.BOOKS_JSON, books)
    rebuild_library_page()
    state.rebuild_nav()
    return {"ok": True, "book": entry}


@router.delete("/api/books/{slug}")
def api_books_delete(slug: str, request: Request):
    state.require_teacher(request)
    if not SLUG_RE.match(slug):
        raise HTTPException(400, "Μη έγκυρο slug.")
    books = load_json(state.BOOKS_JSON, [])
    if slug not in {b["slug"] for b in books}:
        raise HTTPException(404, "Το βιβλίο δεν βρέθηκε.")
    pdf = state.LIBRARY_DIR / f"{slug}.pdf"
    if pdf.is_file():
        state.backup_file(pdf)
        pdf.unlink()
    save_json(state.BOOKS_JSON, [b for b in books if b["slug"] != slug])
    rebuild_library_page()
    state.rebuild_nav()
    return {"ok": True}


@router.post("/api/books/link")
async def api_books_link(request: Request):
    """Εισαγωγή link βιβλίου με #page=N στο τέλος της κεφαλίδας ενός μαθήματος."""
    state.require_teacher(request)
    body = await request.json()
    slug = str(body.get("slug", "")).strip()
    page = int(body.get("page", 1))
    key = str(body.get("lesson_key", "")).split("/")
    if len(key) != 3:
        raise HTTPException(400, "Δώσε μάθημα (τάξη/μάθημα/φάκελος).")
    d = state.lesson_dir(*key)
    idx = d / "index.md"
    if not idx.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    book = next((b for b in load_json(state.BOOKS_JSON, []) if b["slug"] == slug), None)
    if not book:
        raise HTTPException(404, "Το βιβλίο δεν βρέθηκε.")
    max_p = book.get("pages") or 10000
    if not (1 <= page <= max_p):
        raise HTTPException(400, f"Η σελίδα πρέπει να είναι 1–{max_p}.")
    parsed = parse_lesson(idx.read_text(encoding="utf-8"))
    link = f"[📖 {book['title']}, σελ. {page}]({book['file']}#page={page}){{target=_blank}}"
    if link in parsed["header"]:
        return {"ok": True, "link": link, "already": True}
    parsed["header"] = parsed["header"].rstrip() + "\n\n" + link
    state.backup_file(idx)
    idx.write_text(render_lesson(parsed), encoding="utf-8")
    return {"ok": True, "link": link}
