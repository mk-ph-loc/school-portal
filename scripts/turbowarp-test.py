#!/opt/school-portal/venv/bin/python
"""
turbowarp-test.py — Έλεγχος του offline Scratch editor TurboWarp (/apps/turbowarp/).

Σε headless Chromium (CDP) ελέγχει:
  * το wrapper /apps/turbowarp/ σπέρνει τα Ελληνικά (tw:language=el) και
    ανακατευθύνει στο ./editor.html — ο editor φορτώνει (blocks workspace,
    timeout 90s λόγω μεγάλου bundle)
  * Ελληνικό UI («Κινήσεις»/«Εμφάνιση» στις κατηγορίες μπλοκ)
  * άνοιγμα βιβλιοθήκης sprites → τα thumbnails φορτώνουν ΑΠΟ ΤΟΠΙΚΑ
    (./scratch-assets/) & ΟΛΑ τα network requests ΜΟΝΟ στο 127.0.0.1
    (κανένα scratch.mit.edu / trampoline / clouddata.turbowarp.org)
  * προσθήκη sprite από τη βιβλιοθήκη → εμφανίζεται στη λίστα & στο stage
  * το pill «← Portal» είναι ορατό (fixed top-left δίπλα στο logo) και
    ΔΕΝ καλύπτει το menu bar ή τα stage controls

Χρήση: /opt/school-portal/venv/bin/python scripts/turbowarp-test.py
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import check, launch_chrome, results, stop_chrome, wait_for

PORT = 9353  # διαφορετική θύρα από τα υπόλοιπα browser tests
BASE = "http://127.0.0.1"

LOCAL_SCHEMES = ("data:", "blob:", "about:", "chrome:", "devtools:")


class NetLog:
    """Συλλογή ΟΛΩΝ των network requests μέσω CDP Network.enable + on_event."""

    def __init__(self):
        self.urls: list[str] = []

    def on_event(self, msg):
        if msg.get("method") == "Network.requestWillBeSent":
            url = msg.get("params", {}).get("request", {}).get("url", "")
            if url:
                self.urls.append(url)

    def external(self):
        return [u for u in self.urls
                if not u.startswith(LOCAL_SCHEMES) and "127.0.0.1" not in u]
def main() -> int:
    net = NetLog()
    try:
        proc, cdp = launch_chrome(PORT, window="1400,1000", timeout=90, on_event=net.on_event)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1

    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")

        # ---------------------------------------------------------------
        print("\n=== 1. Wrapper → editor.html & φόρτωση GUI ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/turbowarp/"})
        got = wait_for(cdp, "location.pathname.endsWith('/editor.html')", timeout=30)
        check("Το wrapper ανακατεύθυνε στο ./editor.html", bool(got),
              cdp.evaluate("location.pathname"))
        lang = cdp.evaluate("localStorage.getItem('tw:language')")
        check("Default γλώσσα el (tw:language στο localStorage)", lang == "el", str(lang))

        # Ο editor είναι βαρύς (~10 MB JS) — περιμένουμε το blocks workspace.
        ready = wait_for(cdp, """(() => {
            const g = document.querySelector('[class*="gui_editor-wrapper"], [class*="gui_editor"]');
            const blocks = document.querySelector('.blocklySvg, [class*="blocks_blocks"]');
            return !!(g && blocks);
        })()""", timeout=90)
        check("Ο editor φόρτωσε (GUI + blocks workspace)", bool(ready))
        # Περιμένουμε να φύγει το loading overlay & να ζωγραφιστεί η γάτα (default project)
        wait_for(cdp, "!document.querySelector('[class*=\"loader_background\"]')", timeout=60)
        time.sleep(3)

        # ---------------------------------------------------------------
        print("\n=== 2. Ελληνικό UI ===")
        # Οι κατηγορίες μπλοκ είναι SVG <text> (όχι innerText) — τα πραγματικά
        # ελληνικά labels του scratch-blocks el locale: «Κίνηση», «Όψεις».
        cats = wait_for(cdp, """(() => {
            const t = document.body.innerText;
            return (t.includes('Κίνηση') && t.includes('Όψεις') && t.includes('Ενδυμασίες')) ? true : null;
        })()""", timeout=30)
        check("Κατηγορίες μπλοκ στα Ελληνικά («Κίνηση», «Όψεις»)", bool(cats))

        # ---------------------------------------------------------------
        print("\n=== 3. Βιβλιοθήκη sprites — τοπικά thumbnails ===")
        opened = cdp.evaluate("""(() => {
            // Κύριο κουμπί «Επιλέξτε ένα Αντικείμενο» του sprite selector (action menu)
            const btns = [...document.querySelectorAll('[class*="action-menu_main-button"]')];
            const b = btns.find(x => x.closest('[class*="sprite-selector"]'));
            if (!b) return false;
            b.click(); return true;
        })()""")
        check("Κλικ στο κουμπί προσθήκης sprite (βιβλιοθήκη)", bool(opened))
        lib = wait_for(cdp, """document.querySelectorAll('[class*="library-item_library-item_"][role="button"]').length""",
                 timeout=30)
        check("Η βιβλιοθήκη sprites άνοιξε", bool(lib), f"{lib or 0} items")
        thumbs = wait_for(cdp, """(() => {
            const imgs = [...document.querySelectorAll('[class*="library-item_library-item_"][role="button"] img')];
            const loaded = imgs.filter(i => i.complete && i.naturalWidth > 0);
            return loaded.length >= 10 ? loaded.length : null;
        })()""", timeout=30)
        check("Τα thumbnails φορτώθηκαν (≥10 ορατά)", isinstance(thumbs, int), f"{thumbs} εικόνες")
        local_thumbs = cdp.evaluate("""(() => {
            const imgs = [...document.querySelectorAll('[class*="library-item_library-item_"][role="button"] img')];
            const remote = imgs.filter(i => /^https?:/.test(i.src) && !i.src.includes('/apps/turbowarp/'));
            const local = imgs.filter(i => i.src.includes('/apps/turbowarp/scratch-assets/'));
            return {total: imgs.length, local: local.length, remote: remote.length};
        })()""")
        check("ΟΛΑ τα thumbnails από το τοπικό ./scratch-assets/ (κανένα εξωτερικό)",
              bool(local_thumbs and local_thumbs["local"] >= 10 and local_thumbs["remote"] == 0),
              str(local_thumbs))
        # ---------------------------------------------------------------
        print("\n=== 4. Προσθήκη sprite από τη βιβλιοθήκη ===")
        before = cdp.evaluate("""document.querySelectorAll('[class*="sprite-selector-item_sprite-name"]').length""")
        picked = cdp.evaluate("""(() => {
            const items = [...document.querySelectorAll('[class*="library-item_library-item_"][role="button"]')];
            const it = items.find(x => (x.textContent || '').includes('Abby')) || items[3];
            if (!it) return null;
            const name = (it.querySelector('[class*="library-item_name"], [class*="library-item_library-item-name"]') || it).textContent.trim();
            it.click(); return name;
        })()""")
        check("Επιλογή sprite από τη βιβλιοθήκη", bool(picked), str(picked))
        added = wait_for(cdp, f"""(() => {{
            const names = [...document.querySelectorAll('[class*="sprite-selector-item_sprite-name"]')].map(e => e.textContent);
            return names.length > {before or 1} ? names.join(',') : null;
        }})()""", timeout=30)
        check("Το νέο sprite εμφανίστηκε στη λίστα sprites", bool(added), str(added)[:80])
        on_stage = wait_for(cdp, """!!document.querySelector('[class*="stage_stage"] canvas')""", timeout=30)
        check("Το stage (canvas) είναι ενεργό με τα sprites", bool(on_stage))

        # ---------------------------------------------------------------
        print("\n=== 5. Offline & pill επιστροφής ===")
        time.sleep(2)
        ext = net.external()
        check("Κανένα request σε εξωτερικό host (μόνο 127.0.0.1)", not ext,
              f"{len(net.urls)} requests" + (f" — ΕΞΩΤΕΡΙΚΑ: {ext[:3]}" if ext else ""))
        bad_hosts = [u for u in net.urls if not u.startswith(LOCAL_SCHEMES) and any(h in u for h in
                     ("scratch.mit.edu", "trampoline", "turbowarp.org", "clouddata"))]
        check("Κανένα scratch.mit.edu/trampoline/clouddata request", not bad_hosts,
              str(bad_hosts[:3]) if bad_hosts else "καθαρό")
        local_assets = [u for u in net.urls if "/apps/turbowarp/scratch-assets/" in u]
        check("Assets βιβλιοθήκης φορτώθηκαν τοπικά", len(local_assets) >= 10,
              f"{len(local_assets)} τοπικά assets")

        pill = cdp.evaluate("""(() => {
            const a = document.getElementById('portal-back-pill');
            if (!a) return null;
            const s = getComputedStyle(a), r = a.getBoundingClientRect();
            // Το pill δεν πρέπει να καλύπτει κανένα κουμπί του menu bar
            const covered = [...document.querySelectorAll('[class*="menu-bar"] [role="button"], [class*="menu-bar_menu-bar-item"]')]
                .some(el => { const b = el.getBoundingClientRect();
                    return b.width > 0 && !(b.right < r.left || b.left > r.right || b.bottom < r.top || b.top > r.bottom); });
            return {text: a.textContent.trim(), href: a.getAttribute('href'),
                    position: s.position, left: r.left, top: r.top, coversMenu: covered,
                    visible: r.width > 0 && r.height > 0};
        })()""")
        ok_pill = bool(pill and pill["visible"] and pill["text"] == "← Portal"
                       and pill["href"] == "/" and pill["position"] == "fixed"
                       and pill["left"] < 60 and pill["top"] < 60 and not pill["coversMenu"])
        check("Pill «← Portal» ορατό (top-left) χωρίς να καλύπτει το menu bar", ok_pill,
              str(pill)[:140])

        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: "
              f"{r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())