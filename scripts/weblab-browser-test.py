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
import shutil
import subprocess
import sys
import time
import urllib.request

import websocket

CHROME = shutil.which("chromium") or shutil.which("chromium-browser")
PORT = 9337
BASE = "http://127.0.0.1"


class CDP:
    """Ελάχιστο CDP client πάνω από WebSocket."""

    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=200)
        self._id = 0

    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def evaluate(self, expression: str):
        res = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("text", "JS exception"))
        return res.get("result", {}).get("value")

    def send_session(self, session_id: str, method: str, params: dict | None = None) -> dict:
        """Εντολή σε attached target (π.χ. out-of-process iframe)."""
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method,
                                 "params": params or {}, "sessionId": session_id}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for(cdp: CDP, expr: str, timeout: float = 60, interval: float = 0.5):
    """Περιμένει μέχρι η JS έκφραση να γίνει truthy."""
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


def main() -> int:
    if not CHROME:
        print("✗ Δεν βρέθηκε chromium")
        return 1

    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", f"--remote-debugging-port={PORT}",
         "--window-size=1500,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    passed = failed = 0

    def check(label: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        mark = "\033[0;32m✓\033[0m" if ok else "\033[0;31m✗\033[0m"
        print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
        if ok:
            passed += 1
        else:
            failed += 1

    cdp = None
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
        if not targets:
            print("✗ Το Chromium δεν ξεκίνησε")
            return 1

        page = next((t for t in targets if t["type"] == "page"), targets[0])
        cdp = CDP(page["webSocketDebuggerUrl"])
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
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print(f"\n{'✓ Όλοι οι έλεγχοι browser πέρασαν!' if failed == 0 else '✗ Αποτυχίες!'} ({passed} ✓ / {failed} ✗)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())