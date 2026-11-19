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
import sys

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE, check, launch_chrome, results, stop_chrome, wait_for

PORT = 9333
BASE = "http://127.0.0.1"


def main() -> int:
    try:
        proc, cdp = launch_chrome(PORT, timeout=200)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1

    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")

        # ---------------------------------------------------------------
        print("\n=== 1. Κουμπιά «▶ Εκτέλεση» (Python) ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/_paradeigma/gymnasio-a/python/"})
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
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/_paradeigma/gymnasio-a/pseudoglossa/"})
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
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/_paradeigma/lykeio-a/quiz/"})
        q = wait_for(cdp, "document.querySelectorAll('.quiz-option').length", timeout=40)
        check("Τα κουίζ αποδίδονται", bool(q), f"{q} επιλογές")
        cdp.evaluate("document.querySelectorAll('.quiz-option')[2].click(); true")
        fb = wait_for(cdp, "document.querySelector('.quiz-feedback').textContent.trim()", timeout=20)
        check("Ανατροφοδότηση μετά την απάντηση", bool(fb), repr(str(fb)[:70]))

        # ---------------------------------------------------------------
        print("\n=== 5. Φιλτράρισμα μενού ανά τάξη ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/_paradeigma/gymnasio-b/dyadiko/"})
        sw = wait_for(cdp, "!!document.querySelector('.class-switcher__select')", timeout=40)
        check("Selector εναλλαγής τάξης", bool(sw))
        sel = cdp.evaluate(
            "(()=>{const s=document.querySelector('.class-switcher__select');return s?s.value:null})()")
        check("Επιλεγμένη η σωστή τάξη", bool(sel) and "gymnasio-b" in str(sel), str(sel))

        # ---------------------------------------------------------------
        print("\n=== 6. Παιχνίδι δυαδικού ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/docs/_paradeigma/games/binary-game.html"})
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
        unlocked = cdp.evaluate(f"""(() => {{
            const el=document.querySelector('[x-data]');
            const app=el._x_dataStack ? el._x_dataStack[0] : null;
            if(!app) return 'no-alpine';
            app.password={json.dumps(TEACHER_CODE)}; app.unlock();
            return app.unlocked;
        }})()""")
        check("Ξεκλείδωμα με τον κοινό κωδικό καθηγητή", unlocked is True, str(unlocked))

    except Exception as exc:
        print(f"\n\033[0;31m✗ Σφάλμα ελέγχου: {exc}\033[0m")
        check("Χωρίς απρόσμενο σφάλμα ελέγχου", False, str(exc))
    finally:
        cdp.close()
        stop_chrome(proc)

    r = results()
    total = r.passed + r.failed
    print("\n" + "=" * 58)
    if r.failed == 0:
        print(f"  \033[0;32m✅ ΟΛΟΙ ΟΙ BROWSER ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ ({r.passed}/{total})\033[0m")
    else:
        print(f"  \033[0;31m⚠️  {r.failed} αποτυχίες σε {total} ελέγχους\033[0m")
    print("=" * 58 + "\n")
    return r.exit_code()


if __name__ == "__main__":
    sys.exit(main())