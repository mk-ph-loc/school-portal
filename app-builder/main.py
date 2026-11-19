"""
Δημιουργός Custom Εφαρμογών (App Builder Wizard) — Ψηφιακή Πύλη Σχολείου

Περιβάλλον καθηγητή (κωδικός teacher2026, HMAC-signed cookie όπως στο /exams/)
που αυτοματοποιεί ΟΛΑ τα βήματα του CUSTOM-APPS-GUIDE.md μέσα από τον browser:
  * δημιουργία standalone HTML/CSS/JS εφαρμογής στο custom-apps/<id>/
    (upload .zip ή πολλαπλών αρχείων, ή Quick Paste κώδικα πάνω στο _template),
  * αυτόματος έλεγχος & διόρθωση απόλυτων διαδρομών που σπάνε σε subpath,
  * σωστά δικαιώματα (755/644) + εκτέλεση build-apps-manifest.py,
  * λίστα/διαγραφή εφαρμογών, προεπισκόπηση στο /apps/<id>/,
  * γεννήτρια snippet ενσωμάτωσης σε μάθημα MkDocs (iframe) με αντιγραφή
    ή άμεση εισαγωγή στο τέλος υπάρχοντος .md (auto-rebuild μέσω mkdocs.path).

Τρέχει στο 127.0.0.1:8008 πίσω από τον Nginx στο /app-builder/. Χωρίς Docker.
"""
from __future__ import annotations

import hmac
import html as html_mod
import io
import logging
import json
import re
import secrets
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from common.auth import TeacherAuth, TEACHER_CODE, COOKIE_MAX_AGE
from common.lessons import list_lessons_flat

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent
APPS_DIR = PORTAL_DIR / "custom-apps"
TEMPLATE_DIR = APPS_DIR / "_template"
MANIFEST_SCRIPT = PORTAL_DIR / "scripts" / "build-apps-manifest.py"
DOCS_DIR = PORTAL_DIR / "mkdocs-site" / "docs"
BUILD_DOCS_SCRIPT = PORTAL_DIR / "scripts" / "build-docs.sh"

COOKIE_NAME = "appbuilder_teacher"

# stderr → journalctl (systemd)
logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("appbuilder")

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VALID_ACCESS = {"all", "teachers"}
MAX_FILES = 300                      # όριο αρχείων ανά εφαρμογή
MAX_TOTAL_BYTES = 50 * 1024 * 1024   # 50 MB (ίδιο με το client_max_body_size)
EMBED_MARKER = "custom-app-embed"

CATEGORIES = [
    "Γενικά",
    "Α' Γυμνασίου / Πληροφορική",
    "Β' Γυμνασίου / Πληροφορική",
    "Γ' Γυμνασίου / Πληροφορική",
    "Α' Λυκείου / Πληροφορική",
    "Β' Λυκείου / Πληροφορική",
    "Γ' Λυκείου / Πληροφορική",
]
ICONS = ["🚀", "🧮", "⚡", "🧪", "🎮", "💻", "📐", "🌍", "🔢", "🧩", "🎨", "📊"]

app = FastAPI(
    title="Δημιουργός Custom Εφαρμογών (App Builder Wizard)",
    description="Δημιουργία standalone εφαρμογών & ενσωμάτωση σε μαθήματα MkDocs",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/app-builder) ορίζεται στο uvicorn μέσω του systemd
# unit, ώστε τα url_for() των templates να παράγουν σωστό πρόθεμα πίσω από
# τον Nginx.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC) — common.auth
# ---------------------------------------------------------------------------
auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
make_token = auth.make_token
token_valid = auth.token_valid
require_teacher = auth.require_teacher


# ---------------------------------------------------------------------------
# Βοηθητικά: manifest, δικαιώματα, επικύρωση id
# ---------------------------------------------------------------------------
def rebuild_manifest() -> None:
    """Εκτελεί το build-apps-manifest.py ώστε το Dashboard να ενημερωθεί άμεσα."""
    proc = subprocess.run(
        [sys.executable, str(MANIFEST_SCRIPT)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise HTTPException(500, "Αποτυχία ενημέρωσης manifest: " + (proc.stderr or proc.stdout).strip())


def fix_permissions(app_dir: Path) -> None:
    """Φάκελοι 755, αρχεία 644 — όπως ορίζει ο CUSTOM-APPS-GUIDE.md."""
    for p in sorted(app_dir.rglob("*"), reverse=True):
        p.chmod(0o755 if p.is_dir() else 0o644)
    app_dir.chmod(0o755)


def validate_id(app_id: str) -> str:
    app_id = (app_id or "").strip()
    if app_id == "_template" or app_id.startswith(("_", ".")):
        raise HTTPException(400, "Το id δεν μπορεί να ξεκινά με '_' ή '.' (δεσμευμένα ονόματα, π.χ. _template).")
    if not ID_RE.match(app_id):
        raise HTTPException(400, "Το id επιτρέπεται να περιέχει μόνο πεζά λατινικά, ψηφία και παύλες (π.χ. my-app).")
    return app_id


def read_app_meta(app_dir: Path) -> dict:
    try:
        meta = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}
    return {
        "id": app_dir.name,
        "title": str(meta.get("title", app_dir.name)),
        "description": str(meta.get("description", "")),
        "category": str(meta.get("category", "Γενικά")),
        "icon": str(meta.get("icon", "🚀")),
        "access": str(meta.get("access", "all")),
        "url": f"/apps/{app_dir.name}/",
    }


# ---------------------------------------------------------------------------
# Έλεγχος & αυτόματη διόρθωση σχετικών διαδρομών (subpath /apps/<id>/)
# ---------------------------------------------------------------------------
# Κοινόχρηστα assets της πύλης που ΕΠΙΤΡΕΠΕΤΑΙ να μένουν απόλυτα ("/assets/…").
PORTAL_ASSET_PREFIXES = ("/assets/",)
# Attributes που δείχνουν σε τοπικούς πόρους της εφαρμογής.
PATH_ATTR_RE = re.compile(
    r"""(?P<attr>\b(?:href|src|poster)\s*=\s*)(?P<q>["'])(?P<path>/[^"'>]*)(?P=q)""",
    re.IGNORECASE,
)
CSS_URL_RE = re.compile(r"""url\(\s*(?P<q>["']?)(?P<path>/[^)"']+)(?P=q)\s*\)""", re.IGNORECASE)


def _is_external_or_special(path: str) -> bool:
    return path.startswith("//") or path.startswith(PORTAL_ASSET_PREFIXES)


def fix_index_paths(html_text: str) -> tuple[str, list[str]]:
    """Μετατρέπει href="/style.css" → href="./style.css" κ.λπ. στο index.html.

    Εξαιρούνται τα κοινόχρηστα /assets/… της πύλης και τα protocol-relative URLs.
    Επιστρέφει (διορθωμένο HTML, λίστα αλλαγών για προειδοποίηση στον χρήστη).
    """
    changes: list[str] = []

    def repl(m: re.Match) -> str:
        path = m.group("path")
        if _is_external_or_special(path):
            return m.group(0)
        new_path = "." + path
        changes.append(f'{m.group("attr").strip()}"{path}" → "./{path.lstrip("/")}"')
        return f'{m.group("attr")}{m.group("q")}{new_path}{m.group("q")}'

    fixed = PATH_ATTR_RE.sub(repl, html_text)
    # Και url(/…) μέσα σε inline <style>
    def css_repl(m: re.Match) -> str:
        path = m.group("path")
        if _is_external_or_special(path):
            return m.group(0)
        changes.append(f'url({path}) → url(.{path})')
        return f"url({m.group('q')}.{path}{m.group('q')})"

    fixed = CSS_URL_RE.sub(css_repl, fixed)
    return fixed, changes


def scan_other_files(app_dir: Path) -> list[str]:
    """Εντοπίζει (χωρίς αλλαγή) ύποπτες απόλυτες διαδρομές σε .css/.js αρχεία."""
    warnings: list[str] = []
    for p in app_dir.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".css", ".js"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = p.relative_to(app_dir)
        for m in CSS_URL_RE.finditer(text):
            if not _is_external_or_special(m.group("path")):
                warnings.append(f"{rel}: url({m.group('path')}) — απόλυτη διαδρομή, ίσως χρειαστεί σχετική")
        for m in re.finditer(r"""["'](?P<path>/[a-zA-Z0-9_./-]+\.(?:css|js|png|jpe?g|gif|svg|webp|json|woff2?))["']""", text):
            if not _is_external_or_special(m.group("path")):
                warnings.append(f"{rel}: '{m.group('path')}' — απόλυτη διαδρομή, ίσως χρειαστεί './…'")
    return warnings[:20]  # όριο ώστε η απάντηση να παραμένει ευανάγνωστη


# ---------------------------------------------------------------------------
# Ασφαλής αποσυμπίεση ZIP (zip-slip protection + αφαίρεση ενιαίου root φακέλου)
# ---------------------------------------------------------------------------
def safe_extract_zip(data: bytes, dest: Path) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Το αρχείο δεν είναι έγκυρο ZIP.")

    members = [i for i in zf.infolist() if not i.is_dir()]
    if not members:
        raise HTTPException(400, "Το ZIP είναι κενό.")
    if len(members) > MAX_FILES:
        raise HTTPException(400, f"Πάρα πολλά αρχεία στο ZIP (> {MAX_FILES}).")
    total = sum(i.file_size for i in members)
    if total > MAX_TOTAL_BYTES:
        raise HTTPException(400, "Το αποσυμπιεσμένο περιεχόμενο ξεπερνά τα 50 MB.")

    names: list[str] = []
    for info in members:
        name = info.filename.replace("\\", "/")
        parts = PurePosixPath(name).parts
        if any(p in ("..", "") for p in parts) or name.startswith("/"):
            raise HTTPException(400, f"Μη ασφαλής διαδρομή μέσα στο ZIP: {info.filename}")
        if "__MACOSX" in parts or parts[-1].startswith("."):
            continue  # σκουπίδια macOS / κρυφά αρχεία
        # symlinks: απόρριψη (external_attr >> 16 & 0xF000 == 0xA000)
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise HTTPException(400, f"Τα symlinks δεν επιτρέπονται: {info.filename}")
        names.append(name)

    if not names:
        raise HTTPException(400, "Το ZIP δεν περιέχει χρησιμοποιήσιμα αρχεία.")

    # Αν ΟΛΑ τα αρχεία μοιράζονται έναν ενιαίο root φάκελο, τον αφαιρούμε
    # ώστε το index.html να βρεθεί απευθείας στη ρίζα του custom-apps/<id>/.
    strip_prefix = ""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        strip_prefix = next(iter(tops)) + "/"

    for info in members:
        name = info.filename.replace("\\", "/")
        if name not in names:
            continue
        rel = name[len(strip_prefix):] if strip_prefix else name
        target = (dest / rel).resolve()
        if not str(target).startswith(str(dest.resolve()) + "/"):
            raise HTTPException(400, f"Μη ασφαλής διαδρομή μέσα στο ZIP: {info.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


# ---------------------------------------------------------------------------
# Quick Paste: κατασκευή index.html από το _template + περιεχόμενο <main>/JS/CSS
# ---------------------------------------------------------------------------
def build_from_template(title: str, icon: str, main_html: str, js_code: str, css_code: str) -> str:
    """Χρησιμοποιεί το _template/index.html όταν δίνεται μόνο <main> περιεχόμενο & JS."""
    tpl = (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")

    safe_title = html_mod.escape(title, quote=False)
    tpl = tpl.replace("Τίτλος Εφαρμογής", safe_title)
    tpl = tpl.replace("🚀", icon if icon else "🚀", 1)  # μόνο το εικονίδιο της μπάρας/titλου

    # Αντικατάσταση του placeholder <main> του προτύπου με το περιεχόμενο του χρήστη
    main_block = f'<main class="flex-1 w-full max-w-5xl mx-auto px-4 py-8 space-y-6">\n{main_html.strip()}\n</main>'
    tpl = re.sub(r"<main\b.*?</main>", lambda _m: main_block, tpl, count=1, flags=re.DOTALL)

    # Inline CSS στο <head> (πριν το </head>)
    if css_code.strip():
        tpl = tpl.replace("</head>", f"<style>\n{css_code.strip()}\n</style>\n</head>", 1)

    # JS: εξωτερικό ./app.js (σωστή πρακτική σχετικών διαδρομών) αντί για inline
    if js_code.strip():
        tpl = tpl.replace("</body>", '<script src="./app.js"></script>\n</body>', 1)

    # Αφαίρεση του σχολίου οδηγιών του προτύπου (δεν χρειάζεται πλέον)
    tpl = re.sub(r"<!-- Προαιρετικά δικά σου αρχεία.*?-->\n?", "", tpl, flags=re.DOTALL)
    return tpl


def embed_snippet(app_id: str, title: str, icon: str) -> str:
    """Έτοιμο Markdown/HTML block ενσωμάτωσης σε μάθημα MkDocs (iframe πλήρους πλάτους)."""
    t = html_mod.escape(f"{icon} {title}".strip(), quote=False)
    return (
        '<div class="custom-app-embed" style="margin: 1.5rem 0; border-radius: 12px; overflow: hidden; '
        'border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);">\n'
        '  <div style="background: #1e293b; color: white; padding: 0.5rem 1rem; display: flex; '
        'justify-content: space-between; align-items: center; font-size: 0.875rem;">\n'
        f'    <span>{t}</span>\n'
        f'    <a href="/apps/{app_id}/" target="_blank" style="color: #38bdf8; text-decoration: none;">Άνοιγμα σε πλήρη οθόνη ↗</a>\n'
        '  </div>\n'
        f'  <iframe src="/apps/{app_id}/" width="100%" height="600" style="border: none; display: block;" loading="lazy"></iframe>\n'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Σελίδα Wizard (HTML)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def wizard_page(request: Request):
    return templates.TemplateResponse(
        request,
        "wizard.html",
        {
            "logged_in": token_valid(request.cookies.get(COOKIE_NAME)),
            "categories": CATEGORIES,
            "icons": ICONS,
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "school-appbuilder"}


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
# API — δημιουργία εφαρμογής (multipart: μεταδεδομένα + αρχεία ή Quick Paste)
# ---------------------------------------------------------------------------
@app.post("/api/create")
async def create_app(
    request: Request,
    id: str = Form(...),
    title: str = Form(""),   # επικυρώνεται παρακάτω με ελληνικό μήνυμα (όχι 422)
    description: str = Form(""),
    category: str = Form("Γενικά"),
    icon: str = Form("🚀"),
    access: str = Form("all"),
    replace: str = Form("false"),
    mode: str = Form("upload"),               # upload | paste
    paste_html: str = Form(""),               # πλήρες HTML ή μόνο <main> περιεχόμενο
    paste_css: str = Form(""),
    paste_js: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    require_teacher(request)

    app_id = validate_id(id)
    title = title.strip()
    if not title:
        raise HTTPException(400, "Ο τίτλος είναι υποχρεωτικός.")
    if len(title) > 200:
        raise HTTPException(400, "Ο τίτλος είναι πολύ μεγάλος (> 200 χαρακτήρες).")
    access = access.strip()
    if access not in VALID_ACCESS:
        raise HTTPException(400, "Το access πρέπει να είναι 'all' ή 'teachers'.")
    category = category.strip() or "Γενικά"
    icon = icon.strip() or "🚀"
    do_replace = replace.lower() in ("1", "true", "on", "yes")

    dest = APPS_DIR / app_id
    if dest.exists() and not do_replace:
        raise HTTPException(409, f"Η εφαρμογή '{app_id}' υπάρχει ήδη. Τσέκαρε την «Αντικατάσταση υπάρχουσας» για αντικατάσταση.")
    if dest.is_symlink():
        raise HTTPException(400, "Μη επιτρεπτός φάκελος προορισμού (symlink).")

    # --- Κατασκευή περιεχομένου σε προσωρινό φάκελο (ατομική αντικατάσταση) ---
    staging = APPS_DIR / f".staging-{app_id}-{secrets.token_hex(4)}"
    staging.mkdir(parents=True)
    warnings: list[str] = []
    try:
        if mode == "paste":
            html_text = paste_html.strip()
            if not html_text and not paste_js.strip():
                raise HTTPException(400, "Συμπλήρωσε τουλάχιστον HTML (ή περιεχόμενο <main>) ή JavaScript.")
            if re.search(r"<html\b", html_text, re.IGNORECASE):
                index_html = paste_html  # πλήρες έγγραφο όπως το έδωσε ο χρήστης
            else:
                index_html = build_from_template(title, icon, paste_html, paste_js, paste_css)
            if paste_js.strip():
                (staging / "app.js").write_text(paste_js.strip() + "\n", encoding="utf-8")
                if "./app.js" not in index_html:
                    # πλήρες HTML χωρίς αναφορά στο app.js → προσθήκη πριν το </body>
                    if "</body>" in index_html:
                        index_html = index_html.replace("</body>", '<script src="./app.js"></script>\n</body>', 1)
                    else:
                        index_html += '\n<script src="./app.js"></script>\n'
        elif mode == "upload":
            real_files = [f for f in files if f and f.filename]
            if not real_files:
                raise HTTPException(400, "Δεν ανέβηκε κανένα αρχείο.")
            if len(real_files) == 1 and real_files[0].filename.lower().endswith(".zip"):
                data = await real_files[0].read()
                if len(data) > MAX_TOTAL_BYTES:
                    raise HTTPException(400, "Το ZIP ξεπερνά τα 50 MB.")
                safe_extract_zip(data, staging)
            else:
                total = 0
                for f in real_files[:MAX_FILES]:
                    # webkitdirectory uploads μπορεί να φέρουν σχετικό μονοπάτι
                    name = (f.filename or "").replace("\\", "/").lstrip("/")
                    parts = PurePosixPath(name).parts
                    if not parts or any(p in ("..", "") for p in parts) or parts[-1].startswith("."):
                        continue
                    target = (staging / name).resolve()
                    if not str(target).startswith(str(staging.resolve()) + "/"):
                        raise HTTPException(400, f"Μη ασφαλές όνομα αρχείου: {f.filename}")
                    data = await f.read()
                    total += len(data)
                    if total > MAX_TOTAL_BYTES:
                        raise HTTPException(400, "Τα αρχεία ξεπερνούν συνολικά τα 50 MB.")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            index_file = staging / "index.html"
            if not index_file.is_file():
                raise HTTPException(400, "Δεν βρέθηκε index.html στη ρίζα των αρχείων (ούτε μετά την αφαίρεση ενιαίου root φακέλου του ZIP).")
            index_html = index_file.read_text(encoding="utf-8", errors="replace")
        else:
            raise HTTPException(400, "Άγνωστος τρόπος εισαγωγής (mode).")

        # --- Αυτόματος έλεγχος & διόρθωση απόλυτων διαδρομών στο index.html ---
        index_html, changes = fix_index_paths(index_html)
        if changes:
            warnings.append("Διορθώθηκαν αυτόματα απόλυτες διαδρομές στο index.html: " + "; ".join(changes[:10]))
        (staging / "index.html").write_text(index_html, encoding="utf-8")

        # --- app.json (τα μεταδεδομένα της φόρμας υπερισχύουν τυχόν δικού του χρήστη) ---
        meta = {
            "id": app_id, "title": title, "description": description.strip(),
            "category": category, "icon": icon, "access": access,
        }
        (staging / "app.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        warnings.extend(scan_other_files(staging))
        fix_permissions(staging)

        # --- Ατομική αντικατάσταση & ενημέρωση manifest ---
        backup = None
        if dest.exists():
            backup = APPS_DIR / f".backup-{app_id}-{secrets.token_hex(4)}"
            dest.rename(backup)
        try:
            staging.rename(dest)
        except OSError:
            if backup:
                backup.rename(dest)
            raise
        if backup:
            shutil.rmtree(backup, ignore_errors=True)
        rebuild_manifest()
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "ok": True,
        "app": read_app_meta(dest),
        "warnings": warnings,
        "embed": embed_snippet(app_id, title, icon),
    }


# ---------------------------------------------------------------------------
# API — λίστα & διαγραφή εφαρμογών
# ---------------------------------------------------------------------------
@app.get("/api/list")
def list_apps(request: Request):
    require_teacher(request)
    apps = []
    for d in sorted(APPS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        meta = read_app_meta(d)
        meta["files"] = sum(1 for p in d.rglob("*") if p.is_file())
        meta["embed"] = embed_snippet(meta["id"], meta["title"], meta["icon"])
        apps.append(meta)
    return {"apps": apps}


@app.delete("/api/delete/{app_id}")
def delete_app(app_id: str, request: Request):
    require_teacher(request)
    app_id = validate_id(app_id)
    dest = APPS_DIR / app_id
    if not dest.is_dir() or dest.is_symlink():
        raise HTTPException(404, f"Η εφαρμογή '{app_id}' δεν βρέθηκε.")
    shutil.rmtree(dest)
    rebuild_manifest()
    return {"ok": True, "deleted": app_id}


# ---------------------------------------------------------------------------
# API — MkDocs Embed Generator (snippet + άμεση εισαγωγή σε μάθημα)
# ---------------------------------------------------------------------------
def list_lessons() -> list[dict]:
    """Όλα τα .md μαθήματα του mkdocs-site/docs/ (εκτός assets/teachers).

    common.lessons.list_lessons_flat — single source of truth με bridge/h5p.
    """
    return list_lessons_flat(DOCS_DIR)


@app.get("/api/lessons")
def api_lessons(request: Request):
    require_teacher(request)
    return {"lessons": list_lessons()}


@app.get("/api/embed/{app_id}")
def api_embed(app_id: str, request: Request):
    require_teacher(request)
    app_id = validate_id(app_id)
    dest = APPS_DIR / app_id
    if not dest.is_dir():
        raise HTTPException(404, f"Η εφαρμογή '{app_id}' δεν βρέθηκε.")
    meta = read_app_meta(dest)
    return {"embed": embed_snippet(app_id, meta["title"], meta["icon"]), "app": meta}


@app.post("/api/embed-into-lesson")
async def embed_into_lesson(request: Request):
    """Προσθέτει το embed block στο ΤΕΛΟΣ υπάρχοντος μαθήματος .md (1 κλικ).

    Το school-mkdocs.path (inotify) αναλαμβάνει αυτόματα την ανακατασκευή
    του static site — δεν χρειάζεται καμία ενέργεια από τον καθηγητή.
    """
    require_teacher(request)
    body = await request.json()
    app_id = validate_id(str(body.get("id", "")))
    lesson = str(body.get("lesson", "")).strip().replace("\\", "/").lstrip("/")

    dest = APPS_DIR / app_id
    if not dest.is_dir():
        raise HTTPException(404, f"Η εφαρμογή '{app_id}' δεν βρέθηκε.")

    parts = PurePosixPath(lesson).parts
    if not lesson.endswith(".md") or not parts or any(p in ("..", "") for p in parts):
        raise HTTPException(400, "Μη έγκυρη διαδρομή μαθήματος.")
    target = (DOCS_DIR / lesson).resolve()
    if not str(target).startswith(str(DOCS_DIR.resolve()) + "/") or not target.is_file():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    rel_parts = target.relative_to(DOCS_DIR.resolve()).parts
    if rel_parts[0] == "assets" or "teachers" in rel_parts:
        raise HTTPException(400, "Δεν επιτρέπεται εισαγωγή σε assets ή στην προστατευμένη περιοχή teachers.")

    meta = read_app_meta(dest)
    snippet = embed_snippet(app_id, meta["title"], meta["icon"])
    text = target.read_text(encoding="utf-8")
    if f'src="/apps/{app_id}/"' in text:
        raise HTTPException(409, "Η εφαρμογή είναι ήδη ενσωματωμένη σε αυτό το μάθημα.")

    heading = f"\n\n## {meta['icon']} {meta['title']}\n\n"
    new_text = text.rstrip() + heading + snippet + "\n"
    target.write_text(new_text, encoding="utf-8")
    # Το inotify path unit θα χτίσει αυτόματα· κάνουμε και άμεσο trigger για σιγουριά
    subprocess.Popen(
        ["/bin/bash", str(BUILD_DOCS_SCRIPT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"ok": True, "lesson": lesson, "url": "/docs/" + lesson[:-3] + "/"}