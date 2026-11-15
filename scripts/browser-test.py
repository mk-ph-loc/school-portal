#!/opt/school-portal/venv/bin/python
"""
browser-test.py — Έλεγχος των διαδραστικών στοιχείων σε ΠΡΑΓΜΑΤΙΚΟ browser.

Χρησιμοποιεί headless Chromium μέσω DevTools Protocol (CDP) για να ελέγξει:
  * ότι τα κουμπιά «▶ Εκτέλεση» εμφανίζονται και είναι ορατά
  * ότι το Pyodide φορτώνεται και εκτελεί Python
  * ότι ο χρωματισμός ψευδογλώσσας εφαρμόζεται
  * ότι τα κουίζ, το φίλτρο τάξης και το παιχνίδι δυαδικού λειτουργούν

Χρήση: /opt/school-portal/venv/bin/python scripts/browser-test.py
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
PORT = 9333
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
        print("\n=== 1. Κουμπιά «▶ Εκτέλεση» (Python) ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/gymnasio-a/python/"})
        got = wait_for(cdp, "document.querySelectorAll('.py-run-btn').length", timeout=40)
        check("Τα κουμπιά δημιουργούνται", bool(got), f"{got} κουμπιά")

        info = cdp.evaluate("""(() => {
            const b=[...document.querySelectorAll('.py-run-btn')];
            let vis=0;
            b.forEach(x=>{const s=getComputedStyle(x),r=x.getBoundingClientRect();
              if(s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0)vis++;});
            return {total:b.length, visible:vis, label:b[0]?b[0].textContent.trim():null};
        })()""")
        check("Είναι ΟΡΑΤΑ στον browser",
              info["visible"] == info["total"] and info["total"] > 0,
              f"{info['visible']}/{info['total']} ορατά")
        check('Σωστή ετικέτα «▶ Εκτέλεση»', info["label"] == "▶ Εκτέλεση", str(info["label"]))

        # ---------------------------------------------------------------
        print("\n=== 2. Πραγματική εκτέλεση Python (Pyodide) ===")
        cdp.evaluate("document.querySelectorAll('.py-run-btn')[0].click(); true")
        out = wait_for(cdp, """(() => {
            const o=document.querySelector('.py-output');
            if(!o||!o.classList.contains('is-visible'))return null;
            const t=o.textContent.trim();
            return (t&&!t.includes('⏳'))?t:null;
        })()""", timeout=170, interval=1.0)
        check("Ο κώδικας εκτελέστηκε & εμφάνισε έξοδο",
              bool(out) and "Γεια σου κόσμε" in str(out), repr(str(out)[:90]))
        err_out = cdp.evaluate(
            "document.querySelector('.py-output').classList.contains('py-output--err')")
        check("Χωρίς σφάλμα εκτέλεσης", not err_out)

        cdp.evaluate("document.querySelectorAll('.py-run-btn')[1].click(); true")
        out2 = wait_for(cdp, """(() => {
            const o=document.querySelectorAll('.py-output')[1];
            if(!o||!o.classList.contains('is-visible'))return null;
            const t=o.textContent.trim();
            return (t&&!t.includes('⏳'))?t:null;
        })()""", timeout=90, interval=1.0)
        check("2ο μπλοκ: μεταβλητές & τύποι",
              bool(out2) and "Μαρία" in str(out2), repr(str(out2)[:70]))
        # ---------------------------------------------------------------
        print("\n=== 3. Χρωματισμός ελληνικής ψευδογλώσσας ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/gymnasio-a/pseudoglossa/"})
        g = wait_for(cdp, "document.querySelectorAll('.gl-k').length", timeout=40)
        check("Keywords χρωματίζονται (.gl-k)", bool(g), f"{g} spans")
        gd = cdp.evaluate("""(() => ({
            highlighted: document.querySelectorAll('.glossa-highlighted').length,
            strings: document.querySelectorAll('.gl-s').length,
            comments: document.querySelectorAll('.gl-c').length,
            operators: document.querySelectorAll('.gl-o').length
        }))()""")
        check("Strings / σχόλια / τελεστές",
              all(gd[k] > 0 for k in ("strings", "comments", "operators")), json.dumps(gd))

        # ---------------------------------------------------------------
        print("\n=== 4. Διαδραστικό κουίζ ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/lykeio-a/quiz/"})
        q = wait_for(cdp, "document.querySelectorAll('.quiz-option').length", timeout=40)
        check("Τα κουίζ αποδίδονται", bool(q), f"{q} επιλογές")
        cdp.evaluate("document.querySelectorAll('.quiz-option')[2].click(); true")
        fb = wait_for(cdp, "document.querySelector('.quiz-feedback').textContent.trim()", timeout=20)
        check("Ανατροφοδότηση μετά την απάντηση", bool(fb), repr(str(fb)[:70]))

        # ---------------------------------------------------------------
        print("\n=== 5. Φιλτράρισμα μενού ανά τάξη ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/gymnasio-b/dyadiko/"})
        sw = wait_for(cdp, "!!document.querySelector('.class-switcher__select')", timeout=40)
        check("Selector εναλλαγής τάξης", bool(sw))
        sel = cdp.evaluate(
            "(()=>{const s=document.querySelector('.class-switcher__select');return s?s.value:null})()")
        check("Επιλεγμένη η σωστή τάξη", bool(sel) and "gymnasio-b" in str(sel), str(sel))

        # ---------------------------------------------------------------
        print("\n=== 6. Παιχνίδι δυαδικού ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/games/binary-game.html"})
        bg = wait_for(cdp,
                      "!!document.getElementById('target') && document.getElementById('target').textContent.length>0",
                      timeout=40)
        check("Το παιχνίδι ξεκινά (στόχος εμφανίζεται)", bool(bg))
        st = cdp.evaluate("""(() => {
            document.querySelector('[data-mode="bits"]').click();
            return {bits: document.querySelectorAll('.bit').length,
                    btn: !!document.getElementById('bitsCheckBtn')};
        })()""")
        check("Λειτουργία «Άναψε τα Bits»", st["bits"] > 0 and st["btn"], json.dumps(st))

        # ---------------------------------------------------------------
        print("\n=== 7. Dashboard (Ζώνη Καθηγητών) ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/"})
        cards = wait_for(cdp, "document.querySelectorAll('#mathites a[href^=\"/docs/\"]').length", timeout=40)
        check("6 κάρτες τάξεων", cards == 6, f"{cards} κάρτες")
        unlocked = cdp.evaluate("""(() => {
            const el=document.querySelector('[x-data]');
            const app=el._x_dataStack ? el._x_dataStack[0] : null;
            if(!app) return 'no-alpine';
            app.password='teacher2026'; app.unlock();
            return app.unlocked;
        })()""")
        check("Ξεκλείδωμα με teacher2026", unlocked is True, str(unlocked))

    except Exception as exc:
        print(f"\n\033[0;31m✗ Σφάλμα ελέγχου: {exc}\033[0m")
        failed += 1
    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    total = passed + failed
    print("\n" + "=" * 58)
    if failed == 0:
        print(f"  \033[0;32m✅ ΟΛΟΙ ΟΙ BROWSER ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ ({passed}/{total})\033[0m")
    else:
        print(f"  \033[0;31m⚠️  {failed} αποτυχίες σε {total} ελέγχους\033[0m")
    print("=" * 58 + "\n")
    return failed


if __name__ == "__main__":
    sys.exit(main())