#!/usr/bin/env python3
"""
End-to-end έλεγχος του Εργαστηρίου Web (/web-lab/) μέσω Nginx (θύρα 80).

Προσομοιώνει έναν καθηγητή (login, δημιουργία δωματίου, broadcast, κλείδωμα,
δημοσίευση στο custom-apps) και δύο μαθητές (είσοδος με PIN, WebSocket,
ζωντανός συγχρονισμός HTML/CSS/JS, απόρριψη edit σε Μόνο Ανάγνωση), ελέγχοντας
και την επιβίωση του κώδικα μετά από refresh (SQLite). Χωρίς εξαρτήσεις εκτός
του venv (websocket-client). Εκτέλεση:
    /opt/school-portal/venv/bin/python /opt/school-portal/scripts/weblab-test.py
"""
import json
import sys
import time
import urllib.request
import http.cookiejar

from websocket import create_connection

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE                            # ίδιος κωδικός με τα apps

BASE = "http://127.0.0.1/web-lab/"
WS_BASE = "ws://127.0.0.1/web-lab/ws/"
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

    def call(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=15) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def cookie(self, name):
        return next((c.value for c in self.jar if c.name == name), None)

    def ws(self, pin, name):
        cookies = "; ".join(f"{c.name}={c.value}" for c in self.jar)
        return create_connection(
            WS_BASE + pin + "?name=" + urllib.parse.quote(name),
            header={"Cookie": cookies} if cookies else {}, timeout=15)


def ws_recv(ws, types, timeout=15):
    """Διαβάζει μηνύματα μέχρι να βρει έναν από τους ζητούμενους τύπους."""
    end = time.time() + timeout
    while time.time() < end:
        ws.settimeout(max(0.5, end - time.time()))
        msg = json.loads(ws.recv())
        if msg.get("type") in types:
            return msg
    raise TimeoutError(f"Δεν ελήφθη μήνυμα {types}")


def main():
    teacher = Client()
    student1 = Client()
    student2 = Client()

    print("[1] Σελίδες & αυθεντικοποίηση")
    with urllib.request.urlopen(BASE, timeout=10) as r:
        check("GET /web-lab/ → 200", r.status == 200)
    code, _ = teacher.call("api/publish", {"id": "x", "title": "x", "html": "<p>x</p>"})
    check("Δημοσίευση χωρίς login → 401", code == 401)
    code, _ = teacher.call("api/teacher/login", {"password": "λάθος"})
    check("Λάθος κωδικός → 401", code == 401)
    code, _ = teacher.call("api/teacher/login", {"password": TEACHER_CODE})
    check("Σωστός κωδικός → 200 + cookie", code == 200 and teacher.cookie("weblab_teacher"))

    print("[2] Δημιουργία δωματίου & είσοδος μαθητών (WebSockets)")
    code, room = teacher.call("api/rooms", {
        "name": "Αυτοματοποιημένος Έλεγχος",
        "html": "<h1>Άσκηση Τάξης</h1>", "css": "h1{color:red}", "js": "console.log('start');"})
    pin = room.get("pin", "")
    check("POST api/rooms → 4-ψήφιο PIN", code == 200 and len(pin) == 4 and pin.isdigit())
    code, snap = student1.call("api/rooms/" + pin)
    check("GET snapshot δωματίου (refresh-safe)", code == 200 and snap["code"]["html"] == "<h1>Άσκηση Τάξης</h1>")
    code, _ = student1.call("api/rooms/0000")
    check("Άγνωστο δωμάτιο → 404", code == 404)

    tws = teacher.ws(pin, "Καθηγητής")
    s1 = student1.ws(pin, "Μαρία")
    s2 = student2.ws(pin, "Γιώργος")
    st = ws_recv(tws, {"state"})
    check("Καθηγητής: snapshot κατά τη σύνδεση", st["code"]["css"] == "h1{color:red}")
    ws_recv(s1, {"state"}); ws_recv(s2, {"state"})
    # Τα μέλη μπαίνουν διαδοχικά → διαβάζουμε broadcasts μέχρι να φανούν και οι 3
    end = time.time() + 15
    names = []
    while time.time() < end:
        m = ws_recv(tws, {"members"})
        names = [x["name"] for x in m["members"]]
        if len(names) >= 3:
            break
    check("Λίστα μελών: 3 συνδέσεις με ονόματα", len(names) == 3 and "Μαρία" in names and "Γιώργος" in names)

    print("[3] Ζωντανός συγχρονισμός κώδικα")
    s1.send(json.dumps({"type": "edit", "panel": "html", "code": "<h1>Γεια από τη Μαρία!</h1>"}))
    got = ws_recv(s2, {"code"})
    check("HTML της Μαρίας → Γιώργος (live)", got["panel"] == "html" and "Μαρία" in got["code"])
    got_t = ws_recv(tws, {"code"})
    check("HTML της Μαρίας → Καθηγητής (live)", "Μαρία" in got_t["code"])
    s2.send(json.dumps({"type": "edit", "panel": "js", "code": "console.log('Γιώργος');"}))
    got = ws_recv(s1, {"code"})
    check("JS του Γιώργου → Μαρία (live)", got["panel"] == "js" and "Γιώργος" in got["code"])
    _, snap = student1.call("api/rooms/" + pin)
    check("Ο κώδικας αποθηκεύτηκε στη SQLite", "Μαρία" in snap["code"]["html"] and "Γιώργος" in snap["code"]["js"])

    print("[4] Broadcast & Κλείδωμα Καθηγητή")
    tws.send(json.dumps({"type": "broadcast", "html": "<h1>Βασική Άσκηση</h1>",
                         "css": "body{font-family:Arial}", "js": "// γράψε εδώ"}))
    full = ws_recv(s1, {"full"})
    check("«Αποστολή σε Όλους» → πλήρης αντικατάσταση", full["code"]["html"] == "<h1>Βασική Άσκηση</h1>")
    ws_recv(s2, {"full"})
    tws.send(json.dumps({"type": "lock", "locked": True}))
    lk = ws_recv(s1, {"lock"})
    check("«Μόνο Ανάγνωση» → lock στους μαθητές", lk["locked"] is True)
    ws_recv(s2, {"lock"}); ws_recv(tws, {"lock"})
    s1.send(json.dumps({"type": "edit", "panel": "html", "code": "<h1>ΔΕΝ ΕΠΙΤΡΕΠΕΤΑΙ</h1>"}))
    denied = ws_recv(s1, {"denied", "state"})
    check("Edit μαθητή σε κλειδωμένο δωμάτιο → απόρριψη", denied["type"] == "denied")
    _, snap = student1.call("api/rooms/" + pin)
    check("Ο κώδικας ΔΕΝ άλλαξε όσο είναι κλειδωμένος", snap["code"]["html"] == "<h1>Βασική Άσκηση</h1>")
    tws.send(json.dumps({"type": "edit", "panel": "css", "code": "body{background:#eef}"}))
    got = ws_recv(s1, {"code"})
    check("Ο καθηγητής γράφει ακόμα και κλειδωμένο", got["panel"] == "css")
    tws.send(json.dumps({"type": "lock", "locked": False}))
    lk = ws_recv(s1, {"lock"})
    check("Ξεκλείδωμα → οι μαθητές γράφουν ξανά", lk["locked"] is False)
    ws_recv(s2, {"lock"}); ws_recv(tws, {"lock"})

    print("[5] Δημοσίευση στα Custom Apps του Portal")
    pub_id = "weblab-e2e-test"
    code, pub = teacher.call("api/publish", {
        "id": pub_id, "title": "Weblab E2E Test", "description": "Αυτοματοποιημένος έλεγχος",
        "html": "<h1>Δημοσιευμένο!</h1>", "css": "h1{color:green}", "js": "console.log('ok');"})
    check("POST api/publish → 200 + url", code == 200 and pub.get("url") == f"/apps/{pub_id}/")
    with urllib.request.urlopen(f"http://127.0.0.1/apps/{pub_id}/", timeout=10) as r:
        body = r.read().decode()
    check("Η σελίδα σερβίρεται στο /apps/<id>/", r.status == 200 and "<style>" in body and "<script>" in body)
    with urllib.request.urlopen("http://127.0.0.1/apps/apps-manifest.json", timeout=10) as r:
        manifest = json.loads(r.read())
    check("Το apps-manifest.json περιέχει τη νέα κάρτα", any(a["id"] == pub_id for a in manifest["apps"]))
    code, _ = teacher.call("api/publish", {
        "id": pub_id, "title": "Weblab E2E Test", "html": "<p>ξανά</p>"})
    check("Διπλότυπο id χωρίς replace → 409", code == 409)
    code, _ = teacher.call("api/publish", {
        "id": "../evil", "title": "x", "html": "<p>x</p>"})
    check("Μη έγκυρο id (path traversal) → 400", code == 400)

    # --- Καθαρισμός test εφαρμογής & manifest ---
    import shutil, subprocess
    shutil.rmtree(f"/opt/school-portal/custom-apps/{pub_id}", ignore_errors=True)
    subprocess.run([sys.executable, "/opt/school-portal/scripts/build-apps-manifest.py"],
                   capture_output=True, timeout=60)
    print("  ↺ Η δοκιμαστική εφαρμογή αφαιρέθηκε & το manifest επανήλθε.")

    for w in (tws, s1, s2):
        w.close()

    print()
    if FAILED:
        print(f"✗ {FAILED} έλεγχοι απέτυχαν!")
        sys.exit(1)
    print("✓ Όλοι οι έλεγχοι του Web Lab πέρασαν επιτυχώς!")


if __name__ == "__main__":
    main()