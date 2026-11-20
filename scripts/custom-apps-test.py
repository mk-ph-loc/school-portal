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
        check("Badge κατηγορίας", bool(card and "Υλικό & Δεδομένα" in card["text"]))

        # ---------------------------------------------------------------
        print("\n=== 1β. Tabs κατηγοριών, αναζήτηση & pinned ===")
        tabs = wait_for(cdp, """(() => {
            const btns=[...document.querySelectorAll('#custom-apps-tabs button')];
            if(!btns.length) return null;
            return btns.map(b=>({cat:b.dataset.category, text:b.textContent.replace(/\\s+/g,' ').trim()}));
        })()""")
        check("Μπάρα tabs ορατή", bool(tabs), f"{len(tabs or [])} tabs")
        tab_ids = [t["cat"] for t in (tabs or [])]
        check("Tabs: Όλες + οι 4 τυποποιημένες κατηγορίες",
              all(c in tab_ids for c in ("all", "Προγραμματισμός", "Γραφικά & Πολυμέσα",
                                         "Τεχνολογία & ΤΝ", "Υλικό & Δεδομένα")), str(tab_ids))
        counts = cdp.evaluate("Alpine.$data(document.querySelector('[x-data]')).categoryCounts()")
        n_all = cdp.evaluate("document.querySelectorAll('#custom-apps a[href^=\"/apps/\"]').length")
        check("Μετρητής «Όλες» = πλήθος ορατών καρτών", bool(counts) and counts.get("all") == n_all,
              f"all={counts.get('all') if counts else None}, κάρτες={n_all}")
        tab_count = cdp.evaluate("""(() => {
            const b=document.querySelector('#custom-apps-tabs button[data-category="Υλικό & Δεδομένα"]');
            return b ? parseInt(b.querySelector('span:last-child').textContent, 10) : -1;
        })()""")
        check("Μετρητής tab «Υλικό & Δεδομένα» σωστός",
              bool(counts) and tab_count == counts.get("Υλικό & Δεδομένα"), str(tab_count))

        # Πραγματικό κλικ σε tab → φιλτράρει τις κάρτες (instant scroll ώστε οι
        # συντεταγμένες του CDP mouse event να είναι έγκυρες αμέσως)
        rect = cdp.evaluate("""(() => {
            const b=document.querySelector('#custom-apps-tabs button[data-category="Γραφικά & Πολυμέσα"]');
            if(!b) return null;
            b.scrollIntoView({block:'center', behavior:'instant'});
            const r=b.getBoundingClientRect();
            return {x:r.x+r.width/2, y:r.y+r.height/2};
        })()""")
        check("Tab «Γραφικά & Πολυμέσα» υπάρχει για κλικ", bool(rect))
        time.sleep(0.3)
        if rect:
            cdp.click(rect["x"], rect["y"])
        # Οι κάρτες της κατηγορίας προκύπτουν ΔΥΝΑΜΙΚΑ από το manifest (όσες
        # εφαρμογές υπάρχουν) — όχι hard-coded λίστα.
        got = wait_for(cdp, """(() => {
            const st=Alpine.$data(document.querySelector('[x-data]'));
            if(st.categoryFilter!=='Γραφικά & Πολυμέσα') return false;
            const expected=st.customApps.filter(a=>a.category==='Γραφικά & Πολυμέσα' && a.access!=='teachers').map(a=>a.url).sort();
            const shown=[...document.querySelectorAll('#custom-apps a[href^="/apps/"]')].map(a=>a.getAttribute('href')).sort();
            return expected.length>0 && JSON.stringify(expected)===JSON.stringify(shown);
        })()""")
        n_filtered = cdp.evaluate("document.querySelectorAll('#custom-apps a[href^=\"/apps/\"]').length")
        check("Κλικ σε tab φιλτράρει τις κάρτες", bool(got) and n_filtered >= 1, f"{n_filtered} κάρτες")
        active = cdp.evaluate("""(() => {
            const b=document.querySelector('#custom-apps-tabs button[data-category="Γραφικά & Πολυμέσα"]');
            return b && b.className.includes('bg-blue-700');
        })()""")
        check("Active state στο επιλεγμένο tab", bool(active))
        cdp.evaluate("""(() => {
            const b=document.querySelector('#custom-apps-tabs button[data-category="all"]');
            if(b) b.click(); return true;
        })()""")
        time.sleep(0.4)

        # Αναζήτηση «δυαδικ» (χωρίς τόνους) → μόνο binary-converter
        cdp.evaluate("""(() => {
            const el=document.getElementById('custom-apps-search');
            el.value='δυαδικ'; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        got = wait_for(cdp, """(() => {
            const st=Alpine.$data(document.querySelector('[x-data]'));
            const links=[...document.querySelectorAll('#custom-apps a[href^="/apps/"]')];
            return st.searchQuery==='δυαδικ' && links.length===1 &&
                   links[0].getAttribute('href')==='/apps/binary-converter/';
        })()""")
        check("Αναζήτηση «δυαδικ» βρίσκει μόνο το binary-converter", bool(got))

        # Αναζήτηση χωρίς αποτέλεσμα → ξεχωριστό μήνυμα «Δεν βρέθηκε εφαρμογή…»
        cdp.evaluate("""(() => {
            const el=document.getElementById('custom-apps-search');
            el.value='zzz-ανυπαρκτο'; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        got = wait_for(cdp, """(() => {
            const sec=document.getElementById('custom-apps');
            const empty=[...sec.querySelectorAll('div')].find(d=>d.textContent.includes('Δεν βρέθηκε εφαρμογή'));
            return empty && getComputedStyle(empty).display!=='none' &&
                   document.querySelectorAll('#custom-apps a[href^="/apps/"]').length===0;
        })()""")
        check("Κενή αναζήτηση → μήνυμα «Δεν βρέθηκε εφαρμογή…»", bool(got))
        cdp.evaluate("""(() => {
            const el=document.getElementById('custom-apps-search');
            el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); return true;
        })()""")
        time.sleep(0.4)

        # Pinned: badge 📌, ring και σειρά (pinned πρώτες, μετά αλφαβητικά κατά
        # τίτλο — η σειρά του manifest ΔΙΑΤΗΡΕΙΤΑΙ, όσες pinned εφαρμογές κι αν υπάρχουν)
        pin = cdp.evaluate("""(() => {
            const a=document.querySelector('#custom-apps a[href="/apps/binary-converter/"]');
            if(!a) return null;
            const st=Alpine.$data(document.querySelector('[x-data]'));
            const visible=st.customApps.filter(x=>x.access!=='teachers');
            const nPinned=visible.filter(x=>x.pinned).length;
            const hrefs=[...document.querySelectorAll('#custom-apps a[href^="/apps/"]')].map(x=>x.getAttribute('href'));
            const pinnedHrefs=new Set(visible.filter(x=>x.pinned).map(x=>x.url));
            const orderOk=hrefs.slice(0,nPinned).every(h=>pinnedHrefs.has(h)) &&
                          hrefs.slice(nPinned).every(h=>!pinnedHrefs.has(h));
            return {badge:a.textContent.includes('📌 Επιλεγμένο'),
                    ring:a.className.includes('ring-amber-300'),
                    first:orderOk, nPinned:nPinned};
        })()""")
        check("Pinned badge «📌 Επιλεγμένο» ορατό", bool(pin and pin["badge"]))
        check("Pinned κάρτα με ring-amber-300", bool(pin and pin["ring"]))
        check("Pinned-first σειρά manifest διατηρείται", bool(pin and pin["first"]),
              f"{pin['nPinned']} pinned πρώτες" if pin else "")

        # access:"teachers" — προσωρινή δοκιμαστική εγγραφή στο Alpine state
        hidden = cdp.evaluate("""(() => {
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.customApps.push({id:'t',title:'TEACHERS-ONLY',description:'',category:'Προγραμματισμός',icon:'🔐',access:'teachers',pinned:false,url:'/apps/t/'});
            return true;
        })()""")
        time.sleep(0.5)
        n = cdp.evaluate("document.querySelectorAll('#custom-apps a[href=\"/apps/t/\"]').length")
        check("Κάρτα teachers ΚΡΥΒΕΤΑΙ από μαθητές", bool(hidden) and n == 0, f"{n} ορατές")
        # Οι πραγματικές κάρτες «Προγραμματισμός» προκύπτουν δυναμικά από το
        # manifest (π.χ. basthon) — η δοκιμαστική teachers κάρτα δεν πρέπει να
        # αλλάξει τους μετρητές όσο είναι κρυμμένη.
        n_prog = cdp.evaluate("""(() => {
            const st=Alpine.$data(document.querySelector('[x-data]'));
            return st.customApps.filter(a=>a.category==='Προγραμματισμός' && a.access!=='teachers').length;
        })()""")
        cnt = cdp.evaluate("""(() => {
            const c=Alpine.$data(document.querySelector('[x-data]')).categoryCounts();
            return {all:c.all, prog:c['Προγραμματισμός']||0};
        })()""")
        check("Teachers-only κάρτα ΔΕΝ μετράει στους μετρητές μαθητή",
              bool(cnt) and cnt["all"] == n_all and cnt["prog"] == n_prog, str(cnt))

        cdp.evaluate(f"""(() => {{
            const st=Alpine.$data(document.querySelector('[x-data]'));
            st.password={json.dumps(TEACHER_CODE)}; st.unlock(); return true;
        }})()""")
        time.sleep(0.5)
        n = cdp.evaluate("document.querySelectorAll('#custom-apps a[href=\"/apps/t/\"]').length")
        check("Κάρτα teachers ΕΜΦΑΝΙΖΕΤΑΙ μετά το ξεκλείδωμα", n == 1, f"{n} ορατές")
        cnt = cdp.evaluate("""(() => {
            const c=Alpine.$data(document.querySelector('[x-data]')).categoryCounts();
            return {all:c.all, prog:c['Προγραμματισμός']||0};
        })()""")
        check("Μετά το ξεκλείδωμα η teachers κάρτα μετράει κανονικά",
              bool(cnt) and cnt["all"] == n_all + 1 and cnt["prog"] == n_prog + 1, str(cnt))
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