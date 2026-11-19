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
import sys
import time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE, check, launch_chrome, results, stop_chrome, wait_for

PORT = 9345
BASE = "http://127.0.0.1"


def main() -> int:
    try:
        proc, cdp = launch_chrome(PORT, timeout=60)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1

    try:
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

        cdp.evaluate(f"""(() => {{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.password={json.dumps(TEACHER_CODE)}; st.unlock(); return true;
        }})()""")
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
        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: {r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())