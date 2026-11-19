"""
Ενιαίο πρότυπο Excel ρυθμίσεων — δημιουργία (12 καρτέλες, χρωματικοί κώδικες,
οδηγίες), parser → config.json και routes upload/template. Οι 3 καρτέλες
ωραρίου είναι ΑΥΤΟΥΣΙΕΣ με το πρότυπο του Lesson Wizard (common.schedule).
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse

from common.schedule import hhmm as _hhmm, parse_schedule_xlsx
from common.xlsx import style_sheet, yesno_validation

import state
from presence import broadcast

router = APIRouter()

# ---------------------------------------------------------------------------
# Ενιαίο πρότυπο Excel — δημιουργία (12 καρτέλες, χρωματικοί κώδικες, οδηγίες)
# Styling helpers: common.xlsx (κοινά με το πρότυπο ωραρίου του Lesson Wizard).
# ---------------------------------------------------------------------------
# Χρώμα tab ανά θεματική ομάδα (εξηγείται στο φύλλο Οδηγίες):
TAB_COLORS = {"Οδηγίες": "9E9E9E", "Τμήματα": "1E88E5", "Ωρες": "1E88E5",
              "Ωραριο": "1E88E5", "Μενού": "8E24AA", "Εργαλειοθήκες": "8E24AA",
              "Ρόλοι": "FB8C00", "Ονόματα Guest": "43A047", "Timers": "FDD835",
              "Γεγονότα": "FDD835", "Μηνύματα": "E53935", "Poll-Quiz": "E53935"}


def _style_sheet(ws, headers: list[str], widths: list[int], req_cols: set[int],
                 warn_cols: set[int] | None = None):
    style_sheet(ws, headers, widths, req_cols, warn_cols, tab_colors=TAB_COLORS)


def _yesno_validation(ws, cols: list[int]):
    yesno_validation(ws, cols)


def make_template_xlsx() -> None:
    """Ενιαίο πρότυπο ΟΛΩΝ των ρυθμίσεων· οι 3 καρτέλες ωραρίου είναι ΑΥΤΟΥΣΙΕΣ
    με το πρότυπο του Lesson Wizard ώστε το ίδιο αρχείο να ανεβαίνει παντού."""
    from openpyxl import Workbook

    wb = Workbook()

    # --- 1. Οδηγίες (γκρι) ---------------------------------------------------
    ws = wb.active
    ws.title = "Οδηγίες"
    _style_sheet(ws, ["Ενιαίο Πρότυπο Ρυθμίσεων — Ζωντανή Τάξη (/classroom/)"], [110], set())
    rows = [
        "",
        "🎨 ΧΡΩΜΑΤΙΚΟΣ ΚΩΔΙΚΑΣ",
        "🟦 Μπλε κεφαλίδα (γραμμή 1): τίτλοι στηλών — ΜΗΝ τους αλλάξετε/μετονομάσετε.",
        "🟨 Κίτρινο κελί: ΥΠΟΧΡΕΩΤΙΚΟ πεδίο — συμπληρώστε το.",
        "🟩 Πράσινο κελί: προαιρετικό πεδίο — αφήστε το κενό αν δεν χρειάζεται.",
        "🟥 Κόκκινο κελί: ΕΥΑΙΣΘΗΤΟ (κωδικοί πρόσβασης) — προσοχή, φαίνεται σε όποιον έχει το αρχείο.",
        "",
        "🗂️ ΚΑΡΤΕΛΕΣ (χρώμα tab = θεματική ομάδα)",
        "🔵 Τμήματα / Ωρες / Ωραριο → το ΩΡΑΡΙΟ του σχολείου (ίδια δομή με το Lesson Wizard·",
        "     το ίδιο αρχείο μπορεί να ανέβει και στο /lesson-wizard/ → καρτέλα Ωράριο).",
        "🟣 Μενού / Εργαλειοθήκες → τι βλέπει κάθε ρόλος στο κεντρικό παράθυρο.",
        "🟠 Ρόλοι → κωδικός τάξης & δικαιώματα επισκεπτών (guests).",
        "🟢 Ονόματα Guest → παιχνιδιάρικα ονόματα τύπου Google Docs (Επίθετο + Όνομα).",
        "🟡 Timers / Γεγονότα → χρονομετρητές & αυτόματα γεγονότα δεμένα με το ωράριο (±offset λεπτά).",
        "🔴 Μηνύματα / Poll-Quiz → έτοιμες ανακοινώσεις, δημοσκοπήσεις & τράπεζα quiz.",
        "",
        "📤 ΡΟΗ ΕΡΓΑΣΙΑΣ",
        "1. Συμπληρώνετε τις καρτέλες (κάθε γραμμή = μία εγγραφή· τα παραδείγματα μπορείτε να τα σβήσετε).",
        "2. Αποθήκευση ως .xlsx και ανέβασμα: /classroom/ → ⚙️ Ρυθμίσεις (καθηγητής, κωδικός teacher2026).",
        "3. Οι ρυθμίσεις εφαρμόζονται ΖΩΝΑΝΑ σε όλους τους συνδεδεμένους — χωρίς επανεκκίνηση.",
        "4. Μπορείτε να επεκτείνετε το αρχείο αργότερα: άγνωστες καρτέλες αγνοούνται με ασφάλεια.",
        "",
        "⚠️ ΣΗΜΑΝΤΙΚΑ",
        "• ΝΑΙ/ΟΧΙ: διαλέξτε από το αναδυόμενο μενού του κελιού (όχι ελεύθερο κείμενο).",
        "• Ώρες σε 24ωρη μορφή HH:MM (π.χ. 08:15). Offset σε λεπτά: -5 = πέντε λεπτά ΝΩΡΙΤΕΡΑ.",
        "• URL εφαρμογών: σχετικά με την πύλη (π.χ. /docs/, /live-quiz/, /apps/my-app/).",
        "• Τα αποτελέσματα quiz καταγράφονται ΜΟΝΟ για μαθητές· οι guests κάνουν εξάσκηση.",
        "• Poll/quiz: από το UI υπάρχει 🔚 αυτόματο κλείσιμο όταν απαντήσουν όλοι + χρονικό όριο.",
        "• Ανακοινώσεις/polls/quiz/chat αποθηκεύονται μόνιμα — διαχείριση (edit/delete/bulk)",
        "     από το μενού «🗄️ Διαχείριση» του καθηγητή (προστίθεται αυτόματα και σε παλιά uploads).",
    ]
    for r in rows:
        ws.append([r])

    # --- 2-4. Ωράριο (μπλε — ΙΔΙΑ ΔΟΜΗ με lesson-wizard) ----------------------
    ws = wb.create_sheet("Τμήματα")
    _style_sheet(ws, ["Τμήμα", "Τάξη (slug)", "Σημείωση"], [14, 20, 40], {1, 2})
    ws.append(["Γ1", "gymnasio-g", "Πληροφορική Γ' Γυμνασίου"])
    ws.append(["Γ2", "gymnasio-g", ""])
    ws.append(["Β1", "gymnasio-b", ""])

    ws = wb.create_sheet("Ωρες")
    _style_sheet(ws, ["Ωρα", "Εναρξη", "Ληξη"], [10, 14, 14], {1, 2, 3})
    for i, (s, e) in enumerate([("08:15", "09:00"), ("09:10", "09:55"), ("10:05", "10:50"),
                                 ("11:10", "11:55"), ("12:05", "12:50"), ("13:00", "13:45"),
                                 ("13:55", "14:40")], 1):
        ws.append([i, s, e])

    ws = wb.create_sheet("Ωραριο")
    _style_sheet(ws, ["Τμήμα", "Ημέρα", "Ωρα", "Μάθημα", "URL μαθήματος (προαιρετικό)"],
                 [12, 14, 8, 30, 46], {1, 2, 3, 4})
    ws.append(["Γ1", "Δευτέρα", 3, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    ws.append(["Γ1", "Τετάρτη", 5, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])
    ws.append(["Γ2", "Τρίτη", 2, "Πληροφορική", "/docs/mathimata/gymnasio-g/pliroforiki/"])

    # --- 5. Μενού (μωβ) -------------------------------------------------------
    ws = wb.create_sheet("Μενού")
    _style_sheet(ws, ["id", "Τίτλος", "Emoji", "URL ή #panel", "Σειρά",
                      "Guest", "Μαθητής", "Καθηγητής"],
                 [16, 22, 8, 34, 8, 10, 10, 12], {1, 2, 4})
    _yesno_validation(ws, [6, 7, 8])
    for row in [["mathimata", "Μαθήματα", "📚", "/docs/", 1, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["anakoinoseis", "Ανακοινώσεις", "📣", "#announcements", 2, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["chat", "Chat", "💬", "#chat", 3, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["forum", "Forum", "🗂️", "#forum", 4, "ΟΧΙ", "ΝΑΙ", "ΝΑΙ"],
                ["voitheia", "Βοήθεια", "❓", "#help", 5, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["manage", "Διαχείριση", "🗄️", "#manage", 6, "ΟΧΙ", "ΟΧΙ", "ΝΑΙ"],
                ["live-quiz", "Live Quiz", "🎮", "/live-quiz/", 7, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"]]:
        ws.append(row)

    # --- 6. Εργαλειοθήκες (μωβ) ----------------------------------------------
    ws = wb.create_sheet("Εργαλειοθήκες")
    _style_sheet(ws, ["id", "Τίτλος", "Τύπος (dock/float)", "X", "Y", "Πλάτος", "Ύψος",
                      "Guest", "Μαθητής", "Καθηγητής"],
                 [14, 24, 18, 8, 8, 10, 10, 10, 10, 12], {1, 2, 3})
    _yesno_validation(ws, [8, 9, 10])
    from openpyxl.worksheet.datavalidation import DataValidation
    dv = DataValidation(type="list", formula1='"dock,float"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("C2:C200")
    for row in [["roster", "👥 Συνδεδεμένοι", "dock", 20, 90, 300, 380, "ΟΧΙ", "ΟΧΙ", "ΝΑΙ"],
                ["commands", "🎛️ Εντολές Τάξης", "dock", 20, 90, 340, 480, "ΟΧΙ", "ΟΧΙ", "ΝΑΙ"],
                ["timer", "⏱️ Χρονομετρητής", "float", 60, 120, 280, 200, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"],
                ["chat", "💬 Chat Τάξης", "dock", 20, 90, 320, 420, "ΝΑΙ", "ΝΑΙ", "ΝΑΙ"]]:
        ws.append(row)

    # --- 7. Ρόλοι (πορτοκαλί) -----------------------------------------------
    ws = wb.create_sheet("Ρόλοι")
    _style_sheet(ws, ["Ρύθμιση", "Τιμή", "Εξήγηση"], [24, 24, 66], {1}, warn_cols={2})
    for row in [["student_code", "", "Προαιρετικός κωδικός τάξης για είσοδο ως μαθητής (κενό = χωρίς κωδικό)."],
                ["guest_chat", "ΝΑΙ", "Επιτρέπεται στους guests το chat τάξης;"],
                ["guest_forum", "ΟΧΙ", "Επιτρέπεται στους guests το forum;"],
                ["allowed_guest", "*", "Εφαρμογές για guests: * = όλες, ή λίστα με κόμμα (/docs/,/live-quiz/)"],
                ["allowed_student", "*", "Εφαρμογές για μαθητές: * = όλες, ή λίστα με κόμμα."],
                ["allowed_teacher", "*", "Εφαρμογές για καθηγητές: * = όλες."]]:
        ws.append(row)

    # --- 8. Ονόματα Guest (πράσινο) ------------------------------------------
    ws = wb.create_sheet("Ονόματα Guest")
    _style_sheet(ws, ["Επίθετα", "Ονόματα (ζώα/ρόλοι)", "Emoji", "Χρώματα (hex)"],
                 [24, 26, 10, 16], set())
    examples = list(zip(state.DEFAULT_ADJ, [n for n, _ in state.DEFAULT_NOUNS],
                        [e for _, e in state.DEFAULT_NOUNS], state.GUEST_COLORS + [""] * 5))
    for adj, noun, emoji, color in examples[:15]:
        ws.append([adj, noun, emoji, color])

    # --- 9. Timers (κίτρινο) --------------------------------------------------
    ws = wb.create_sheet("Timers")
    _style_sheet(ws, ["id", "Ετικέτα", "Ορατότητα (private/public)", "Διάρκεια (δευτ.)",
                      "Τμήμα ωραρίου", "Ημέρα", "Ωρα (#)", "Άκρη (start/end)",
                      "Offset (±λεπτά)", "Μήνυμα λήξης", "Κοινό", "Ενεργό"],
                 [12, 24, 22, 14, 14, 12, 8, 14, 14, 30, 12, 10], {1, 2, 3})
    _yesno_validation(ws, [12])
    dv = DataValidation(type="list", formula1='"private,public"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("C2:C200")
    dv2 = DataValidation(type="list", formula1='"start,end"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add("H2:H200")
    ws.append(["break", "Διάλειμμα", "public", "", "Γ1", "Δευτέρα", 2, "end", -2,
               "Σε 2 λεπτά τελειώνει η ώρα!", "all", "ΝΑΙ"])
    ws.append(["focus", "Χρόνος εργασίας", "public", 600, "", "", "", "", 0,
               "Ο χρόνος τελείωσε — αποθηκεύστε!", "students", "ΝΑΙ"])

    # --- 10. Γεγονότα (κίτρινο) ----------------------------------------------
    ws = wb.create_sheet("Γεγονότα")
    _style_sheet(ws, ["id", "Trigger (day_end/period_end/time)", "Ωρα (#)", "Ώρα HH:MM",
                      "Offset (±λεπτά)", "Ημέρες (κενό=καθημερινές)", "Ενέργεια (announce/congrats/award/navigate)",
                      "Μήνυμα", "URL (για navigate)", "Κοινό", "Τμήμα", "Ενεργό"],
                 [12, 30, 8, 12, 14, 26, 34, 36, 30, 12, 10, 10], {1, 2, 7, 8})
    _yesno_validation(ws, [12])
    dv = DataValidation(type="list", formula1='"day_end,period_end,time"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("B2:B200")
    dv2 = DataValidation(type="list", formula1='"announce,congrats,award,navigate"', allow_blank=True)
    ws.add_data_validation(dv2)
    dv2.add("G2:G200")
    ws.append(["telos-imeras", "day_end", "", "", -5, "", "congrats",
               "Μπράβο παιδιά! Τελειώσαμε για σήμερα 🎉", "", "all", "", "ΝΑΙ"])
    ws.append(["anafora", "period_end", 4, "", 0, "Παρασκευή", "announce",
               "Μην ξεχάσετε την εβδομαδιαία αναφορά στο /exams/", "/exams/", "students", "", "ΝΑΙ"])

    # --- 11. Μηνύματα (κόκκινο) ----------------------------------------------
    ws = wb.create_sheet("Μηνύματα")
    _style_sheet(ws, ["id", "Είδος (announce/congrats/award)", "Κείμενο"],
                 [14, 28, 80], {1, 2, 3})
    dv = DataValidation(type="list", formula1='"announce,congrats,award"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("B2:B200")
    for row in [["kalimera", "announce", "Καλημέρα! Ξεκινάμε σε 2 λεπτά — ανοίξτε το μάθημα."],
                ["bravo", "congrats", "Συγχαρητήρια {name}! Εξαιρετική προσπάθεια 👏"],
                ["vraveio", "award", "🏆 Βραβείο ημέρας απονέμεται στον/στη {name}!"],
                ["swsti-apantisi", "congrats", "Μπράβο {name}, σωστή απάντηση! ⭐"]]:
        ws.append(row)

    # --- 12. Poll-Quiz (κόκκινο) ---------------------------------------------
    ws = wb.create_sheet("Poll-Quiz")
    _style_sheet(ws, ["Τύπος (poll/quiz)", "id", "Τίτλος/Ερώτηση", "Επιλογή 1", "Επιλογή 2",
                      "Επιλογή 3", "Επιλογή 4", "Σωστή (1-4, μόνο quiz)",
                      "Ορατά αποτελέσματα (poll)", "Ομάδα quiz (ίδιο id = ίδιο quiz)"],
                 [16, 14, 44, 22, 22, 22, 22, 20, 24, 28], {1, 2, 3, 4, 5})
    _yesno_validation(ws, [9])
    dv = DataValidation(type="list", formula1='"poll,quiz"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("A2:A200")
    ws.append(["poll", "diathesi", "Πώς νιώθετε σήμερα;", "😀 Τέλεια", "🙂 Καλά",
               "😐 Έτσι κι έτσι", "😴 Κουρασμένοι", "", "ΝΑΙ", ""])
    ws.append(["quiz", "dyadiko-1", "Πόσα bits έχει ένα byte;", "4", "8", "16", "32", 2, "", "dyadiko"])
    ws.append(["quiz", "dyadiko-1", "Το 1010 (δυαδικό) σε δεκαδικό είναι:", "8", "10", "12", "14", 2, "", "dyadiko"])

    state.DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(state.TEMPLATE_XLSX)


# ---------------------------------------------------------------------------
# Parser ενιαίου Excel → config.json (δέχεται και το παλιό 4-φυλλο ωράριο)
# ---------------------------------------------------------------------------
# _hhmm: common.schedule (ίδιο με lesson-wizard)
def _bool(v, default=False) -> bool:
    s = str(v or "").strip().upper()
    if s in ("ΝΑΙ", "NAI", "YES", "TRUE", "1"):
        return True
    if s in ("ΟΧΙ", "OXI", "NO", "FALSE", "0"):
        return False
    return default


def parse_config_xlsx(path: Path) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    cfg = json.loads(json.dumps(state.DEFAULT_CONFIG))

    # --- Ωράριο: ΙΔΙΑ λογική με το Lesson Wizard (common.schedule) -----------
    sched = parse_schedule_xlsx(path)
    if sched["tmimata"]:
        cfg["schedule"] = {"tmimata": sched["tmimata"], "periods": sched["periods"],
                           "timetable": sched["timetable"]}

    # --- Μενού ---------------------------------------------------------------
    if "Μενού" in wb.sheetnames:
        menu = []
        for row in wb["Μενού"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                menu.append({"id": str(row[0]).strip(), "title": str(row[1]).strip(),
                             "icon": str(row[2] or "🔗").strip(),
                             "url": str(row[3] or "").strip(),
                             "order": int(row[4] or 99),
                             "guest": _bool(row[5], True), "student": _bool(row[6], True),
                             "teacher": _bool(row[7], True)})
        if menu:
            cfg["menu"] = sorted(menu, key=lambda m: m["order"])

    # --- Εργαλειοθήκες ---------------------------------------------------------
    if "Εργαλειοθήκες" in wb.sheetnames:
        toolbars = []
        for row in wb["Εργαλειοθήκες"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                mode = str(row[2] or "dock").strip().lower()
                toolbars.append({"id": str(row[0]).strip(), "title": str(row[1]).strip(),
                                 "mode": mode if mode in ("dock", "float") else "dock",
                                 "x": int(row[3] or 40), "y": int(row[4] or 100),
                                 "w": int(row[5] or 300), "h": int(row[6] or 360),
                                 "guest": _bool(row[7]), "student": _bool(row[8]),
                                 "teacher": _bool(row[9], True)})
        if toolbars:
            cfg["toolbars"] = toolbars

    # --- Ρόλοι & πρόσβαση ------------------------------------------------------
    if "Ρόλοι" in wb.sheetnames:
        acc = cfg["access"]
        for row in wb["Ρόλοι"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0]:
                continue
            key, val = str(row[0]).strip(), str(row[1] or "").strip()
            if key == "student_code":
                acc["student_code"] = val
            elif key == "guest_chat":
                acc["guest_chat"] = _bool(val, True)
            elif key == "guest_forum":
                acc["guest_forum"] = _bool(val, False)
            elif key in ("allowed_guest", "allowed_student", "allowed_teacher"):
                role = key.split("_", 1)[1]
                acc["allowed_apps"][role] = (
                    "*" if val in ("", "*") else [u.strip() for u in val.split(",") if u.strip()])

    # --- Ονόματα guest ---------------------------------------------------------
    if "Ονόματα Guest" in wb.sheetnames:
        adjs, nouns, colors = [], [], []
        for row in wb["Ονόματα Guest"].iter_rows(min_row=2, values_only=True):
            if not row:
                continue
            if row[0]:
                adjs.append(str(row[0]).strip())
            if row[1]:
                nouns.append({"name": str(row[1]).strip(),
                              "emoji": str(row[2] or "🎲").strip()})
            if len(row) > 3 and row[3] and re.match(r"^#[0-9a-fA-F]{6}$", str(row[3]).strip()):
                colors.append(str(row[3]).strip())
        if adjs and nouns:
            cfg["guest_names"] = {"adjectives": adjs, "nouns": nouns,
                                  "colors": colors or state.GUEST_COLORS}

    # --- Timers ----------------------------------------------------------------
    if "Timers" in wb.sheetnames:
        timers = []
        for row in wb["Timers"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                vis = str(row[2] or "public").strip().lower()
                timers.append({"id": str(row[0]).strip(), "label": str(row[1]).strip(),
                               "visibility": vis if vis in ("private", "public") else "public",
                               "duration_sec": int(row[3]) if row[3] else None,
                               "anchor_tmima": str(row[4] or "").strip(),
                               "day": str(row[5] or "").strip(),
                               "period": int(row[6]) if row[6] else None,
                               "edge": str(row[7] or "end").strip(),
                               "offset_min": float(row[8] or 0),
                               "message": str(row[9] or "").strip(),
                               "audience": str(row[10] or "all").strip(),
                               "enabled": _bool(row[11], True)})
        cfg["timers"] = timers

    # --- Γεγονότα ---------------------------------------------------------------
    if "Γεγονότα" in wb.sheetnames:
        events = []
        for row in wb["Γεγονότα"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[1]:
                trig = str(row[1]).strip()
                action = str(row[6] or "announce").strip()
                events.append({"id": str(row[0]).strip(),
                               "trigger": trig if trig in ("day_end", "period_end", "time") else "day_end",
                               "period": int(row[2]) if row[2] else None,
                               "time": _hhmm(row[3]) if row[3] else "",
                               "offset_min": float(row[4] or 0),
                               "days": [d.strip() for d in str(row[5] or "").split(",") if d.strip()],
                               "action": action if action in ("announce", "congrats", "award", "navigate") else "announce",
                               "text": str(row[7] or "").strip(),
                               "url": str(row[8] or "").strip(),
                               "audience": str(row[9] or "all").strip(),
                               "tmima": str(row[10] or "").strip(),
                               "enabled": _bool(row[11], True)})
        cfg["events"] = events

    # --- Μηνύματα ----------------------------------------------------------------
    if "Μηνύματα" in wb.sheetnames:
        messages = []
        for row in wb["Μηνύματα"].iter_rows(min_row=2, values_only=True):
            if row and row[0] and row[2]:
                kind = str(row[1] or "announce").strip()
                messages.append({"id": str(row[0]).strip(),
                                 "kind": kind if kind in ("announce", "congrats", "award") else "announce",
                                 "text": str(row[2]).strip()})
        cfg["messages"] = messages

    # --- Poll & Quiz τράπεζες ------------------------------------------------------
    if "Poll-Quiz" in wb.sheetnames:
        polls, quiz_groups = [], {}
        for row in wb["Poll-Quiz"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0] or not row[2]:
                continue
            typ = str(row[0]).strip().lower()
            options = [str(o).strip() for o in row[3:7] if o]
            if typ == "poll" and len(options) >= 2:
                polls.append({"id": str(row[1] or secrets.token_hex(4)).strip(),
                              "question": str(row[2]).strip(), "options": options,
                              "show_results": _bool(row[8], True)})
            elif typ == "quiz" and len(options) >= 2 and row[7]:
                gid = str(row[9] or row[1] or "quiz").strip()
                group = quiz_groups.setdefault(gid, {"id": gid, "title": gid, "questions": []})
                group["questions"].append({"text": str(row[2]).strip(), "options": options,
                                           "correct": int(row[7]) - 1})
        cfg["polls_bank"] = polls
        cfg["quizzes_bank"] = [g for g in quiz_groups.values()
                               if all(0 <= q["correct"] < len(q["options"]) for q in g["questions"])]

    wb.close()
    return cfg


# ---------------------------------------------------------------------------
# Routes — ρυθμίσεις Excel (καθηγητής) & δημόσιες ρυθμίσεις ανά ρόλο
# ---------------------------------------------------------------------------
@router.get("/api/config/template")
def api_config_template(request: Request):
    state.require_teacher(request)
    if not state.TEMPLATE_XLSX.exists():
        make_template_xlsx()
    return FileResponse(state.TEMPLATE_XLSX, filename="rythmiseis-protypo.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/api/config/upload")
async def api_config_upload(request: Request, file: UploadFile = File(...)):
    state.require_teacher(request)
    name = PurePosixPath(file.filename or "").name
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Απαιτείται αρχείο Excel (.xlsx).")
    state.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = state.DATA_DIR / "rythmiseis-upload.xlsx"
    tmp.write_bytes(await file.read())
    try:
        cfg = parse_config_xlsx(tmp)
    except Exception as exc:
        raise HTTPException(400, f"Σφάλμα ανάγνωσης Excel: {exc}")
    state.save_config(cfg)
    state.CONFIG = state.load_config()                  # ΟΛΟΙ οι routers βλέπουν το νέο dict
    state.EVENTS_FIRED.clear()                          # νέο config → ξανα-οπλισμός γεγονότων
    await broadcast({"type": "config_updated"})         # όλοι ξαναφορτώνουν το μενού τους
    return {"ok": True,
            "summary": {"tmimata": len(state.CONFIG["schedule"]["tmimata"]),
                        "menu": len(state.CONFIG["menu"]), "toolbars": len(state.CONFIG["toolbars"]),
                        "timers": len(state.CONFIG["timers"]), "events": len(state.CONFIG["events"]),
                        "messages": len(state.CONFIG["messages"]),
                        "polls": len(state.CONFIG["polls_bank"]), "quizzes": len(state.CONFIG["quizzes_bank"])}}


@router.get("/api/config")
def api_config_get(request: Request):
    state.require_teacher(request)
    return state.CONFIG