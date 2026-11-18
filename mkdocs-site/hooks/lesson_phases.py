"""
lesson_phases.py — MkDocs hook για τη δομή ημερήσιων μαθημάτων.

Μετατρέπει τα markers διδακτικών φάσεων του markdown:

    <!-- phase: aformisi | title: Αφόρμηση | duration: 5 -->
    ...περιεχόμενο φάσης (κανονικό markdown)...
    <!-- /phase -->

σε τυλιγμένα <div class="lesson-phase" data-phase="..." data-duration="...">
(το εσωτερικό markdown μετατρέπεται κανονικά μέσω md_in_html), και τις
σημειώσεις καθηγητή:

    <!-- teacher-notes -->
    ...markdown μόνο για τον καθηγητή...
    <!-- /teacher-notes -->

σε <div class="teacher-notes" hidden>.

ΑΣΦΑΛΕΙΑ: Το περιεχόμενο των σημειώσεων ΔΕΝ μπαίνει στο HTML των μαθητών.
Κατά το build αποθηκεύεται σε ξεχωριστό αρχείο `index.teacher.html` δίπλα στη
σελίδα, το οποίο ο Nginx σερβίρει ΜΟΝΟ με έγκυρο cookie καθηγητή (auth_request
προς το /lesson-wizard/api/check). Το lesson-phases.js το φορτώνει δυναμικά·
αν ο χρήστης δεν είναι καθηγητής, το αίτημα απορρίπτεται (401) και δεν
υπάρχει κανένα ίχνος των σημειώσεων στη σελίδα.
"""
from __future__ import annotations

import re
from pathlib import Path

# ΣΗΜΕΙΩΣΗ: τα attrs επιτρέπουν ΚΑΙ '>' (π.χ. τίτλοι με «→» ή «>=»)· ο marker
# τερματίζει αυστηρά στο '-->' στη δική του γραμμή.
PHASE_OPEN = re.compile(
    r"^<!--\s*phase:\s*(?P<type>[a-z0-9_-]+)(?P<attrs>[^\n]*?)-->\s*$",
    re.MULTILINE,
)
PHASE_ATTR = re.compile(r"\|\s*([a-z_]+):\s*([^|]*?)(?=\||$)")
PHASE_CLOSE = "<!-- /phase -->"
TN_OPEN = "<!-- teacher-notes -->"
TN_CLOSE = "<!-- /teacher-notes -->"

# Τύποι φάσεων → εικονίδιο & προεπιλεγμένος τίτλος (για το wizard/badges)
PHASE_TYPES = {
    "aformisi": ("🎯", "Αφόρμηση"),
    "syzitisi": ("💬", "Συζήτηση"),
    "parousiasi": ("📽️", "Παρουσίαση"),
    "drastiriotita": ("✍️", "Δραστηριότητα"),
    "aksiologisi": ("✅", "Αξιολόγηση"),
    "kleisimo": ("🧭", "Κλείσιμο & Αναστοχασμός"),
    "custom": ("🧩", "Φάση"),
}


def _wrap_body(text: str) -> str:
    """Τυλίγει το περιεχόμενο φάσης σε εμφωλευμένο div markdown="1".

    ΣΗΜΕΙΩΣΗ: Δεν χρησιμοποιούμε 4-space indent στο ίδιο το lesson-phase div,
    γιατί η Python-Markdown τότε ΔΕΝ επεξεργάζεται raw HTML μπλοκ (iframe,
    <div class="quiz"> κ.λπ.) και τα εμφανίζει escaped. Το εμφωλευμένο div με
    markdown="1" επεξεργάζεται σωστά τόσο markdown όσο και raw HTML.
    """
    return '<div class="phase-body" markdown="1">\n\n' + text.strip("\n") + "\n\n</div>"


def on_page_markdown(markdown: str, *, page, config, files, **kwargs):
    src = Path(page.file.abs_src_path)
    # Οι σημειώσεις εξάγονται ΜΟΝΟ για ημερήσια μαθήματα (φάκελος με index.md
    # κάτω από mathimata/) — όχι για τα index ενότητας/τάξης.
    is_lesson = "mathimata" in src.parts and src.name == "index.md" and src.parent.name not in (
        "mathimata", "pliroforiki",
    ) and "phase:" in markdown

    teacher_chunks: list[str] = []

    # --- 1. Εξαγωγή σημειώσεων καθηγητή (πριν από κάθε άλλη επεξεργασία) ---
    def _tn_sub(m: re.Match) -> str:
        teacher_chunks.append(m.group(1).strip())
        return '<div class="teacher-notes" hidden></div>'

    pattern = re.escape(TN_OPEN) + r"(.*?)" + re.escape(TN_CLOSE)
    markdown = re.sub(pattern, _tn_sub, markdown, flags=re.DOTALL)

    if teacher_chunks and is_lesson:
        page.meta["_teacher_notes_md"] = "\n\n---\n\n".join(teacher_chunks)

    # --- 2. Τύλιγμα φάσεων σε div (md_in_html) ---
    out: list[str] = []
    pos = 0
    while True:
        m = PHASE_OPEN.search(markdown, pos)
        if not m:
            out.append(markdown[pos:])
            break
        end = markdown.find(PHASE_CLOSE, m.end())
        if end == -1:
            out.append(markdown[pos:])
            break
        out.append(markdown[pos:m.start()])
        ptype = m.group("type")
        attrs = dict((k.strip(), v.strip()) for k, v in PHASE_ATTR.findall(m.group("attrs") or ""))
        icon, default_title = PHASE_TYPES.get(ptype, PHASE_TYPES["custom"])
        title = attrs.get("title", default_title)
        duration = attrs.get("duration", "")
        body = markdown[m.end():end].strip("\n")
        out.append(
            f'<div class="lesson-phase" data-phase="{ptype}" data-title="{icon} {title}"'
            f' data-duration="{duration}" markdown="1">\n\n'
            + _wrap_body(body)
            + "\n\n</div>"
        )
        pos = end + len(PHASE_CLOSE)
    return "\n".join(out)


def on_page_content(html: str, *, page, config, files, **kwargs):
    # --- Chips tags/αγαπημένου (front-matter) για το mkdocs-extras.js ---
    tags = page.meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    favorite = bool(page.meta.get("favorite"))
    if tags or favorite:
        import json as _json
        payload = _json.dumps({"tags": tags, "favorite": favorite}, ensure_ascii=False)
        html += f'\n<script>window.__lessonMeta = {payload};</script>'

    notes_md = page.meta.pop("_teacher_notes_md", None)
    if not notes_md:
        return html
    # Μετατροπή των σημειώσεων σε HTML με την ίδια μηχανή markdown του MkDocs.
    import markdown as md_mod

    extensions = config.get("markdown_extensions", [])
    ext_configs = config.get("mdx_configs", {})
    converter = md_mod.Markdown(extensions=extensions, extension_configs=ext_configs)
    notes_html = converter.convert(notes_md)
    dest = Path(page.file.abs_dest_path).parent / "index.teacher.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        '<div class="teacher-notes__inner admonition note">\n'
        '<p class="admonition-title">🔒 Σημειώσεις Καθηγητή (δεν τις βλέπουν οι μαθητές)</p>\n'
        + notes_html
        + "\n</div>",
        encoding="utf-8",
    )
    return html