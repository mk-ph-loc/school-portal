#!/opt/school-portal/venv/bin/python
"""
snap-tf-test.py — Έλεγχος των offline εφαρμογών Snap! & TensorFlow Playground.

Σε headless Chromium (CDP) ελέγχει:
  * /apps/snap/: το wrapper σπέρνει Ελληνικά ΜΟΝΟ αν δεν υπάρχει ήδη επιλογή
    χρήστη (-snap-setting-language), ανακατευθύνει στο ./snap.html, το IDE
    φορτώνει (canvas#world + world.children, timeout 60s), ελληνικά μπλοκ
    («κάνε _ βήματα» της κατηγορίας «Κίνηση»), κλικ στην κατηγορία → palette
    με ορατά μπλοκ, ΟΛΑ τα network requests ΜΟΝΟ τοπικά (κανένα
    snap.berkeley.edu / stackhero Matomo), pill «← Portal» ορατό.
  * /apps/tf-playground/: το δίκτυο σχεδιάζεται (#svg g.core + node canvases),
    play → το training loss μειώνεται μετά από iterations, τα εικονίδια
    play/pause είναι unicode glyphs (όχι σπασμένα material-icons ligatures),
    ΟΛΑ τα requests τοπικά (κανένα googleapis/gstatic/google-analytics),
    pill «← Portal» ορατό.

Χρήση: /opt/school-portal/venv/bin/python scripts/snap-tf-test.py
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import check, launch_chrome, results, stop_chrome, wait_for

PORT = 9354  # διαφορετική θύρα από τα υπόλοιπα browser tests
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


IDE_JS = """(() => {
    const ide = (window.world && world.children || []).find(
        c => c.constructor && c.constructor.name === 'IDE_Morph');
    return ide || null;
})()"""

PILL_JS = """(() => {
    const a = document.getElementById('portal-back-pill');
    if (!a) return null;
    const s = getComputedStyle(a), r = a.getBoundingClientRect();
    return {text: a.textContent.trim(), href: a.getAttribute('href'),
            position: s.position, visible: r.width > 0 && r.height > 0};
})()"""


def check_pill(cdp, label):
    pill = cdp.evaluate(PILL_JS)
    check(label, bool(pill and pill["visible"] and pill["text"] == "← Portal"
                      and pill["href"] == "/" and pill["position"] == "fixed"),
          str(pill)[:120])


def test_snap(cdp, net):
    print("\n=== 1. Snap! — wrapper, γλώσσα & φόρτωση IDE ===")
    net.urls.clear()
    cdp.send("Page.navigate", {"url": f"{BASE}/apps/snap/"})
    got = wait_for(cdp, "location.pathname.endsWith('/snap.html')", timeout=30)
    check("Το wrapper ανακατεύθυνε στο ./snap.html", bool(got),
          cdp.evaluate("location.pathname"))
    lang = cdp.evaluate("localStorage.getItem('-snap-setting-language')")
    check("Default γλώσσα el (-snap-setting-language στο localStorage)",
          lang == "el", str(lang))

    ready = wait_for(cdp, """(() => {
        const w = window.world;
        return !!(w && w.children.length > 0 && document.getElementById('world'));
    })()""", timeout=60)
    check("Το IDE φόρτωσε (canvas#world + world.children > 0)", bool(ready))
    check("Δεν υπάρχει Matomo tracker (_paq)",
          cdp.evaluate("typeof window._paq === 'undefined'"))
    cdp.evaluate("""window.__sw = 'pending';
        navigator.serviceWorker.getRegistrations()
            .then(rs => { window.__sw = rs.length; }); true""")
    no_sw = wait_for(cdp, "window.__sw === 0 ? true : null", timeout=10)
    check("Κανένας service worker registered", no_sw is True,
          str(cdp.evaluate("window.__sw")))

    print("\n=== 2. Snap! — Ελληνικά μπλοκ & palette «Κίνηση» ===")
    # Το locale/lang-el.js φορτώνει async — περιμένουμε πρώτα το translation.
    wait_for(cdp, "typeof SnapTranslator !== 'undefined' && SnapTranslator.language === 'el'",
             timeout=30)
    # Τα abstract specs χρησιμοποιούν '_' για τα inputs (π.χ. 'move _ steps')
    # ενώ τα στιγμιότυπα μπλοκ '%n' — η μετάφραση γίνεται στο localizeBlockSpec.
    greek = wait_for(cdp, f"""(() => {{
        const ide = {IDE_JS};
        if (!ide || !ide.currentSprite) return null;
        const b = ide.currentSprite.blocks['forward'];
        if (!b) return null;
        const abstract = b.spec.replace(/%[a-zA-Z]+/g, '_');
        const spec = localize(abstract);
        return (spec && spec.includes('βήματα')) ? spec : null;
    }})()""", timeout=30)
    check("Ελληνικό block spec «κάνε _ βήματα» (forward)", bool(greek), str(greek))

    # Πραγματικό κλικ στο κουμπί κατηγορίας «Κίνηση» (συντεταγμένες morph → CSS px)
    pos = cdp.evaluate(f"""(() => {{
        const ide = {IDE_JS};
        if (!ide || !ide.categories || !ide.categories.buttons) return null;
        const b = ide.categories.buttons.find(x => x.category === 'motion');
        if (!b) return null;
        const p = b.center();
        return {{x: p.x, y: p.y, label: b.label.text}};
    }})()""")
    check("Βρέθηκε το κουμπί κατηγορίας με ελληνικό label «Κίνηση»",
          bool(pos and pos["label"] == "Κίνηση"), str(pos))
    if pos:
        cdp.click(pos["x"], pos["y"])
    blocks = wait_for(cdp, f"""(() => {{
        const ide = {IDE_JS};
        if (!ide || !ide.palette || ide.currentCategory !== 'motion') return null;
        let n = 0, texts = [];
        (function walk(m) {{
            if (m instanceof BlockMorph) {{
                n++;
                m.children.forEach(c => {{
                    if (c instanceof StringMorph && c.text) texts.push(c.text);
                }});
            }}
            (m.children || []).forEach(walk);
        }})(ide.palette.contents);
        return n >= 5 ? {{n: n, sample: texts.slice(0, 14).join(' ')}} : null;
    }})()""", timeout=30)
    check("Άνοιγμα palette «Κίνηση» → τουλάχιστον 5 μπλοκ ορατά", bool(blocks),
          f"{blocks['n']} μπλοκ" if blocks else "κανένα")
    check("Τα μπλοκ της palette είναι στα Ελληνικά («βήματα»)",
          bool(blocks and "βήματα" in blocks["sample"]),
          (blocks or {}).get("sample", "")[:80])

    print("\n=== 3. Snap! — offline & pill επιστροφής ===")
    time.sleep(2)
    ext = net.external()
    check("Κανένα request σε εξωτερικό host (μόνο 127.0.0.1)", not ext,
          f"{len(net.urls)} requests" + (f" — ΕΞΩΤΕΡΙΚΑ: {ext[:3]}" if ext else ""))
    bad = [u for u in net.urls if any(h in u for h in
           ("berkeley.edu", "stackhero", "cs10.org"))]
    check("Κανένα berkeley.edu/stackhero request (cloud & Matomo νεκρά)", not bad,
          str(bad[:3]) if bad else "καθαρό")
    local_api = [u for u in net.urls if "/apps/snap/api/v1/" in u]
    check("Cloud calls same-origin relative (./api/v1/ → τοπικά 404)",
          len(local_api) >= 1, f"{len(local_api)} τοπικά api calls")
    check_pill(cdp, "Pill «← Portal» ορατό (fixed πάνω από το canvas)")

    # Σεβασμός υπάρχουσας επιλογής χρήστη: το wrapper ΔΕΝ την overwrite-άρει
    cdp.evaluate("localStorage.setItem('-snap-setting-language', 'de'); true")
    cdp.send("Page.navigate", {"url": f"{BASE}/apps/snap/"})
    wait_for(cdp, "location.pathname.endsWith('/snap.html')", timeout=30)
    kept = cdp.evaluate("localStorage.getItem('-snap-setting-language')")
    check("Το wrapper σέβεται υπάρχουσα επιλογή γλώσσας (de παρέμεινε)", kept == "de", str(kept))
    cdp.evaluate("localStorage.setItem('-snap-setting-language', 'el'); true")


def test_tf(cdp, net):
    print("\n=== 4. TF Playground — wrapper & σχεδίαση δικτύου ===")
    net.urls.clear()
    cdp.send("Page.navigate", {"url": f"{BASE}/apps/tf-playground/"})
    got = wait_for(cdp, "location.pathname.endsWith('/playground.html')", timeout=30)
    check("Το wrapper ανακατεύθυνε στο ./playground.html", bool(got),
          cdp.evaluate("location.pathname"))
    drawn = wait_for(cdp, """(() => {
        const svg = document.querySelector('#svg g.core');
        const nodes = document.querySelectorAll('#network .canvas').length;
        return (svg && nodes >= 5) ? nodes : null;
    })()""", timeout=60)
    check("Το δίκτυο σχεδιάστηκε (svg g.core + node canvases)", bool(drawn),
          f"{drawn} κόμβοι" if drawn else "όχι ακόμα")

    print("\n=== 5. TF Playground — εικονίδια unicode (όχι σπασμένα glyphs) ===")
    icons = cdp.evaluate("""(() => {
        const btn = document.getElementById('play-pause-button');
        const is = [...btn.querySelectorAll('i.material-icons')];
        const vis = is.map(i => ({t: i.textContent,
            shown: getComputedStyle(i).display !== 'none',
            w: i.getBoundingClientRect().width}));
        const words = [...document.querySelectorAll('i.material-icons')]
            .map(i => i.textContent.trim())
            .filter(t => /^[a-z_]+$/.test(t));
        return {icons: vis, brokenWords: words,
                reset: document.querySelector('#reset-button i').textContent,
                step: document.querySelector('#next-step-button i').textContent};
    })()""")
    play_ok = bool(icons and icons["icons"][0]["t"].startswith("▶")
                   and icons["icons"][0]["shown"] and icons["icons"][0]["w"] > 0)
    check("Εικονίδιο play ▶ ορατό πριν την εκκίνηση", play_ok, str(icons)[:160])
    check("Κανένα σπασμένο material-icon ligature (replay/add/remove κ.λπ.)",
          bool(icons and not icons["brokenWords"]),
          str(icons["brokenWords"]) if icons else "?")
    check("Reset ↻ & step ⏭ αντικαταστάθηκαν",
          bool(icons and icons["reset"] == "↻" and icons["step"].startswith("⏭")),
          f"reset={icons['reset']!r} step={icons['step']!r}" if icons else "?")

    print("\n=== 6. TF Playground — play → το loss μειώνεται ===")
    cdp.evaluate("document.getElementById('play-pause-button').click(); true")
    playing = wait_for(cdp, """(() => {
        const btn = document.getElementById('play-pause-button');
        if (!btn.classList.contains('playing')) return null;
        const pause = btn.querySelectorAll('i.material-icons')[1];
        return getComputedStyle(pause).display !== 'none' ? pause.textContent : null;
    })()""", timeout=15)
    check("Μετά το play εμφανίζεται το εικονίδιο pause ⏸", bool(playing), str(playing))
    trained = wait_for(cdp, """(() => {
        const it = parseInt(document.getElementById('iter-number').textContent
            .replace(/[^0-9]/g, ''), 10) || 0;
        const loss = parseFloat(document.getElementById('loss-train').textContent);
        return (it >= 30 && !isNaN(loss)) ? {iter: it, loss: loss} : null;
    })()""", timeout=60)
    check("Η εκπαίδευση τρέχει (≥30 epochs, loss αριθμός)", bool(trained), str(trained))
    if trained:
        first_loss = trained["loss"]
        better = wait_for(cdp, f"""(() => {{
            const it = parseInt(document.getElementById('iter-number').textContent
                .replace(/[^0-9]/g, ''), 10) || 0;
            const loss = parseFloat(document.getElementById('loss-train').textContent);
            return (it >= {trained['iter'] + 50} && !isNaN(loss) && loss < {first_loss})
                ? {{iter: it, loss: loss}} : null;
        }})()""", timeout=60)
        check("Το training loss μειώθηκε μετά από iterations", bool(better),
              f"{first_loss} → {better['loss'] if better else '?'}")
    cdp.evaluate("document.getElementById('play-pause-button').click(); true")

    print("\n=== 7. TF Playground — offline & pill επιστροφής ===")
    time.sleep(2)
    ext = net.external()
    check("Κανένα request σε εξωτερικό host (μόνο 127.0.0.1)", not ext,
          f"{len(net.urls)} requests" + (f" — ΕΞΩΤΕΡΙΚΑ: {ext[:3]}" if ext else ""))
    bad = [u for u in net.urls if any(h in u for h in
           ("googleapis", "gstatic", "google-analytics", "fonts.g"))]
    check("Κανένα googleapis/gstatic/google-analytics request", not bad,
          str(bad[:3]) if bad else "καθαρό")
    check_pill(cdp, "Pill «← Portal» ορατό")


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
        test_snap(cdp, net)
        test_tf(cdp, net)
        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: "
              f"{r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())
