#!/opt/school-portal/venv/bin/python
"""
custom-apps-test.py — Έλεγχος του μηχανισμού custom-apps σε ΠΡΑΓΜΑΤΙΚΟ browser.

Χρησιμοποιεί headless Chromium μέσω DevTools Protocol (CDP) για να ελέγξει:
  * ότι το Dashboard φορτώνει το apps-manifest.json και εμφανίζει δυναμικά
    τις κάρτες στην ενότητα «Δικές μου Εφαρμογές & Προσομοιώσεις»
  * ότι το access:"teachers" κρύβεται από μαθητές & εμφανίζεται μετά το ξεκλείδωμα
  * ότι η εφαρμογή /apps/binary-converter/ ανοίγει, τα 8 διακοπτάκια bits
    λειτουργούν και οι μετατροπές δεκαδικού/δυαδικού/δεκαεξαδικού είναι σωστές

Χρήση: /opt/school-portal/venv/bin/python scripts/custom-apps-test.py
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
PORT = 9345
BASE = "http://127.0.0.1"


class CDP:
    """Ελάχιστο CDP client πάνω από WebSocket."""

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
        res = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("text", "JS exception"))
        return res.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for(cdp: CDP, expr: str, timeout: float = 30, interval: float = 0.4):
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
         "--window-size=1400,1000", "about:blank"],
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

        # ---------------------------------------------------------------
        print("\n=== 1. Dashboard — δυναμικές κάρτες custom apps ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/"})
        got = wait_for(cdp, "document.querySelectorAll('#custom-apps a[href^=\"/apps/\"]').length")
        check("Η ενότητα εμφανίζει κάρτες από το manifest", bool(got), f"{got} κάρτες")

        card = cdp.evaluate("""(() => {
            const a=document.querySelector('#custom-apps a[href="/apps/binary-converter/"]');
            if(!a) return null;
            const s=getComputedStyle(a), r=a.getBoundingClientRect();
            return {visible:s.display!=='none'&&r.width>0&&r.height>0, text:a.textContent};
        })()""")
        check("Κάρτα binary-converter ορατή", bool(card and card["visible"]))
        check("Σωστός τίτλος κάρτας", bool(card and "Μετατροπέας Δυαδικού" in card["text"]))
        check("Badge κατηγορίας", bool(card and "Γυμνασίου" in card["text"]))

        # access:"teachers" — προσωρινή δοκιμαστική εγγραφή στο Alpine state
        hidden = cdp.evaluate("""(() => {
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.customApps.push({id:'t',title:'TEACHERS-ONLY',description:'',category:'',icon:'🔐',access:'teachers',url:'/apps/t/'});
            return true;
        })()""")
        time.sleep(0.5)
        n = cdp.evaluate("document.querySelectorAll('#custom-apps a[href=\"/apps/t/\"]').length")
        check("Κάρτα teachers ΚΡΥΒΕΤΑΙ από μαθητές", bool(hidden) and n == 0, f"{n} ορατές")

        cdp.evaluate("""(() => {
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.password='teacher2026'; st.unlock(); return true;
        })()""")
        time.sleep(0.5)
        n = cdp.evaluate("document.querySelectorAll('#custom-apps a[href=\"/apps/t/\"]').length")
        check("Κάρτα teachers ΕΜΦΑΝΙΖΕΤΑΙ μετά το ξεκλείδωμα", n == 1, f"{n} ορατές")
        cdp.evaluate("Alpine.$data(document.querySelector('[x-data]')).lock(); true")

        # ---------------------------------------------------------------
        print("\n=== 2. Εφαρμογή /apps/binary-converter/ ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/binary-converter/"})
        got = wait_for(cdp, "document.querySelectorAll('#bits-row button').length === 8")
        check("8 διακοπτάκια bits δημιουργούνται", bool(got))
        check("Μπάρα «← Επιστροφή στο Portal»",
              cdp.evaluate("!!document.querySelector('nav a[href=\"/\"]')"))
        check("Αρχική τιμή 0", cdp.evaluate("document.getElementById('out-dec').textContent") == "0")

        # Πάτημα bit θέσης 5 (βάρος 32) και θέσης 1 (βάρος 2) → 34
        cdp.evaluate("document.getElementById('bit-5').click(); document.getElementById('bit-1').click(); true")
        dec = cdp.evaluate("document.getElementById('out-dec').textContent")
        bin_ = cdp.evaluate("document.getElementById('out-bin').textContent")
        hex_ = cdp.evaluate("document.getElementById('out-hex').textContent")
        summ = cdp.evaluate("document.getElementById('sum-expression').textContent")
        check("Κλικ στα bits → δεκαδικό 34", dec == "34", dec)
        check("Δυαδικό 0010 0010", bin_ == "0010 0010", bin_)
        check("Δεκαεξαδικό 0x22", hex_ == "0x22", hex_)
        check("Άθροισμα βαρών 32 + 2 = 34", summ == "32 + 2 = 34", summ)

        # Αντίστροφη πορεία: δεκαδική εισαγωγή 200 → bits & hex
        cdp.evaluate("""(() => {
            const el=document.getElementById('in-dec');
            el.value='200'; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        check("Εισαγωγή 200 → δυαδικό 1100 1000",
              cdp.evaluate("document.getElementById('out-bin').textContent") == "1100 1000")
        check("Εισαγωγή 200 → 0xC8",
              cdp.evaluate("document.getElementById('out-hex').textContent") == "0xC8")
        check("Το bit-7 άναψε αυτόματα",
              cdp.evaluate("document.getElementById('bit-7').getAttribute('aria-pressed')") == "true")

        # Δυαδική εισαγωγή 10101010 → 170 / 0xAA
        cdp.evaluate("""(() => {
            const el=document.getElementById('in-bin');
            el.value='10101010'; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        check("Δυαδικό 10101010 → 170",
              cdp.evaluate("document.getElementById('out-dec').textContent") == "170")
        check("Δυαδικό 10101010 → 0xAA",
              cdp.evaluate("document.getElementById('out-hex').textContent") == "0xAA")

        # Δεκαεξαδική εισαγωγή 0xFF → 255, όλα τα bits ON
        cdp.evaluate("""(() => {
            const el=document.getElementById('in-hex');
            el.value='0xFF'; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        check("Hex 0xFF → 255", cdp.evaluate("document.getElementById('out-dec').textContent") == "255")
        check("Όλα τα bits ON",
              cdp.evaluate("[...document.querySelectorAll('#bits-row button')].every(b=>b.getAttribute('aria-pressed')==='true')"))

        # Μη έγκυρη εισαγωγή → ελληνικό μήνυμα σφάλματος, κατάσταση αμετάβλητη
        cdp.evaluate("""(() => {
            const el=document.getElementById('in-dec');
            el.value='999'; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        err = cdp.evaluate("!document.getElementById('input-error').classList.contains('hidden')")
        check("Μη έγκυρο 999 → μήνυμα σφάλματος", bool(err))
        check("Η τιμή παρέμεινε 255", cdp.evaluate("document.getElementById('out-dec').textContent") == "255")

        # Κουμπιά ενεργειών
        cdp.evaluate("document.getElementById('btn-invert').click(); true")
        check("Αντιστροφή του 255 → 0", cdp.evaluate("document.getElementById('out-dec').textContent") == "0")
        cdp.evaluate("document.getElementById('btn-all-on').click(); true")
        check("Όλα ON → 255", cdp.evaluate("document.getElementById('out-dec').textContent") == "255")
        cdp.evaluate("document.getElementById('btn-all-off').click(); true")
        check("Όλα OFF → 0", cdp.evaluate("document.getElementById('out-dec').textContent") == "0")

        # ---------------------------------------------------------------
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