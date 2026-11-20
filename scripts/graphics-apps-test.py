#!/opt/school-portal/venv/bin/python
"""
graphics-apps-test.py — Έλεγχος των 3 offline γραφικών εφαρμογών σε headless Chromium.

Για ΚΑΘΕ εφαρμογή (/apps/drawio/, /apps/minipaint/, /apps/piskel/):
  * το wrapper index.html ανακατευθύνει στην πραγματική είσοδο και το UI φορτώνει
    (drawio: .geEditor canvas · minipaint: #canvas_minipaint · piskel: #drawing-canvas-container)
  * το pill «← Portal» υπάρχει, δείχνει στο "/" και είναι fixed bottom-left
  * με Network.enable + on_event συλλέγονται ΟΛΑ τα requests → κανένα σε εξωτερικό
    host (μόνο 127.0.0.1· data:/blob:/about: αγνοούνται ως μη-δικτυακά)
  * drawio & minipaint: ελληνικό menu («Αρχείο»)
  * piskel: πραγματικό click ζωγραφίζει pixel + άνοιγμα export dialog

Χρήση: /opt/school-portal/venv/bin/python scripts/graphics-apps-test.py
"""
from __future__ import annotations

import sys
import time
import urllib.parse

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import check, launch_chrome, results, stop_chrome, wait_for

PORT = 9351  # διαφορετική θύρα από τα υπόλοιπα browser tests
BASE = "http://127.0.0.1"

# Μη-δικτυακά schemes που δεν αποτελούν request προς host.
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

    def reset(self):
        self.urls.clear()

    def external(self) -> list[str]:
        out = []
        for u in self.urls:
            if u.startswith(LOCAL_SCHEMES):
                continue
            host = urllib.parse.urlsplit(u).hostname
            if host != "127.0.0.1":
                out.append(u)
        return out


def check_portal_pill(cdp):
    """Το injected pill «← Portal»: href="/", fixed, bottom-left, max z-index."""
    pill = cdp.evaluate("""(() => {
        const a = document.getElementById('portal-back-pill');
        if (!a) return null;
        const s = getComputedStyle(a), r = a.getBoundingClientRect();
        return {text: a.textContent.trim(), href: a.getAttribute('href'),
                position: s.position, zIndex: s.zIndex, opacity: parseFloat(s.opacity),
                left: r.left, bottomGap: innerHeight - r.bottom,
                visible: r.width > 0 && r.height > 0};
    })()""")
    ok = bool(pill and pill["visible"] and pill["text"] == "← Portal"
              and pill["href"] == "/" and pill["position"] == "fixed"
              and pill["left"] < 60 and pill["bottomGap"] < 60
              and pill["opacity"] < 1 and int(pill["zIndex"]) >= 2147483647)
    check("Pill «← Portal» (fixed bottom-left, ημιδιαφανές, href=/)", ok, str(pill)[:120])
    return pill


def check_no_external(net, label):
    ext = net.external()
    check(f"{label}Κανένα request σε εξωτερικό host (μόνο 127.0.0.1)", not ext,
          f"{len(net.urls)} requests" + (f" — ΕΞΩΤΕΡΙΚΑ: {ext[:3]}" if ext else ""))


def main() -> int:
    net = NetLog()
    try:
        proc, cdp = launch_chrome(PORT, timeout=120, on_event=net.on_event)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1

    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")

        # ---------------------------------------------------------------
        print("\n=== 1. draw.io (/apps/drawio/) ===")
        net.reset()
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/drawio/"})
        got = wait_for(cdp, "location.pathname.indexOf('/apps/drawio/app/') === 0", timeout=30)
        check("Wrapper → ./app/index.html με παραμέτρους offline/lang=el/pwa=0", bool(got))
        params = cdp.evaluate("location.search")
        check("Παράμετροι: offline=1&splash=0&lang=el&…&pwa=0 (ΟΧΙ local=1)",
              all(p in params for p in ("offline=1", "splash=0", "lang=el", "pwa=0"))
              and "local=1" not in params, params)
        # Σημ.: το draw.io v32 σχεδιάζει με SVG μέσα στο .geDiagramContainer του
        # .geEditor (όχι <canvas>) — ελέγχουμε editor + diagram surface + menubar.
        got = wait_for(cdp, "!!document.querySelector('.geEditor .geDiagramContainer') && "
                            "!!document.querySelector('.geMenubarContainer a.geItem')", timeout=120)
        check("Το draw.io φορτώνει (.geEditor diagram surface + menubar)", bool(got))
        greek = wait_for(cdp, "document.body.innerText.includes('Αρχείο')", timeout=30)
        check("Ελληνικό menu («Αρχείο»)", bool(greek))
        check_portal_pill(cdp)
        sw = cdp.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.length)",
                          await_promise=True)
        check("Χωρίς service worker (pwa=0)", sw == 0, f"{sw} registrations")
        time.sleep(2)  # αφήνουμε τυχόν deferred requests να καταγραφούν
        check_no_external(net, "drawio: ")

        # ---------------------------------------------------------------
        print("\n=== 2. miniPaint (/apps/minipaint/) ===")
        net.reset()
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/minipaint/"})
        got = wait_for(cdp, "location.pathname === '/apps/minipaint/editor.html' && "
                            "location.search === '?lang=el'", timeout=30)
        check("Wrapper → ./editor.html?lang=el", bool(got))
        got = wait_for(cdp, "!!document.getElementById('canvas_minipaint') && "
                            "document.getElementById('main_menu').children.length > 0",
                       timeout=60)
        check("Το miniPaint φορτώνει (#canvas_minipaint + menu)", bool(got))
        greek = wait_for(cdp, "document.getElementById('main_menu').innerText.includes('Αρχείο')",
                         timeout=30)
        check("Ελληνικό UI («Αρχείο»)", bool(greek))
        check_portal_pill(cdp)
        time.sleep(2)
        check_no_external(net, "minipaint: ")
        # ---------------------------------------------------------------
        print("\n=== 3. Piskel (/apps/piskel/) ===")
        net.reset()
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/piskel/"})
        got = wait_for(cdp, "location.pathname === '/apps/piskel/editor.html'", timeout=30)
        check("Wrapper → ./editor.html", bool(got))
        got = wait_for(cdp, "!!document.getElementById('drawing-canvas-container') && "
                            "!!document.querySelector('#drawing-canvas-container canvas') && "
                            "window.pskl && pskl.app && pskl.app.drawingController", timeout=90)
        check("Το Piskel φορτώνει (#drawing-canvas-container + canvas + app)", bool(got))
        check_portal_pill(cdp)

        # Πραγματικό click στο κέντρο του pixel (5,5) → ο default pen ζωγραφίζει.
        pos = cdp.evaluate("""(() => {
            const p = pskl.app.drawingController.renderer.reverseCoordinates(5, 5);
            const f = pskl.app.piskelController.getCurrentFrame();
            return {x: Math.round(p.x), y: Math.round(p.y), before: f.getPixel(5, 5)};
        })()""")
        check("Το pixel (5,5) είναι αρχικά κενό", bool(pos) and not pos["before"], str(pos))
        cdp.click(pos["x"], pos["y"])
        painted = wait_for(cdp, """(() => {
            const f = pskl.app.piskelController.getCurrentFrame();
            const v = f.getPixel(5, 5);
            return v ? String(v) : false;
        })()""", timeout=15)
        check("Click με το pen ζωγράφισε pixel στο frame", bool(painted), f"(5,5)={painted}")

        # Άνοιγμα export dialog από το πραγματικό εικονίδιο της μπάρας ρυθμίσεων.
        opened = cdp.evaluate("""(() => {
            const icon = document.querySelector('[data-setting="export"]');
            if (!icon) return false;
            icon.dispatchEvent(new MouseEvent('click', {bubbles: true}));
            return true;
        })()""")
        got = wait_for(cdp, """(() => {
            const d = document.getElementById('drawer-container');
            return d && d.querySelector('[data-tab-id="png"]') && d.innerText.includes('EXPORT')
                   ? d.innerText.replace(/\\s+/g, ' ').slice(0, 80) : false;
        })()""", timeout=15)
        check("Export dialog ανοίγει (tabs PNG/GIF)", bool(opened and got), str(got)[:80])
        time.sleep(2)
        check_no_external(net, "piskel: ")

        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: "
              f"{r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())