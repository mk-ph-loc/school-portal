"""
H5P Studio — χτίσιμο έγκυρων πακέτων H5P (Task 3: διάσπαση σε APIRouters).

Βοηθητικά βιβλιοθηκών (dependency closure, h5p.json), μετατροπή της απλής
δομής editor/AI → content.json ανά τύπο, αποθήκευση στον δίσκο (library/<id>/)
+ βάση, και η αντίστροφη μετατροπή content.json → δομή editor. Καθαρή
βιβλιοθήκη: εξαρτάται μόνο από state/store (κανένα import router).
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import HTTPException

import state
import store

# ---------------------------------------------------------------------------
# Βοηθητικά βιβλιοθηκών H5P (dependency closure, έγκυρο h5p.json)
# ---------------------------------------------------------------------------
_LIB_CACHE: dict[str, dict] = {}


def lib_json(folder: str) -> dict:
    if folder not in _LIB_CACHE:
        p = state.H5P_LIBS_DIR / folder / "library.json"
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
    if t not in state.TYPE_LIBS:
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
        extra = sorted({state.TYPE_LIBS["multichoice"]})
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
        extra = ["H5P.Text-1.1", "H5P.Summary-1.10", state.TYPE_LIBS["multichoice"]]
        return t, params, extra

    raise HTTPException(400, f"Άγνωστος τύπος: {t}")


# ---------------------------------------------------------------------------
# Αποθήκευση δραστηριότητας στον δίσκο (library/<id>/) + βάση
# ---------------------------------------------------------------------------
def activity_dir(aid: str) -> Path:
    if not state.ID_RE.match(aid):
        raise HTTPException(400, "Μη έγκυρο id δραστηριότητας.")
    return state.LIBRARY_DIR / aid


def get_activity_row(aid: str) -> sqlite3.Row:
    with store.db() as conn:
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
    with store.db() as conn:
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
    src_root = activity_dir(state.PREVIEW_ID) / "content"
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
