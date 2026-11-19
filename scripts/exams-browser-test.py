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
import sys

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE, Client, check, launch_chrome, results, stop_chrome, wait_for

PORT = 9335  # διαφορετική θύρα από τα υπόλοιπα browser tests
BASE = "http://127.0.0.1"


class AsyncCDP:
    """Λεπτό wrapper του κοινού CDP: κάθε evaluate/wait_for με awaitPromise=True
    (οι έλεγχοι εδώ χρησιμοποιούν async fetch expressions)."""

    def __init__(self, cdp):
        self._cdp = cdp

    def send(self, method, params=None):
        return self._cdp.send(method, params)

    def evaluate(self, expr):
        return self._cdp.evaluate(expr, await_promise=True)

    def close(self):
        self._cdp.close()


def main():
    api = Client(BASE + "/exams/api/", timeout=20)

    # --- Προετοιμασία μέσω API: καθαρισμός παλιών δοκιμών & νέες δραστηριότητες ---
    api.call("teacher/login", {"password": TEACHER_CODE})
    _, acts = api.call("teacher/activities")
    for a in acts["activities"]:
        if a["title"].startswith("BROWSER TEST"):
            api.call(f"teacher/activities/{a['id']}", method="DELETE")
    _, assignment = api.call("teacher/activities", {
        "title": "BROWSER TEST Εργασία", "class_slug": "lykeio-a",
        "kind": "assignment", "active": True,
    })
    _, test_act = api.call("teacher/activities", {
        "title": "BROWSER TEST Διαγώνισμα", "class_slug": "lykeio-b",
        "kind": "test", "duration": 10, "active": True,
        "questions": [
            {"type": "mc", "text": "Πόσο κάνει 2**10;",
             "options": ["512", "1024", "2048"], "correct": 1, "points": 3},
            {"type": "essay", "text": "Εξήγησε τι είναι η αναδρομή.", "points": 7},
        ],
    })
    with open("/tmp/exams-browser-upload.py", "w", encoding="utf-8") as f:
        f.write('print("Έλεγχος browser upload")\n')

    try:
        proc, raw_cdp = launch_chrome(PORT, timeout=120)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    cdp = AsyncCDP(raw_cdp)
    try:
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
        cdp.evaluate(f"""(() => {{
            document.getElementById('login-pass').value={json.dumps(TEACHER_CODE)};
            document.getElementById('login-form').dispatchEvent(new Event('submit',{{cancelable:true}}));
        }})()""")
        got = wait_for(cdp, "!document.getElementById('teacher-app').hidden && document.getElementById('activities-list').innerHTML.includes('BROWSER TEST')")
        check("Login καθηγητή → λίστα δραστηριοτήτων", bool(got))

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
        cdp.close()
        stop_chrome(proc)
        # Καθαρισμός δοκιμαστικών δραστηριοτήτων
        try:
            _, acts = api.call("teacher/activities")
            for a in acts["activities"]:
                if a["title"].startswith("BROWSER TEST"):
                    api.call(f"teacher/activities/{a['id']}", method="DELETE")
        except Exception:
            pass

    r = results()
    print(f"\n{'✅ ΟΛΑ ΠΕΡΑΣΑΝ' if not r.failed else '⚠️ ΑΠΟΤΥΧΙΕΣ'}: {r.passed}/{r.passed + r.failed}")
    return r.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())