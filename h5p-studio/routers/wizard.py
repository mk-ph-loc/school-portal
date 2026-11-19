"""
H5P Studio — AI Οδηγός Δημιουργίας (Wizard) & Ρυθμίσεις AI (Task 3: APIRouters).

Παιδαγωγικές προτάσεις ανά διδακτικό στόχο, εξειδικευμένα ελληνικά prompts
για εξωτερικά AI, άμεση παραγωγή άσκησης μέσω OpenAI-compatible API
(Alibaba Qwen — .env.keys) και επικόλληση JSON απάντησης → νέα δραστηριότητα.
"""
from __future__ import annotations

import json
import re

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from common.classes import CLASS_LABELS

import state
import store
import content

router = APIRouter()


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


@router.post("/api/wizard/suggest")
def wizard_suggest(request: Request, ctx: WizardContext):
    state.require_teacher(request)
    suggestions = GOAL_SUGGESTIONS.get(ctx.goal, GOAL_SUGGESTIONS["practice"])
    return {"suggestions": [
        {**s, "label": state.TYPE_LABELS[s["type"]], "icon": state.TYPE_ICONS[s["type"]]}
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
        f"Δημιούργησε μία δραστηριότητα H5P τύπου «{state.TYPE_LABELS.get(t, t)}» για:\n"
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


@router.post("/api/wizard/prompts")
def wizard_prompts(request: Request, ctx: WizardContext):
    state.require_teacher(request)
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
    if data["type"] not in state.TYPE_LIBS:
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


@router.post("/api/wizard/generate")
def wizard_generate(request: Request, ctx: WizardContext):
    state.require_teacher(request)
    cfg = store.ai_config()
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
            json={"model": store.get_setting("ai_model_active") or cfg["model"],
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
    aid = content.new_activity_id()
    data["type"] = t
    atype, params, extra = content.build_content(data)
    content.save_activity_files(aid, title, state.TYPE_LIBS[atype], params, extra)
    content.save_editor_state(aid, data)
    lj = content.lib_json(state.TYPE_LIBS[atype])
    content.upsert_activity(aid, title, atype,
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


@router.post("/api/wizard/paste-json")
def wizard_paste_json(request: Request, body: PasteJSON):
    """Επικόλληση JSON απάντησης εξωτερικού AI → νέα δραστηριότητα στον editor."""
    state.require_teacher(request)
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
    aid = content.new_activity_id()
    atype, params, extra = content.build_content(data)
    content.save_activity_files(aid, title, state.TYPE_LIBS[atype], params, extra)
    content.save_editor_state(aid, data)
    lj = content.lib_json(state.TYPE_LIBS[atype])
    content.upsert_activity(aid, title, atype,
                    f"{lj['machineName']} {lj['majorVersion']}.{lj['minorVersion']}",
                    body.model_dump())
    return {"ok": True, "draft": False, "id": aid, "title": title,
            "edit_url": f"/h5p-studio/edit/{aid}"}


@router.get("/api/settings")
def api_settings_get(request: Request):
    state.require_teacher(request)
    cfg = store.ai_config()
    return {"configured": cfg["configured"], "base_url": cfg["base_url"],
            "model": cfg["model"], "models": cfg["models"],
            "active_model": store.get_setting("ai_model_active") or cfg["model"],
            "custom_key": bool(store.get_setting("ai_api_key")),
            "source": "ρυθμίσεις Studio" if store.get_setting("ai_api_key")
                      else (".env.keys / περιβάλλον" if cfg["configured"] else "—")}


class AISettings(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


@router.post("/api/settings")
def api_settings_set(request: Request, body: AISettings):
    state.require_teacher(request)
    if body.api_key:
        store.set_setting("ai_api_key", body.api_key.strip())
    if body.base_url:
        store.set_setting("ai_base_url", body.base_url.strip())
    if body.model:
        store.set_setting("ai_model_active", body.model.strip())
    return {"ok": True}
