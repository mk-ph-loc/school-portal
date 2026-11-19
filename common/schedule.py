"""
common.schedule — Ωράριο σχολείου: Excel → JSON, ώρες HH:MM & deadlines.

Ενοποιεί τη λογική που ήταν διπλογραμμένη σε Lesson Wizard και Classroom Hub:
  * parse_schedule_xlsx(): οι καρτέλες Τμήματα/Ωρες/Ωραριο του ενιαίου Excel
    (το ίδιο αρχείο ανεβαίνει και στα δύο apps — βλ. rythmiseis-protypo.xlsx),
  * hhmm(): κανονικοποίηση '8:15' / datetime.time / κλάσματος ημέρας του Excel,
  * schedule_deadline()/event_deadline(): epoch στιγμές από διδακτική ώρα
    ±offset λεπτών (timers & γεγονότα τέλους ημέρας/ώρας του Classroom Hub),
  * load_json()/save_json(): ανάγνωση/εγγραφή των JSON ρυθμίσεων.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

DAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή"]

EMPTY_SCHEDULE = {"tmimata": [], "periods": [], "timetable": {}}


def empty_schedule() -> dict:
    """Φρέσκο αντίγραφο του κενού ωραρίου (όχι κοινό mutable default)."""
    return json.loads(json.dumps(EMPTY_SCHEDULE))


def load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def hhmm(v) -> str:
    """Δέχεται '8:15', datetime.time ή κλάσμα ημέρας του Excel."""
    if hasattr(v, "strftime"):
        return v.strftime("%H:%M")
    if isinstance(v, (int, float)):
        mins = round(float(v) * 24 * 60)
        return f"{mins // 60:02d}:{mins % 60:02d}"
    s = str(v).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else s


def parse_schedule_xlsx(path: Path) -> dict:
    """Μετατρέπει το Excel ωραρίου στο JSON που καταναλώνει το schedule.js.

    Δέχεται τόσο το 4-φυλλο πρότυπο του Lesson Wizard όσο και το ενιαίο
    12-φυλλο του Classroom Hub (οι υπόλοιπες καρτέλες αγνοούνται εδώ).
    """
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    tmimata = []
    if "Τμήματα" in wb.sheetnames:
        for row in wb["Τμήματα"].iter_rows(min_row=2, values_only=True):
            if row and row[0]:
                tmimata.append({"name": str(row[0]).strip(),
                                "class_slug": str(row[1] or "").strip()})
    periods = []
    if "Ωρες" in wb.sheetnames:
        for row in wb["Ωρες"].iter_rows(min_row=2, values_only=True):
            if row and row[1] and row[2]:
                periods.append({"start": hhmm(row[1]), "end": hhmm(row[2])})
    timetable: dict = {}
    if "Ωραριο" in wb.sheetnames:
        for row in wb["Ωραριο"].iter_rows(min_row=2, values_only=True):
            if not row or not row[0] or not row[1] or not row[2]:
                continue
            tm, day, period = str(row[0]).strip(), str(row[1]).strip(), str(int(row[2]))
            title = str(row[3] or "").strip()
            url = str(row[4] or "").strip() if len(row) > 4 else ""
            timetable.setdefault(tm, {}).setdefault(day, {})[period] = {"title": title, "url": url}
    wb.close()
    return {"tmimata": tmimata, "periods": periods, "timetable": timetable,
            "updated": datetime.now().isoformat(timespec="seconds")}


def schedule_deadline(periods: list[dict], day: str, period: int,
                      edge: str, offset_min: float) -> float | None:
    """Υπολογίζει epoch deadline από διδακτική ώρα του ωραρίου + offset.
    edge: start|end· day='' → σημερινή ημέρα."""
    if not (1 <= period <= len(periods)):
        return None
    day_idx = DAYS.index(day) if day in DAYS else datetime.now().weekday()
    t = str(periods[period - 1]["start" if edge == "start" else "end"])
    try:
        h, m = map(int, t.split(":"))
    except ValueError:
        return None
    now = datetime.now()
    base = now.replace(hour=h, minute=m, second=0, microsecond=0)
    # μεταφορά στη σωστή ημέρα της εβδομάδας (ίδια εβδομάδα)
    return base.timestamp() + (day_idx - now.weekday()) * 86400 + offset_min * 60


def event_deadline(ev: dict, periods: list[dict]) -> float | None:
    """trigger: day_end (τέλος τελευταίας ώρας), period_end (συγκεκριμένη ώρα),
    time (συγκεκριμένη HH:MM) — πάντα με offset ±λεπτών."""
    trigger = ev.get("trigger", "day_end")
    offset = float(ev.get("offset_min", 0))
    now = datetime.now()
    if trigger == "day_end" and periods:
        t = periods[-1]["end"]
    elif trigger == "period_end":
        p = int(ev.get("period", 0))
        if not (1 <= p <= len(periods)):
            return None
        t = periods[p - 1]["end"]
    elif trigger == "time":
        t = str(ev.get("time", ""))
    else:
        return None
    try:
        h, m = map(int, t.split(":"))
    except ValueError:
        return None
    return now.replace(hour=h, minute=m, second=0, microsecond=0).timestamp() + offset * 60
