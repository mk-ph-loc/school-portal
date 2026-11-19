"""
H5P Studio — κοινό state & αυθεντικοποίηση (Task 3: διάσπαση σε APIRouters).

Εδώ ζουν ΟΛΑ τα globals που μοιράζονται οι routers (διαδρομές, σταθερές,
TYPE_LIBS/labels/icons, PREVIEW_ID, TeacherAuth), ώστε να μην υπάρχουν
κυκλικά imports: κάθε module κάνει `import state` και διαβάζει
`state.LIBRARY_DIR` κ.λπ. ΠΟΤΕ `from state import …` για μεταβλητές
(ίδιο μοτίβο με το classroom-hub).

Καμία ενέργεια πέρα από τον ορισμό σταθερών κατά το import — το init_db()
ζει στο store.py και καλείται από το main.py (όπως στον παλιό μονόλιθο).
"""
from __future__ import annotations

import re
from pathlib import Path

from common.auth import TeacherAuth

# ---------------------------------------------------------------------------
# Διαδρομές & σταθερές
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PORTAL_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "h5p.db"
LIBRARY_DIR = BASE_DIR / "library"                 # library/<activity-id>/
H5P_LIBS_DIR = BASE_DIR / "h5p-libraries"          # κοινόχρηστες βιβλιοθήκες H5P
DOCS_DIR = PORTAL_DIR / "mkdocs-site" / "docs"
VIDEOS_DIRS = [DOCS_DIR / "assets" / "videos", DOCS_DIR / "videos"]
BUILD_DOCS_SCRIPT = PORTAL_DIR / "scripts" / "build-docs.sh"
BACKUP_DIR = BASE_DIR / "backups"
ENV_KEYS_FILE = PORTAL_DIR / ".env.keys"

COOKIE_NAME = "h5pstudio_teacher"
PREVIEW_ID = "preview-tmp"                         # προσωρινή προεπισκόπηση editor
MAX_UPLOAD_BYTES = 100 * 1024 * 1024               # ίδιο με client_max_body_size
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LIBDIR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._]*-\d+\.\d+$")

# Οι 6 τάξεις του mkdocs-site — κοινές σε όλη την πύλη (common.classes)

SUBJECTS = ["Πληροφορική", "Μαθηματικά", "Φυσική", "Χημεία", "Βιολογία",
            "Γλώσσα", "Αρχαία Ελληνικά", "Ιστορία", "Γεωγραφία", "Αγγλικά",
            "Θρησκευτικά", "Μουσική", "Καλλιτεχνικά", "Άλλο"]

# Υποστηριζόμενοι τύποι → κύρια βιβλιοθήκη H5P (τοπικά, h5p-libraries/)
TYPE_LIBS = {
    "multichoice":  "H5P.MultiChoice-1.16",
    "questionset":  "H5P.QuestionSet-1.20",
    "blanks":       "H5P.Blanks-1.14",
    "dragtext":     "H5P.DragText-1.10",
    "hotspots":     "H5P.ImageHotspots-1.10",
    "dialogcards":  "H5P.Dialogcards-1.9",
    "video":        "H5P.InteractiveVideo-1.27",
}
LIB_TYPE = {v.split("-")[0]: k for k, v in TYPE_LIBS.items()}
TYPE_LABELS = {
    "multichoice": "Πολλαπλής Επιλογής",
    "questionset": "Σετ Ερωτήσεων",
    "blanks": "Συμπλήρωση Κενών",
    "dragtext": "Σύρε τις Λέξεις",
    "hotspots": "Εικόνα με Hotspots",
    "dialogcards": "Κάρτες Μνήμης",
    "video": "Διαδραστικό Βίντεο",
    "external": "Εξωτερικό H5P",
}
TYPE_ICONS = {
    "multichoice": "✅", "questionset": "📝", "blanks": "✏️", "dragtext": "🔀",
    "hotspots": "📍", "dialogcards": "🃏", "video": "🎬", "external": "📦",
}


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC) — common.auth
# ---------------------------------------------------------------------------
auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
make_token = auth.make_token
token_valid = auth.token_valid
require_teacher = auth.require_teacher
