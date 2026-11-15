#!/opt/school-portal/venv/bin/python
"""
exams-browser-test.py — Έλεγχος του /exams/ σε ΠΡΑΓΜΑΤΙΚΟ headless Chromium (CDP).

Ελέγχει τη πλήρη ροή:
  * Μαθητής: φίλτρο τάξης → επιλογή δραστηριότητας → παράδοση αρχείου → κωδικός.
  * Μαθητής: διαγώνισμα με χρονόμετρο, απαντήσεις, οριστική υποβολή.
  * Καθηγητής: login με teacher2026, λίστα, αυτόματη βαθμολογία, διακόπτης.

Χρήση: /opt/school-portal/venv/bin/python scripts/exams-browser-test.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request

import websocket

CHROME = shutil.which("chromium") or shutil.which("chromium-browser")
PORT = 9335  # διαφορετική θύρα από τα υπόλοιπα browser tests
BASE = "http://127.0.0.1"


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=120)
        self._id = 0

    def send(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def evaluate(self, expression):
        res = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(json.dumps(res["exceptionDetails"])[:400])
        return res.get("result", {}).get("value")


def wait_for(cdp, expr, timeout=60, interval=0.5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = cdp.evaluate(expr)
            if last:
                return last
        except Exception as exc:
            last = str(exc)
        time.sleep(interval)
    return last


passed = failed = 0


def check(label, ok, detail=""):
    global passed, failed
    mark = "\033[0;32m✓\033[0m" if ok else "\033[0;31m✗\033[0m"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    passed += bool(ok)
    failed += (not ok)


def api(path, payload=None, cookie=None, method=None):
    req = urllib.request.Request(BASE + "/exams/api/" + path)
    req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    if method:
        req.method = method
    data = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(req, data=data, timeout=20) as r:
        headers = r.headers
        body = json.load(r)
    return body, headers


def main():
    if not CHROME:
        print("✗ Δεν βρέθηκε chromium")
        return 1

    # --- Προετοιμασία μέσω API: καθαρισμός παλιών δοκιμών & νέες δραστηριότητες ---
    _, hdrs = api("teacher/login", {"password": "teacher2026"})
    cookie = hdrs.get("Set-Cookie", "").split(";")[0]
    acts, _ = api("teacher/activities", cookie=cookie)
    for a in acts["activities"]:
        if a["title"].startswith("BROWSER TEST"):
            api(f"teacher/activities/{a['id']}", cookie=cookie, method="DELETE")
    assignment, _ = api("teacher/activities", {
        "title": "BROWSER TEST Εργασία", "class_slug": "lykeio-a",
        "kind": "assignment", "active": True,
    }, cookie=cookie)
    test_act, _ = api("teacher/activities", {
        "title": "BROWSER TEST Διαγώνισμα", "class_slug": "lykeio-b",
        "kind": "test", "duration": 10, "active": True,
        "questions": [
            {"type": "mc", "text": "Πόσο κάνει 2**10;",
             "options": ["512", "1024", "2048"], "correct": 1, "points": 3},
            {"type": "essay", "text": "Εξήγησε τι είναι η αναδρομή.", "points": 7},
        ],
    }, cookie=cookie)
    with open("/tmp/exams-browser-upload.py", "w", encoding="utf-8") as f:
        f.write('print("Έλεγχος browser upload")\n')

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", f"--remote-debugging-port={PORT}",
         "--window-size=1400,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        targets = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=3) as r:
                    targets = json.load(r)
                if targets:
                    break
            except Exception:
                time.sleep(0.5)
        page = next(t for t in targets if t["type"] == "page")
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("DOM.enable")

        print("\n=== 1. Περιβάλλον Μαθητή — φόρτωση & φίλτρο τάξης ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/exams/"})
        got = wait_for(cdp, "!!document.getElementById('sel-class') && typeof loadActivities==='function'")
        check("Η σελίδα μαθητή φορτώνει", bool(got))
        opts = cdp.evaluate("[...document.getElementById('sel-class').options].map(o=>o.value).filter(Boolean)")
        check("Dropdown 6 τάξεων", len(opts) == 6, ", ".join(opts))

        cdp.evaluate("""(() => {
            const s=document.getElementById('sel-class');
            s.value='lykeio-a'; s.dispatchEvent(new Event('change'));
        })()""")
        got = wait_for(cdp, "[...document.getElementById('sel-activity').options].some(o=>o.textContent.includes('BROWSER TEST'))")
        check("Φιλτράρισμα ενεργών δραστηριοτήτων ανά τάξη", bool(got))
        wrong = cdp.evaluate("[...document.getElementById('sel-activity').options].some(o=>o.textContent.includes('Διαγώνισμα'))")
        check("Δεν εμφανίζονται δραστηριότητες άλλης τάξης", not wrong)

        print("\n=== 2. Παράδοση αρχείου εργασίας ===")
        cdp.evaluate(f"""(() => {{
            const s=document.getElementById('sel-activity');
            s.value='{assignment["id"]}'; s.dispatchEvent(new Event('change'));
            document.getElementById('inp-name').value='Ελένη Δημητρίου';
            document.getElementById('inp-section').value='Α3';
            document.getElementById('inp-comment').value='Δοκιμαστικό σχόλιο';
        }})()""")
        visible = wait_for(cdp, "!document.getElementById('file-fields').hidden")
        check("Εμφάνιση πεδίων αρχείου για assignment", bool(visible))
        doc = cdp.send("DOM.getDocument")
        node = cdp.send("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "#inp-file"})
        cdp.send("DOM.setFileInputFiles", {"files": ["/tmp/exams-browser-upload.py"], "nodeId": node["nodeId"]})
        cdp.evaluate("document.getElementById('btn-continue').click()")
        got = wait_for(cdp, "!document.getElementById('step-confirm-file').hidden")
        check("Οθόνη επιβεβαίωσης παράδοσης", bool(got))
        cdp.evaluate("document.getElementById('btn-submit-file').click()")
        code = wait_for(cdp, "!document.getElementById('step-done').hidden && document.getElementById('done-code').textContent")
        check("Κωδικός επιβεβαίωσης μετά την Οριστική Υποβολή", bool(code), str(code))
        check("Μορφή κωδικού XXXX-XXXX", bool(code) and len(str(code)) == 9 and "-" in str(code))

        print("\n=== 3. Ψηφιακό διαγώνισμα με χρονόμετρο ===")
        cdp.evaluate("document.getElementById('btn-new').click()")
        cdp.evaluate("""(() => {
            const s=document.getElementById('sel-class');
            s.value='lykeio-b'; s.dispatchEvent(new Event('change'));
        })()""")
        wait_for(cdp, "[...document.getElementById('sel-activity').options].some(o=>o.textContent.includes('BROWSER TEST'))")
        cdp.evaluate(f"""(() => {{
            const s=document.getElementById('sel-activity');
            s.value='{test_act["id"]}'; s.dispatchEvent(new Event('change'));
            document.getElementById('inp-name').value='Κώστας Νικολάου';
            document.getElementById('inp-section').value='Β2';
        }})()""")
        cdp.evaluate("document.getElementById('btn-continue').click()")
        got = wait_for(cdp, "!document.getElementById('step-test').hidden && document.querySelectorAll('#questions > div').length===2")
        check("Εμφάνιση 2 ερωτήσεων (MC + ανάπτυξης)", bool(got))
        timer = wait_for(cdp, "/^\\d{2}:\\d{2}$/.test(document.getElementById('timer').textContent) && document.getElementById('timer').textContent!=='--:--'")
        check("Χρονόμετρο αντίστροφης μέτρησης τρέχει", bool(timer), str(timer))
        leaked = cdp.evaluate("document.getElementById('questions').innerHTML.includes('correct')")
        check("Δεν διαρρέουν οι σωστές απαντήσεις στο DOM", not leaked)
        cdp.evaluate("""(() => {
            document.querySelector('input[name="q0"][value="1"]').checked=true;
            document.querySelector('textarea[name="q1"]').value='Η αναδρομή είναι…';
            window.confirm=()=>true;
            document.getElementById('btn-submit-test').click();
        })()""")
        code2 = wait_for(cdp, "!document.getElementById('step-done').hidden && document.getElementById('done-code').textContent")
        check("Οριστική υποβολή διαγωνίσματος με κωδικό", bool(code2), str(code2))

        print("\n=== 4. Περιβάλλον Καθηγητή ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/exams/teacher"})
        got = wait_for(cdp, "!!document.getElementById('login-form')")
        check("Η σελίδα καθηγητή φορτώνει", bool(got))
        cdp.evaluate("""(() => {
            document.getElementById('login-pass').value='λάθος';
            document.getElementById('login-form').dispatchEvent(new Event('submit',{cancelable:true}));
        })()""")
        err = wait_for(cdp, "!document.getElementById('login-error').hidden")
        check("Λανθασμένος κωδικός → μήνυμα σφάλματος", bool(err))
        cdp.evaluate("""(() => {
            document.getElementById('login-pass').value='teacher2026';
            document.getElementById('login-form').dispatchEvent(new Event('submit',{cancelable:true}));
        })()""")
        got = wait_for(cdp, "!document.getElementById('teacher-app').hidden && document.getElementById('activities-list').innerHTML.includes('BROWSER TEST')")
        check("Login teacher2026 → λίστα δραστηριοτήτων", bool(got))

        subs = wait_for(cdp, f"""(async () => {{
            const r = await fetch(window.EXAMS_BASE.replace(/teacher\\/$/,'')+'api/teacher/activities/{test_act["id"]}/submissions');
            const d = await r.json();
            const s = d.submissions.find(x=>x.fullname==='Κώστας Νικολάου');
            return s ? s.mc_score+'/'+s.mc_max : null;
        }})()""")
        check("Αυτόματη βαθμολογία MC στον πίνακα υποβολών", subs == "3/3", str(subs))

        toggle = cdp.evaluate(f"""(async () => {{
            const api = window.EXAMS_BASE.replace(/teacher\\/$/,'')+'api/';
            await fetch(api+'teacher/activities/{assignment["id"]}', {{method:'PATCH',
                headers:{{'Content-Type':'application/json'}}, body:'{{"active":false}}'}});
            const r = await fetch(api+'activities?class_slug=lykeio-a');
            const d = await r.json();
            return d.activities.every(a=>a.id!=={assignment["id"]});
        }})()""")
        check("Διακόπτης Κλειστό → εξαφάνιση από τους μαθητές", bool(toggle))

        print("\n=== 5. Dashboard card ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/"})
        got = wait_for(cdp, "[...document.querySelectorAll('a')].some(a=>a.getAttribute('href')==='/exams/' && a.textContent.includes('Παράδοση Εργασιών'))")
        check("Κάρτα «Παράδοση Εργασιών & Τεστ» στο Dashboard", bool(got))

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        # Καθαρισμός δοκιμαστικών δραστηριοτήτων
        try:
            acts, _ = api("teacher/activities", cookie=cookie)
            for a in acts["activities"]:
                if a["title"].startswith("BROWSER TEST"):
                    api(f"teacher/activities/{a['id']}", cookie=cookie, method="DELETE")
        except Exception:
            pass

    print(f"\n{'✅ ΟΛΑ ΠΕΡΑΣΑΝ' if not failed else '⚠️ ΑΠΟΤΥΧΙΕΣ'}: {passed}/{passed+failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())