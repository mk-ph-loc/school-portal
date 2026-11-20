#!/opt/school-portal/venv/bin/python
"""
bipes-test.py — Έλεγχος της offline εφαρμογής BIPES (ρομποτική/μικροελεγκτές).

Σε headless Chromium (CDP) ελέγχει:
  * /apps/bipes/: το wrapper ανακατευθύνει στο ./ui/index.html?lang=el,
    ο editor φορτώνει (Blockly workspace), ελληνικά tabs (Μπλοκ/Κονσόλα/
    Αρχεία/Κοινόχρηστα/Συσκευή), τα tabs IOT/EasyMQTT/Databoard ΔΕΝ υπάρχουν,
    toolbox Blockly με ελληνικές κατηγορίες ορατό μετά τη φόρτωση συσκευής,
    κλικ σε κατηγορία → flyout με μπλοκ, κλικ σε μπλοκ → δημιουργείται στο
    workspace, tab switching (Αρχεία → CodeMirror, Συσκευή → λίστα πλακετών),
    ΟΛΑ τα network requests ΜΟΝΟ τοπικά (κανένα appspot/jsdelivr/google/
    bipes.net.br), pill «← Portal» ορατό.

Χρήση: /opt/school-portal/venv/bin/python scripts/bipes-test.py
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import check, launch_chrome, results, stop_chrome, wait_for

PORT = 9355  # διαφορετική θύρα από τα υπόλοιπα browser tests
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


PILL_JS = """(() => {
    const a = document.getElementById('portal-back-pill');
    if (!a) return null;
    const s = getComputedStyle(a), r = a.getBoundingClientRect();
    return {text: a.textContent.trim(), href: a.getAttribute('href'),
            position: s.position, visible: r.width > 0 && r.height > 0};
})()"""


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

        print("\n=== 1. Wrapper & φόρτωση editor ===")
        cdp.send("Page.navigate", {"url": f"{BASE}/apps/bipes/"})
        got = wait_for(cdp, "location.pathname.endsWith('/ui/index.html')", timeout=30)
        check("Το wrapper ανακατεύθυνε στο ./ui/index.html", bool(got),
              cdp.evaluate("location.pathname + location.search"))
        check("Default γλώσσα el (?lang=el)",
              cdp.evaluate("location.search.includes('lang=el')"))

        ready = wait_for(cdp, """(() => {
            return !!(window.Code && Code.workspace && window.Blockly &&
                      document.querySelector('#content_blocks .blocklySvg'));
        })()""", timeout=60)
        check("Ο editor φόρτωσε (Code.workspace + Blockly SVG)", bool(ready))
        lang = cdp.evaluate("Code.LANG")
        check("Code.LANG = el", lang == "el", str(lang))
        check("Ελληνικά στο μενού γλωσσών (Code.LANGUAGE_NAME.el)",
              cdp.evaluate("Code.LANGUAGE_NAME['el']") == "Ελληνικά")

        print("\n=== 2. Ελληνικά tabs & αφαίρεση cloud tabs ===")
        tabs = cdp.evaluate("""(() => {
            const ids = ['blocks','console','files','programs','device'];
            const out = {};
            ids.forEach(i => { const e = document.getElementById('tab_'+i);
                               out[i] = e ? e.textContent.trim() : null; });
            return out;
        })()""")
        check("Tab «Μπλοκ»", tabs.get("blocks") == "Μπλοκ", str(tabs))
        check("Tab «Κονσόλα»", tabs.get("console") == "Κονσόλα")
        check("Tab «Αρχεία»", tabs.get("files") == "Αρχεία")
        check("Tab «Κοινόχρηστα»", tabs.get("programs") == "Κοινόχρηστα")
        check("Tab «Συσκευή»", tabs.get("device") == "Συσκευή")
        gone = cdp.evaluate("""(() => {
            return ['tab_iot','tab_mqtt','tab_databoard','content_iot',
                    'content_mqtt','content_databoard','easymqtt_iframe',
                    'databoard_iframe'].filter(i => document.getElementById(i));
        })()""")
        check("Tabs/divs IOT-EasyMQTT-Databoard αφαιρέθηκαν", not gone, str(gone))
        n_iframes = cdp.evaluate("document.querySelectorAll('iframe').length")
        check("Κανένα iframe κατά την εκκίνηση (freeboard/databoard/shared)",
              n_iframes == 0, f"{n_iframes} iframes")
        check("Code.TABS_ χωρίς databoard/mqtt/iot",
              cdp.evaluate("JSON.stringify(Code.TABS_)") ==
              '["blocks","console","files","device","programs"]')

        print("\n=== 3. Toolbox Blockly (ελληνικές κατηγορίες) ===")
        # Η toolbox γεμίζει μετά τη φόρτωση του devinfo/devinfo.json + toolbox XML
        toolbox = wait_for(cdp, """(() => {
            const cats = [...document.querySelectorAll(
                '#content_blocks .blocklyToolboxDiv .blocklyTreeLabel')];
            if (!cats.length) return null;
            return cats.map(c => c.textContent.trim());
        })()""", timeout=30)
        check("Toolbox ορατό με κατηγορίες", bool(toolbox),
              f"{len(toolbox or [])} κατηγορίες")
        check("Ελληνικές κατηγορίες (Λογική/Επαναλήψεις/Μαθηματικά)",
              bool(toolbox) and all(c in toolbox for c in
                                    ("Λογική", "Επαναλήψεις", "Μαθηματικά")),
              str((toolbox or [])[:8]))
        vis = cdp.evaluate("""(() => {
            const t = document.querySelector('#content_blocks .blocklyToolboxDiv');
            if (!t) return null;
            const r = t.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        })()""")
        check("Η εργαλειοθήκη είναι ορατή (width/height > 0)", bool(vis))

        print("\n=== 4. Κλικ σε κατηγορία → flyout → δημιουργία μπλοκ ===")
        # Το splash modal (ελληνικό καλωσόρισμα) εμφανίζεται στο onload και
        # καλύπτει το UI — το κλείνουμε όπως θα έκανε ο μαθητής («Κλείσιμο»).
        splash = wait_for(cdp, """(() => {
            const m = document.getElementById('myModal');
            if (!m || getComputedStyle(m).display === 'none') return null;
            const t = document.getElementById('modalTitle').textContent;
            return t.includes('BIPES') ? t : null;
        })()""", timeout=15)
        check("Ελληνικό splash screen εμφανίστηκε", bool(splash), str(splash))
        cdp.evaluate("closeModal(); true")
        closed = wait_for(cdp,
                          "getComputedStyle(document.getElementById('myModal')).display === 'none'",
                          timeout=10)
        check("Το splash έκλεισε με «Κλείσιμο»", bool(closed))
        rect = cdp.evaluate("""(() => {
            const labels = [...document.querySelectorAll(
                '#content_blocks .blocklyToolboxDiv .blocklyTreeLabel')];
            const l = labels.find(x => x.textContent.trim() === 'Λογική');
            if (!l) return null;
            const r = l.getBoundingClientRect();
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        })()""")
        check("Κατηγορία «Λογική» υπάρχει για κλικ", bool(rect))
        if rect:
            cdp.click(rect["x"], rect["y"])
        flyout = wait_for(cdp, """(() => {
            const f = document.querySelector(
                '#content_blocks .blocklyFlyout .blocklyDraggable');
            if (!f) return null;
            const r = f.getBoundingClientRect();
            return r.width > 0 ? {x: r.x + Math.min(r.width/2, 60),
                                 y: r.y + r.height/2} : null;
        })()""", timeout=15)
        check("Κλικ στην κατηγορία άνοιξε flyout με μπλοκ", bool(flyout))
        n_before = cdp.evaluate("Code.workspace.getAllBlocks(false).length")
        if flyout:
            cdp.click(flyout["x"], flyout["y"])
        created = wait_for(cdp,
                           f"Code.workspace.getAllBlocks(false).length > {n_before}",
                           timeout=15)
        n_after = cdp.evaluate("Code.workspace.getAllBlocks(false).length")
        check("Κλικ σε μπλοκ του flyout → δημιουργήθηκε μπλοκ στο workspace",
              bool(created), f"{n_before} → {n_after} μπλοκ")

        print("\n=== 5. Tab switching (Αρχεία / Συσκευή / Μπλοκ) ===")
        cdp.evaluate("document.getElementById('tab_files').click(); true")
        files_ok = wait_for(cdp, """(() => {
            const c = document.getElementById('content_files');
            return c && c.classList.contains('on') &&
                   document.querySelector('#content_files .CodeMirror');
        })()""", timeout=15)
        check("Tab Αρχεία → CodeMirror editor ορατός", bool(files_ok))
        cdp.evaluate("document.getElementById('tab_device').click(); true")
        dev_ok = wait_for(cdp, """(() => {
            const c = document.getElementById('content_device');
            const img = document.getElementById('device_img');
            return c && c.classList.contains('on') && img && img.src.length > 0;
        })()""", timeout=15)
        check("Tab Συσκευή → πληροφορίες πλακέτας ορατές", bool(dev_ok))
        cdp.evaluate("document.getElementById('tab_blocks').click(); true")
        back_ok = wait_for(cdp, """(() => {
            const c = document.getElementById('content_blocks');
            return c && c.classList.contains('on') &&
                   Code.workspace.getAllBlocks(false).length > 0;
        })()""", timeout=15)
        check("Επιστροφή στα Μπλοκ → το workspace διατηρεί τα μπλοκ", bool(back_ok))

        print("\n=== 6. Offline & pill επιστροφής ===")
        time.sleep(2)
        ext = net.external()
        check("Κανένα request σε εξωτερικό host (μόνο 127.0.0.1)", not ext,
              f"{len(net.urls)} requests" + (f" — ΕΞΩΤΕΡΙΚΑ: {ext[:3]}" if ext else ""))
        bad = [u for u in net.urls if any(h in u for h in
               ("appspot", "jsdelivr", "google", "gstatic", "bipes.net.br",
                "rawgit", "bootstrapcdn"))]
        check("Κανένα appspot/jsdelivr/google/bipes.net.br request", not bad,
              str(bad[:3]) if bad else "καθαρό")
        pill = cdp.evaluate(PILL_JS)
        check("Pill «← Portal» ορατό",
              bool(pill and pill["visible"] and pill["text"] == "← Portal"
                   and pill["href"] == "/" and pill["position"] == "fixed"),
              str(pill)[:120])

        r = results()
        print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if r.failed == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'}: "
              f"{r.passed} OK, {r.failed} FAIL")
        return r.exit_code()
    finally:
        cdp.close()
        stop_chrome(proc)


if __name__ == "__main__":
    sys.exit(main())