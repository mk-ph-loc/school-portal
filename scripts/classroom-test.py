#!/usr/bin/env python3
"""
End-to-end έλεγχος της Ζωντανής Τάξης (/classroom/) μέσω Nginx (θύρα 80).

Προσομοιώνει καθηγητή + μαθητή + guest: είσοδοι, παρουσία (roster/heartbeat),
ανακοινώσεις/βραβεία, τυχαία επιλογή, υποχρεωτική πλοήγηση, poll (ορατότητα
αποτελεσμάτων), quiz (καταγραφή ΜΟΝΟ για μαθητές), timers ιδιωτικούς/δημόσιους
με offset ωραρίου, chat/forum και το ενιαίο Excel ρυθμίσεων (round-trip και
με τον parser του Lesson Wizard). Εκτέλεση:
    /opt/school-portal/venv/bin/python /opt/school-portal/scripts/classroom-test.py
"""
import io
import json
import sys
import time
import urllib.request
import http.cookiejar

from websocket import create_connection

BASE = "http://127.0.0.1/classroom/"
WS_URL = "ws://127.0.0.1/classroom/ws"
FAILED = 0


def check(label, cond):
    global FAILED
    print(("  ✓ " if cond else "  ✗ ") + label)
    if not cond:
        FAILED += 1


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.ws = None
        self.last_roster = None

    def call(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=15) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def cookie_header(self):
        return "; ".join(f"{c.name}={c.value}" for c in self.jar)

    def connect(self):
        self.ws = create_connection(WS_URL, timeout=15,
                                    header={"Cookie": self.cookie_header()})
        return self.ws

    def send(self, obj):
        self.ws.send(json.dumps(obj))

    def recv(self, types, timeout=15):
        """Διαβάζει μέχρι να βρει ζητούμενο τύπο· τα roster κρατιούνται πάντα
        ενημερωμένα στο self.last_roster (ώστε να μην χάνονται ενημερώσεις)."""
        end = time.time() + timeout
        while time.time() < end:
            self.ws.settimeout(max(0.5, end - time.time()))
            msg = json.loads(self.ws.recv())
            if msg.get("type") == "roster":
                self.last_roster = msg
            if msg.get("type") in types:
                return msg
        raise TimeoutError(f"Δεν ελήφθη μήνυμα {types}")

    def wait_roster(self, pred, timeout=10):
        """Περιμένει roster που να ικανοποιεί τη συνθήκη (τρέχον ή επόμενο)."""
        if self.last_roster and pred(self.last_roster):
            return self.last_roster
        end = time.time() + timeout
        while time.time() < end:
            msg = self.recv(["roster"], timeout=max(0.5, end - time.time()))
            if pred(msg):
                return msg
        raise TimeoutError("Το roster δεν ικανοποίησε τη συνθήκη")

    def close(self):
        try:
            self.ws and self.ws.close()
        except Exception:
            pass


def main():
    teacher, student, guest = Client(), Client(), Client()

    print("[1] Σελίδες & είσοδοι ανά ρόλο")
    with urllib.request.urlopen(BASE, timeout=10) as r:
        check("GET /classroom/ → 200", r.status == 200)
    code, _ = teacher.call("api/roster")
    check("Roster χωρίς login → 401", code == 401)
    code, _ = teacher.call("api/join", {"role": "teacher", "code": "λάθος"})
    check("Λάθος κωδικός καθηγητή → 403", code == 403)
    code, r = teacher.call("api/join", {"role": "teacher", "code": "teacher2026", "name": "Κος Παπαδόπουλος"})
    check("Καθηγητής → 200 + HMAC cookies", code == 200 and r["identity"]["role"] == "teacher")
    code, r = student.call("api/join", {"role": "student", "name": "Μαρία", "tmima": "Γ1"})
    check("Μαθητής (όνομα+τμήμα) → 200", code == 200 and r["identity"]["name"] == "Μαρία")
    code, r = guest.call("api/join", {"role": "guest"})
    gname = r["identity"]["name"]
    check(f"Guest → παιχνιδιάρικο όνομα ('{gname}')", code == 200 and " " in gname and r["identity"]["emoji"])

    print("[2] Παρουσία σε πραγματικό χρόνο (WebSocket + heartbeat)")
    teacher.connect(); teacher.recv(["welcome"])
    student.connect(); student.recv(["welcome"])
    guest.connect(); guest.recv(["welcome"])
    roster = teacher.wait_roster(
        lambda r: {"Κος Παπαδόπουλος", "Μαρία", gname} <= {c["name"] for c in r["clients"]})
    check("Roster καθηγητή: βλέπει και τους 3", True)
    roles = {c["name"]: c["role"] for c in roster["clients"]}
    check("Σωστοί ρόλοι στο roster", roles.get("Μαρία") == "student" and roles.get(gname) == "guest")
    student.send({"type": "ping", "page": "/docs/"})
    student.recv(["pong"])
    roster = teacher.wait_roster(
        lambda r: any(c["name"] == "Μαρία" and c["page"] == "/docs/" for c in r["clients"]))
    check("Heartbeat ενημερώνει τη σελίδα που βλέπει ο μαθητής", True)

    print("[3] Ανακοινώσεις / συγχαρητήρια / βραβεία")
    code, r = teacher.call("api/cmd/announce", {"kind": "announce", "text": "Ξεκινάμε!", "audience": "all"})
    check("Ανακοίνωση → εστάλη σε ≥3", code == 200 and r["sent"] >= 3)
    m = student.recv(["announcement"]); check("Μαθητής έλαβε ανακοίνωση", m["text"] == "Ξεκινάμε!")
    guest.recv(["announcement"])
    guid = next(c["uid"] for c in roster["clients"] if c["name"] == gname)
    code, r = teacher.call("api/cmd/announce", {"kind": "award", "text": f"🏆 {gname}!", "target_uid": guid})
    m = guest.recv(["announcement"])
    check("Προσωπικό βραβείο στον guest", m["kind"] == "award" and m["target_uid"] == guid)
    code, r = teacher.call("api/cmd/random-pick", {"audience": "students"})
    check("Τυχαία επιλογή από συνδεδεμένους", code == 200 and r["picked"]["name"] in ("Μαρία", gname))
    student.recv(["random_pick"]); guest.recv(["random_pick"])

    print("[4] Υποχρεωτική πλοήγηση μαθητών/guests")
    code, r = teacher.call("api/cmd/navigate", {"url": "/live-quiz/", "audience": "students"})
    check("Navigate → εστάλη σε μαθητή+guest", code == 200 and r["sent"] == 2)
    m = student.recv(["navigate"]); check("Μαθητής μεταφέρθηκε στο /live-quiz/", m["url"] == "/live-quiz/")
    guest.recv(["navigate"])
    code, _ = teacher.call("api/cmd/navigate", {"url": "https://evil.example.com"})
    check("Εξωτερικό URL απορρίπτεται → 400", code == 400)


    print("[5] Poll — ορατότητα αποτελεσμάτων")
    code, r = teacher.call("api/cmd/poll", {"question": "Αρέσει η Python;", "options": ["Ναι", "Όχι"],
                                            "show_results": True, "audience": "students"})
    pid = r.get("id")
    check("Poll δημιουργήθηκε", code == 200 and pid)
    student.recv(["poll"]); guest.recv(["poll"])
    student.send({"type": "poll_vote", "id": pid, "choice": 0})
    m = student.recv(["poll_voted", "poll_results"])
    res = student.recv(["poll_results"]) if m["type"] == "poll_voted" else m
    check("Ψήφος μαθητή + ζωντανά αποτελέσματα (show=1)", res["counts"][0] == 1)
    guest.send({"type": "poll_vote", "id": pid, "choice": 1})
    guest.recv(["poll_voted", "poll_results"])
    # poll με ΚΡΥΦΑ αποτελέσματα
    code, r = teacher.call("api/cmd/poll", {"question": "Κρυφή ψηφοφορία;", "options": ["Α", "Β"],
                                            "show_results": False, "audience": "students"})
    pid2 = r["id"]
    student.recv(["poll"]); guest.recv(["poll"])
    student.send({"type": "poll_vote", "id": pid2, "choice": 0})
    got_results = False
    end = time.time() + 3
    while time.time() < end:
        student.ws.settimeout(0.6)
        try:
            msg = json.loads(student.ws.recv())
            if msg.get("type") == "poll_results" and msg.get("id") == pid2:
                got_results = True
        except Exception:
            break
    check("Κρυφό poll: ο μαθητής ΔΕΝ βλέπει αποτελέσματα", not got_results)
    code, r = teacher.call(f"api/cmd/poll/{pid2}/close", {})
    check("Ο καθηγητής βλέπει πάντα τα αποτελέσματα", code == 200 and r["results"]["counts"][0] == 1)
    m = student.recv(["poll_results"])
    check("Στο κλείσιμο όλοι βλέπουν το τελικό αποτέλεσμα", m["closed"] is True)
    guest.recv(["poll_results"])

    print("[6] Quiz — καταγραφή ΜΟΝΟ για μαθητές")
    quiz = {"title": "Δυαδικά", "questions": [
        {"text": "Πόσα bits ένα byte;", "options": ["4", "8", "16"], "correct": 1},
        {"text": "1010₂ = ;", "options": ["8", "10", "12"], "correct": 1}], "audience": "students"}
    code, r = teacher.call("api/cmd/quiz", quiz)
    qid = r.get("id")
    check("Quiz εστάλη", code == 200 and r["count"] == 2)
    mq = student.recv(["quiz"])
    check("Οι ερωτήσεις ΔΕΝ αποκαλύπτουν το correct", "correct" not in mq["questions"][0])
    guest.recv(["quiz"])
    student.send({"type": "quiz_submit", "id": qid, "answers": [1, 1]})
    ms = student.recv(["quiz_result"])
    check("Μαθητής: 2/2 + καταγράφηκε", ms["score"] == 2 and ms["recorded"] is True)
    prog = teacher.recv(["quiz_progress"])
    check("Καθηγητής βλέπει ζωντανά το σκορ", prog["name"] == "Μαρία" and prog["score"] == 2)
    guest.send({"type": "quiz_submit", "id": qid, "answers": [1, 0]})
    mg = guest.recv(["quiz_result"])
    check("Guest: εξάσκηση ΧΩΡΙΣ καταγραφή", mg["score"] == 1 and mg["recorded"] is False)
    code, r = teacher.call("api/quizzes")
    results = next(q["results"] for q in r["quizzes"] if q["id"] == qid)
    check("SQLite: μόνο ο μαθητής στο ιστορικό", len(results) == 1 and results[0]["name"] == "Μαρία"
          and results[0]["tmima"] == "Γ1" and results[0]["score"] == 2)


    print("[7] Timers — ιδιωτικός/δημόσιος + ωράριο ±offset")
    code, r = teacher.call("api/cmd/timer", {"label": "Ιδιωτικός", "duration_sec": 300, "visibility": "private"})
    check("Ιδιωτικός timer δημιουργήθηκε", code == 200)
    teacher.recv(["timer"])
    got_private = False
    end = time.time() + 2
    while time.time() < end:
        student.ws.settimeout(0.6)
        try:
            msg = json.loads(student.ws.recv())
            if msg.get("type") == "timer":
                got_private = True
        except Exception:
            break
    check("Ιδιωτικός timer: ΔΕΝ φαίνεται στους μαθητές", not got_private)
    code, r = teacher.call("api/cmd/timer", {"label": "Δημόσιος", "duration_sec": 5, "visibility": "public"})
    tid = r["id"]
    student.recv(["timer"]); guest.recv(["timer"]); teacher.recv(["timer"])
    m = student.recv(["timer_done"], timeout=12)
    check("Λήξη δημόσιου timer → ειδοποίηση σε όλους", m["id"] == tid)
    guest.recv(["timer_done"]); teacher.recv(["timer_done"])
    # anchor στο ωράριο: επόμενη ώρα που δεν έχει περάσει σήμερα, με offset -1'
    code, cfg = teacher.call("api/config")
    from datetime import datetime
    now = datetime.now()
    periods = cfg["schedule"]["periods"]
    future = None
    for i, p in enumerate(periods, 1):
        h, mnt = map(int, p["end"].split(":"))
        if (h * 60 + mnt) > (now.hour * 60 + now.minute + 2):
            future = i
            break
    if future and now.weekday() < 5:
        code, r = teacher.call("api/cmd/timer", {"label": "Ωράριο", "period": future,
                                                 "edge": "end", "offset_min": -1, "visibility": "public"})
        check(f"Timer αγκυρωμένος στη λήξη {future}ης ώρας −1΄", code == 200)
        if code == 200:
            h, mnt = map(int, periods[future - 1]["end"].split(":"))
            expected = now.replace(hour=h, minute=mnt, second=0, microsecond=0).timestamp() - 60
            check("Το deadline = λήξη ώρας − 60s (offset)", abs(r["ends_at"] - expected) < 2)
            teacher.call(f"api/cmd/timer/{r['id']}/stop", {})
            teacher.recv(["timer_stop"]); student.recv(["timer_stop"]); guest.recv(["timer_stop"])
    else:
        print("  ⏭ (παράλειψη anchor test: εκτός ωραρίου/Σαββατοκύριακο)")

    print("[8] Chat & Forum")
    student.send({"type": "chat", "text": "Γεια από τη Μαρία!"})
    m = guest.recv(["chat"])
    check("Chat μαθητή → όλοι το βλέπουν", m["text"] == "Γεια από τη Μαρία!" and m["name"] == "Μαρία")
    teacher.recv(["chat"]); student.recv(["chat"])
    code, _ = guest.call("api/forum/threads")
    check("Forum: ο guest αποκλείεται (Ρόλοι!guest_forum=ΟΧΙ)", code == 403)
    code, r = student.call("api/forum/threads", {"title": "Αναδρομή", "text": "Πώς δουλεύει;"})
    ftid = r.get("id")
    check("Μαθητής άνοιξε νήμα forum", code == 200 and ftid)
    teacher.recv(["forum_thread"])
    teacher.send({"type": "forum_post", "thread_id": ftid, "text": "Δες το μάθημα 3!"})
    m = student.recv(["forum_post"])
    check("Απάντηση καθηγητή ζωντανά στο νήμα", m["text"] == "Δες το μάθημα 3!")
    code, _ = teacher.call(f"api/forum/threads/{ftid}/lock", {"locked": True})
    student.recv(["forum_lock"])
    check("Κλείδωμα νήματος από καθηγητή", code == 200)


    print("[9] Ενιαίο Excel ρυθμίσεων (round-trip + συμβατότητα Lesson Wizard)")
    code, _ = Client().call("api/config/template")
    check("Πρότυπο χωρίς login → 401", code == 401)
    req = urllib.request.Request(BASE + "api/config/template",
                                 headers={"Cookie": teacher.cookie_header()})
    with urllib.request.urlopen(req, timeout=20) as res:
        xlsx_bytes = res.read()
    check("Λήψη προτύπου .xlsx", xlsx_bytes[:2] == b"PK")
    sys.path.insert(0, "/opt/school-portal")            # κοινό πακέτο common/
    sys.path.insert(0, "/opt/school-portal/apps/classroom-hub")
    import app as hub
    from pathlib import Path
    tmp = Path("/tmp/classroom-test-config.xlsx")
    tmp.write_bytes(xlsx_bytes)
    cfg = hub.parse_config_xlsx(tmp)
    check("Parser: καρτέλες → menu/toolbars/timers/events/quiz",
          len(cfg["menu"]) >= 5 and len(cfg["toolbars"]) >= 3 and len(cfg["timers"]) >= 2
          and len(cfg["events"]) >= 2 and len(cfg["quizzes_bank"]) >= 1)
    import importlib.util
    spec = importlib.util.spec_from_file_location("lw", "/opt/school-portal/apps/lesson-wizard/app.py")
    lw = importlib.util.module_from_spec(spec); spec.loader.exec_module(lw)
    sched = lw.parse_schedule_xlsx(tmp)
    check("Το ίδιο Excel διαβάζεται ΑΥΤΟΥΣΙΟ από το Lesson Wizard (ωράριο)",
          sched["tmimata"] == cfg["schedule"]["tmimata"]
          and sched["periods"] == cfg["schedule"]["periods"]
          and sched["timetable"] == cfg["schedule"]["timetable"])
    # upload μέσω multipart
    boundary = "----classroomtest"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"r.xlsx\"\r\n"
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n").encode() \
        + xlsx_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE + "api/config/upload", data=body, method="POST",
                                 headers={"Cookie": teacher.cookie_header(),
                                          "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=20) as res:
        up = json.loads(res.read())
    check("Upload Excel → εφαρμογή ρυθμίσεων", up.get("ok") and up["summary"]["tmimata"] == 3)
    student.recv(["config_updated"], timeout=10); guest.recv(["config_updated"]); teacher.recv(["config_updated"])
    check("config_updated broadcast σε όλους", True)
    code, pub = guest.call("api/config/public")
    check("Guest: μενού χωρίς Forum (ανά ρόλο)", all(m["id"] != "forum" for m in pub["menu"]))
    code, pubs = student.call("api/config/public")
    check("Μαθητής: μενού ΜΕ Forum", any(m["id"] == "forum" for m in pubs["menu"]))

    print("[9β] Μόνιμες ανακοινώσεις + διαχείριση (edit/delete/bulk)")
    code, r = teacher.call("api/announcements?limit=50")
    anns = r.get("announcements", [])
    check("Ανακοινώσεις αποθηκευμένες στη SQLite", code == 200 and any(a["text"] == "Ξεκινάμε!" for a in anns))
    aid = next(a["id"] for a in anns if a["text"] == "Ξεκινάμε!")
    code, r = teacher.call(f"api/announcements/{aid}", {"text": "Ξεκινάμε τώρα!", "kind": "announce"}, method="PUT")
    m = student.recv(["announcement_updated"])
    check("Edit ανακοίνωσης → ζωντανή ενημέρωση σε όλους", code == 200 and m["text"] == "Ξεκινάμε τώρα!")
    guest.recv(["announcement_updated"]); teacher.recv(["announcement_updated"])
    # σύνθετη ανακοίνωση με συνδέσμους + άμεση μετάβαση
    code, r = teacher.call("api/cmd/announce", {
        "kind": "announce", "text": "Δείτε το μάθημα", "audience": "students",
        "links": [{"title": "Αναδρομή", "url": "/docs/mathimata/gymnasio-g/pliroforiki/"},
                  {"title": "bad", "url": "https://evil.example"}], "navigate": True})
    adv_id = r["announcement"]["id"]
    check("Σύνθετη: κρατιέται μόνο ο έγκυρος σχετικός σύνδεσμος",
          code == 200 and len(r["announcement"]["links"]) == 1)
    m = student.recv(["announcement"])
    check("Μαθητής έλαβε σύνθετη ανακοίνωση με links", m["id"] == adv_id and m["links"][0]["title"] == "Αναδρομή")
    m = student.recv(["navigate"])
    check("Άμεση μετάβαση στον 1ο σύνδεσμο", m["url"] == "/docs/mathimata/gymnasio-g/pliroforiki/")
    guest.recv(["announcement"]); guest.recv(["navigate"])
    # Ο καθηγητής ΔΕΝ λαμβάνει announce/navigate με audience=students (σωστό).
    code, cat = teacher.call("api/lessons-catalog")
    check("Κατάλογος μαθημάτων (tags/favorite) για τη σύνθετη",
          code == 200 and len(cat["lessons"]) >= 3
          and all("tags" in l and "favorite" in l for l in cat["lessons"]))
    code, r = teacher.call("api/announce-links", {"action": "add", "title": "Εργασίες", "url": "/exams/"})
    check("Διαμορφώσιμος σύνδεσμος αποθηκεύεται", code == 200 and any(l["url"] == "/exams/" for l in r["links"]))
    teacher.call("api/announce-links", {"action": "remove", "url": "/exams/"})
    code, r = teacher.call(f"api/announcements/{adv_id}", method="DELETE")
    m = student.recv(["announcement_deleted"])
    check("Delete ανακοίνωσης → αφαίρεση παντού", code == 200 and m["id"] == adv_id)
    guest.recv(["announcement_deleted"]); teacher.recv(["announcement_deleted"])
    code, r = teacher.call("api/announcements/bulk", {"action": "delete", "ids": [aid]})
    check("Bulk διαγραφή ανακοινώσεων", code == 200 and r["affected"] == 1)
    student.recv(["announcements_bulk_deleted"]); guest.recv(["announcements_bulk_deleted"])
    teacher.recv(["announcements_bulk_deleted"])

    print("[9γ] Poll/Quiz lifecycle — auto-close & όχι επανεμφάνιση μετά την απάντηση")
    code, r = teacher.call("api/cmd/poll", {"question": "Auto-close poll;", "options": ["Ναι", "Όχι"],
                                            "audience": "role:student", "auto_close": True})
    apid = r["id"]
    student.recv(["poll"])
    student.send({"type": "poll_vote", "id": apid, "choice": 0})
    student.recv(["poll_voted"])
    # Πρώτα έρχεται το ζωντανό αποτέλεσμα (closed=False) και μετά το τελικό
    # του αυτόματου κλεισίματος (closed=True) — διαβάζουμε μέχρι το closed.
    closed_seen = False
    for _ in range(3):
        m = student.recv(["poll_results"], timeout=10)
        if m.get("closed"):
            closed_seen = True
            break
    check("Poll έκλεισε ΜΟΝΟ του όταν ψήφισαν όλοι οι eligible", closed_seen)
    teacher.recv(["poll_results"]); teacher.recv(["poll_results"])
    # reconnect του μαθητή: το welcome ΔΕΝ πρέπει να ξαναστείλει το απαντημένο poll
    student.close(); student.connect()
    w = student.recv(["welcome"])
    check("Reconnect: κανένα απαντημένο poll στο welcome", all(p["id"] != apid for p in w["polls"]))
    check("Reconnect: κανένα υποβεβλημένο quiz στο welcome", len(w["quizzes"]) == 0)
    # χρονικό όριο poll
    code, r = teacher.call("api/cmd/poll", {"question": "Με όριο;", "options": ["Α", "Β"],
                                            "audience": "guests", "auto_close": False, "duration_sec": 5})
    tpid = r["id"]
    guest.recv(["poll"])
    m = guest.recv(["poll_results"], timeout=12)
    check("Poll με duration_sec έκλεισε αυτόματα στη λήξη", m["id"] == tpid and m["closed"] is True)
    teacher.recv(["poll_results"])
    # edit & bulk polls
    code, _ = teacher.call(f"api/polls/{tpid}", {"question": "Με όριο — διορθωμένο"}, method="PUT")
    check("Edit δημοσκόπησης", code == 200)
    teacher.recv(["poll_updated"])
    code, r = teacher.call("api/polls/bulk", {"action": "delete", "ids": [apid, tpid]})
    check("Bulk διαγραφή polls (+ψήφοι)", code == 200 and r["affected"] == 2)
    student.recv(["poll_deleted"]); student.recv(["poll_deleted"])
    guest.recv(["poll_deleted"]); guest.recv(["poll_deleted"])
    teacher.recv(["poll_deleted"]); teacher.recv(["poll_deleted"])
    # quiz edit (τίτλος) & διαγραφή αποτελέσματος & bulk delete
    code, qs = teacher.call("api/quizzes")
    last_q = qs["quizzes"][0]
    code, _ = teacher.call(f"api/quizzes/{last_q['id']}", {"title": "Quiz — νέο όνομα"}, method="PUT")
    check("Edit τίτλου quiz", code == 200)
    teacher.recv(["quiz_updated"])
    rid = last_q["results"][0]["id"]
    code, _ = teacher.call(f"api/quiz-results/{rid}", method="DELETE")
    check("Διαγραφή μεμονωμένου αποτελέσματος", code == 200)
    code, r = teacher.call("api/quizzes/bulk", {"action": "delete", "ids": [last_q["id"]]})
    check("Bulk διαγραφή quiz (+αποτελέσματα)", code == 200 and r["affected"] == 1)
    student.recv(["quiz_deleted"]); guest.recv(["quiz_deleted"]); teacher.recv(["quiz_deleted"])

    print("[9δ] Chat moderation — σιωπή & διαγραφή μηνυμάτων")
    suid = next(c["uid"] for c in teacher.last_roster["clients"] if c["name"] == "Μαρία")
    code, r = teacher.call("api/mutes", {"uid": suid, "minutes": 5})
    m = student.recv(["muted"])
    check("Σιωπή μαθητή → προσωπική ειδοποίηση", code == 200 and r["muted"] and m["until_ts"] > time.time())
    teacher.recv(["mute_changed"])
    student.send({"type": "chat", "text": "Δεν πρέπει να περάσει"})
    m = student.recv(["muted"], timeout=8)
    check("Muted μήνυμα μπλοκάρεται στον server", m["until_ts"] > time.time())
    code, r = teacher.call("api/mutes", {"uid": suid, "minutes": 0})
    student.recv(["unmuted"])
    check("Άρση σιωπής", code == 200 and not r["muted"])
    teacher.recv(["mute_changed"])
    student.send({"type": "chat", "text": "Ανάρμοστο μήνυμα"})
    m = guest.recv(["chat"]); bad_id = m["id"]
    student.recv(["chat"]); teacher.recv(["chat"])
    code, _ = teacher.call(f"api/chat/messages/{bad_id}", method="DELETE")
    m = guest.recv(["chat_deleted"])
    check("Διαγραφή μηνύματος → ζωντανά σε όλους", code == 200 and bad_id in m["ids"])
    student.recv(["chat_deleted"]); teacher.recv(["chat_deleted"])
    code, hist = student.call("api/chat/history")
    check("Το διαγραμμένο μήνυμα δεν υπάρχει στο ιστορικό", all(x["id"] != bad_id for x in hist["messages"]))
    student.send({"type": "chat", "text": "msg για bulk 1"})
    b1 = guest.recv(["chat"])["id"]; student.recv(["chat"]); teacher.recv(["chat"])
    student.send({"type": "chat", "text": "msg για bulk 2"})
    b2 = guest.recv(["chat"])["id"]; student.recv(["chat"]); teacher.recv(["chat"])
    code, r = teacher.call("api/chat/bulk", {"ids": [b1, b2]})
    check("Bulk διαγραφή chat", code == 200 and r["affected"] == 2)
    guest.recv(["chat_deleted"]); student.recv(["chat_deleted"]); teacher.recv(["chat_deleted"])

    print("[10] Αποσύνδεση → ενημέρωση roster")
    guest.close()
    try:
        teacher.wait_roster(lambda r: all(c["name"] != gname for c in r["clients"]), timeout=10)
        removed = True
    except TimeoutError:
        removed = False
    check("Ο guest έφυγε από το roster άμεσα", removed)
    student.close(); teacher.close()

    print()
    if FAILED:
        print(f"✗ {FAILED} έλεγχοι ΑΠΕΤΥΧΑΝ")
        sys.exit(1)
    print("✓ ΟΛΟΙ οι έλεγχοι πέρασαν — η Ζωντανή Τάξη λειτουργεί!")


if __name__ == "__main__":
    main()
