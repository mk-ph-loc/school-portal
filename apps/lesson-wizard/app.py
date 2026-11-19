"""
Lesson Wizard — Οπτικός επεξεργαστής ημερήσιων μαθημάτων (Ψηφιακή Πύλη Σχολείου).

Περιβάλλον καθηγητή (κωδικός teacher2026, HMAC cookie όπως στο /app-builder/):
  * λίστα ημερήσιων μαθημάτων ανά τάξη/μάθημα (docs/mathimata/<τάξη>/<μάθημα>/),
  * visual editor διδακτικών φάσεων: drag & drop αναδιάταξη, προσθήκη από
    παλέτα τύπων, επεξεργασία markdown/τίτλου/διάρκειας, σημειώσεις καθηγητή,
  * upload υλικού (εικόνες/pdf/html/video) στον φάκελο του μαθήματος,
  * δημιουργία νέου ημερήσιου μαθήματος από template + αυτόματο nav,
  * ωράριο σχολείου από Excel (openpyxl) + χειροκίνητο «ενεργό μάθημα»,
  * /api/check για το nginx auth_request των σημειώσεων καθηγητή.

Δομή (Task 3 architecture review — διάσπαση μονόλιθου σε APIRouters):
  app.py            wiring: FastAPI, mounts, include_router (+ compat aliases)
  state.py          κοινό state (διαδρομές/σταθερές), auth, lesson_dir/nav/backup
  routers/          lessons · schedule · fs_browser · books

Τρέχει στο 127.0.0.1:8013 πίσω από τον Nginx στο /lesson-wizard/. Χωρίς Docker.
Το rebuild του static site γίνεται αυτόματα από το school-mkdocs.path/service.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from common.schedule import parse_schedule_xlsx

import state
from routers import lessons, schedule, fs_browser, books

app = FastAPI(
    title="Lesson Wizard — Ημερήσια Μαθήματα",
    description="Οπτικός επεξεργαστής διδακτικών φάσεων & ωραρίου",
    docs_url=None, redoc_url=None, openapi_url=None,
)
app.mount("/static", StaticFiles(directory=str(state.BASE_DIR / "static")), name="static")

for module in (lessons, schedule, fs_browser, books):
    app.include_router(module.router)

# Συμβατότητα με scripts/classroom-test.py (φορτώνει το app.py ως module και
# καλεί lw.parse_schedule_xlsx — ο parser ζει πλέον στο common.schedule).
make_template_xlsx = schedule.make_template_xlsx
