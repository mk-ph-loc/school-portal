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

Δομή (Task 3 architecture review — διάσπαση μονόλιθου σε APIRouters):
  main.py           wiring: FastAPI, mounts, healthz, include_router
  state.py          κοινό state (διαδρομές/σταθερές/TYPE_*), auth cookies
  store.py          SQLite schema + queries (activities/settings) + AI config
  content.py        χτίσιμο H5P: dependency closure, content.json ↔ editor
  routers/          editor · player · wizard · embed

Προστασία: κωδικός καθηγητή teacher2026 (HMAC cookie όπως στο /exams/) για
δημιουργία/επεξεργασία/διαγραφή· το /h5p-studio/play/<id>/ είναι ανοιχτό.
Τρέχει στο 127.0.0.1:8012 πίσω από τον Nginx στο /h5p-studio/.
ΣΗΜΕΙΩΣΗ: η 8011 ανήκει ήδη στο Web Lab (/web-lab/) — βλ. README.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import state
import store
from routers import editor, player, wizard, embed

store.init_db()

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
app.mount("/static", StaticFiles(directory=str(state.BASE_DIR / "static")), name="static")
app.mount("/h5p-libraries", StaticFiles(directory=str(state.H5P_LIBS_DIR)), name="h5p-libraries")
app.mount("/library", StaticFiles(directory=str(state.LIBRARY_DIR)), name="library")

for module in (editor, player, wizard, embed):
    app.include_router(module.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "school-h5p"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8012, log_level="info")
