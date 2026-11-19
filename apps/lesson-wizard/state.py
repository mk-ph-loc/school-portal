"""
Lesson Wizard — κοινό state & αυθεντικοποίηση (Task 3: διάσπαση σε APIRouters).

Εδώ ζουν ΟΛΑ τα globals που μοιράζονται οι routers (διαδρομές, σταθερές,
TeacherAuth) + οι κοινοί βοηθοί μαθημάτων (lesson_dir/list_all_lessons/
backup_file/rebuild_nav), ώστε να μην υπάρχουν κυκλικά imports: κάθε router
κάνει `import state` και διαβάζει `state.DOCS_DIR` κ.λπ. ΠΟΤΕ
`from state import …` για μεταβλητές (ίδιο μοτίβο με το classroom-hub).

Καμία ενέργεια κατά το import (όπως στον παλιό μονόλιθο app.py).
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from common.auth import TeacherAuth
from common.classes import CLASS_GROUPS
from common.fs import backup_history
from common.lessons import FM_RE, valid_lesson_path, list_all_lessons as _list_all_lessons

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent.parent                 # apps/lesson-wizard → /opt/school-portal
DOCS_DIR = PORTAL_DIR / "mkdocs-site" / "docs"
MATH_DIR = DOCS_DIR / "mathimata"
MKDOCS_YML = PORTAL_DIR / "mkdocs-site" / "mkdocs.yml"
BACKUP_DIR = BASE_DIR / "backups"
DATA_DIR = BASE_DIR / "data"
SCHEDULE_JSON = DATA_DIR / "schedule.json"
OVERRIDES_JSON = DATA_DIR / "active-overrides.json"
BROADCAST_JSON = DATA_DIR / "broadcast.json"
BOOKS_JSON = DATA_DIR / "books.json"
TEMPLATE_XLSX = DATA_DIR / "orari-protypo.xlsx"
LIBRARY_DIR = DOCS_DIR / "vivliothiki"

COOKIE_NAME = "lessonwizard_teacher"

# Τάξεις & τύποι φάσεων: common.classes / common.lessons (ίδια σε όλη την πύλη)
UPLOAD_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf",
               ".html", ".mp4", ".webm", ".mp3", ".ogg", ".pptx", ".odp", ".zip"}
UPLOAD_MAX = 40 * 1024 * 1024                        # 40 MB ανά αρχείο
# Γενικός file browser: επιπλέον τύποι για υλικό μαθημάτων (md/css/js/data).
FS_UPLOAD_EXTS = UPLOAD_EXTS | {".md", ".txt", ".css", ".js", ".json", ".csv",
                                ".docx", ".odt", ".xlsx", ".ipynb", ".py"}
NAME_RE = re.compile(r"^[^/\\\x00-\x1f]+$")          # όνομα αρχείου/φακέλου χωρίς διαδρομές

NAV_BEGIN = "# BEGIN AUTO-NAV MATHIMATA"
NAV_END = "# END AUTO-NAV MATHIMATA"


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC) — common.auth
# ---------------------------------------------------------------------------
auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
make_token = auth.make_token
token_valid = auth.token_valid
require_teacher = auth.require_teacher


# ---------------------------------------------------------------------------
# Μαθήματα: parsing/render/front-matter στο common.lessons (ίδιο format με το hook)
# ---------------------------------------------------------------------------
def lesson_dir(class_slug: str, subject: str, lesson: str) -> Path:
    """Έγκυρος φάκελος ημερήσιου μαθήματος (αυστηρή επαλήθευση διαδρομών)."""
    if not valid_lesson_path(class_slug, subject, lesson):
        raise HTTPException(400, "Μη έγκυρη τάξη ή όνομα μαθήματος/ενότητας.")
    d = (MATH_DIR / class_slug / subject / lesson).resolve()
    if not str(d).startswith(str(MATH_DIR.resolve())):
        raise HTTPException(400, "Μη έγκυρη διαδρομή.")
    return d


def list_all_lessons() -> list[dict]:
    """Όλα τα ημερήσια μαθήματα του mkdocs-site (common.lessons)."""
    return _list_all_lessons(MATH_DIR)


def backup_file(path: Path) -> None:
    """Ιστορικό .bak στο backups/ πριν από κάθε εγγραφή (common.fs)."""
    backup_history(path, BACKUP_DIR, relative_to=PORTAL_DIR)


# ---------------------------------------------------------------------------
# Αυτόματο nav στο mkdocs.yml (μεταξύ των δεικτών BEGIN/END AUTO-NAV)
# ---------------------------------------------------------------------------
def rebuild_nav() -> None:
    """Ξαναγράφει το μπλοκ Μαθήματα στο nav με βάση τους φακέλους."""
    text = MKDOCS_YML.read_text(encoding="utf-8")
    i = text.find(NAV_BEGIN)
    j = text.find(NAV_END)
    if i == -1 or j == -1:
        return                                    # χωρίς δείκτες δεν πειράζουμε
    j_end = text.find("\n", j)
    # Ο δείκτης BEGIN πρέπει να ξεκινά στην αρχή της γραμμής του (όχι μετά τα
    # κενά indent της προηγούμενης χρήσης — θα διπλασιάζονταν σε κάθε rebuild).
    i = text.rfind("\n", 0, i) + 1
    lines = ["  " + NAV_BEGIN + " (διαχειρίζεται το Lesson Wizard — μην επεξεργάζεστε χειροκίνητα)"]
    if LIBRARY_DIR.is_dir() and any(LIBRARY_DIR.glob("*.pdf")):
        lines.append("  - 📖 Βιβλιοθήκη: vivliothiki/index.md")
    lines.append("  - Μαθήματα:")
    lessons = list_all_lessons()
    by_class: dict[str, dict[str, list]] = {}
    for les in lessons:
        by_class.setdefault(les["class_slug"], {}).setdefault(les["subject"], []).append(les)
    for cls in CLASS_GROUPS:
        subjects = by_class.get(cls["slug"])
        if not subjects:
            continue
        lines.append(f"      - {cls['label']}:")
        for subj, items in subjects.items():
            subj_label = subj.replace("-", " ").capitalize()
            idx_rel = f"mathimata/{cls['slug']}/{subj}/index.md"
            if (DOCS_DIR / idx_rel).is_file():
                # Προτίμηση του title από το front-matter του index (π.χ. «Πληροφορική Γ' Γυμνασίου»)
                fm = FM_RE.match((DOCS_DIR / idx_rel).read_text(encoding="utf-8", errors="ignore"))
                if fm:
                    tm = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", fm.group(1), re.MULTILINE)
                    if tm:
                        subj_label = tm.group(1).strip().replace("'", "''")
                lines.append(f"          - '{subj_label}': {idx_rel}")
            for les in items:
                title = les["title"].replace("'", "''")
                rel = f"mathimata/{cls['slug']}/{subj}/{les['lesson']}/index.md"
                lines.append(f"          - '{title}': {rel}")
    lines.append("  " + NAV_END)
    new_text = text[:i] + "\n".join(lines) + text[j_end:]
    if new_text != text:
        backup_file(MKDOCS_YML)
        MKDOCS_YML.write_text(new_text, encoding="utf-8")
