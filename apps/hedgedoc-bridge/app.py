"""
Γέφυρα Δημοσίευσης HedgeDoc → MkDocs (MD Publish Bridge) — Ψηφιακή Πύλη Σχολείου

Περιβάλλον καθηγητή (κωδικός teacher2026, HMAC-signed cookie όπως στο
/app-builder/) που γεφυρώνει το συνεργατικό Markdown του HedgeDoc (/md-pad/)
με τα μαθήματα του MkDocs (mkdocs-site/docs/):
  * λίστα ενεργών σημειώσεων απευθείας από τη SQLite βάση hedgedoc.sqlite
    (πίνακας Notes: τίτλος, ID/alias, τελευταία τροποποίηση),
  * επιλογή σημείωσης με URL/ID + κουμπί «Άνοιγμα Πρότυπου Δυνατοτήτων»,
  * προεπισκόπηση raw markdown (ίδια έξοδος με το /md-pad/<id>/download),
  * Επιλογή Α: append στο τέλος υπάρχοντος .md μαθήματος (ομαδοποίηση ανά
    τάξη), ως κανονικό Markdown ή σε αναδιπλούμενο ??? info κουτί,
  * Επιλογή Β: νέο μάθημα σε φάκελο τάξης + αυτόματη προσθήκη στο nav:,
  * αυτόματο αντίγραφο ασφαλείας .bak πριν από κάθε εγγραφή & καθαρισμός
    σύνταξης HedgeDoc → Material for MkDocs (:::info → !!! info κ.λπ.).

Τρέχει στο 127.0.0.1:8009 πίσω από τον Nginx στο /md-publish/. Χωρίς Docker.
Το rebuild του static site γίνεται αυτόματα από το school-mkdocs.path/service.
"""
from __future__ import annotations

import hmac
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from common.auth import TeacherAuth, TEACHER_CODE, COOKIE_MAX_AGE
from common.classes import CLASS_GROUPS, CLASS_SLUGS, CLASS_LABELS
from common.db import connect_ro
from common.fs import backup_beside, backup_history
from common.lessons import list_lessons_grouped

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent.parent            # apps/hedgedoc-bridge → /opt/school-portal
HEDGEDOC_DB = PORTAL_DIR / "apps" / "hedgedoc" / "hedgedoc.sqlite"
DOCS_DIR = PORTAL_DIR / "mkdocs-site" / "docs"
MKDOCS_YML = PORTAL_DIR / "mkdocs-site" / "mkdocs.yml"
BUILD_DOCS_SCRIPT = PORTAL_DIR / "scripts" / "build-docs.sh"
BACKUP_DIR = BASE_DIR / "backups"

COOKIE_NAME = "mdbridge_teacher"

TEMPLATE_NOTE_ALIAS = "template-demo"          # έτοιμο πρότυπο δυνατοτήτων
NOTE_URL_BASE = "/md-pad/"                     # subpath του HedgeDoc στον Nginx

# Οι 6 τάξεις του mkdocs-site — κοινές σε όλη την πύλη (common.classes)

FILENAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")     # πεζά λατινικά/greeklish
NOTE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")    # UUID/base64url/alias

app = FastAPI(
    title="Γέφυρα Δημοσίευσης HedgeDoc → MkDocs",
    description="Επιλογή συνεργατικής σημείωσης & δημοσίευση σε μάθημα MkDocs",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/md-publish) ορίζεται στο uvicorn μέσω του systemd
# unit, ώστε τα url_for() των templates να παράγουν σωστό πρόθεμα πίσω από
# τον Nginx.
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC) — common.auth
# ---------------------------------------------------------------------------
auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
make_token = auth.make_token
token_valid = auth.token_valid
require_teacher = auth.require_teacher


# ---------------------------------------------------------------------------
# Βοηθητικά: βάση HedgeDoc (read-only), δικαιώματα, backup, rebuild
# ---------------------------------------------------------------------------
def hedgedoc_conn() -> sqlite3.Connection:
    """Read-only σύνδεση στη βάση του HedgeDoc (mode=ro — ποτέ δεν γράφουμε)."""
    if not HEDGEDOC_DB.is_file():
        raise HTTPException(503, "Δεν βρέθηκε η βάση HedgeDoc (hedgedoc.sqlite). "
                                 "Ελέγξτε το school-hedgedoc.service.")
    return connect_ro(HEDGEDOC_DB)


def fix_md_permissions(path: Path) -> None:
    """664/2775 όπως ορίζει το install.sh (root & www-data συνεργάζονται)."""
    try:
        path.chmod(0o664)
        if path.parent != DOCS_DIR:
            path.parent.chmod(0o2775)
    except OSError:
        pass  # αν είμαστε www-data και ιδιοκτήτης root, αρκεί το group-write


def trigger_rebuild() -> None:
    """Άμεσο rebuild (το school-mkdocs.path θα το έκανε έτσι κι αλλιώς)."""
    subprocess.Popen(
        ["/bin/bash", str(BUILD_DOCS_SCRIPT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def backup_file(target: Path) -> str:
    """Αντίγραφο ασφαλείας .bak δίπλα στο αρχείο + ιστορικό στο backups/ (common.fs)."""
    bak = backup_beside(target)                  # πάντα το πιο πρόσφατο .bak
    fix_md_permissions(bak)
    backup_history(target, BACKUP_DIR, relative_to=DOCS_DIR, mirror_tree=True)
    return bak.name


# ---------------------------------------------------------------------------
# Καθαρισμός σύνταξης HedgeDoc → Material for MkDocs
# ---------------------------------------------------------------------------
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
CONTAINER_OPEN_RE = re.compile(r"^(:{3,})\s*(info|success|warning|danger)\s*(.*)$")
CONTAINER_CLOSE_RE = re.compile(r"^:{3,}\s*$")
YOUTUBE_RE = re.compile(r"^\{%youtube\s+([\w-]{11})\s*%\}$")
VIMEO_RE = re.compile(r"^\{%vimeo\s+(\d+)\s*%\}$")
PDF_RE = re.compile(r"^\{%pdf\s+(.+?)\s*%\}$")
TOC_RE = re.compile(r"^\[TOC\]\s*$", re.IGNORECASE)
IMSIZE_RE = re.compile(r"(!\[[^\]]*\]\([^)\s]+)\s+=\d*x\d*\)")
KEYS_RE = re.compile(r"\+\+([a-zA-Z0-9+\- ]{1,24})\+\+")
MARK_RE = re.compile(r"==([^=\n]+)==")
INS_RE = re.compile(r"\+\+([^+\n]{1,200})\+\+")


def strip_yaml_meta(text: str) -> tuple[str, str]:
    """Αφαιρεί το YAML front-matter του HedgeDoc· επιστρέφει (body, title)."""
    title = ""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                meta = lines[1:i]
                for ln in meta:
                    m = re.match(r"^title:\s*(.+)$", ln)
                    if m:
                        title = m.group(1).strip().strip("'\"")
                return "\n".join(lines[i + 1:]).lstrip("\n"), title
    return text, title


def clean_hedgedoc_markdown(text: str) -> tuple[str, str]:
    """Μετατρέπει τη σύνταξη HedgeDoc σε Material for MkDocs.

    * :::info/success/warning/danger → !!! info/success/warning/danger
      (με 4-space indent στο περιεχόμενο — admonition extension)
    * {%youtube id%} / {%vimeo id%} → iframe embed
    * {%pdf url%} → σύνδεσμος (το PDF object δεν υπάρχει στο Material)
    * [TOC] → αφαίρεση (το Material έχει αυτόματο TOC)
    * ![img](url =WxH) → ![img](url){ width="W" } (attr_list)
    * ++πλήκτρο++ → keys syntax, ==mark== & ++ins++ → mark/underline
    * Αγνοεί ΟΛΑ τα fenced code blocks (``` και ~~~) — δεν πειράζει κώδικα!
    Επιστρέφει (καθαρό_κείμενο, τίτλος_από_yaml).
    """
    body, yaml_title = strip_yaml_meta(text.replace("\r\n", "\n").replace("\r", "\n"))
    out: list[str] = []
    fence: str | None = None          # ενεργό fence marker (``` ή ~~~)
    containers: list[str] = []        # στοίβα ανοιχτών ::: containers

    def prefix() -> str:
        return "    " * len(containers)

    for line in body.splitlines():
        stripped = line.strip()
        fm = FENCE_RE.match(stripped)
        if fence is not None:
            out.append(prefix() + line if containers else line)
            if fm and stripped.startswith(fence):
                fence = None          # κλείσιμο ίδιου τύπου fence
            continue
        if fm:
            fence = fm.group(1)[:3]
            out.append(prefix() + line if containers else line)
            continue

        cm = CONTAINER_OPEN_RE.match(stripped)
        if cm:
            label = cm.group(3).strip().strip('"')
            head = f'{prefix()}!!! {cm.group(2)}'
            if label:
                head += f' "{label}"'
            out.append(head)
            containers.append(cm.group(2))
            continue
        if containers and CONTAINER_CLOSE_RE.match(stripped):
            containers.pop()
            out.append("")
            continue

        if TOC_RE.match(stripped):
            continue
        ym = YOUTUBE_RE.match(stripped)
        if ym:
            out.append(prefix() + f'<iframe width="560" height="315" '
                       f'src="https://www.youtube.com/embed/{ym.group(1)}" '
                       f'title="YouTube video" frameborder="0" allowfullscreen></iframe>')
            continue
        vm = VIMEO_RE.match(stripped)
        if vm:
            out.append(prefix() + f'<iframe width="560" height="315" '
                       f'src="https://player.vimeo.com/video/{vm.group(1)}" '
                       f'title="Vimeo video" frameborder="0" allowfullscreen></iframe>')
            continue
        pm = PDF_RE.match(stripped)
        if pm:
            out.append(prefix() + f"[📄 Προβολή PDF]({pm.group(1)})")
            continue

        line = IMSIZE_RE.sub(lambda m: m.group(1) + ')', line)
        line = KEYS_RE.sub(lambda m: "++" + m.group(1).lower() + "++", line)
        line = MARK_RE.sub(r"==\1==", line)       # pymdownx.mark: ίδιο syntax ✓
        line = INS_RE.sub(r"^^\1^^", line)        # ++ins++ → caret (insert)
        out.append(prefix() + line if containers else line)

    return "\n".join(out).strip() + "\n", yaml_title


# ---------------------------------------------------------------------------
# Βοηθητικά: σημειώσεις HedgeDoc & μαθήματα MkDocs
# ---------------------------------------------------------------------------
def note_ref(row: sqlite3.Row) -> str:
    """Το αναγνωριστικό που χρησιμοποιείται στο URL (/md-pad/<ref>)."""
    return row["alias"] or row["id"]


def fmt_ts(value: str | None) -> str:
    """ISO timestamp της Sequelize → ελληνική ημερομηνία/ώρα (τοπική)."""
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return value[:16]


def fetch_note(ref: str) -> dict:
    """Βρίσκει σημείωση με alias ή UUID· επιστρέφει metadata + raw content."""
    ref = ref.strip()
    # Αποδοχή πλήρους URL: http(s)://host/md-pad/<ref>(/download)?(#…)?
    m = re.search(r"/md-pad/([^/?#]+)", ref)
    if m:
        ref = m.group(1)
    ref = ref.rstrip("/")
    if ref.endswith("/download"):
        ref = ref[: -len("/download")]
    if not NOTE_ID_RE.match(ref):
        raise HTTPException(400, "Μη έγκυρο ID/URL σημείωσης.")
    conn = hedgedoc_conn()
    try:
        row = conn.execute(
            "SELECT id, alias, title, content, permission, createdAt, "
            "updatedAt, lastchangeAt FROM Notes WHERE alias = ? OR id = ?",
            (ref, ref),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, f"Η σημείωση '{ref}' δεν βρέθηκε στη βάση HedgeDoc.")
    return {
        "id": row["id"],
        "ref": note_ref(row),
        "title": row["title"] or "Untitled",
        "content": row["content"] or "",
        "permission": row["permission"],
        "updated": fmt_ts(row["lastchangeAt"] or row["updatedAt"]),
        "url": NOTE_URL_BASE + note_ref(row),
    }


def list_lessons() -> list[dict]:
    """Όλα τα .md μαθήματα ανά τάξη (Α'-Γ' Γυμνασίου, Α'-Γ' Λυκείου).

    mathimata/ + _paradeigma/ fallback — common.lessons (single source of truth).
    """
    return list_lessons_grouped(DOCS_DIR)


def validate_lesson_path(lesson: str) -> Path:
    """Επικύρωση διαδρομής .md μέσα στις 6 τάξεις (όχι assets/teachers).

    Δέχεται τη νέα δομή mathimata/<τάξη>/… και την παλιά _paradeigma/<τάξη>/…
    — ίδια paths με αυτά που επιστρέφει η list_lessons() στο UI.
    """
    lesson = lesson.strip().replace("\\", "/").lstrip("/")
    parts = PurePosixPath(lesson).parts
    slug = parts[1] if len(parts) > 1 and parts[0] in ("mathimata", "_paradeigma") else (
        parts[0] if parts else "")
    if (not lesson.endswith(".md") or not parts
            or any(p in ("..", "") for p in parts)
            or slug not in CLASS_SLUGS):
        raise HTTPException(400, "Μη έγκυρη διαδρομή μαθήματος (μόνο φάκελοι τάξεων).")
    target = (DOCS_DIR / lesson).resolve()
    if not str(target).startswith(str(DOCS_DIR.resolve()) + "/"):
        raise HTTPException(400, "Μη έγκυρη διαδρομή μαθήματος.")
    return target


def add_to_nav(rel_path: str, title: str) -> bool:
    """Προσθέτει το νέο μάθημα στο nav: του mkdocs.yml κάτω από την τάξη του.

    Text-based εισαγωγή (όχι yaml round-trip) ώστε να διατηρούνται σχόλια,
    !!python/name tags και η μορφοποίηση του αρχείου ανέπαφα.
    """
    parts = PurePosixPath(rel_path).parts
    slug = parts[1] if parts[0] == "_paradeigma" else parts[0]
    label = CLASS_LABELS[slug]
    text = MKDOCS_YML.read_text(encoding="utf-8")
    if rel_path in text:
        return False                              # ήδη υπάρχει στο nav
    lines = text.splitlines()
    # Βρίσκουμε τη γραμμή "- <Τάξη>:" μέσα στο nav (6 spaces indent)
    class_idx = None
    in_nav = False
    for i, ln in enumerate(lines):
        if re.match(r"^nav:\s*$", ln):
            in_nav = True
            continue
        if in_nav and re.match(r"^\S", ln):       # τέλος του nav block
            break
        if in_nav and ln.strip() == f"- {label}:":
            class_idx = i
            break
    if class_idx is None:
        return False
    # Τελευταία γραμμή της ενότητας τάξης (indent > 6, πριν την επόμενη "- Χ:" 6-space ή λιγότερο)
    insert_at = class_idx + 1
    for j in range(class_idx + 1, len(lines)):
        ln = lines[j]
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= 6:
            break
        insert_at = j + 1
    safe_title = title.replace('"', "'")
    lines.insert(insert_at, f'          - "{safe_title}": {rel_path}')
    # Backup του mkdocs.yml πριν την αλλαγή (δίπλα + ιστορικό στο backups/)
    shutil.copy2(MKDOCS_YML, MKDOCS_YML.with_name("mkdocs.yml.bak"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MKDOCS_YML, BACKUP_DIR / f"mkdocs.{stamp}.yml.bak")
    MKDOCS_YML.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def demote_headings(text: str) -> str:
    """Σε append: # → ##, ## → ### κ.λπ. ώστε το μάθημα να κρατά ένα H1.

    Μέσα σε fenced code blocks οι γραμμές # μένουν ανέπαφες.
    """
    out = []
    fence = None
    for line in text.splitlines():
        stripped = line.strip()
        fm = FENCE_RE.match(stripped)
        if fence is not None:
            out.append(line)
            if fm and stripped.startswith(fence):
                fence = None
            continue
        if fm:
            fence = fm.group(1)[:3]
            out.append(line)
            continue
        if re.match(r"^#{1,5} ", line):
            line = "#" + line
        out.append(line)
    return "\n".join(out)


def wrap_collapsible(text: str, heading: str) -> str:
    """Τυλίγει το περιεχόμενο σε ??? info "…" (pymdownx.details)."""
    indented = "\n".join(("    " + ln) if ln.strip() else "" for ln in text.splitlines())
    safe = heading.replace('"', "'")
    return f'??? info "{safe}"\n{indented}\n'


# ---------------------------------------------------------------------------
# Σελίδες & health
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def publisher_page(request: Request):
    return templates.TemplateResponse(
        request,
        "publisher.html",
        {
            "logged_in": token_valid(request.cookies.get(COOKIE_NAME)),
            "classes": CLASS_GROUPS,
            "template_alias": TEMPLATE_NOTE_ALIAS,
            "note_url_base": NOTE_URL_BASE,
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "school-mdbridge"}


# ---------------------------------------------------------------------------
# API — login/logout
# ---------------------------------------------------------------------------
@app.post("/api/login")
async def login(request: Request, response: Response):
    body = await request.json()
    password = str(body.get("password", ""))
    # encode() ώστε να υποστηρίζονται και μη-ASCII (λανθασμένοι) κωδικοί
    if not hmac.compare_digest(password.encode(), TEACHER_CODE.encode()):
        raise HTTPException(401, "Λανθασμένος κωδικός καθηγητή.")
    response.set_cookie(
        COOKIE_NAME, make_token(),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/",
    )
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


# ---------------------------------------------------------------------------
# API — σημειώσεις HedgeDoc & μαθήματα
# ---------------------------------------------------------------------------
@app.get("/api/notes")
def api_notes(request: Request):
    """Ενεργές σημειώσεις από τη βάση hedgedoc.sqlite (τίτλος, ID, τροποποίηση)."""
    require_teacher(request)
    conn = hedgedoc_conn()
    try:
        rows = conn.execute(
            "SELECT id, alias, title, permission, createdAt, updatedAt, lastchangeAt, "
            "length(content) AS size FROM Notes "
            "ORDER BY COALESCE(lastchangeAt, updatedAt) DESC LIMIT 500"
        ).fetchall()
    finally:
        conn.close()
    notes = [{
        "id": r["id"],
        "ref": note_ref(r),
        "title": r["title"] or "Untitled",
        "permission": r["permission"],
        "updated": fmt_ts(r["lastchangeAt"] or r["updatedAt"]),
        "size": r["size"] or 0,
        "url": NOTE_URL_BASE + note_ref(r),
        "is_template": r["alias"] == TEMPLATE_NOTE_ALIAS,
    } for r in rows]
    return {"notes": notes, "template_alias": TEMPLATE_NOTE_ALIAS}


@app.get("/api/note")
def api_note(request: Request, ref: str = ""):
    """Raw markdown σημείωσης (όπως το /md-pad/<id>/download) + καθαρισμένη εκδοχή."""
    require_teacher(request)
    note = fetch_note(ref)
    cleaned, yaml_title = clean_hedgedoc_markdown(note["content"])
    return {
        "note": {k: v for k, v in note.items() if k != "content"},
        "raw": note["content"],
        "cleaned": cleaned,
        "suggested_title": yaml_title or note["title"],
    }


@app.get("/api/lessons")
def api_lessons(request: Request):
    require_teacher(request)
    return {"groups": list_lessons(), "classes": CLASS_GROUPS}


# ---------------------------------------------------------------------------
# API — δημοσίευση (append ή νέο μάθημα)
# ---------------------------------------------------------------------------
def build_section(note: dict, mode: str, heading: str) -> str:
    """Καθαρισμένο περιεχόμενο σημείωσης έτοιμο για εισαγωγή σε μάθημα."""
    cleaned, _ = clean_hedgedoc_markdown(note["content"])
    if mode == "collapsible":
        block = wrap_collapsible(cleaned, heading or "Συνεργατική Σημείωση Τάξης")
        return f"\n\n## 📝 {heading or 'Συνεργατική Σημείωση Τάξης'}\n\n{block}"
    # plain: επικεφαλίδα ενότητας + demoted headings της σημείωσης
    body = demote_headings(cleaned)
    stamp = datetime.now().strftime("%d/%m/%Y")
    return (f"\n\n## 📝 {heading or note['title']}\n\n"
            f"*Συνεργατική σημείωση τάξης από το [HedgeDoc]({note['url']}) — {stamp}*\n\n"
            f"{body}\n")


@app.post("/api/publish-append")
async def publish_append(request: Request):
    """Επιλογή Α — προσθήκη στο τέλος υπάρχοντος μαθήματος (.bak backup πρώτα)."""
    require_teacher(request)
    body = await request.json()
    note = fetch_note(str(body.get("ref", "")))
    target = validate_lesson_path(str(body.get("lesson", "")))
    if not target.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    mode = str(body.get("mode", "plain"))
    if mode not in ("plain", "collapsible"):
        raise HTTPException(400, "Μη έγκυρος τρόπος εισαγωγής.")
    heading = str(body.get("heading", "")).strip()[:120]

    section = build_section(note, mode, heading)
    bak_name = backup_file(target)               # ΠΑΝΤΑ backup πριν την εγγραφή
    text = target.read_text(encoding="utf-8")
    target.write_text(text.rstrip() + section, encoding="utf-8")
    fix_md_permissions(target)
    trigger_rebuild()
    rel = target.relative_to(DOCS_DIR).as_posix()
    # use_directory_urls: index.md → /docs/<dir>/, αλλιώς /docs/<dir>/<stem>/
    url = "/docs/" + (rel[:-8] if rel.endswith("/index.md") else rel[:-3] + "/")
    return {"ok": True, "lesson": rel, "backup": bak_name, "url": url}


@app.post("/api/publish-new")
async def publish_new(request: Request):
    """Επιλογή Β — νέο μάθημα σε φάκελο τάξης + αυτόματη προσθήκη στο nav."""
    require_teacher(request)
    body = await request.json()
    note = fetch_note(str(body.get("ref", "")))
    slug = str(body.get("class_slug", "")).strip()
    if slug not in CLASS_SLUGS:
        raise HTTPException(400, "Επιλέξτε έγκυρη τάξη.")
    filename = str(body.get("filename", "")).strip().lower()
    filename = filename[:-3] if filename.endswith(".md") else filename
    if not FILENAME_RE.match(filename) or len(filename) > 60:
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου (πεζά λατινικά, ψηφία, παύλες — greeklish).")
    title = str(body.get("title", "")).strip()[:120]
    if not title:
        _, yaml_title = clean_hedgedoc_markdown(note["content"])
        title = yaml_title or note["title"]
    mode = str(body.get("mode", "plain"))
    if mode not in ("plain", "collapsible"):
        raise HTTPException(400, "Μη έγκυρος τρόπος εισαγωγής.")

    # Νέα δομή: οι δημοσιεύσεις πάνε στο _paradeigma/<τάξη>/ (παλιό υλικό/σημειώσεις).
    # Τα δομημένα ημερήσια μαθήματα δημιουργούνται από το /lesson-wizard/.
    rel = f"_paradeigma/{slug}/{filename}.md"
    target = DOCS_DIR / rel
    if target.exists():
        raise HTTPException(409, f"Το αρχείο {rel} υπάρχει ήδη — δώστε άλλο όνομα ή χρησιμοποιήστε την Επιλογή Α.")

    cleaned, _ = clean_hedgedoc_markdown(note["content"])
    stamp = datetime.now().strftime("%d/%m/%Y")
    header = (f"# {title}\n\n"
              f"*Δημιουργήθηκε από συνεργατική σημείωση [HedgeDoc]({note['url']}) — {stamp}*\n\n")
    content = header + (wrap_collapsible(cleaned, "Συνεργατική Σημείωση Τάξης")
                        if mode == "collapsible" else cleaned)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    fix_md_permissions(target)
    nav_added = add_to_nav(rel, title)
    trigger_rebuild()
    return {"ok": True, "lesson": rel, "nav_added": nav_added,
            "url": f"/docs/_paradeigma/{slug}/{filename}/"}
