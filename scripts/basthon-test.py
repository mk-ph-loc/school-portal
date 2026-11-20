#!/opt/school-portal/venv/bin/python
"""
basthon-test.py — Έλεγχος του offline εργαστηρίου Python Basthon (/apps/basthon/).

Σε headless Chromium (CDP) ελέγχει:
  * το wrapper ανακατευθύνει στο ./console/index.html?kernel=python3
  * ο kernel φορτώνει ΤΟΠΙΚΟ Pyodide & γίνεται έτοιμος (banner Python 3.12.1
    στο terminal — το init παίρνει χρόνο, timeout 120s)
  * print(2**10) μέσω editor + «Exécuter» → output "1024" στο terminal
  * import turtle + forward(100) + done() → SVG στο #graphics χωρίς σφάλμα
  * ΟΛΑ τα network requests ΜΟΝΟ στο 127.0.0.1 (κανένα cdn.basthon.fr/jsdelivr)
  * το pill «← Portal» είναι ορατό (fixed bottom-left, href=/)

Χρήση: /opt/school-portal/venv/bin/python scripts/basthon-test.py
"""
from __future__ import annotations

import sys
import time
import urllib.parse

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import check, launch_chrome, results, stop_chrome

PORT = 9352  # διαφορετική θύρα από τα υπόλοιπα browser tests
BASE = "http://127.0.0.1"

LOCAL_SCHEMES = ("data:", "blob:", "about:", "chrome:", "devtools:")


class NetLog:
    """Συλλογή ΟΛΩΝ των network requests μέσω CDP Network.enable + on_event.

    Ο Python kernel του Basthon τρέχει σε sandboxed dedicated worker (data: URL).
    Τα importScripts/fetch του worker ΔΕΝ φαίνονται πάντα ως Network events στο
    page session — γι' αυτό:
      * Target.setAutoAttach → attach σε κάθε worker session (Network.enable),
      * στο τέλος διαβάζουμε το performance.getEntriesByType('resource') ΜΕΣΑ
        σε κάθε worker (πλήρης λίστα πραγματικών loads, incl. pyodide.js/wasm).
    Τα pending attaches επεξεργάζονται ΕΚΤΟΣ του on_event callback (το
    send_session μέσα στο callback θα κλείδωνε το ίδιο WebSocket).
    """

    def __init__(self):
        self.urls: list[str] = []
        self.pending_sessions: list[str] = []
        self.worker_sessions: list[str] = []
        self.cdp = None  # ορίζεται μετά το launch_chrome

    def on_event(self, msg):
        method = msg.get("method")
        if method == "Network.requestWillBeSent":
            url = msg.get("params", {}).get("request", {}).get("url", "")
            if url:
                self.urls.append(url)
        elif method == "Target.attachedToTarget":
            info = msg.get("params", {})
            sid = info.get("sessionId")
            if sid and info.get("targetInfo", {}).get("type") in ("worker", "shared_worker"):
                self.pending_sessions.append(sid)

    def pump(self):
        """Attach στα νέα worker sessions — καλείται από το main loop του test."""
        while self.pending_sessions:
            sid = self.pending_sessions.pop(0)
            self.worker_sessions.append(sid)
            try:
                self.cdp.send_session(sid, "Network.enable")
                self.cdp.send_session(sid, "Runtime.runIfWaitingForDebugger")
                self.cdp.send_session(sid, "Target.setAutoAttach",
                                      {"autoAttach": True,
                                       "waitForDebuggerOnStart": False,
                                       "flatten": True})
            except Exception:
                pass

    def collect_worker_resources(self):
        """Πραγματικά resource loads κάθε worker (performance API μέσα στον worker)."""
        for sid in self.worker_sessions:
            try:
                res = self.cdp.send_session(sid, "Runtime.evaluate", {
                    "expression": "performance.getEntriesByType('resource').map(e=>e.name)",
                    "returnByValue": True})
                for u in res.get("result", {}).get("value") or []:
                    if u not in self.urls:
                        self.urls.append(u)
            except Exception:
                pass

    def external(self) -> list[str]:
        out = []
        for u in self.urls:
            if u.startswith(LOCAL_SCHEMES):
                continue
            host = urllib.parse.urlsplit(u).hostname
            if host != "127.0.0.1":
                out.append(u)
        return out


# Editor API: το Ace instance είναι προσδεμένο στο DOM node (#editor .env.editor).
SET_EDITOR = """(() => {
    const el = document.querySelector('#editor');
    const ed = el && el.env && el.env.editor;
    if (!ed) return false;
    ed.setValue(%s, -1);
    return true;
})()"""


def run_script(cdp, net, code: str) -> bool:
    """Γράφει κώδικα στον editor και πατά το πραγματικό κουμπί «Exécuter»."""
    import json
    net.pump()
    got = cdp.evaluate(SET_EDITOR % json.dumps(code))
    if not got:
        return False
    cdp.evaluate("document.getElementById('run').click(); true")
    net.pump()
    return True


def wait_ready(cdp, net, expr, timeout=60, interval=0.5):
    """wait_for που παράλληλα επεξεργάζεται τα pending worker attaches."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        net.pump()
        try:
            last = cdp.evaluate(expr)
            if last:
                return last
        except Exception as exc:
            last = str(exc)
        time.sleep(interval)
    return last


def main() -> int:
    net = NetLog()
    try:
        proc, cdp = launch_chrome(PORT, timeout=180, on_event=net.on_event)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    net.cdp = cdp

    try:
        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        cdp.send("Network.enable")
        # Attach σε dedicated workers (ο kernel τρέχει εκεί) χωρίς pause.
        cdp.send("Target.setAutoAttach", {"autoAttach": True,
                                          "waitForDebuggerOnStart": False,
                                          "flatten": True})

        # ---------------------------------------------------------------
        print("\n=== 1. Άνοιγμα /apps/basthon/ & εκκίνηση kernel ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/basthon/"})
        got = wait_ready(cdp, net, "location.pathname === '/apps/basthon/console/index.html' && "
                                   "location.search === '?kernel=python3'", timeout=30)
        check("Wrapper → ./console/index.html?kernel=python3", bool(got))

        # Το Pyodide init (wasm + stdlib + basthon kernel) παίρνει χρόνο.
        # Έτοιμο = window.Basthon.ready() resolved + το xterm terminal έχει
        # σχεδιαστεί (canvas renderer — το DOM .xterm-rows ΔΕΝ υπάρχει πλέον).
        cdp.evaluate("""(() => {
            window.__kernelReady = false;
            const poll = () => {
                if (window.Basthon) {
                    window.Basthon.ready().then(() => { window.__kernelReady = true; });
                } else { setTimeout(poll, 500); }
            };
            poll();
            return true;
        })()""")
        ready = wait_ready(cdp, net, """(() => {
            const t = document.getElementById('shell');
            return !!(window.__kernelReady && t && t.querySelector('canvas'));
        })()""", timeout=120, interval=1)
        check("Kernel έτοιμος (Basthon.ready() + xterm terminal)", bool(ready))
        editor = wait_ready(cdp, net, "!!(document.querySelector('#editor')?.env?.editor)", timeout=30)
        check("Ace editor έτοιμος (#editor)", bool(editor))

        # Συλλογή stdout/stderr μέσω των eval.output events του kernel API
        # (το xterm σχεδιάζει σε canvas — δεν υπάρχει αναγνώσιμο DOM text).
        cdp.evaluate("""(() => {
            window.__out = ''; window.__err = '';
            window.Basthon.addEventListener('eval.output', e => {
                if (e.stream === 'stdout') window.__out += e.content;
                else window.__err += e.content;
            });
            return true;
        })()""")
        # ---------------------------------------------------------------
        print("\n=== 2. Εκτέλεση print(2**10) → 1024 ===")
        check("Ο κώδικας γράφτηκε στον editor & πάτησε Exécuter",
              run_script(cdp, net, "print(2**10)"))
        out = wait_ready(cdp, net, "window.__out.includes('1024')", timeout=60)
        check("Output «1024» στο terminal (stdout)", bool(out),
              repr(cdp.evaluate("window.__out.slice(0,80)")))

        # ---------------------------------------------------------------
        print("\n=== 3. Turtle: forward(100) → SVG χωρίς σφάλμα ===")
        turtle_code = ("import turtle\n"
                       "t = turtle.Turtle()\n"
                       "t.forward(100)\n"
                       "turtle.done()\n"
                       "print('TURTLE-OK')\n")
        check("Ο turtle κώδικας εκτελέστηκε", run_script(cdp, net, turtle_code))
        got = wait_ready(cdp, net, """(() => {
            const g = document.getElementById('graphics');
            return !!(g && g.querySelector('svg') && window.__out.includes('TURTLE-OK'));
        })()""", timeout=90)
        check("SVG εμφανίστηκε στο #graphics + TURTLE-OK", bool(got))
        no_err = cdp.evaluate("""(() => {
            const e = window.__err;
            return !e.includes('Traceback') && !e.includes('ModuleNotFoundError');
        })()""")
        check("Χωρίς σφάλμα Python (Traceback/ModuleNotFoundError)", bool(no_err),
              repr(cdp.evaluate("window.__err.slice(0,120)")))

        # ---------------------------------------------------------------
        print("\n=== 4. Offline & pill επιστροφής ===")
        time.sleep(2)
        net.pump()
        net.collect_worker_resources()
        ext = net.external()
        check("Κανένα request σε εξωτερικό host (μόνο 127.0.0.1)", not ext,
              f"{len(net.urls)} requests" + (f" — ΕΞΩΤΕΡΙΚΑ: {ext[:3]}" if ext else ""))
        local_pyodide = [u for u in net.urls if "/pyodide/pyodide.js" in u]
        check("Το pyodide.js φορτώθηκε τοπικά", bool(local_pyodide),
              local_pyodide[0] if local_pyodide else "ΔΕΝ φορτώθηκε")

        pill = cdp.evaluate("""(() => {
            const a = document.getElementById('portal-back-pill');
            if (!a) return null;
            const s = getComputedStyle(a), r = a.getBoundingClientRect();
            return {text: a.textContent.trim(), href: a.getAttribute('href'),
                    position: s.position, left: r.left, bottomGap: innerHeight - r.bottom,
                    visible: r.width > 0 && r.height > 0};
        })()""")
        ok_pill = bool(pill and pill["visible"] and pill["text"] == "← Portal"
                       and pill["href"] == "/" and pill["position"] == "fixed"
                       and pill["left"] < 60 and pill["bottomGap"] < 60)
        check("Pill «← Portal» ορατό (fixed bottom-left, href=/)", ok_pill, str(pill)[:120])

        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: "
              f"{r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())