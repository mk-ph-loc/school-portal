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
from common.fs import backup_history
from common.lessons import valid_lesson_path, list_all_lessons as _list_all_lessons
from common.nav import rebuild_nav as _rebuild_nav

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
# Αυτόματο nav στο mkdocs.yml — single owner: common.nav (Task 4)
# ---------------------------------------------------------------------------
def rebuild_nav() -> None:
    """Folder-driven idempotent rebuild (flock στο data/nav.lock, .bak ιστορικό).

    Η λογική ζει στο common/nav.py — ίδιο μπλοκ χτίζει και το MD-Bridge, ώστε
    οι δημοσιεύσεις του (_paradeigma/) να επιβιώνουν κάθε rebuild.
    """
    _rebuild_nav(MKDOCS_YML, backup_dir=BACKUP_DIR)
