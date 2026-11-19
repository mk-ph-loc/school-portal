#!/opt/school-portal/venv/bin/python
"""
weblab-browser-test.py — Έλεγχος του /web-lab/ σε ΠΡΑΓΜΑΤΙΚΟ browser.

Χρησιμοποιεί headless Chromium μέσω DevTools Protocol (CDP) για να ελέγξει:
  * ότι οι 3 CodeMirror editors (HTML/CSS/JS) φορτώνονται με χρωματισμό σύνταξης
  * ότι η ζωντανή προεπισκόπηση <iframe> εκτελεί τον κώδικα
  * ότι η ενσωματωμένη κονσόλα πιάνει console.log ΚΑΙ σφάλματα JS (χωρίς F12)
  * ότι τα snippets εισάγονται με 1 κλικ και το Auto-Run ενημερώνει την προεπισκόπηση
  * ότι το κουμπί «Εκτέλεση / Ανανέωση» και το dark/light theme λειτουργούν

Χρήση: /opt/school-portal/venv/bin/python scripts/weblab-browser-test.py
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import check, launch_chrome, results, stop_chrome, wait_for

PORT = 9337
BASE = "http://127.0.0.1"


def main() -> int:
    try:
        proc, cdp = launch_chrome(PORT, window="1500,1000", timeout=200)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1

    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")

        print("\n=== 1. Φόρτωση editor (CodeMirror τοπικά, offline) ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/web-lab/"})
        got = wait_for(cdp, "document.querySelectorAll('.CodeMirror').length === 3", timeout=40)
        check("3 πάνελ CodeMirror δημιουργήθηκαν", bool(got))
        colored = wait_for(cdp, "document.querySelectorAll('.CodeMirror .cm-tag').length > 0", timeout=20)
        check("Χρωματισμός σύνταξης HTML (cm-tag)", bool(colored))
        title = cdp.evaluate("document.title")
        check("Ελληνικός τίτλος σελίδας", "Εργαστήριο Web" in str(title), str(title))

        print("\n=== 2. Ζωντανή προεπισκόπηση & κονσόλα ===")
        # Το default project γράφει console.log μόνο στο click — βάζουμε δικό μας κώδικα
        cdp.evaluate("""(() => {
          const cms = document.querySelectorAll('.CodeMirror');
          cms[0].CodeMirror.setValue('<h1 id="t">Δοκιμή</h1>');
          cms[1].CodeMirror.setValue('h1{color:rgb(1,2,3)}');
          cms[2].CodeMirror.setValue('console.log("Γεια από την κονσόλα!");\\nconsole.warn("προσοχή");');
          return true;
        })()""")
        cdp.evaluate("""[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Εκτέλεση')).click(); true""")
        got = wait_for(cdp, """(() => {
          const box=document.getElementById('console-box');
          return box && box.textContent.includes('Γεια από την κονσόλα!');
        })()""", timeout=20)
        check("console.log εμφανίζεται στην ενσωματωμένη κονσόλα", bool(got))
        got = wait_for(cdp, "document.getElementById('console-box').textContent.includes('προσοχή')", timeout=10)
        check("console.warn εμφανίζεται επίσης", bool(got))
        # Το sandbox (χωρίς allow-same-origin) κάνει το contentDocument opaque →
        # ελέγχουμε ότι το srcdoc περιέχει το HTML & το CSS που γράψαμε.
        frame_txt = wait_for(cdp, """(() => {
          const f=document.getElementById('preview');
          return f && f.srcdoc.includes('Δοκιμή') && f.srcdoc.includes('rgb(1,2,3)');
        })()""", timeout=15)
        check("Το iframe srcdoc περιέχει HTML + CSS", bool(frame_txt))

        print("\n=== 3. Σφάλματα JS στην κονσόλα (χωρίς DevTools) ===")
        cdp.evaluate("""document.querySelectorAll('.CodeMirror')[2].CodeMirror.setValue('denyparxei();'); true""")
        cdp.evaluate("""[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Εκτέλεση')).click(); true""")
        got = wait_for(cdp, """(() => {
          const box=document.getElementById('console-box');
          return box && /ReferenceError|denyparxei/.test(box.textContent);
        })()""", timeout=15)
        check("Σφάλμα ReferenceError πιάνεται από την κονσόλα", bool(got))

        print("\n=== 4. Snippets 1-κλικ & Auto-Run ===")
        # Καθαρισμός του σκόπιμου σφάλματος του βήματος 3 (append-only snippets)
        cdp.evaluate("""document.querySelectorAll('.CodeMirror')[2].CodeMirror.setValue(''); true""")
        time.sleep(1.2)   # αναμονή Auto-Run
        # Άνοιγμα dropdown & κλικ στο «Απλός Μετρητής (Counter)»
        cdp.evaluate("""[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Έτοιμα Snippets')).click(); true""")
        time.sleep(0.5)
        cdp.evaluate("""[...document.querySelectorAll('button')].find(b=>b.textContent.includes('JavaScript Διαδραστικότητα')).click(); true""")
        time.sleep(0.5)
        clicked = cdp.evaluate("""(() => {
          const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Απλός Μετρητής'));
          if(!b) return false; b.click(); return true;
        })()""")
        check("Το snippet «Απλός Μετρητής» βρέθηκε & πατήθηκε", bool(clicked))
        got = wait_for(cdp, "document.querySelectorAll('.CodeMirror')[2].CodeMirror.getValue().includes('metritis')", timeout=10)
        check("Ο κώδικας του μετρητή μπήκε στο πάνελ JS", bool(got))
        # Auto-Run: χωρίς πάτημα Εκτέλεσης, το srcdoc πρέπει να πάρει τον μετρητή
        got = wait_for(cdp, """(() => {
          const f=document.getElementById('preview');
          return f && f.srcdoc.includes('Μετρητής') && f.srcdoc.includes('metritis++');
        })()""", timeout=15)
        check("Auto-Run: η προεπισκόπηση ενημερώθηκε μόνη της", bool(got))
        # Το sandboxed iframe είναι out-of-process (OOPIF) → attach με flatten
        # session και εκτέλεση JS μέσα του (κλικ ➕ → console.log → κονσόλα γονέα).
        # Προσοχή: το srcdoc αλλάζει συνεχώς λόγω Auto-Run — κάνουμε κλικ ΜΟΝΟ
        # αφού το τρέχον έγγραφο του iframe περιέχει πραγματικά το #plus.
        clicked = False
        deadline = time.time() + 25
        while time.time() < deadline and not clicked:
            targets = cdp.send("Target.getTargets").get("targetInfos", [])
            frame_t = next((t for t in targets if t["type"] == "iframe"), None)
            if frame_t:
                sess = None
                try:
                    att = cdp.send("Target.attachToTarget",
                                   {"targetId": frame_t["targetId"], "flatten": True})
                    sess = att["sessionId"]
                    res = cdp.send_session(sess, "Runtime.evaluate", {
                        "expression": """(() => {
                          const b = document.getElementById('plus');
                          if (!b) return 'no-plus';
                          b.click();
                          const t = document.getElementById('timh');
                          return JSON.stringify({timh: t ? t.textContent : null});
                        })()""",
                        "returnByValue": True})
                    val = res.get("result", {}).get("value")
                    try:
                        info = json.loads(val) if isinstance(val, str) and val.startswith("{") else {}
                    except Exception:
                        info = {}
                    clicked = info.get("timh") not in (None, "0")
                except Exception:
                    pass
                finally:
                    if sess:
                        try:
                            cdp.send("Target.detachFromTarget", {"sessionId": sess})
                        except Exception:
                            pass
            if not clicked:
                time.sleep(0.7)
        check("Κλικ στο ➕ μέσα στο iframe (με φορτωμένο listener)", clicked)
        # Το μήνυμα μπορεί να ήρθε ήδη (το send_session καταναλώνει events) —
        # ελέγχουμε πρώτα την τρέχουσα κατάσταση και μετά περιμένουμε.
        got = cdp.evaluate("document.getElementById('console-box').textContent.includes('Νέα τιμή μετρητή:')") \
            or wait_for(cdp, "document.getElementById('console-box').textContent.includes('Νέα τιμή μετρητή:')", timeout=10)
        check("Διαδραστικότητα: +1 → console.log στην κονσόλα", bool(got))

        print("\n=== 5. Θέμα & αποθήκευση ===")
        before = cdp.evaluate("document.body.className")
        cdp.evaluate("""[...document.querySelectorAll('button')].find(b=>['☀️','🌙'].includes(b.textContent.trim())).click(); true""")
        time.sleep(0.5)
        after = cdp.evaluate("document.body.className")
        check("Εναλλαγή σκοτεινού/φωτεινού θέματος", before != after)
        solo = cdp.evaluate("localStorage.getItem('weblab.solo.v1') !== null")
        check("Αυτόματη αποθήκευση Solo στο localStorage", bool(solo))

    finally:
        cdp.close()
        stop_chrome(proc)

    r = results()
    print(f"\n{'✓ Όλοι οι έλεγχοι browser πέρασαν!' if r.failed == 0 else '✗ Αποτυχίες!'} ({r.passed} ✓ / {r.failed} ✗)")
    return r.exit_code()


if __name__ == "__main__":
    sys.exit(main())