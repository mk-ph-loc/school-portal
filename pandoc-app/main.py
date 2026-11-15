"""
Visual Pandoc Studio — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

FastAPI εφαρμογή που χρησιμοποιεί το pandoc του συστήματος για μετατροπές
εγγράφων και το WeasyPrint για ελαφριά εξαγωγή PDF με πλήρη υποστήριξη
ελληνικών (χωρίς LaTeX).

Τρέχει στο 127.0.0.1:8002 πίσω από τον Nginx στο /pandoc/.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = DATA_DIR / "templates"          # πρότυπα .docx (reference-doc)
UPLOAD_DIR = DATA_DIR / "uploads"
MKDOCS_ROOT = Path("/opt/school-portal/mkdocs-site")
MKDOCS_DOCS = MKDOCS_ROOT / "docs"
BUILD_SCRIPT = Path("/opt/school-portal/scripts/build-docs.sh")

for _d in (DATA_DIR, TEMPLATES_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)

PANDOC_BIN = shutil.which("pandoc") or "/usr/bin/pandoc"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024      # ευθυγραμμισμένο με client_max_body_size
PANDOC_TIMEOUT = 60                        # δευτερόλεπτα

CLASSES = [
    {"slug": "gymnasio-a", "label": "Α' Γυμνασίου"},
    {"slug": "gymnasio-b", "label": "Β' Γυμνασίου"},
    {"slug": "gymnasio-g", "label": "Γ' Γυμνασίου"},
    {"slug": "lykeio-a", "label": "Α' Λυκείου"},
    {"slug": "lykeio-b", "label": "Β' Λυκείου"},
    {"slug": "lykeio-g", "label": "Γ' Λυκείου"},
    {"slug": "teachers", "label": "🔐 Περιοχή Καθηγητών"},
]
CLASS_SLUGS = {c["slug"] for c in CLASSES}

app = FastAPI(
    title="Visual Pandoc Studio",
    description="Μετατροπή εγγράφων με Pandoc & WeasyPrint",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/pandoc) ορίζεται στο uvicorn μέσω του systemd unit,
# ώστε τα url_for() των templates να παράγουν σωστά πρόθεμα πίσω από τον Nginx.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Βοηθητικές συναρτήσεις
# ---------------------------------------------------------------------------
def slugify(text: str) -> str:
    """Μετατρέπει ελληνικό/λατινικό τίτλο σε ασφαλές όνομα αρχείου."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    greek_map = {
        "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
        "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
        "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
        "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
    }
    text = "".join(greek_map.get(ch, ch) for ch in text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or "mathima"


def safe_template_name(name: str) -> Path:
    """Επιστρέφει ασφαλή διαδρομή προτύπου .docx (αποτροπή path traversal)."""
    base = Path(name).name
    if not base.endswith(".docx"):
        raise HTTPException(400, "Επιτρέπονται μόνο αρχεία .docx")
    target = (TEMPLATES_DIR / base).resolve()
    if TEMPLATES_DIR.resolve() not in target.parents:
        raise HTTPException(400, "Μη έγκυρο όνομα αρχείου")
    return target


def run_pandoc(args: list[str], stdin_data: bytes | None = None) -> bytes:
    """Εκτελεί το pandoc με λίστα ορισμάτων (ΟΧΙ shell) και επιστρέφει stdout."""
    if not Path(PANDOC_BIN).exists():
        raise HTTPException(500, "Το pandoc δεν είναι εγκατεστημένο στο σύστημα.")
    try:
        proc = subprocess.run(
            [PANDOC_BIN, *args],
            input=stdin_data,
            capture_output=True,
            timeout=PANDOC_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f"Λήψη χρόνου μετατροπής ({PANDOC_TIMEOUT}s).")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise HTTPException(400, f"Σφάλμα pandoc: {err[:800]}")
    return proc.stdout


def pandoc_version() -> str:
    try:
        out = subprocess.run(
            [PANDOC_BIN, "--version"], capture_output=True, timeout=10, check=False
        )
        return out.stdout.decode("utf-8", errors="replace").splitlines()[0]
    except Exception:
        return "μη διαθέσιμο"
# ---------------------------------------------------------------------------
# Visual Flags Explorer — κατάλογος επιλογών του pandoc
# ---------------------------------------------------------------------------
FLAGS_CATALOG: list[dict[str, Any]] = [
    {
        "group": "Δομή εγγράφου",
        "flags": [
            {"id": "standalone", "flag": "--standalone", "type": "bool", "default": True,
             "label": "Πλήρες έγγραφο (--standalone)",
             "help": "Παράγει ολοκληρωμένο έγγραφο με κεφαλίδες, όχι μόνο θραύσμα."},
            {"id": "toc", "flag": "--toc", "type": "bool", "default": False,
             "label": "Πίνακας περιεχομένων (--toc)",
             "help": "Δημιουργεί αυτόματο πίνακα περιεχομένων από τις επικεφαλίδες."},
            {"id": "toc_depth", "flag": "--toc-depth", "type": "int", "default": 3,
             "min": 1, "max": 6, "label": "Βάθος πίνακα περιεχομένων",
             "help": "Πόσα επίπεδα επικεφαλίδων εμφανίζονται στον πίνακα."},
            {"id": "number_sections", "flag": "--number-sections", "type": "bool", "default": False,
             "label": "Αρίθμηση ενοτήτων (--number-sections)",
             "help": "Αριθμεί αυτόματα τις επικεφαλίδες (1, 1.1, 1.2…)."},
        ],
    },
    {
        "group": "Μορφοποίηση",
        "flags": [
            {"id": "shift_heading", "flag": "--shift-heading-level-by", "type": "int",
             "default": 0, "min": -3, "max": 3, "label": "Μετατόπιση επιπέδου επικεφαλίδων",
             "help": "Ανεβάζει ή κατεβάζει το επίπεδο όλων των επικεφαλίδων."},
            {"id": "columns", "flag": "--columns", "type": "int", "default": 72,
             "min": 20, "max": 200, "label": "Πλάτος στηλών (χαρακτήρες)",
             "help": "Καθορίζει το πλάτος αναδίπλωσης για έξοδο απλού κειμένου."},
            {"id": "wrap", "flag": "--wrap", "type": "select", "default": "auto",
             "options": ["auto", "none", "preserve"], "label": "Αναδίπλωση κειμένου (--wrap)",
             "help": "auto: αυτόματη, none: χωρίς αναδίπλωση, preserve: διατήρηση αρχικής."},
            {"id": "highlight", "flag": "--highlight-style", "type": "select",
             "default": "pygments",
             "options": ["pygments", "tango", "espresso", "zenburn", "kate", "monochrome", "breezedark"],
             "label": "Στυλ χρωματισμού κώδικα",
             "help": "Θέμα χρωματισμού για μπλοκ κώδικα στο HTML/DOCX."},
        ],
    },
]
FLAGS_CATALOG += [
    {
        "group": "Μεταδεδομένα",
        "flags": [
            {"id": "title", "flag": "--metadata=title", "type": "text", "default": "",
             "label": "Τίτλος εγγράφου", "help": "Τίτλος που εμφανίζεται στην κορυφή."},
            {"id": "author", "flag": "--metadata=author", "type": "text", "default": "",
             "label": "Συγγραφέας", "help": "Όνομα δημιουργού του εγγράφου."},
            {"id": "date", "flag": "--metadata=date", "type": "text", "default": "",
             "label": "Ημερομηνία", "help": "Ημερομηνία εγγράφου."},
            {"id": "lang", "flag": "--metadata=lang", "type": "text", "default": "el",
             "label": "Γλώσσα (lang)", "help": "el για ελληνικά — επηρεάζει τυπογραφία."},
        ],
    },
    {
        "group": "Πρότυπα & αναφορές",
        "flags": [
            {"id": "reference_doc", "flag": "--reference-doc", "type": "template", "default": "",
             "label": "Πρότυπο .docx (reference-doc)",
             "help": "Χρησιμοποιεί σχολικό πρότυπο για γραμματοσειρές, στυλ και περιθώρια."},
            {"id": "css", "flag": "--css", "type": "text", "default": "",
             "label": "Εξωτερικό CSS (URL)",
             "help": "Σύνδεσμος προς stylesheet για έξοδο HTML."},
        ],
    },
]

OUTPUT_FORMATS = [
    {"id": "docx", "label": "Word (.docx)", "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "ext": "docx", "binary": True},
    {"id": "html", "label": "Ιστοσελίδα (.html)", "mime": "text/html; charset=utf-8", "ext": "html", "binary": False},
    {"id": "pdf", "label": "PDF (WeasyPrint, ελληνικά)", "mime": "application/pdf", "ext": "pdf", "binary": True},
    {"id": "odt", "label": "OpenDocument (.odt)", "mime": "application/vnd.oasis.opendocument.text", "ext": "odt", "binary": True},
    {"id": "epub", "label": "EPUB (.epub)", "mime": "application/epub+zip", "ext": "epub", "binary": True},
    {"id": "markdown", "label": "Markdown (.md)", "mime": "text/markdown; charset=utf-8", "ext": "md", "binary": False},
    {"id": "plain", "label": "Απλό κείμενο (.txt)", "mime": "text/plain; charset=utf-8", "ext": "txt", "binary": False},
]
FORMAT_MAP = {f["id"]: f for f in OUTPUT_FORMATS}


def build_flag_args(values: dict[str, Any], target: str) -> list[str]:
    """Μετατρέπει τις τιμές του Visual Flags Explorer σε ορίσματα pandoc."""
    args: list[str] = []
    for group in FLAGS_CATALOG:
        for spec in group["flags"]:
            fid = spec["id"]
            val = values.get(fid, spec["default"])
            ftype = spec["type"]

            if ftype == "bool":
                if bool(val):
                    args.append(spec["flag"])
            elif ftype == "int":
                try:
                    num = int(val)
                except (TypeError, ValueError):
                    continue
                lo, hi = spec.get("min"), spec.get("max")
                if lo is not None:
                    num = max(lo, num)
                if hi is not None:
                    num = min(hi, num)
                if num != spec["default"] or fid == "toc_depth":
                    args.extend([spec["flag"], str(num)])
            elif ftype == "select":
                if val in spec.get("options", []) and val != spec["default"]:
                    args.extend([spec["flag"], str(val)])
            elif ftype == "template":
                if val:
                    tpl = safe_template_name(str(val))
                    if not tpl.exists():
                        raise HTTPException(400, f"Το πρότυπο '{tpl.name}' δεν βρέθηκε.")
                    if target in ("docx", "odt"):
                        args.extend([spec["flag"], str(tpl)])
            elif ftype == "text":
                text = str(val).strip()
                if not text:
                    continue
                if any(ord(c) < 32 for c in text):
                    raise HTTPException(400, "Μη έγκυροι χαρακτήρες στις μεταβλητές.")
                if fid == "css" and target not in ("html", "epub"):
                    continue
                if spec["flag"].startswith("--metadata="):
                    args.extend([spec["flag"] + ":" + text])
                else:
                    args.extend([spec["flag"], text])
    return args
# ---------------------------------------------------------------------------
# CSS για PDF με πλήρη υποστήριξη ελληνικών (WeasyPrint, χωρίς LaTeX)
# ---------------------------------------------------------------------------
PDF_CSS = """
@page {
  size: A4;
  margin: 2cm 2cm 2.2cm 2cm;
  @bottom-center {
    content: "Σελίδα " counter(page) " από " counter(pages);
    font-family: "DejaVu Sans", sans-serif;
    font-size: 9pt; color: #666;
  }
}
body {
  font-family: "DejaVu Serif", "Liberation Serif", serif;
  font-size: 11pt; line-height: 1.55; color: #1a1a1a;
  text-align: justify; hyphens: auto;
}
h1, h2, h3, h4, h5, h6 {
  font-family: "DejaVu Sans", "Liberation Sans", sans-serif;
  color: #1c2aae; page-break-after: avoid; line-height: 1.3;
}
h1 { font-size: 20pt; border-bottom: 2px solid #1c2aae; padding-bottom: .2em; }
h2 { font-size: 15pt; margin-top: 1.2em; }
h3 { font-size: 12.5pt; }
code, pre, tt {
  font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt;
}
pre {
  background: #f5f5f7; border-left: 3px solid #1c2aae;
  padding: .6em .8em; white-space: pre-wrap; word-wrap: break-word;
  page-break-inside: avoid;
}
code { background: #f0f0f4; padding: .1em .3em; border-radius: 2px; }
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 10pt; }
th, td { border: 1px solid #bbb; padding: .4em .6em; text-align: left; }
th { background: #eef1fb; font-family: "DejaVu Sans", sans-serif; }
blockquote {
  border-left: 3px solid #ccc; margin-left: 0; padding-left: 1em; color: #555;
}
img { max-width: 100%; }
a { color: #1c2aae; text-decoration: none; }
#TOC { background: #f8f9fc; padding: .8em 1.2em; border: 1px solid #dde; }
"""


def html_to_pdf(html_bytes: bytes) -> bytes:
    """Μετατρέπει HTML σε PDF με το WeasyPrint (ελαφρύ, χωρίς LaTeX)."""
    try:
        from weasyprint import CSS, HTML
    except ImportError:
        raise HTTPException(500, "Το WeasyPrint δεν είναι εγκατεστημένο στο venv.")
    try:
        doc = HTML(string=html_bytes.decode("utf-8", errors="replace"),
                   base_url=str(BASE_DIR))
        return doc.write_pdf(stylesheets=[CSS(string=PDF_CSS)])
    except Exception as exc:
        raise HTTPException(400, f"Σφάλμα δημιουργίας PDF: {str(exc)[:500]}")


def convert_document(markdown: str, target: str, flag_values: dict[str, Any]) -> tuple[bytes, str]:
    """Κεντρική συνάρτηση μετατροπής. Επιστρέφει (bytes, filename_extension)."""
    if target not in FORMAT_MAP:
        raise HTTPException(400, f"Άγνωστη μορφή εξόδου: {target}")
    if len(markdown.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το έγγραφο υπερβαίνει το μέγιστο επιτρεπτό μέγεθος.")

    args = ["--from", "markdown+smart+footnotes+pipe_tables+task_lists", "--to"]
    pandoc_target = "html5" if target == "pdf" else target
    args.append(pandoc_target)
    args.extend(build_flag_args(flag_values, target))

    if target == "pdf":
        # Πάντα standalone HTML για σωστή απόδοση PDF
        if "--standalone" not in args:
            args.append("--standalone")
        html_bytes = run_pandoc(args, markdown.encode("utf-8"))
        return html_to_pdf(html_bytes), "pdf"

    data = run_pandoc(args, markdown.encode("utf-8"))
    return data, FORMAT_MAP[target]["ext"]


# ---------------------------------------------------------------------------
# Routes — Διεπαφή
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tpl_files = sorted(p.name for p in TEMPLATES_DIR.glob("*.docx"))
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "flags_catalog": FLAGS_CATALOG,
            "formats": OUTPUT_FORMATS,
            "classes": CLASSES,
            "docx_templates": tpl_files,
            "pandoc_ver": pandoc_version(),
        },
    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "pandoc": Path(PANDOC_BIN).exists()}


@app.get("/api/config")
async def api_config():
    return {
        "flags": FLAGS_CATALOG,
        "formats": OUTPUT_FORMATS,
        "classes": CLASSES,
        "templates": sorted(p.name for p in TEMPLATES_DIR.glob("*.docx")),
        "pandoc_version": pandoc_version(),
    }
@app.post("/api/preview")
async def api_preview(request: Request):
    """Ζωντανή προεπισκόπηση Markdown → HTML (θραύσμα)."""
    payload = await request.json()
    markdown = str(payload.get("markdown", ""))
    if len(markdown.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το κείμενο είναι πολύ μεγάλο.")
    html = run_pandoc(
        ["--from", "markdown+smart+footnotes+pipe_tables+task_lists", "--to", "html5"],
        markdown.encode("utf-8"),
    )
    return {"html": html.decode("utf-8", errors="replace")}


@app.post("/api/command")
async def api_command(request: Request):
    """Επιστρέφει την εντολή pandoc που αντιστοιχεί στις επιλογές (Visual Flags)."""
    payload = await request.json()
    target = str(payload.get("format", "docx"))
    values = payload.get("flags", {}) or {}
    if target not in FORMAT_MAP:
        raise HTTPException(400, "Άγνωστη μορφή εξόδου.")
    args = build_flag_args(values, target)
    pandoc_target = "html5" if target == "pdf" else target
    parts = ["pandoc", "input.md", "--from", "markdown", "--to", pandoc_target, *args,
             "-o", f"output.{FORMAT_MAP[target]['ext']}"]
    cmd = " ".join(f'"{p}"' if (" " in p or ":" in p) else p for p in parts)
    if target == "pdf":
        cmd += "   # → WeasyPrint για το PDF (ελληνικά, χωρίς LaTeX)"
    return {"command": cmd}


@app.post("/api/convert")
async def api_convert(request: Request):
    """Μετατροπή και λήψη αρχείου."""
    payload = await request.json()
    markdown = str(payload.get("markdown", ""))
    target = str(payload.get("format", "docx"))
    values = payload.get("flags", {}) or {}
    filename = slugify(str(payload.get("filename", "eggrafo")))

    data, ext = convert_document(markdown, target, values)
    mime = FORMAT_MAP[target]["mime"]
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.{ext}"',
            "X-Output-Format": target,
        },
    )


# ---------------------------------------------------------------------------
# Διαχείριση προτύπων .docx
# ---------------------------------------------------------------------------
@app.get("/api/templates")
async def list_templates():
    items = []
    for p in sorted(TEMPLATES_DIR.glob("*.docx")):
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "modified": int(st.st_mtime)})
    return {"templates": items}


@app.post("/api/templates/upload")
async def upload_template(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Επιτρέπονται μόνο αρχεία .docx")
    target = safe_template_name(file.filename)
    size = 0
    with target.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                fh.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, "Το αρχείο υπερβαίνει τα 100 MB.")
            fh.write(chunk)
    return {"ok": True, "name": target.name, "size": size}


@app.delete("/api/templates/{name}")
async def delete_template(name: str):
    target = safe_template_name(name)
    if not target.exists():
        raise HTTPException(404, "Το πρότυπο δεν βρέθηκε.")
    target.unlink()
    return {"ok": True, "deleted": target.name}


@app.post("/api/templates/generate")
async def generate_default_template():
    """Δημιουργεί το προεπιλεγμένο πρότυπο αναφοράς του pandoc."""
    target = TEMPLATES_DIR / "sxoliko-protypo.docx"
    try:
        proc = subprocess.run(
            [PANDOC_BIN, "--print-default-data-file", "reference.docx"],
            capture_output=True, timeout=PANDOC_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Λήξη χρόνου δημιουργίας προτύπου.")
    if proc.returncode != 0 or not proc.stdout:
        raise HTTPException(400, "Αδυναμία δημιουργίας προτύπου από το pandoc.")
    target.write_bytes(proc.stdout)
    return {"ok": True, "name": target.name, "size": len(proc.stdout)}
# ---------------------------------------------------------------------------
# Απευθείας αποστολή μαθήματος στο MkDocs
# ---------------------------------------------------------------------------
def insert_into_nav(class_slug: str, filename: str, title: str) -> bool:
    """
    Προσθέτει τη νέα σελίδα στο nav του mkdocs.yml κάτω από τη σωστή τάξη.
    Επιστρέφει True αν έγινε ενημέρωση, False αν υπήρχε ήδη.
    """
    yml_path = MKDOCS_ROOT / "mkdocs.yml"
    if not yml_path.exists():
        raise HTTPException(500, "Δεν βρέθηκε το mkdocs.yml.")

    rel_entry = f"{class_slug}/{filename}"
    lines = yml_path.read_text(encoding="utf-8").splitlines()
    if any(rel_entry in ln for ln in lines):
        return False

    try:
        nav_start = next(i for i, ln in enumerate(lines) if ln.strip() == "nav:")
    except StopIteration:
        raise HTTPException(500, "Δεν βρέθηκε ενότητα nav στο mkdocs.yml.")

    class_label = next((c["label"] for c in CLASSES if c["slug"] == class_slug), class_slug)
    target_idx = None
    for i in range(nav_start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("- ") and stripped.endswith(":"):
            label = stripped[2:-1].strip().strip("'\"")
            if label == class_label or label == class_slug:
                target_idx = i
                break

    new_line = f"          - {title}: {rel_entry}"

    if target_idx is None:
        end_idx = len(lines)
        for i in range(nav_start + 1, len(lines)):
            if lines[i] and not lines[i].startswith((" ", "\t", "#")):
                end_idx = i
                break
        lines[end_idx:end_idx] = [f"      - {class_label}:", new_line]
    else:
        base_indent = len(lines[target_idx]) - len(lines[target_idx].lstrip())
        insert_at = target_idx + 1
        for i in range(target_idx + 1, len(lines)):
            ln = lines[i]
            if not ln.strip():
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= base_indent:
                break
            insert_at = i + 1
        lines.insert(insert_at, new_line)

    yml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def trigger_rebuild() -> dict[str, Any]:
    """Εκτελεί ανακατασκευή του MkDocs site."""
    if BUILD_SCRIPT.exists():
        try:
            proc = subprocess.run(
                ["/bin/bash", str(BUILD_SCRIPT)],
                capture_output=True, timeout=180, check=False,
            )
            ok = proc.returncode == 0
            out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
            return {"ok": ok, "output": out[-1500:]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "Λήξη χρόνου ανακατασκευής."}
    return {"ok": False, "output": "Δεν βρέθηκε το script ανακατασκευής."}
@app.post("/api/publish")
async def api_publish(request: Request):
    """Αποθηκεύει το μάθημα στον φάκελο της τάξης και ενημερώνει το site."""
    payload = await request.json()
    markdown = str(payload.get("markdown", "")).strip()
    title = str(payload.get("title", "")).strip()
    class_slug = str(payload.get("class_slug", "")).strip()
    overwrite = bool(payload.get("overwrite", False))
    do_rebuild = bool(payload.get("rebuild", True))

    if not markdown:
        raise HTTPException(400, "Το περιεχόμενο του μαθήματος είναι κενό.")
    if not title:
        raise HTTPException(400, "Απαιτείται τίτλος μαθήματος.")
    if class_slug not in CLASS_SLUGS:
        raise HTTPException(400, "Μη έγκυρη τάξη.")
    if len(markdown.encode("utf-8")) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το μάθημα είναι πολύ μεγάλο.")

    class_dir = MKDOCS_DOCS / class_slug
    class_dir.mkdir(parents=True, exist_ok=True)

    filename = slugify(title) + ".md"
    target = (class_dir / filename).resolve()
    if MKDOCS_DOCS.resolve() not in target.parents:
        raise HTTPException(400, "Μη έγκυρη διαδρομή αρχείου.")
    if target.exists() and not overwrite:
        raise HTTPException(409, f"Το αρχείο '{filename}' υπάρχει ήδη. Ενεργοποίησε την αντικατάσταση.")

    content = markdown if markdown.lstrip().startswith("#") else f"# {title}\n\n{markdown}"
    target.write_text(content + "\n", encoding="utf-8")

    nav_updated = insert_into_nav(class_slug, filename, title)
    rebuild_result = trigger_rebuild() if do_rebuild else {"ok": None, "output": "Παραλείφθηκε."}

    return {
        "ok": True,
        "file": f"{class_slug}/{filename}",
        "url": f"/docs/{class_slug}/{filename[:-3]}/",
        "nav_updated": nav_updated,
        "rebuild": rebuild_result,
    }


@app.get("/api/lessons/{class_slug}")
async def list_lessons(class_slug: str):
    """Λίστα υπαρχόντων μαθημάτων μιας τάξης."""
    if class_slug not in CLASS_SLUGS:
        raise HTTPException(400, "Μη έγκυρη τάξη.")
    class_dir = MKDOCS_DOCS / class_slug
    if not class_dir.exists():
        return {"lessons": []}
    items = []
    for p in sorted(class_dir.glob("*.md")):
        first_line = p.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
        items.append({
            "filename": p.name,
            "title": first_line.lstrip("# ").strip() or p.stem,
            "size": p.stat().st_size,
        })
    return {"lessons": items}


@app.get("/api/lesson/{class_slug}/{filename}")
async def get_lesson(class_slug: str, filename: str):
    """Φορτώνει υπάρχον μάθημα για επεξεργασία."""
    if class_slug not in CLASS_SLUGS:
        raise HTTPException(400, "Μη έγκυρη τάξη.")
    base = Path(filename).name
    if not base.endswith(".md"):
        raise HTTPException(400, "Επιτρέπονται μόνο αρχεία .md")
    target = (MKDOCS_DOCS / class_slug / base).resolve()
    if MKDOCS_DOCS.resolve() not in target.parents or not target.exists():
        raise HTTPException(404, "Το μάθημα δεν βρέθηκε.")
    return {"filename": base, "markdown": target.read_text(encoding="utf-8")}


@app.post("/api/rebuild")
async def api_rebuild():
    """Χειροκίνητη ανακατασκευή του εκπαιδευτικού υλικού."""
    return trigger_rebuild()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002, log_level="info")