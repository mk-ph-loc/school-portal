"""
H5P Studio — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

Αυτόνομο περιβάλλον δημιουργίας, διαχείρισης & αναπαραγωγής διαδραστικών
ασκήσεων H5P (FastAPI + Uvicorn + SQLite, χωρίς Docker):
  * Offline player h5p-standalone (static/h5p-player/) + τοπικές βιβλιοθήκες
    H5P (h5p-libraries/) — καμία εξάρτηση από CDN/Internet στην αναπαραγωγή.
  * Βιβλιοθήκη δραστηριοτήτων: library/<activity-id>/ με έγκυρη δομή H5P
    (h5p.json, content/content.json, media) + μεταδεδομένα στο h5p.db.
  * Γραφικός Visual Editor (Tailwind + Alpine, ελληνικά) με split-screen
    ζωντανή προεπισκόπηση για 7 τύπους H5P (MultiChoice, QuestionSet, Blanks,
    DragText, ImageHotspots, Dialogcards, InteractiveVideo).
  * Import/Export επίσημων πακέτων .h5p (Lumi Desktop, Φωτόδεντρο, h5p.org).
  * AI Οδηγός Δημιουργίας (Wizard 3 βημάτων): παιδαγωγικές προτάσεις ανά
    διδακτικό στόχο, άμεση παραγωγή άσκησης μέσω OpenAI-compatible API
    (Alibaba Qwen — .env.keys) και γεννήτρια εξειδικευμένων prompts.
  * Ενσωμάτωση σε μάθημα MkDocs με 1 κλικ (iframe + αυτόματο .bak backup).

Προστασία: κωδικός καθηγητή teacher2026 (HMAC cookie όπως στο /exams/) για
δημιουργία/επεξεργασία/διαγραφή· το /h5p-studio/play/<id>/ είναι ανοιχτό.
Τρέχει στο 127.0.0.1:8012 πίσω από τον Nginx στο /h5p-studio/.
ΣΗΜΕΙΩΣΗ: η 8011 ανήκει ήδη στο Web Lab (/web-lab/) — βλ. README.
"""
from __future__ import annotations

import hmac
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

import requests
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from common.auth import TeacherAuth, TEACHER_CODE, COOKIE_MAX_AGE
from common.classes import CLASS_GROUPS, CLASS_SLUGS, CLASS_LABELS
from common.db import connect

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

app = FastAPI(
    title="H5P Studio (Διαδραστικές Ασκήσεις)",
    description="Δημιουργία, διαχείριση & αναπαραγωγή διαδραστικών ασκήσεων H5P",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
# ΣΗΜΕΙΩΣΗ: Το root_path (/h5p-studio) ορίζεται στο uvicorn μέσω του systemd
# unit, ώστε τα url_for() των templates να παράγουν σωστό πρόθεμα πίσω από
# τον Nginx.
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/h5p-libraries", StaticFiles(directory=str(H5P_LIBS_DIR)), name="h5p-libraries")
app.mount("/library", StaticFiles(directory=str(LIBRARY_DIR)), name="library")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Βάση δεδομένων (SQLite — κοινές ρυθμίσεις πύλης μέσω common.db)
# ---------------------------------------------------------------------------
def db() -> sqlite3.Connection:
    # Χωρίς FK constraints στο σχήμα — foreign_keys όπως πριν (default OFF)
    return connect(DB_PATH, foreign_keys=False)


def init_db() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                type        TEXT NOT NULL,             -- multichoice|...|external
                main_lib    TEXT NOT NULL DEFAULT '',  -- π.χ. H5P.MultiChoice 1.16
                class_slug  TEXT NOT NULL DEFAULT '',
                subject     TEXT NOT NULL DEFAULT '',
                chapter     TEXT NOT NULL DEFAULT '',
                goal        TEXT NOT NULL DEFAULT '',
                difficulty  TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


init_db()


# ---------------------------------------------------------------------------
# Αυθεντικοποίηση καθηγητή: υπογεγραμμένο cookie (HMAC) — common.auth
# ---------------------------------------------------------------------------
auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
make_token = auth.make_token
token_valid = auth.token_valid
require_teacher = auth.require_teacher


# ---------------------------------------------------------------------------
# Ρυθμίσεις AI (OpenAI-compatible — Alibaba Qwen από το .env.keys της πύλης)
# ---------------------------------------------------------------------------
def read_env_keys() -> dict[str, str]:
    """Διαβάζει το .env.keys της πύλης (ALIBABA_API_KEY/BASE_URL/PLAN_MODEL)."""
    out: dict[str, str] = {}
    if ENV_KEYS_FILE.is_file():
        try:
            for line in ENV_KEYS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip()
        except OSError:
            pass
    return out


def get_setting(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def ai_config() -> dict:
    """Ρυθμίσεις AI: οι τιμές του Studio υπερισχύουν, αλλιώς .env.keys/περιβάλλον."""
    env = read_env_keys()
    key = (get_setting("ai_api_key") or os.environ.get("ALIBABA_API_KEY")
           or env.get("ALIBABA_API_KEY", ""))
    base = (get_setting("ai_base_url") or os.environ.get("ALIBABA_BASE_URL")
            or env.get("ALIBABA_BASE_URL",
                       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"))
    model = (get_setting("ai_model") or os.environ.get("PLAN_MODEL")
             or env.get("PLAN_MODEL", "qwen-plus"))
    models = (env.get("AVAILABLE_MODELS", "") or model).split(",")
    return {"configured": bool(key), "key": key, "base_url": base.rstrip("/"),
            "model": model, "models": [m.strip() for m in models if m.strip()]}



# ---------------------------------------------------------------------------
# Βοηθητικά βιβλιοθηκών H5P (dependency closure, έγκυρο h5p.json)
# ---------------------------------------------------------------------------
_LIB_CACHE: dict[str, dict] = {}


def lib_json(folder: str) -> dict:
    if folder not in _LIB_CACHE:
        p = H5P_LIBS_DIR / folder / "library.json"
        if not p.is_file():
            raise HTTPException(500, f"Λείπει η τοπική βιβλιοθήκη H5P: {folder}")
        _LIB_CACHE[folder] = json.loads(p.read_text(encoding="utf-8"))
    return _LIB_CACHE[folder]


def dep_folder(dep: dict) -> str:
    return f"{dep['machineName']}-{dep['majorVersion']}.{dep['minorVersion']}"


def dep_ref(folder: str) -> dict:
    lj = lib_json(folder)
    return {"machineName": lj["machineName"],
            "majorVersion": str(lj["majorVersion"]),
            "minorVersion": str(lj["minorVersion"])}


def dependency_closure(root_folders: list[str]) -> list[str]:
    """Όλες οι preloaded βιβλιοθήκες (αναδρομικά), ταξινομημένες leaves-first."""
    seen: dict[str, None] = {}

    def visit(folder: str) -> None:
        if folder in seen:
            return
        lj = lib_json(folder)
        for dep in lj.get("preloadedDependencies", []):
            visit(dep_folder(dep))
        seen[folder] = None

    for f in root_folders:
        visit(f)
    return list(seen)


def build_h5p_json(title: str, main_folder: str, extra_roots: list[str]) -> dict:
    """Έγκυρο h5p.json με πλήρες flattened preloadedDependencies (όπως του Lumi)."""
    closure = dependency_closure([main_folder] + extra_roots)
    main = lib_json(main_folder)
    deps = [dep_ref(f) for f in closure]
    # Η κύρια βιβλιοθήκη πρέπει να είναι πρώτη (h5p-standalone convention)
    deps.sort(key=lambda d: 0 if d["machineName"] == main["machineName"] else 1)
    return {
        "title": title or "Δραστηριότητα H5P",
        "language": "el",
        "mainLibrary": main["machineName"],
        "embedTypes": ["div"],
        "license": "U",
        "defaultLanguage": "el",
        "preloadedDependencies": deps,
    }


def new_subcontent_id() -> str:
    return str(uuid.uuid4())


def image_params(path: str, mime: str, width: int = 0, height: int = 0) -> dict:
    p = {"path": path, "mime": mime, "copyright": {"license": "U"}}
    if width and height:
        p["width"], p["height"] = width, height
    return p


def image_subcontent(path: str, mime: str, alt: str = "", title: str = "") -> dict:
    return {"library": "H5P.Image 1.1",
            "params": {"file": image_params(path, mime), "alt": alt or title or "Εικόνα",
                       "title": title or alt or "Εικόνα", "decorative": False},
            "subContentId": new_subcontent_id(),
            "metadata": {"contentType": "Image", "title": title or "Εικόνα",
                         "license": "U"}}


def text_subcontent(html: str) -> dict:
    return {"library": "H5P.Text 1.1",
            "params": {"text": html if html.strip().startswith("<") else f"<p>{html}</p>"},
            "subContentId": new_subcontent_id(),
            "metadata": {"contentType": "Text", "license": "U"}}


def mc_subcontent(q: dict) -> dict:
    """Μία ερώτηση πολλαπλής επιλογής από απλή δομή του editor/AI."""
    answers = []
    for a in q.get("answers", []):
        answers.append({
            "text": f"<div>{a.get('text', '')}</div>",
            "correct": bool(a.get("correct")),
            "tipsAndFeedback": {
                "tip": a.get("tip", ""),
                "chosenFeedback": a.get("feedback", ""),
                "notChosenFeedback": "",
            },
        })
    params: dict = {
        "question": f"<p>{q.get('question', '')}</p>",
        "answers": answers,
        "behaviour": {
            "enableRetry": True, "enableSolutionsButton": True,
            "enableCheckButton": True, "type": "auto",
            "singlePoint": False, "randomAnswers": False,
            "showSolutionsRequiresInput": True, "confirmCheckDialog": False,
            "confirmRetryDialog": False, "autoCheck": False,
            "passPercentage": 100, "showScorePoints": True,
        },
        "UI": {
            "checkAnswerButton": "Έλεγχος",
            "submitAnswerButton": "Υποβολή",
            "showSolutionButton": "Εμφάνιση λύσης",
            "tryAgainButton": "Ξανά",
            "tipsLabel": "Εμφάνιση υπόδειξης",
            "scoreBarLabel": "Πέτυχες :num από :total βαθμούς",
            "tipAvailable": "Διαθέσιμη υπόδειξη",
            "feedbackAvailable": "Διαθέσιμη ανατροφοδότηση",
            "readFeedback": "Ανάγνωση ανατροφοδότησης",
            "wrongAnswer": "Λάθος απάντηση",
            "correctAnswer": "Σωστή απάντηση",
            "shouldCheck": "Έπρεπε να επιλεγεί",
            "shouldNotCheck": "Δεν έπρεπε να επιλεγεί",
            "noInput": "Απάντησε πριν δεις τη λύση",
            "a11yCheck": "Έλεγχος απαντήσεων.",
            "a11yShowSolution": "Εμφάνιση της σωστής λύσης.",
            "a11yRetry": "Επανάληψη της άσκησης από την αρχή.",
        },
        "overallFeedback": [{"from": 0, "to": 100, "feedback": ""}],
    }
    img = q.get("image")
    if img and img.get("path"):
        params["media"] = {
            "type": image_subcontent(img["path"], img.get("mime", "image/png"),
                                     img.get("alt", ""), q.get("question", "")[:60]),
            "disableImageZooming": False,
        }
    return {"library": "H5P.MultiChoice 1.16", "params": params,
            "subContentId": new_subcontent_id(),
            "metadata": {"contentType": "Multiple Choice", "license": "U",
                         "title": q.get("question", "")[:60]}}



# ---------------------------------------------------------------------------
# Μετατροπή απλής δομής editor/AI → content.json ανά τύπο H5P
# ---------------------------------------------------------------------------
def build_content(data: dict) -> tuple[str, dict, list[str]]:
    """Επιστρέφει (type, content.json params, extra_root_libraries)."""
    t = data.get("type", "multichoice")
    if t not in TYPE_LIBS:
        raise HTTPException(400, f"Άγνωστος τύπος δραστηριότητας: {t}")
    extra: list[str] = []

    if t == "multichoice":
        mc = mc_subcontent(data)
        return t, mc["params"], extra

    if t == "questionset":
        questions = [mc_subcontent(q) for q in data.get("questions", [])]
        if not questions:
            raise HTTPException(400, "Το Σετ Ερωτήσεων χρειάζεται τουλάχιστον 1 ερώτηση.")
        params = {
            "introPage": {"showIntroPage": bool(data.get("showIntro", True)),
                          "title": data.get("title", "Σετ Ερωτήσεων"),
                          "introduction": data.get("intro", ""),
                          "startButtonText": "Έναρξη"},
            "progressType": "dots",
            "passPercentage": int(data.get("passPercentage", 50)),
            "questions": questions,
            "disableBackwardsNavigation": False,
            "randomQuestions": False,
            "endGame": {
                "showResultPage": True, "showSolutionButton": True,
                "showRetryButton": True,
                "noResultMessage": "Ολοκληρώθηκε!",
                "message": "Το αποτέλεσμά σου:",
                "scoreBarLabel": "Πέτυχες :num από :total βαθμούς",
                "overallFeedback": [{"from": 0, "to": 100, "feedback": ""}],
                "solutionButtonText": "Εμφάνιση λύσης",
                "retryButtonText": "Ξανά",
                "finishButtonText": "Τέλος",
                "submitButtonText": "Υποβολή",
                "showAnimations": False, "skippable": False,
                "skipButtonText": "Παράλειψη βίντεο",
            },
            "override": {"checkButton": True},
            "texts": {
                "prevButton": "Προηγούμενη", "nextButton": "Επόμενη",
                "finishButton": "Τέλος", "submitButton": "Υποβολή",
                "textualProgress": "Ερώτηση :current από :total",
                "jumpToQuestion": "Μετάβαση στην ερώτηση %d",
                "questionLabel": "Ερώτηση",
                "readSpeakerProgress": "Ερώτηση :current από :total",
                "unansweredText": "Αναπάντητη", "answeredText": "Απαντημένη",
                "currentQuestionText": "Τρέχουσα ερώτηση",
                "navigationLabel": "Ερωτήσεις",
            },
        }
        # Οι βιβλιοθήκες των επιμέρους ερωτήσεων φορτώνονται δυναμικά από το
        # QuestionSet — πρέπει να δηλωθούν στο preloadedDependencies του h5p.json.
        extra = sorted({TYPE_LIBS["multichoice"]})
        return t, params, extra

    if t == "blanks":
        questions = data.get("questions", [])
        if isinstance(questions, str):
            questions = [questions]
        questions = [q if q.strip().startswith("<") else f"<p>{q}</p>"
                     for q in questions if q.strip()]
        if not questions:
            raise HTTPException(400, "Χρειάζεται τουλάχιστον μία πρόταση με *κενά*.")
        params = {
            "text": data.get("text", "<p>Συμπλήρωσε τα κενά στις παρακάτω προτάσεις.</p>"),
            "questions": questions,
            "behaviour": {
                "enableRetry": True, "enableSolutionsButton": True,
                "enableCheckButton": True, "autoCheck": False,
                "caseSensitive": False, "showSolutionsRequiresInput": True,
                "separateLines": True, "confirmCheckDialog": False,
                "confirmRetryDialog": False, "acceptSpellingErrors": False,
            },
            "showSolutions": "Εμφάνιση λύσης", "tryAgain": "Ξανά",
            "checkAnswer": "Έλεγχος", "submitAnswer": "Υποβολή",
            "notFilledOut": "Συμπλήρωσε όλα τα κενά",
            "answerIsCorrect": "Το ':ans' είναι σωστό",
            "answerIsWrong": "Το ':ans' είναι λάθος",
            "answeredCorrectly": "Απάντησες σωστά",
            "answeredIncorrectly": "Απάντησες λάθος",
            "solutionLabel": "Σωστή απάντηση:",
            "inputLabel": "Κενό @num από @total",
            "inputHasTipLabel": "Διαθέσιμη υπόδειξη", "tipLabel": "Υπόδειξη",
            "overallFeedback": [{"from": 0, "to": 100, "feedback": ""}],
            "scoreBarLabel": "Πέτυχες :num από :total βαθμούς",
        }
        img = data.get("image")
        if img and img.get("path"):
            params["media"] = {
                "type": image_subcontent(img["path"], img.get("mime", "image/png")),
                "disableImageZooming": False}
        return t, params, extra


    if t == "dragtext":
        text_field = data.get("textField", "")
        if not text_field.strip():
            raise HTTPException(400, "Χρειάζεται κείμενο με *λέξεις* προς σύρσιμο.")
        params = {
            "taskDescription": data.get("taskDescription",
                                        "<p>Σύρε τις λέξεις στη σωστή θέση.</p>"),
            "textField": text_field,
            "distractors": data.get("distractors", ""),
            "behaviour": {"enableRetry": True, "enableSolutionsButton": True,
                          "enableCheckButton": True, "instantFeedback": False},
            "overallFeedback": [{"from": 0, "to": 100, "feedback": ""}],
            "checkAnswer": "Έλεγχος", "submitAnswer": "Υποβολή",
            "tryAgain": "Ξανά", "showSolution": "Εμφάνιση λύσης",
            "dropZoneIndex": "Θέση @index.",
            "empty": "Η θέση @index είναι κενή.",
            "contains": "Η θέση @index περιέχει τη λέξη @draggable.",
            "ariaDraggableIndex": "@index από @count λέξεις.",
            "tipLabel": "Εμφάνιση υπόδειξης",
            "correctText": "Σωστό!", "incorrectText": "Λάθος!",
            "resetDropTitle": "Αφαίρεση λέξης",
            "resetDropDescription": "Σίγουρα θέλεις να αφαιρέσεις τη λέξη;",
            "grabbed": "Η λέξη επιλέχθηκε.",
            "cancelledDragging": "Ακύρωση μεταφοράς.",
            "correctAnswer": "Σωστή απάντηση:",
            "feedbackHeader": "Ανατροφοδότηση",
            "scoreBarLabel": "Πέτυχες :num από :total βαθμούς",
        }
        return t, params, extra

    if t == "hotspots":
        img = data.get("image") or {}
        if not img.get("path"):
            raise HTTPException(400, "Ανέβασε πρώτα μια εικόνα για τα hotspots.")
        hotspots = []
        for h in data.get("hotspots", []):
            hotspots.append({
                "position": {"x": float(h.get("x", 50)), "y": float(h.get("y", 50)),
                             "legacyPositioning": False},
                "alwaysFullscreen": False,
                "header": h.get("header", ""),
                "content": [text_subcontent(h.get("content", ""))],
            })
        if not hotspots:
            raise HTTPException(400, "Πρόσθεσε τουλάχιστον μία πινέζα (hotspot).")
        params = {
            "image": image_params(img["path"], img.get("mime", "image/png"),
                                  int(img.get("width", 0)), int(img.get("height", 0))),
            "backgroundImageAltText": data.get("imageAlt", "Εικόνα δραστηριότητας"),
            "iconType": "icon",
            "icon": data.get("icon", "plus"),
            "color": data.get("color", "#981d99"),
            "hotspots": hotspots,
            "hotspotNumberLabel": "Hotspot #num",
            "closeButtonLabel": "Κλείσιμο",
        }
        extra = ["H5P.Text-1.1"]
        return t, params, extra

    if t == "dialogcards":
        dialogs = []
        for c in data.get("cards", []):
            d: dict = {
                "text": f"<p>{c.get('front', '')}</p>",
                "answer": f"<p>{c.get('back', '')}</p>",
                "tips": {"tip": c.get("tip", "")},
            }
            img = c.get("image")
            if img and img.get("path"):
                d["image"] = image_params(img["path"], img.get("mime", "image/png"))
                d["imageAltText"] = c.get("imageAlt", c.get("front", "Εικόνα")[:80])
            dialogs.append(d)
        if not dialogs:
            raise HTTPException(400, "Χρειάζεται τουλάχιστον μία κάρτα.")
        params = {
            "title": data.get("title", "Κάρτες Μνήμης"),
            "description": data.get("description",
                                    "<p>Πάτησε την κάρτα για να δεις την απάντηση.</p>"),
            "mode": "normal",
            "dialogs": dialogs,
            "behaviour": {"enableRetry": True, "disableBackwardsNavigation": False,
                          "scaleTextNotCard": False, "randomCards": False,
                          "maxProficiency": 5, "quickProgression": False},
            "answer": "Ήξερα την απάντηση", "next": "Επόμενη", "prev": "Προηγούμενη",
            "retry": "Ξανά", "correctAnswer": "Το ήξερα!",
            "incorrectAnswer": "Δεν το ήξερα",
            "round": "Γύρος @round", "cardsLeft": "Κάρτες που απομένουν: @number",
            "nextRound": "Επόμενος γύρος", "startOver": "Από την αρχή",
            "showSummary": "Επόμενη", "summary": "Σύνοψη",
            "summaryCardsRight": "Κάρτες που ήξερες:",
            "summaryCardsWrong": "Κάρτες που δεν ήξερες:",
            "summaryCardsNotShown": "Κάρτες που δεν εμφανίστηκαν:",
            "summaryOverallScore": "Συνολικό σκορ",
            "summaryCardsCompleted": "Ολοκληρωμένες κάρτες:",
            "summaryCompletedRounds": "Ολοκληρωμένοι γύροι:",
            "summaryAllDone": "Τέλεια! Τις έμαθες όλες!",
            "progressText": "Κάρτα @card από @total",
            "cardFrontLabel": "Εμπρός όψη", "cardBackLabel": "Πίσω όψη",
            "tipButtonLabel": "Υπόδειξη",
            "audioNotSupported": "Ο browser δεν υποστηρίζει ήχο",
            "confirmStartingOver": {"header": "Από την αρχή;",
                                    "body": "Όλη η πρόοδος θα χαθεί. Σίγουρα;",
                                    "cancelLabel": "Άκυρο", "confirmLabel": "Ναι"},
        }
        return t, params, extra


    if t == "video":
        video = data.get("video") or {}
        if not video.get("path"):
            raise HTTPException(400, "Επίλεξε ή ανέβασε ένα αρχείο βίντεο (.mp4/.webm).")
        interactions = []
        for it in data.get("interactions", []):
            start = float(it.get("time", 0))
            kind = it.get("kind", "text")
            if kind == "mc":
                action = mc_subcontent(it)
            else:
                action = text_subcontent(it.get("text", ""))
            interactions.append({
                "x": 10, "y": 10, "width": 80, "height": 80,
                "duration": {"from": start, "to": start + float(it.get("duration", 10))},
                "pause": bool(it.get("pause", True)),
                "displayType": "poster",
                "buttonOnMobile": True,
                "label": f"<p>{it.get('label', '')}</p>",
                "libraryTitle": action["library"].split(" ")[0],
                "action": action,
                "adaptivity": {
                    "correct": {"allowOptOut": True, "message": "", "seekLabel": "Συνέχεια"},
                    "wrong": {"allowOptOut": True, "message": "", "seekLabel": "Συνέχεια"},
                    "requireCompletion": False,
                },
                "visuals": {"backgroundColor": "rgb(255, 255, 255)",
                            "boxShadow": "0px 0px 20px rgba(0,0,0,0.3)"},
            })
        params = {
            "interactiveVideo": {
                "video": {
                    "files": [{"path": video["path"],
                               "mime": video.get("mime", "video/mp4"),
                               "copyright": {"license": "U"}}],
                    "startScreenOptions": {
                        "title": data.get("title", "Διαδραστικό Βίντεο"),
                        "hideStartTitle": False,
                        "shortStartDescription": data.get("description", ""),
                    },
                    "textTracks": {"videoTrack": [], "defaultTrackLabel": ""},
                },
                "assets": {
                    "interactions": interactions,
                    "bookmarks": [{"time": float(b.get("time", 0)),
                                   "label": b.get("label", "")}
                                  for b in data.get("bookmarks", [])],
                    "endscreens": [],
                },
                "summary": {"task": {"library": "H5P.Summary 1.10",
                                     "params": {}, "subContentId": new_subcontent_id()},
                            "displayAt": 3},
            },
            "override": {"autoplay": False, "loop": False,
                         "showBookmarksmenuOnLoad": False, "showRewind10": True,
                         "deactivateSound": False},
            "l10n": {
                "interaction": "Διαδραστικότητα", "play": "Αναπαραγωγή",
                "pause": "Παύση", "mute": "Σίγαση", "unmute": "Ήχος",
                "quality": "Ποιότητα", "captions": "Υπότιτλοι",
                "close": "Κλείσιμο", "fullscreen": "Πλήρης οθόνη",
                "exitFullscreen": "Έξοδος πλήρους οθόνης",
                "summary": "Σύνοψη", "bookmarks": "Σελιδοδείκτες",
                "endscreen": "Τέλος", "defaultAdaptivitySeekLabel": "Συνέχεια",
                "continueWithVideo": "Συνέχεια του βίντεο", "more": "Περισσότερα",
                "playbackRate": "Ταχύτητα", "rewind10": "10 δευτ. πίσω",
                "navDisabled": "Η πλοήγηση είναι απενεργοποιημένη",
                "navForwardDisabled": "Η μετακίνηση μπροστά είναι απενεργοποιημένη",
                "sndDisabled": "Ο ήχος είναι απενεργοποιημένος",
                "requiresCompletionWarning": "Πρέπει να απαντήσεις σωστά για να συνεχίσεις.",
                "back": "Πίσω", "hours": "Ώρες", "minutes": "Λεπτά",
                "seconds": "Δευτερόλεπτα", "currentTime": "Τρέχων χρόνος:",
                "totalTime": "Συνολικός χρόνος:",
                "singleInteractionAnnouncement": "Εμφανίστηκε διαδραστικότητα:",
                "multipleInteractionsAnnouncement": "Εμφανίστηκαν διαδραστικότητες.",
                "videoPausedAnnouncement": "Το βίντεο βρίσκεται σε παύση",
                "content": "Περιεχόμενο", "answered": "@answered απαντημένες",
            },
        }
        # Οι βιβλιοθήκες των interactions (Text/MultiChoice) φορτώνονται
        # δυναμικά — δηλώνονται στο preloadedDependencies του h5p.json.
        extra = ["H5P.Text-1.1", "H5P.Summary-1.10", TYPE_LIBS["multichoice"]]
        return t, params, extra

    raise HTTPException(400, f"Άγνωστος τύπος: {t}")



# ---------------------------------------------------------------------------
# Αποθήκευση δραστηριότητας στον δίσκο (library/<id>/) + βάση
# ---------------------------------------------------------------------------
def activity_dir(aid: str) -> Path:
    if not ID_RE.match(aid):
        raise HTTPException(400, "Μη έγκυρο id δραστηριότητας.")
    return LIBRARY_DIR / aid


def get_activity_row(aid: str) -> sqlite3.Row:
    with db() as conn:
        row = conn.execute("SELECT * FROM activities WHERE id=?", (aid,)).fetchone()
    if not row:
        raise HTTPException(404, "Η δραστηριότητα δεν βρέθηκε.")
    return row


def save_activity_files(aid: str, title: str, main_folder: str,
                        content_params: dict, extra_roots: list[str]) -> None:
    """Γράφει h5p.json + content/content.json (τα media υπάρχουν ήδη)."""
    adir = activity_dir(aid)
    (adir / "content").mkdir(parents=True, exist_ok=True)
    h5pj = build_h5p_json(title, main_folder, extra_roots)
    (adir / "h5p.json").write_text(json.dumps(h5pj, ensure_ascii=False),
                                   encoding="utf-8")
    (adir / "content" / "content.json").write_text(
        json.dumps(content_params, ensure_ascii=False), encoding="utf-8")


def upsert_activity(aid: str, title: str, atype: str, main_lib: str,
                    meta: dict) -> None:
    now = time.time()
    with db() as conn:
        conn.execute(
            """INSERT INTO activities(id,title,type,main_lib,class_slug,subject,
                                      chapter,goal,difficulty,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, type=excluded.type, main_lib=excluded.main_lib,
                 class_slug=excluded.class_slug, subject=excluded.subject,
                 chapter=excluded.chapter, goal=excluded.goal,
                 difficulty=excluded.difficulty, updated_at=excluded.updated_at""",
            (aid, title, atype, main_lib,
             meta.get("class_slug", ""), meta.get("subject", ""),
             meta.get("chapter", ""), meta.get("goal", ""),
             meta.get("difficulty", ""), now, now))


def new_activity_id() -> str:
    return "act-" + secrets.token_hex(5)


MEDIA_PATH_RE = re.compile(r"^(images|videos|audios)/[A-Za-z0-9._-]+$")


def transfer_preview_media(aid: str, data) -> None:
    """Αντιγράφει αναδρομικά κάθε media path του preview-tmp/content/ στον
    μόνιμο φάκελο της νέας δραστηριότητας (τα σχετικά paths παραμένουν ίδια)."""
    src_root = activity_dir(PREVIEW_ID) / "content"
    dst_root = activity_dir(aid) / "content"

    def walk(node):
        if isinstance(node, dict):
            p = node.get("path")
            if isinstance(p, str) and MEDIA_PATH_RE.match(p):
                src = src_root / p
                if src.is_file():
                    dst = dst_root / p
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        shutil.copy2(src, dst)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)


def read_editor_state(aid: str) -> dict | None:
    """Η απλή δομή του editor αποθηκεύεται στο content/editor-state.json."""
    p = activity_dir(aid) / "content" / "editor-state.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def save_editor_state(aid: str, data: dict) -> None:
    p = activity_dir(aid) / "content" / "editor-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")



# ---------------------------------------------------------------------------
# Αντίστροφη μετατροπή: content.json → απλή δομή editor (για επεξεργασία)
# ---------------------------------------------------------------------------
def strip_html(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "")
    s = re.sub(r"</p>\s*<p[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").strip()


def mc_from_params(params: dict) -> dict:
    q: dict = {"question": strip_html(params.get("question", "")),
               "answers": []}
    for a in params.get("answers", []):
        q["answers"].append({
            "text": strip_html(a.get("text", "")),
            "correct": bool(a.get("correct")),
            "tip": (a.get("tipsAndFeedback") or {}).get("tip", ""),
            "feedback": (a.get("tipsAndFeedback") or {}).get("chosenFeedback", ""),
        })
    media_type = ((params.get("media") or {}).get("type") or {})
    f = (media_type.get("params") or {}).get("file") or {}
    if f.get("path"):
        q["image"] = {"path": f["path"], "mime": f.get("mime", "image/png"),
                      "alt": (media_type.get("params") or {}).get("alt", "")}
    return q


def editor_state_from_content(atype: str, params: dict, title: str) -> dict:
    """Καλύτερη δυνατή ανάκτηση της απλής δομής από υπάρχον content.json."""
    st: dict = {"type": atype, "title": title}
    if atype == "multichoice":
        st.update(mc_from_params(params))
    elif atype == "questionset":
        st["intro"] = (params.get("introPage") or {}).get("introduction", "")
        st["passPercentage"] = params.get("passPercentage", 50)
        st["questions"] = [mc_from_params(q.get("params", {}))
                           for q in params.get("questions", [])
                           if q.get("library", "").startswith("H5P.MultiChoice")]
    elif atype == "blanks":
        st["text"] = params.get("text", "")
        st["questions"] = params.get("questions", [])
    elif atype == "dragtext":
        st["taskDescription"] = params.get("taskDescription", "")
        st["textField"] = params.get("textField", "")
        st["distractors"] = params.get("distractors", "")
    elif atype == "hotspots":
        img = params.get("image") or {}
        st["image"] = {"path": img.get("path", ""), "mime": img.get("mime", "image/png"),
                       "width": img.get("width", 0), "height": img.get("height", 0)}
        st["color"] = params.get("color", "#981d99")
        st["icon"] = params.get("icon", "plus")
        st["hotspots"] = []
        for h in params.get("hotspots", []):
            texts = [strip_html((c.get("params") or {}).get("text", ""))
                     for c in h.get("content", [])
                     if c.get("library", "").startswith("H5P.Text")]
            st["hotspots"].append({
                "x": (h.get("position") or {}).get("x", 50),
                "y": (h.get("position") or {}).get("y", 50),
                "header": h.get("header", ""),
                "content": "\n".join(t for t in texts if t),
            })
    elif atype == "dialogcards":
        st["description"] = params.get("description", "")
        st["cards"] = []
        for d in params.get("dialogs", []):
            card = {"front": strip_html(d.get("text", "")),
                    "back": strip_html(d.get("answer", "")),
                    "tip": (d.get("tips") or {}).get("tip", "")}
            if (d.get("image") or {}).get("path"):
                card["image"] = {"path": d["image"]["path"],
                                 "mime": d["image"].get("mime", "image/png")}
            st["cards"].append(card)
    elif atype == "video":
        iv = params.get("interactiveVideo") or {}
        files = ((iv.get("video") or {}).get("files") or [{}])
        st["video"] = {"path": files[0].get("path", ""),
                       "mime": files[0].get("mime", "video/mp4")}
        sso = (iv.get("video") or {}).get("startScreenOptions") or {}
        st["title"] = sso.get("title", title)
        st["description"] = sso.get("shortStartDescription", "")
        st["interactions"] = []
        for it in (iv.get("assets") or {}).get("interactions", []):
            action = it.get("action") or {}
            entry = {"time": (it.get("duration") or {}).get("from", 0),
                     "pause": bool(it.get("pause", True)),
                     "label": strip_html(it.get("label", ""))}
            if action.get("library", "").startswith("H5P.MultiChoice"):
                entry.update(mc_from_params(action.get("params", {})))
                entry["kind"] = "mc"
            else:
                entry["kind"] = "text"
                entry["text"] = strip_html((action.get("params") or {}).get("text", ""))
            st["interactions"].append(entry)
    return st



# ---------------------------------------------------------------------------
# Σελίδες (Jinja2 templates)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "logged_in": token_valid(request.cookies.get(COOKIE_NAME)),
        "classes": CLASS_GROUPS, "subjects": SUBJECTS,
        "type_labels": TYPE_LABELS, "type_icons": TYPE_ICONS,
    })


@app.get("/edit/{aid}", response_class=HTMLResponse)
def edit_page(request: Request, aid: str):
    if not token_valid(request.cookies.get(COOKIE_NAME)):
        return templates.TemplateResponse(request, "index.html", {
            "logged_in": False, "classes": CLASS_GROUPS, "subjects": SUBJECTS,
            "type_labels": TYPE_LABELS, "type_icons": TYPE_ICONS,
            "login_hint": "Συνδέσου με τον κωδικό καθηγητή για επεξεργασία.",
        })
    if aid == "new":
        # Νέα δραστηριότητα από draft (AI wizard / hotspots / video) —
        # τα δεδομένα έρχονται από το sessionStorage του browser.
        title, atype = "Νέα Δραστηριότητα", ""
    else:
        row = get_activity_row(aid)
        title, atype = row["title"], row["type"]
    return templates.TemplateResponse(request, "editor.html", {
        "activity_id": aid, "title": title, "atype": atype,
        "classes": CLASS_GROUPS, "subjects": SUBJECTS,
        "type_labels": TYPE_LABELS,
    })


@app.get("/play/preview-tmp/", response_class=HTMLResponse)
def preview_page(request: Request):
    """Προσωρινή προεπισκόπηση του Visual Editor — μόνο για καθηγητή."""
    require_teacher(request)
    if not (activity_dir(PREVIEW_ID) / "h5p.json").is_file():
        raise HTTPException(404, "Δεν υπάρχει προεπισκόπηση ακόμη.")
    return templates.TemplateResponse(request, "play.html", {
        "activity_id": PREVIEW_ID, "title": "Προεπισκόπηση", "embed": True,
        "type_label": "Προεπισκόπηση",
    })


@app.get("/play/{aid}/", response_class=HTMLResponse)
def play_page(request: Request, aid: str):
    row = get_activity_row(aid)
    adir = activity_dir(aid)
    if not (adir / "h5p.json").is_file():
        raise HTTPException(404, "Η δραστηριότητα δεν βρέθηκε στο δίσκο.")
    # embed=1 → καθαρή σελίδα για <iframe> (χωρίς μπάρα επιστροφής)
    embed = request.query_params.get("embed") == "1"
    return templates.TemplateResponse(request, "play.html", {
        "activity_id": aid, "title": row["title"], "embed": embed,
        "type_label": TYPE_LABELS.get(row["type"], row["type"]),
    })


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "school-h5p"}


# ---------------------------------------------------------------------------
# API — Login/Logout καθηγητή
# ---------------------------------------------------------------------------
class Login(BaseModel):
    password: str


@app.post("/api/login")
def login(body: Login, response: Response):
    # Σύγκριση σε bytes ώστε να λειτουργεί και με μη-ASCII (ελληνικούς) κωδικούς
    if not hmac.compare_digest(body.password.encode("utf-8"), TEACHER_CODE.encode("utf-8")):
        raise HTTPException(401, "Λάθος κωδικός καθηγητή.")
    response.set_cookie(COOKIE_NAME, make_token(), max_age=COOKIE_MAX_AGE,
                        httponly=True, samesite="lax", path="/")
    return {"ok": True}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}



# ---------------------------------------------------------------------------
# API — Βιβλιοθήκη δραστηριοτήτων
# ---------------------------------------------------------------------------
@app.get("/api/activities")
def api_activities(request: Request, class_slug: str = "", subject: str = ""):
    sql = "SELECT * FROM activities WHERE 1=1"
    args: list = []
    if class_slug:
        sql += " AND class_slug=?"
        args.append(class_slug)
    if subject:
        sql += " AND subject=?"
        args.append(subject)
    sql += " ORDER BY updated_at DESC"
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    teacher = token_valid(request.cookies.get(COOKIE_NAME))
    out = []
    for r in rows:
        d = dict(r)
        d["type_label"] = TYPE_LABELS.get(r["type"], r["type"])
        d["type_icon"] = TYPE_ICONS.get(r["type"], "📦")
        d["class_label"] = CLASS_LABELS.get(r["class_slug"], "")
        d["editable"] = teacher and r["type"] != "external"
        out.append(d)
    return {"activities": out, "teacher": teacher}


class CreateActivity(BaseModel):
    type: str
    title: str = Field(min_length=1, max_length=200)
    class_slug: str = ""
    subject: str = ""
    chapter: str = ""
    goal: str = ""
    difficulty: str = ""
    data: dict = Field(default_factory=dict)


@app.post("/api/activities")
def api_create(request: Request, body: CreateActivity):
    require_teacher(request)
    if body.type not in TYPE_LIBS:
        raise HTTPException(400, "Άγνωστος τύπος δραστηριότητας.")
    aid = new_activity_id()
    data = dict(body.data)
    data["type"] = body.type
    data.setdefault("title", body.title)
    # Νέα δραστηριότητα από τον editor: τα media ανέβηκαν στο preview-tmp/ —
    # μεταφέρονται στον μόνιμο φάκελο πριν το χτίσιμο του content.json.
    transfer_preview_media(aid, data)
    atype, params, extra = build_content(data)
    main_folder = TYPE_LIBS[atype]
    save_activity_files(aid, body.title, main_folder, params, extra)
    save_editor_state(aid, data)
    lj = lib_json(main_folder)
    upsert_activity(aid, body.title, atype,
                    f"{lj['machineName']} {lj['majorVersion']}.{lj['minorVersion']}",
                    body.model_dump())
    return {"ok": True, "id": aid}


@app.get("/api/activities/{aid}")
def api_get_activity(request: Request, aid: str):
    require_teacher(request)
    if aid == PREVIEW_ID:
        raise HTTPException(400, "Χρησιμοποίησε το /api/preview.")
    row = get_activity_row(aid)
    state = read_editor_state(aid)
    if state is None:
        cpath = activity_dir(aid) / "content" / "content.json"
        params = json.loads(cpath.read_text(encoding="utf-8"))
        state = editor_state_from_content(row["type"], params, row["title"])
    return {"meta": dict(row), "data": state}


class UpdateActivity(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    class_slug: str = ""
    subject: str = ""
    chapter: str = ""
    goal: str = ""
    difficulty: str = ""
    data: dict


@app.put("/api/activities/{aid}")
def api_update(request: Request, aid: str, body: UpdateActivity):
    require_teacher(request)
    row = get_activity_row(aid)
    if row["type"] == "external":
        raise HTTPException(400, "Τα εξωτερικά .h5p δεν επεξεργάζονται στον Visual Editor "
                                 "(μόνο αναπαραγωγή/export).")
    data = dict(body.data)
    data["type"] = row["type"]
    data.setdefault("title", body.title)
    atype, params, extra = build_content(data)
    save_activity_files(aid, body.title, TYPE_LIBS[atype], params, extra)
    save_editor_state(aid, data)
    upsert_activity(aid, body.title, atype, row["main_lib"], body.model_dump())
    return {"ok": True, "id": aid}


@app.delete("/api/activities/{aid}")
def api_delete(request: Request, aid: str):
    require_teacher(request)
    if aid == PREVIEW_ID:
        raise HTTPException(400, "Δεν διαγράφεται η προσωρινή προεπισκόπηση.")
    get_activity_row(aid)
    adir = activity_dir(aid)
    shutil.rmtree(adir, ignore_errors=True)
    with db() as conn:
        conn.execute("DELETE FROM activities WHERE id=?", (aid,))
    return {"ok": True}



# ---------------------------------------------------------------------------
# API — Preview (προσωρινή δραστηριότητα για ζωντανή προεπισκόπηση editor)
# ---------------------------------------------------------------------------
PREVIEW_ID = "preview-tmp"


@app.post("/api/preview")
def api_preview(request: Request, body: dict):
    """Χτίζει content.json σε library/preview-tmp/ για το iframe προεπισκόπησης.
    Τα media πρέπει να έχουν ανέβει ήδη μέσω /api/upload (στο ίδιο tmp folder)."""
    require_teacher(request)
    data = dict(body.get("data") or {})
    title = body.get("title") or "Προεπισκόπηση"
    atype, params, extra = build_content(data)
    save_activity_files(PREVIEW_ID, title, TYPE_LIBS[atype], params, extra)
    return {"ok": True, "id": PREVIEW_ID}


# ---------------------------------------------------------------------------
# API — Ανέβασμα media (εικόνες/βίντεο) σε δραστηριότητα ή στο preview-tmp
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp"}
VIDEO_EXTS = {".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg"}


@app.post("/api/upload/{aid}")
async def api_upload(request: Request, aid: str, file: UploadFile = File(...)):
    require_teacher(request)
    if aid != PREVIEW_ID:
        get_activity_row(aid)
    name = Path(file.filename or "file").name
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXTS:
        subdir, mime = "images", IMAGE_EXTS[ext]
    elif ext in VIDEO_EXTS:
        subdir, mime = "videos", VIDEO_EXTS[ext]
    else:
        raise HTTPException(400, "Επιτρέπονται μόνο εικόνες (png/jpg/gif/svg/webp) "
                                 "και βίντεο (mp4/webm/ogv).")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 100 MB.")
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", Path(name).stem)[:40] or "media"
    rel = f"{subdir}/{safe}-{secrets.token_hex(4)}{ext}"
    dest = activity_dir(aid) / "content" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    result = {"ok": True, "path": rel, "mime": mime}
    if ext in IMAGE_EXTS and ext != ".svg":
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                result["width"], result["height"] = im.size
        except Exception:
            pass
    return result


@app.get("/api/videos")
def api_videos(request: Request):
    """Λίστα υπαρχόντων βίντεο στα docs/assets/videos/ & docs/videos/ του MkDocs."""
    require_teacher(request)
    out = []
    for vdir in VIDEOS_DIRS:
        if vdir.is_dir():
            for p in sorted(vdir.rglob("*")):
                if p.suffix.lower() in VIDEO_EXTS and p.is_file():
                    rel = p.relative_to(DOCS_DIR).as_posix()
                    out.append({"path": rel, "name": p.name,
                                "size_mb": round(p.stat().st_size / 1048576, 1),
                                "docs_url": "/docs/" + rel})
    return {"videos": out}


class PickVideo(BaseModel):
    docs_path: str


@app.post("/api/pick-video/{aid}")
def api_pick_video(request: Request, aid: str, body: PickVideo):
    """Αντιγραφή υπάρχοντος βίντεο από τα docs/ στη δραστηριότητα (offline player)."""
    require_teacher(request)
    if aid != PREVIEW_ID:
        get_activity_row(aid)
    rel = body.docs_path.strip().lstrip("/")
    src = (DOCS_DIR / rel).resolve()
    if (not str(src).startswith(str(DOCS_DIR.resolve()) + "/")
            or src.suffix.lower() not in VIDEO_EXTS or not src.is_file()):
        raise HTTPException(400, "Μη έγκυρη διαδρομή βίντεο.")
    dest_rel = f"videos/{src.stem[:40]}-{secrets.token_hex(4)}{src.suffix.lower()}"
    dest = activity_dir(aid) / "content" / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return {"ok": True, "path": dest_rel,
            "mime": VIDEO_EXTS[src.suffix.lower()]}



# ---------------------------------------------------------------------------
# API — Import εξωτερικού .h5p (Lumi Desktop / Φωτόδεντρο / h5p.org)
# ---------------------------------------------------------------------------
def validate_h5p_zip(zf: zipfile.ZipFile) -> dict:
    """Επικύρωση δομής: h5p.json + content/content.json + βιβλιοθήκες."""
    names = zf.namelist()
    if any(n.startswith("/") or ".." in PurePosixPath(n).parts for n in names):
        raise HTTPException(400, "Μη ασφαλές αρχείο .h5p (path traversal).")
    if "h5p.json" not in names:
        raise HTTPException(400, "Μη έγκυρο .h5p: λείπει το h5p.json στη ρίζα.")
    try:
        h5pj = json.loads(zf.read("h5p.json").decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Μη έγκυρο h5p.json (σφάλμα JSON).")
    main = h5pj.get("mainLibrary", "")
    deps = h5pj.get("preloadedDependencies", [])
    if not main or not isinstance(deps, list) or not deps:
        raise HTTPException(400, "Μη έγκυρο h5p.json: λείπει mainLibrary/preloadedDependencies.")
    if not any(d.get("machineName") == main for d in deps):
        raise HTTPException(400, "Η κύρια βιβλιοθήκη δεν υπάρχει στα preloadedDependencies.")
    if "content/content.json" not in names:
        raise HTTPException(400, "Μη έγκυρο .h5p: λείπει το content/content.json.")
    try:
        json.loads(zf.read("content/content.json").decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Μη έγκυρο content/content.json (σφάλμα JSON).")
    # Κάθε preloaded βιβλιοθήκη πρέπει να υπάρχει είτε στο πακέτο είτε τοπικά
    local = {d.name for d in H5P_LIBS_DIR.iterdir() if d.is_dir()}
    missing = []
    for d in deps:
        folder = f"{d.get('machineName')}-{d.get('majorVersion')}.{d.get('minorVersion')}"
        if f"{folder}/library.json" not in names and folder not in local:
            missing.append(folder)
    if missing:
        raise HTTPException(400, "Λείπουν βιβλιοθήκες από το πακέτο: "
                                 + ", ".join(missing[:5]))
    return h5pj


@app.post("/api/import")
async def api_import(request: Request, file: UploadFile = File(...),
                     class_slug: str = Form(""), subject: str = Form("")):
    require_teacher(request)
    if not (file.filename or "").lower().endswith(".h5p"):
        raise HTTPException(400, "Επίλεξε αρχείο με κατάληξη .h5p")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Το αρχείο ξεπερνά τα 100 MB.")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(400, "Το αρχείο δεν είναι έγκυρο ZIP/.h5p.")
    with zf:
        h5pj = validate_h5p_zip(zf)
        aid = new_activity_id()
        adir = activity_dir(aid)
        adir.mkdir(parents=True, exist_ok=True)
        try:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = (adir / info.filename).resolve()
                if not str(target).startswith(str(adir.resolve()) + "/"):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
        except Exception:
            shutil.rmtree(adir, ignore_errors=True)
            raise
    title = h5pj.get("title") or Path(file.filename).stem
    main = h5pj["mainLibrary"]
    dep = next(d for d in h5pj["preloadedDependencies"]
               if d.get("machineName") == main)
    main_lib = f"{main} {dep.get('majorVersion')}.{dep.get('minorVersion')}"
    atype = LIB_TYPE.get(main, "external")
    upsert_activity(aid, title, atype if atype != "external" else "external",
                    main_lib, {"class_slug": class_slug, "subject": subject})
    return {"ok": True, "id": aid, "title": title, "type": atype,
            "play_url": f"/h5p-studio/play/{aid}/"}


# ---------------------------------------------------------------------------
# API — Export σε επίσημο .h5p (με όλες τις βιβλιοθήκες μέσα, όπως του Lumi)
# ---------------------------------------------------------------------------
@app.get("/api/export/{aid}")
def api_export(request: Request, aid: str):
    row = get_activity_row(aid)
    adir = activity_dir(aid)
    h5pj = json.loads((adir / "h5p.json").read_text(encoding="utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) Περιεχόμενο δραστηριότητας (χωρίς editor-state & τυχόν τοπικές βιβλ.)
        for p in sorted(adir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(adir).as_posix()
            if rel == "content/editor-state.json":
                continue
            if LIBDIR_RE.match(rel.split("/")[0]):
                continue                      # οι βιβλιοθήκες μπαίνουν παρακάτω
            zf.write(p, rel)
        # 2) Όλες οι απαιτούμενες βιβλιοθήκες (από το πακέτο ή τα τοπικά assets)
        added: set[str] = set()
        for dep in h5pj.get("preloadedDependencies", []):
            folder = dep_folder(dep)
            src = adir / folder
            if not src.is_dir():
                src = H5P_LIBS_DIR / folder
            if not src.is_dir():
                continue
            for p in sorted(src.rglob("*")):
                if p.is_file():
                    arc = f"{folder}/{p.relative_to(src).as_posix()}"
                    if arc not in added:
                        zf.write(p, arc)
                        added.add(arc)
    safe_title = re.sub(r"[^A-Za-z0-9Α-Ωα-ωά-ώ_-]+", "-", row["title"])[:60] or aid
    from starlette.background import BackgroundTask
    tmp = BASE_DIR / f".export-{secrets.token_hex(4)}.h5p"
    tmp.write_bytes(buf.getvalue())
    return FileResponse(tmp, media_type="application/zip",
                        filename=f"{safe_title}.h5p",
                        background=BackgroundTask(tmp.unlink, missing_ok=True))



# ---------------------------------------------------------------------------
# API — Ενσωμάτωση σε μάθημα MkDocs (iframe + 1 κλικ append με .bak backup)
# ---------------------------------------------------------------------------
def list_lessons() -> list[dict]:
    """Όλα τα .md μαθήματα ανά τάξη (όπως στο apps/hedgedoc-bridge).

    Νέα δομή: mathimata/<τάξη>/· το παλιό υλικό ζει στο _paradeigma/<τάξη>/.
    """
    groups = []
    for c in CLASS_GROUPS:
        lessons = []
        class_dir = DOCS_DIR / "mathimata" / c["slug"]
        if not class_dir.is_dir():
            class_dir = DOCS_DIR / "_paradeigma" / c["slug"]
        if class_dir.is_dir():
            for p in sorted(class_dir.rglob("*.md")):
                rel = p.relative_to(DOCS_DIR).as_posix()
                label = p.name
                try:
                    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.startswith("# "):
                            label = line[2:].strip()
                            break
                except OSError:
                    pass
                lessons.append({"path": rel, "label": f"{p.name} — {label}"})
        groups.append({**c, "lessons": lessons})
    return groups


@app.get("/api/lessons")
def api_lessons(request: Request):
    require_teacher(request)
    return {"groups": list_lessons()}


def iframe_code(aid: str, title: str, height: int = 600) -> str:
    safe = title.replace('"', "'")
    return (f'<iframe src="/h5p-studio/play/{aid}/?embed=1" width="100%" '
            f'height="{height}" frameborder="0" allowfullscreen="allowfullscreen" '
            f'allow="autoplay; fullscreen; encrypted-media" '
            f'title="{safe}" style="border:0;border-radius:12px"></iframe>')


@app.get("/api/embed-code/{aid}")
def api_embed_code(request: Request, aid: str, height: int = 600):
    row = get_activity_row(aid)
    height = max(200, min(2000, height))
    return {"code": iframe_code(aid, row["title"], height),
            "play_url": f"/h5p-studio/play/{aid}/"}


class EmbedRequest(BaseModel):
    lesson: str
    height: int = 600
    heading: str = ""


@app.post("/api/embed/{aid}")
def api_embed(request: Request, aid: str, body: EmbedRequest):
    """1 κλικ: append του iframe στο τέλος υπάρχοντος .md (+ .bak backup)."""
    require_teacher(request)
    row = get_activity_row(aid)
    lesson = body.lesson.strip().replace("\\", "/").lstrip("/")
    parts = PurePosixPath(lesson).parts
    # Νέα δομή: mathimata/<τάξη>/… ή _paradeigma/<τάξη>/… (παλιό υλικό).
    slug = parts[1] if len(parts) > 1 and parts[0] in ("mathimata", "_paradeigma") else (
        parts[0] if parts else "")
    if (not lesson.endswith(".md") or not parts
            or any(p in ("..", "") for p in parts)
            or slug not in CLASS_SLUGS):
        raise HTTPException(400, "Μη έγκυρη διαδρομή μαθήματος (μόνο φάκελοι τάξεων).")
    target = (DOCS_DIR / lesson).resolve()
    if not str(target).startswith(str(DOCS_DIR.resolve()) + "/") or not target.is_file():
        raise HTTPException(400, "Το μάθημα δεν βρέθηκε.")
    text = target.read_text(encoding="utf-8")
    marker = f"/h5p-studio/play/{aid}/"
    if marker in text:
        raise HTTPException(409, "Η δραστηριότητα είναι ήδη ενσωματωμένη σε αυτό το μάθημα.")
    # Backup: .bak δίπλα + ιστορικό στο backups/ (όπως το md-publish bridge)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(target, target.with_name(target.name + ".bak"))
    hist = BACKUP_DIR / target.relative_to(DOCS_DIR).parent
    hist.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, hist / f"{target.stem}.{stamp}.md.bak")
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
    subprocess.Popen(["/bin/bash", str(BUILD_DOCS_SCRIPT)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # use_directory_urls: index.md → /docs/<dir>/, αλλιώς /docs/<dir>/<stem>/
    docs_url = "/docs/" + (lesson[:-8] if lesson.endswith("/index.md") else lesson[:-3] + "/")
    return {"ok": True, "lesson": lesson, "docs_url": docs_url}



# ---------------------------------------------------------------------------
# AI Οδηγός Δημιουργίας (Wizard) — παιδαγωγικές προτάσεις & prompts
# ---------------------------------------------------------------------------
GOALS = {
    "intro": "Εισαγωγή εννοιών",
    "practice": "Εξάσκηση & Εμπέδωση",
    "visual": "Οπτική εξερεύνηση",
    "assessment": "Αξιολόγηση",
}

# Παιδαγωγική αντιστοίχιση στόχου → προτεινόμενοι τύποι H5P (με εξήγηση)
GOAL_SUGGESTIONS = {
    "intro": [
        {"type": "dialogcards", "why": "Ιδανικό για πρώτη γνωριμία με όρους/έννοιες: "
         "ο μαθητής βλέπει την ερώτηση, μαντεύει και γυρίζει την κάρτα. "
         "Χρησιμοποίησέ το στην αρχή του μαθήματος ως «ζέσταμα» ή σε ζευγάρια."},
        {"type": "hotspots", "why": "Μια εικόνα/διάγραμμα με πινέζες που αποκαλύπτουν "
         "επεξηγήσεις προσκαλεί τον μαθητή να εξερευνήσει μόνος του τις νέες έννοιες. "
         "Πρόβαλλέ το στον πίνακα και άφησε μαθητές να πατούν τις πινέζες."},
        {"type": "video", "why": "Σύντομο βίντεο με επεξηγηματικά πλαίσια σε κρίσιμα "
         "σημεία — ιδανικό για flipped classroom ή εισαγωγή πριν τη συζήτηση."},
    ],
    "practice": [
        {"type": "blanks", "why": "Η συμπλήρωση κενών αναγκάζει τον μαθητή να ανακαλέσει "
         "ενεργητικά τη γνώση (retrieval practice). Βάλε υποδείξεις για διαφοροποίηση "
         "και χρησιμοποίησέ το ως εργασία στο σπίτι ή εξάσκηση στο lab."},
        {"type": "dragtext", "why": "Το σύρσιμο λέξεων κρατά ψηλά την εμπλοκή των "
         "μικρότερων τάξεων και εμπεδώνει ορολογία/αντιστοιχίσεις. Καλό για "
         "επαναληπτικά 5λεπτα στο τέλος του μαθήματος."},
        {"type": "multichoice", "why": "Γρήγορη εξάσκηση με άμεση ανατροφοδότηση ανά "
         "επιλογή. Γράψε feedback που εξηγεί ΓΙΑΤΙ μια απάντηση είναι λάθος — "
         "εκεί γίνεται η μάθηση."},
    ],
    "visual": [
        {"type": "hotspots", "why": "Ο καλύτερος τύπος για διαγράμματα, χάρτες, "
         "ανατομία, κυκλώματα: κάθε πινέζα ανοίγει μια επεξήγηση πάνω στην εικόνα. "
         "Ζήτα από τους μαθητές να εξηγήσουν με δικά τους λόγια τι βλέπουν."},
        {"type": "video", "why": "Βίντεο πειράματος/εκδρομής με pause & ερωτήσεις στα "
         "καίρια σημεία μετατρέπει την παθητική θέαση σε ενεργητική παρατήρηση."},
    ],
    "assessment": [
        {"type": "questionset", "why": "Πλήρες quiz πολλών ερωτήσεων με σκορ, progress "
         "dots και τελική ανατροφοδότηση. Όρισε pass percentage 60-80% και άφησε "
         "retry για formative assessment χωρίς άγχος."},
        {"type": "multichoice", "why": "Μία καλογραμμένη ερώτηση με εύλογες λανθασμένες "
         "επιλογές διαγνωστικά αποκαλύπτει παρανοήσεις. Χρησιμοποίησέ το ως "
         "exit ticket στο τέλος του μαθήματος."},
        {"type": "blanks", "why": "Αξιολόγηση ακριβούς ορολογίας/τύπων χωρίς την "
         "βοήθεια των επιλογών — πιο απαιτητικό από πολλαπλής επιλογής."},
    ],
}

DIFFICULTY_LABELS = {"easy": "Εύκολο", "medium": "Μέτριο", "hard": "Δύσκολο"}

# Αυστηρά JSON schemas ανά τύπο για το AI (ίδια δομή με τον Visual Editor)
AI_SCHEMAS = {
    "multichoice": '{"type":"multichoice","title":"...","question":"...",'
                   '"answers":[{"text":"...","correct":true,"feedback":"...","tip":""},'
                   '{"text":"...","correct":false,"feedback":"..."}]}',
    "questionset": '{"type":"questionset","title":"...","intro":"...","passPercentage":60,'
                   '"questions":[{"question":"...","answers":[{"text":"...","correct":true,'
                   '"feedback":"..."},{"text":"...","correct":false,"feedback":"..."}]}]}',
    "blanks": '{"type":"blanks","title":"...","text":"<p>Οδηγία προς τον μαθητή</p>",'
              '"questions":["<p>Η πρωτεύουσα της Ελλάδας είναι η *Αθήνα:Πόλη με Παρθενώνα*.</p>"]}',
    "dragtext": '{"type":"dragtext","title":"...","taskDescription":"<p>Οδηγία</p>",'
                '"textField":"Ο Ήλιος είναι *αστέρας:Τι ουράνιο σώμα είναι;*.",'
                '"distractors":"*πλανήτης* *δορυφόρος*"}',
    "hotspots": '{"type":"hotspots","title":"...","color":"#981d99","icon":"plus",'
                '"hotspots":[{"x":25.5,"y":40.0,"header":"Τίτλος πινέζας",'
                '"content":"Επεξήγηση που εμφανίζεται όταν πατηθεί η πινέζα."}]}',
    "dialogcards": '{"type":"dialogcards","title":"...","description":"<p>Οδηγία</p>",'
                   '"cards":[{"front":"Ερώτηση/Όρος","back":"Απάντηση/Ορισμός","tip":""}]}',
    "video": '{"type":"video","title":"...","description":"...",'
             '"interactions":[{"time":30,"kind":"mc","pause":true,"label":"Ερώτηση",'
             '"question":"...","answers":[{"text":"...","correct":true},{"text":"...","correct":false}]},'
             '{"time":90,"kind":"text","pause":true,"label":"Σημείωση","text":"Επεξήγηση"}]}',
}


class WizardContext(BaseModel):
    class_slug: str = ""
    subject: str = ""
    chapter: str = ""
    goal: str = "practice"
    difficulty: str = "medium"
    notes: str = ""
    type: str = ""


@app.post("/api/wizard/suggest")
def wizard_suggest(request: Request, ctx: WizardContext):
    require_teacher(request)
    suggestions = GOAL_SUGGESTIONS.get(ctx.goal, GOAL_SUGGESTIONS["practice"])
    return {"suggestions": [
        {**s, "label": TYPE_LABELS[s["type"]], "icon": TYPE_ICONS[s["type"]]}
        for s in suggestions]}



def build_prompts(ctx: WizardContext) -> dict:
    """Εξειδικευμένα ελληνικά prompts για εξωτερικά AI (NotebookLM/ChatGPT/...)."""
    t = ctx.type or "multichoice"
    cls = CLASS_LABELS.get(ctx.class_slug, "Γυμνάσιο")
    diff = DIFFICULTY_LABELS.get(ctx.difficulty, "Μέτριο")
    goal = GOALS.get(ctx.goal, ctx.goal)
    schema = AI_SCHEMAS.get(t, AI_SCHEMAS["multichoice"])
    notes_part = (f"\n\nΥλικό μαθήματος (χρησιμοποίησε ΑΠΟΚΛΕΙΣΤΙΚΑ αυτό το περιεχόμενο):\n"
                  f"\"\"\"\n{ctx.notes[:6000]}\n\"\"\"") if ctx.notes.strip() else ""
    content_prompt = (
        f"Είσαι έμπειρος Έλληνας εκπαιδευτικός {ctx.subject or 'Πληροφορικής'} "
        f"και ειδικός στη δημιουργία διαδραστικών ασκήσεων H5P.\n\n"
        f"Δημιούργησε μία δραστηριότητα H5P τύπου «{TYPE_LABELS.get(t, t)}» για:\n"
        f"- Τάξη: {cls}\n- Μάθημα: {ctx.subject or '—'}\n"
        f"- Κεφάλαιο/Ημερήσιο μάθημα: {ctx.chapter or '—'}\n"
        f"- Διδακτικός στόχος: {goal}\n- Επίπεδο δυσκολίας: {diff}\n"
        f"{notes_part}\n\n"
        f"ΑΠΑΙΤΗΣΕΙΣ:\n"
        f"1. Όλο το περιεχόμενο στα Ελληνικά, επιστημονικά ακριβές και κατάλληλο για την ηλικία.\n"
        f"2. Συμπερίλαβε ουσιαστική ανατροφοδότηση (feedback) που εξηγεί γιατί κάθε "
        f"απάντηση είναι σωστή/λάθος (όχι απλά «Σωστό!»).\n"
        f"3. Για πολλαπλής επιλογής: 4 επιλογές με εύλογες λανθασμένες απαντήσεις που "
        f"αντικατοπτρίζουν συχνές παρανοήσεις των μαθητών.\n"
        f"4. Για blanks/dragtext: οι λέξεις-κενά μπαίνουν σε *αστερίσκους* με "
        f"προαιρετική υπόδειξη μετά από άνω-κάτω τελεία, π.χ. *Αθήνα:Πρωτεύουσα*.\n\n"
        f"ΑΠΑΝΤΗΣΕ ΑΠΟΚΛΕΙΣΤΙΚΑ με έγκυρο JSON σε αυτήν ακριβώς τη δομή "
        f"(χωρίς markdown fences, χωρίς σχόλια, χωρίς επιπλέον κείμενο):\n"
        f"{schema}"
    )
    image_prompt = ""
    if t == "hotspots":
        image_prompt = (
            f"Δημιούργησε ένα καθαρό εκπαιδευτικό διάγραμμα/εικονογράφηση για μάθημα "
            f"{ctx.subject or 'Πληροφορικής'} {cls} με θέμα «{ctx.chapter or '—'}».\n\n"
            f"ΑΠΑΙΤΗΣΕΙΣ:\n"
            f"- Οριζόντιος προσανατολισμός (16:9), επίπεδο/flat διανυσματικό στυλ, "
            f"καθαρό λευκό ή απαλό μονόχρωμο φόντο.\n"
            f"- 4-6 διακριτά, ευδιάκριτα στοιχεία/περιοχές ενδιαφέροντος πάνω στα οποία "
            f"θα τοποθετηθούν διαδραστικές πινέζες (hotspots) — άφησε αρκετό κενό χώρο "
            f"γύρω από κάθε στοιχείο.\n"
            f"- ΧΩΡΙΣ καθόλου κείμενο/ετικέτες μέσα στην εικόνα (οι επεξηγήσεις θα "
            f"μπούν ως hotspots).\n"
            f"- Επιστημονικά ακριβής απεικόνιση, κατάλληλη για {cls}.\n\n"
            f"Μαζί με την εικόνα, δώσε και λίστα με τα στοιχεία της και τις συντεταγμένες "
            f"τους ως ποσοστά (x%, y%) ώστε να μπουν ως hotspots, σε μορφή JSON: "
            f'{{"hotspots":[{{"x":25,"y":40,"header":"...","content":"..."}}]}}'
        )
    return {"content_prompt": content_prompt, "image_prompt": image_prompt}


@app.post("/api/wizard/prompts")
def wizard_prompts(request: Request, ctx: WizardContext):
    require_teacher(request)
    return build_prompts(ctx)



# ---------------------------------------------------------------------------
# API — Άμεση παραγωγή άσκησης με AI (OpenAI-compatible / Alibaba Qwen)
# ---------------------------------------------------------------------------
def parse_ai_json(text: str) -> dict:
    """Ανθεκτική εξαγωγή JSON από απάντηση AI (fences, πρόλογος κ.λπ.)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise HTTPException(422, "Η απάντηση του AI δεν περιέχει έγκυρο JSON. "
                             "Δοκίμασε ξανά ή χρησιμοποίησε το πεδίο επικόλλησης.")


def normalize_ai_data(data: dict, fallback_type: str) -> dict:
    """Ελαφρύς καθαρισμός/συμπλήρωση της δομής που επέστρεψε το AI."""
    if not isinstance(data, dict):
        raise HTTPException(422, "Το JSON πρέπει να είναι αντικείμενο.")
    data.setdefault("type", fallback_type)
    if data["type"] not in TYPE_LIBS:
        raise HTTPException(422, f"Άγνωστος τύπος στο JSON: {data['type']}")
    t = data["type"]
    if t == "multichoice":
        if not data.get("question") or not data.get("answers"):
            raise HTTPException(422, "Λείπει question ή answers από το JSON.")
    if t == "questionset":
        if not data.get("questions"):
            raise HTTPException(422, "Λείπουν questions από το JSON.")
    if t == "blanks":
        qs = data.get("questions") or ([data["text"]] if data.get("text") else [])
        data["questions"] = qs
        if not any("*" in q for q in qs):
            raise HTTPException(422, "Οι προτάσεις πρέπει να περιέχουν *κενά*.")
    if t == "dragtext" and "*" not in data.get("textField", ""):
        raise HTTPException(422, "Το textField πρέπει να περιέχει *λέξεις*.")
    if t == "dialogcards" and not data.get("cards"):
        raise HTTPException(422, "Λείπουν cards από το JSON.")
    if t == "hotspots" and not data.get("hotspots"):
        raise HTTPException(422, "Λείπουν hotspots από το JSON.")
    return data


@app.post("/api/wizard/generate")
def wizard_generate(request: Request, ctx: WizardContext):
    require_teacher(request)
    cfg = ai_config()
    if not cfg["configured"]:
        raise HTTPException(503, "Δεν υπάρχει ρυθμισμένο AI API Key. Πρόσθεσέ το στις "
                                 "Ρυθμίσεις AI ή χρησιμοποίησε τα prompts για εξωτερικό AI.")
    t = ctx.type or "multichoice"
    prompt = build_prompts(ctx)["content_prompt"]
    try:
        r = requests.post(
            cfg["base_url"] + "/chat/completions",
            headers={"Authorization": f"Bearer {cfg['key']}",
                     "Content-Type": "application/json"},
            json={"model": get_setting("ai_model_active") or cfg["model"],
                  "messages": [
                      {"role": "system",
                       "content": "Είσαι ειδικός δημιουργός εκπαιδευτικού υλικού H5P. "
                                  "Απαντάς ΜΟΝΟ με έγκυρο JSON χωρίς markdown."},
                      {"role": "user", "content": prompt}],
                  "temperature": 0.7},
            timeout=180)
    except requests.RequestException as e:
        raise HTTPException(502, f"Σφάλμα επικοινωνίας με το AI API: {e}")
    if r.status_code != 200:
        raise HTTPException(502, f"Το AI API επέστρεψε {r.status_code}: {r.text[:300]}")
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise HTTPException(502, "Μη αναμενόμενη απάντηση από το AI API.")
    data = normalize_ai_data(parse_ai_json(content), t)
    title = data.get("title") or ctx.chapter or "Άσκηση AI"
    # Τα hotspots/video χρειάζονται media που το AI δεν παράγει → draft στον editor
    if t in ("hotspots", "video"):
        return {"ok": True, "draft": True, "data": data, "title": title,
                "note": "Ανέβασε εικόνα/βίντεο στον editor για ολοκλήρωση."}
    aid = new_activity_id()
    data["type"] = t
    atype, params, extra = build_content(data)
    save_activity_files(aid, title, TYPE_LIBS[atype], params, extra)
    save_editor_state(aid, data)
    lj = lib_json(TYPE_LIBS[atype])
    upsert_activity(aid, title, atype,
                    f"{lj['machineName']} {lj['majorVersion']}.{lj['minorVersion']}",
                    ctx.model_dump())
    return {"ok": True, "draft": False, "id": aid, "title": title,
            "edit_url": f"/h5p-studio/edit/{aid}"}



class PasteJSON(BaseModel):
    json_text: str
    class_slug: str = ""
    subject: str = ""
    chapter: str = ""
    goal: str = ""
    difficulty: str = ""


@app.post("/api/wizard/paste-json")
def wizard_paste_json(request: Request, body: PasteJSON):
    """Επικόλληση JSON απάντησης εξωτερικού AI → νέα δραστηριότητα στον editor."""
    require_teacher(request)
    data = normalize_ai_data(parse_ai_json(body.json_text), "multichoice")
    t = data["type"]
    title = data.get("title") or body.chapter or "Άσκηση από AI"
    if t in ("hotspots", "video"):
        # Χρειάζονται media: δημιουργούμε σκελετό μόνο αν υπάρχουν ήδη paths
        has_media = ((t == "hotspots" and (data.get("image") or {}).get("path"))
                     or (t == "video" and (data.get("video") or {}).get("path")))
        if not has_media:
            return {"ok": True, "draft": True, "data": data, "title": title,
                    "note": "Πρόσθεσε εικόνα/βίντεο στον editor για ολοκλήρωση."}
    aid = new_activity_id()
    atype, params, extra = build_content(data)
    save_activity_files(aid, title, TYPE_LIBS[atype], params, extra)
    save_editor_state(aid, data)
    lj = lib_json(TYPE_LIBS[atype])
    upsert_activity(aid, title, atype,
                    f"{lj['machineName']} {lj['majorVersion']}.{lj['minorVersion']}",
                    body.model_dump())
    return {"ok": True, "draft": False, "id": aid, "title": title,
            "edit_url": f"/h5p-studio/edit/{aid}"}


# ---------------------------------------------------------------------------
# API — Ρυθμίσεις AI (μόνο καθηγητής)
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def api_settings_get(request: Request):
    require_teacher(request)
    cfg = ai_config()
    return {"configured": cfg["configured"], "base_url": cfg["base_url"],
            "model": cfg["model"], "models": cfg["models"],
            "active_model": get_setting("ai_model_active") or cfg["model"],
            "custom_key": bool(get_setting("ai_api_key")),
            "source": "ρυθμίσεις Studio" if get_setting("ai_api_key")
                      else (".env.keys / περιβάλλον" if cfg["configured"] else "—")}


class AISettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@app.post("/api/settings")
def api_settings_set(request: Request, body: AISettings):
    require_teacher(request)
    if body.api_key:
        set_setting("ai_api_key", body.api_key.strip())
    if body.base_url:
        set_setting("ai_base_url", body.base_url.strip())
    if body.model:
        set_setting("ai_model_active", body.model.strip())
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8012, log_level="info")

