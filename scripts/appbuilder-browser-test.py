#!/opt/school-portal/venv/bin/python
"""
appbuilder-browser-test.py — Έλεγχος του App Builder Wizard UI σε ΠΡΑΓΜΑΤΙΚΟ browser.

Χρησιμοποιεί headless Chromium μέσω CDP (όπως το browser-test.py) και ελέγχει:
  * login gate με κωδικό καθηγητή, ροή βημάτων 1→2→3
  * Quick Paste δημιουργία εφαρμογής μέσα από τη φόρμα
  * εμφάνιση embed snippet & κουμπί αντιγραφής, dropdown μαθημάτων
  * λίστα εφαρμογών με Προεπισκόπηση / Ενσωμάτωση / Διαγραφή (με confirm)
  * κάρτα «Δημιουργός Εφαρμογών» στη Ζώνη Καθηγητών του Dashboard

Χρήση: /opt/school-portal/venv/bin/python scripts/appbuilder-browser-test.py
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
PORT = 9347
BASE = "http://127.0.0.1"


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60)
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
        res = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("text", "JS exception"))
        return res.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for(cdp: CDP, expr: str, timeout: float = 30, interval: float = 0.4):
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
         "--window-size=1400,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    passed = failed = 0

    def check(label, ok, detail=""):
        nonlocal passed, failed
        mark = "\033[0;32m✓\033[0m" if ok else "\033[0;31m✗\033[0m"
        print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
        passed += ok
        failed += (not ok)

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
        page = next((t for t in targets if t["type"] == "page"), targets[0])
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        print("\n=== 1. Dashboard — κάρτα στη Ζώνη Καθηγητών ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/"})
        wait_for(cdp, "typeof Alpine !== 'undefined' && document.querySelector('[x-data]')")
        cdp.evaluate("(()=>{const st=Alpine.$data(document.querySelector('[x-data]'));st.password='teacher2026';st.unlock();})()")
        time.sleep(0.6)
        card = cdp.evaluate("""(()=>{
            const a=document.querySelector('#kathigites a[href="/app-builder/"]');
            if(!a) return null;
            const r=a.getBoundingClientRect();
            return {visible:r.width>0&&r.height>0, text:a.textContent};
        })()""")
        check("Κάρτα App Wizard ορατή μετά το ξεκλείδωμα", bool(card and card["visible"]))
        check("Σωστός τίτλος κάρτας", bool(card and "Δημιουργός Εφαρμογών" in card["text"]))

        print("\n=== 2. Wizard — login & βήματα ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/app-builder/"})
        wait_for(cdp, "typeof Alpine !== 'undefined' && !!document.querySelector('[x-data]')")
        gate = cdp.evaluate("!!document.querySelector('input[type=password]')")
        check("Πύλη κωδικού εμφανίζεται", bool(gate))
        cdp.evaluate("""(()=>{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.password='teacher2026'; st.login();
        })()""")
        got = wait_for(cdp, "Alpine.$data(document.querySelector('[x-data]')).loggedIn === true")
        check("Login επιτυχής", bool(got))
        got = wait_for(cdp, "Alpine.$data(document.querySelector('[x-data]')).apps.length >= 1")
        check("Η λίστα εφαρμογών φορτώνει", bool(got))
        has_bc = cdp.evaluate("Alpine.$data(document.querySelector('[x-data]')).apps.some(a=>a.id==='binary-converter')")
        check("Το binary-converter φαίνεται στη λίστα", bool(has_bc))
        got = wait_for(cdp, "Alpine.$data(document.querySelector('[x-data]')).lessons.length > 10")
        check("Το dropdown μαθημάτων γεμίζει", bool(got))

        # Step 1 → συμπλήρωση φόρμας μέσω Alpine state (ισοδύναμο με typing)
        cdp.evaluate("""(()=>{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.form.id='ui-e2e-app'; st.form.title='UI E2E Δοκιμή';
            st.form.description='από browser test'; st.form.icon='🧪';
            st.gotoStep2();
        })()""")
        time.sleep(0.4)
        check("Μετάβαση στο Βήμα 2", cdp.evaluate("Alpine.$data(document.querySelector('[x-data]')).step") == 2)
        step2_visible = cdp.evaluate("""(()=>{
            const secs=[...document.querySelectorAll('section')];
            const s=secs.find(x=>x.textContent.includes('Βήμα 2'));
            return s && getComputedStyle(s).display!=='none';
        })()""")
        check("Το Βήμα 2 είναι ορατό", bool(step2_visible))

        print("\n=== 3. Quick Paste δημοσίευση μέσω UI ===")
        cdp.evaluate("""(()=>{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.mode='paste';
            st.paste.html='<h2 id="ui-hello">UI γεια</h2>';
            st.paste.js="document.getElementById('ui-hello').style.color='purple';";
            st.publish();
        })()""")
        got = wait_for(cdp, "Alpine.$data(document.querySelector('[x-data]')).step === 3", timeout=40)
        check("Φτάνει στο Βήμα 3 (επιτυχία)", bool(got),
              str(cdp.evaluate("Alpine.$data(document.querySelector('[x-data]')).error")))
        embed_ok = cdp.evaluate("""(()=>{
            const pre=[...document.querySelectorAll('pre')].find(p=>p.textContent.includes('custom-app-embed'));
            return pre && pre.textContent.includes('/apps/ui-e2e-app/');
        })()""")
        check("Το embed snippet εμφανίζεται", bool(embed_ok))
        copy_btn = cdp.evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent.includes('Αντιγραφή Κώδικα'))")
        check("Κουμπί «Αντιγραφή Κώδικα» υπάρχει", bool(copy_btn))
        preview = cdp.evaluate("!!document.querySelector('a[href=\"/apps/ui-e2e-app/\"]')")
        check("Σύνδεσμος προεπισκόπησης υπάρχει", bool(preview))

        print("\n=== 4. Διαγραφή μέσω UI (με confirm) ===")
        # Ο headless CDP αποδέχεται αυτόματα τα dialogs αν δεν υπάρχει handler·
        # για σιγουριά παρακάμπτουμε το confirm και καλούμε απευθείας τη ροή.
        cdp.evaluate("window.confirm = () => true; true")
        cdp.evaluate("""(()=>{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            const a=st.apps.find(x=>x.id==='ui-e2e-app');
            st.deleteApp(a);
        })()""")
        gone = wait_for(cdp, "!Alpine.$data(document.querySelector('[x-data]')).apps.some(a=>a.id==='ui-e2e-app')")
        check("Η εφαρμογή διαγράφεται από τη λίστα", bool(gone))
        with urllib.request.urlopen(f"{BASE}/apps/apps-manifest.json", timeout=15) as r:
            manifest = r.read().decode()
        check("Το manifest ενημερώθηκε (χωρίς ui-e2e-app)", "ui-e2e-app" not in manifest)

        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: {passed} OK, {failed} FAIL")
        return 0 if failed == 0 else 1
    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())