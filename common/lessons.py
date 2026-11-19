"""
common.lessons — Δομή ημερήσιων μαθημάτων (φάσεις με markers) & κατάλογος.

Ενοποιεί το parsing/render που ζούσε στο Lesson Wizard και την ελαφριά
ανάγνωση front-matter που είχε αντιγράψει το Classroom Hub για τη σύνθετη
ανακοίνωση. Ίδιο format με το MkDocs hook (mkdocs-site/hooks/lesson_phases.py):

    <!-- phase: aformisi | title: Αφόρμηση | duration: 5 -->
    ...markdown φάσης...
    <!-- /phase -->
    <!-- teacher-notes --> ...μόνο για τον καθηγητή... <!-- /teacher-notes -->

Χωρίς εξαρτήσεις (ούτε PyYAML, ούτε FastAPI): ο κατάλογος διαβάζεται read-only
από το mkdocs-site/docs/mathimata/ και επιστρέφει απλά dicts.
"""
from __future__ import annotations

import re
from pathlib import Path

from .classes import CLASS_GROUPS, CLASS_LABELS, CLASS_SLUGS, SLUG_RE

# Τύποι διδακτικών φάσεων (παλέτα του visual editor)
PHASE_TYPES = {
    "aformisi":      {"icon": "🎯", "label": "Αφόρμηση",       "duration": 5},
    "syzitisi":      {"icon": "💬", "label": "Συζήτηση",       "duration": 6},
    "parousiasi":    {"icon": "📽️", "label": "Παρουσίαση",     "duration": 10},
    "drastiriotita": {"icon": "✍️", "label": "Δραστηριότητα",  "duration": 15},
    "aksiologisi":   {"icon": "✅", "label": "Αξιολόγηση",     "duration": 6},
    "kleisimo":      {"icon": "🧭", "label": "Κλείσιμο",       "duration": 3},
    "custom":        {"icon": "🧩", "label": "Ελεύθερη φάση",  "duration": 5},
}

PHASE_RE = re.compile(
    r"^<!--\s*phase:\s*([a-z0-9_-]+)([^\n]*?)-->\s*$(.*?)^<!--\s*/phase\s*-->\s*$",
    re.MULTILINE | re.DOTALL,
)
ATTR_RE = re.compile(r"\|\s*([a-z_]+):\s*([^|]*?)(?=\||$)")
TN_RE = re.compile(r"<!--\s*teacher-notes\s*-->(.*?)<!--\s*/teacher-notes\s*-->", re.DOTALL)
FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def parse_lesson(md: str) -> dict:
    """Χωρίζει το markdown σε front-matter, κεφαλίδα, φάσεις & σημειώσεις."""
    fm = ""
    m = FM_RE.match(md)
    if m:
        fm = m.group(1)
        md_rest = md[m.end():]
    else:
        md_rest = md
    tn = ""
    tnm = TN_RE.search(md_rest)
    if tnm:
        tn = tnm.group(1).strip()
        md_rest = TN_RE.sub("", md_rest)
    phases = []
    header_parts = []
    pos = 0
    for pm in PHASE_RE.finditer(md_rest):
        header_parts.append(md_rest[pos:pm.start()])
        attrs = dict((k.strip(), v.strip()) for k, v in ATTR_RE.findall(pm.group(2) or ""))
        ptype = pm.group(1)
        phases.append({
            "type": ptype,
            "title": attrs.get("title", PHASE_TYPES.get(ptype, {}).get("label", "Φάση")),
            "duration": int(attrs.get("duration", "0") or 0),
            "body": pm.group(3).strip("\n"),
        })
        pos = pm.end()
    header_parts.append(md_rest[pos:])
    return {
        "front_matter": fm,
        "header": "".join(header_parts).strip("\n"),
        "phases": phases,
        "teacher_notes": tn,
    }


def render_lesson(data: dict) -> str:
    """Συναρμολογεί το markdown από τα δομικά στοιχεία (στρογγυλοποίηση μορφής)."""
    out = []
    if data.get("front_matter"):
        out.append("---\n" + data["front_matter"].strip() + "\n---\n")
    out.append(data.get("header", "").strip() + "\n")
    for ph in data.get("phases", []):
        ptype = ph.get("type", "custom")
        title = ph.get("title") or PHASE_TYPES.get(ptype, {}).get("label", "Φάση")
        dur = int(ph.get("duration") or 0)
        out.append(
            f"\n<!-- phase: {ptype} | title: {title} | duration: {dur} -->\n"
            + ph.get("body", "").strip()
            + "\n<!-- /phase -->\n"
        )
    if data.get("teacher_notes", "").strip():
        out.append("\n<!-- teacher-notes -->\n" + data["teacher_notes"].strip() + "\n<!-- /teacher-notes -->\n")
    return "\n".join(out).replace("\n\n\n", "\n\n")


def fm_meta(fm: str) -> dict:
    """Ελαφρύ διάβασμα μεταδεδομένων front-matter (tags/favorite/unit/book).

    Δεν απαιτεί PyYAML — καλύπτει τις μορφές που γράφει το wizard:
      tags: [a, b]  ή  tags:\\n    - a\\n    - b
      favorite: true
    """
    meta: dict = {"tags": [], "favorite": False}
    m = re.search(r"^tags:\s*\[(.*?)\]\s*$", fm, re.MULTILINE)
    if m:
        meta["tags"] = [t.strip().strip("'\"") for t in m.group(1).split(",") if t.strip()]
    else:
        m = re.search(r"^tags:\s*\n((?:\s+-\s+.+\n?)+)", fm, re.MULTILINE)
        if m:
            meta["tags"] = [x.strip().lstrip("-").strip().strip("'\"")
                            for x in m.group(1).strip().splitlines() if x.strip()]
    m = re.search(r"^favorite:\s*(true|yes|1)\s*$", fm, re.MULTILINE | re.IGNORECASE)
    meta["favorite"] = bool(m)
    m = re.search(r"^\s+unit:\s*['\"]?(.*?)['\"]?\s*$", fm, re.MULTILINE)
    if m:
        meta["unit"] = m.group(1).strip()
    m = re.search(r"^\s+book_pages:\s*['\"]?(.*?)['\"]?\s*$", fm, re.MULTILINE)
    if m:
        meta["book_pages"] = m.group(1).strip()
    return meta


def set_fm_meta(fm: str, tags: list[str] | None, favorite: bool | None) -> str:
    """Γράφει/αντικαθιστά τα tags & favorite στο front-matter (χωρίς YAML lib)."""
    lines = fm.splitlines()
    out: list[str] = []
    skip_block = False
    for ln in lines:
        if skip_block:
            if re.match(r"^\s+-\s+", ln):
                continue                          # γραμμές παλιάς λίστας tags
            skip_block = False
        if re.match(r"^tags:", ln):
            if not re.match(r"^tags:\s*\[", ln):
                skip_block = True                 # block-style λίστα → αφαίρεση
            continue
        if re.match(r"^favorite:", ln):
            continue
        out.append(ln)
    if tags is not None:
        clean = [re.sub(r"[\[\],#'\"\n]", "", str(t)).strip() for t in tags]
        clean = [t for t in clean if t][:12]
        if clean:
            out.append("tags: [" + ", ".join(clean) + "]")
    if favorite:
        out.append("favorite: true")
    return "\n".join(out).strip("\n")


def valid_lesson_path(class_slug: str, subject: str, lesson: str) -> bool:
    """Έγκυρα ονόματα τάξη/μάθημα/ενότητα (αυστηρή επαλήθευση διαδρομών).

    Ο έλεγχος containment στο filesystem γίνεται από τον caller (lesson_dir).
    """
    return bool(SLUG_RE.match(class_slug) and class_slug in CLASS_SLUGS
                and SLUG_RE.match(subject) and SLUG_RE.match(lesson))


def list_all_lessons(math_dir: Path) -> list[dict]:
    """Όλα τα ημερήσια μαθήματα (φάκελοι με index.md κάτω από mathimata/)."""
    out = []
    math_dir = Path(math_dir)
    if not math_dir.is_dir():
        return out
    for cls_dir in sorted(math_dir.iterdir()):
        if not cls_dir.is_dir() or cls_dir.name not in CLASS_SLUGS:
            continue
        for subj_dir in sorted(cls_dir.iterdir()):
            if not subj_dir.is_dir():
                continue
            for les_dir in sorted(subj_dir.iterdir()):
                idx = les_dir / "index.md"
                if not les_dir.is_dir() or not idx.is_file():
                    continue
                text = idx.read_text(encoding="utf-8", errors="ignore")
                parsed = parse_lesson(text)
                if not parsed["phases"]:
                    continue                      # index ενότητας, όχι μάθημα
                title = les_dir.name
                hm = re.search(r"^# (.+)$", parsed["header"], re.MULTILINE)
                if hm:
                    title = hm.group(1).strip()
                total = sum(p["duration"] for p in parsed["phases"])
                files = [p.name for p in sorted(les_dir.iterdir())
                         if p.is_file() and p.name != "index.md"]
                meta = fm_meta(parsed["front_matter"])
                out.append({
                    "class_slug": cls_dir.name,
                    "class_label": CLASS_LABELS[cls_dir.name],
                    "subject": subj_dir.name,
                    "lesson": les_dir.name,
                    "title": title,
                    "phases": len(parsed["phases"]),
                    "duration": total,
                    "files": files,
                    "tags": meta["tags"],
                    "favorite": meta["favorite"],
                    "unit": meta.get("unit", ""),
                    "book_pages": meta.get("book_pages", ""),
                    "url": f"/docs/mathimata/{cls_dir.name}/{subj_dir.name}/{les_dir.name}/",
                })
    return out


def lessons_catalog(math_dir: Path) -> list[dict]:
    """Read-only κατάλογος (τίτλος/tags/favorite/τάξη) για τη ΣΥΝΘΕΤΗ ανακοίνωση
    του Classroom Hub — ίδια ελαφριά λογική με το Lesson Wizard, χωρίς να
    διαβάζονται ολόκληρα τα αρχεία (μόνο τα πρώτα 8 KB)."""
    math_dir = Path(math_dir)
    out = []
    if not math_dir.is_dir():
        return out
    for idx in sorted(math_dir.glob("*/*/*/index.md")):
        parts = idx.relative_to(math_dir).parts
        if len(parts) != 4 or parts[0] not in CLASS_LABELS:
            continue
        try:
            text = idx.read_text(encoding="utf-8", errors="ignore")[:8000]
        except OSError:
            continue
        fm_m = FM_RE.match(text)
        meta = fm_meta(fm_m.group(1) if fm_m else "")
        hm = re.search(r"^# (.+)$", text, re.MULTILINE)
        title = hm.group(1).strip() if hm else parts[2]
        out.append({"title": title[:120], "class_slug": parts[0],
                    "class_label": CLASS_LABELS[parts[0]], "subject": parts[1],
                    "lesson": parts[2], "tags": meta["tags"],
                    "favorite": meta["favorite"],
                    "url": f"/docs/mathimata/{parts[0]}/{parts[1]}/{parts[2]}/"})
    return out


def _first_heading(path: Path, fallback: str) -> str:
    """Πρώτη επικεφαλίδα «# …» του .md ως φιλικός τίτλος (αλλιώς fallback)."""
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return fallback


def list_lessons_grouped(docs_dir: Path) -> list[dict]:
    """Όλα τα .md μαθήματα ΟΜΑΔΟΠΟΙΗΜΕΝΑ ανά τάξη (dropdowns bridge/h5p).

    Νέα δομή: mathimata/<τάξη>/· αν δεν υπάρχει, το παλιό υλικό ζει στο
    _paradeigma/<τάξη>/ (fallback ανά τάξη — single source of truth, Β1/Β2).
    Επιστρέφει [{slug, label, lessons: [{path, label}]}] με paths σχετικά
    στο docs_dir — ίδια με αυτά που δέχονται οι validators των apps.
    """
    docs_dir = Path(docs_dir)
    groups = []
    for c in CLASS_GROUPS:
        lessons = []
        class_dir = docs_dir / "mathimata" / c["slug"]
        if not class_dir.is_dir():
            class_dir = docs_dir / "_paradeigma" / c["slug"]
        if class_dir.is_dir():
            for p in sorted(class_dir.rglob("*.md")):
                rel = p.relative_to(docs_dir).as_posix()
                label = _first_heading(p, p.name)
                lessons.append({"path": rel, "label": f"{p.name} — {label}"})
        groups.append({**c, "lessons": lessons})
    return groups


def list_lessons_flat(docs_dir: Path) -> list[dict]:
    """Επίπεδη λίστα ΟΛΩΝ των .md του docs/ (app-builder), εκτός assets/teachers.

    Label: «<rel-path> — <πρώτη επικεφαλίδα>» (αλλιώς σκέτο το rel-path).
    Οι προστατευμένες περιοχές καθηγητών εξαιρούνται σε ΟΠΟΙΟδήποτε βάθος.
    """
    docs_dir = Path(docs_dir)
    lessons = []
    for p in sorted(docs_dir.rglob("*.md")):
        rel = p.relative_to(docs_dir).as_posix()
        if rel.startswith(("assets/", "teachers/", "_paradeigma/teachers/")):
            continue  # assets: όχι μαθήματα· teachers: προστατευμένη περιοχή Basic Auth
        label = rel
        heading = _first_heading(p, "")
        if heading:
            label = f"{rel} — {heading}"
        lessons.append({"path": rel, "label": label})
    return lessons
