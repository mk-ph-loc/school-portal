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
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE, check, launch_chrome, results, stop_chrome, wait_for

PORT = 9347
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
        print("\n=== 1. Dashboard — κάρτα στη Ζώνη Καθηγητών ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/"})
        wait_for(cdp, "typeof Alpine !== 'undefined' && document.querySelector('[x-data]')")
        cdp.evaluate(f"(()=>{{const st=Alpine.$data(document.querySelector('[x-data]'));st.password={json.dumps(TEACHER_CODE)};st.unlock();}})()")
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
        cdp.evaluate(f"""(()=>{{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.password={json.dumps(TEACHER_CODE)}; st.login();
        }})()""")
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

        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: {r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())