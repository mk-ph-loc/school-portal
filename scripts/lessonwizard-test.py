#!/opt/school-portal/venv/bin/python
"""
lessonwizard-test.py — Έλεγχος του πιλότου ημερήσιων μαθημάτων & Lesson Wizard.

Ελέγχει σε πραγματικό headless Chromium (CDP, όπως το browser-test.py):
  * οι 6 διδακτικές φάσεις εμφανίζονται στη σελίδα μαθητή,
  * οι σημειώσεις καθηγητή ΔΕΝ υπάρχουν στο HTML/JS των μαθητών,
  * με teacher cookie εμφανίζονται badges φάσεων + σημειώσεις,
  * το κουμπί «🖥️ Παρουσίαση» ανοίγει fullscreen overlay με πλοήγηση,
  * τα διαδραστικά (Ανόι) φορτώνουν σε iframe, το κουίζ χτίζεται,
  * το dropdown τμήματος & το widget ωραρίου δουλεύουν,
  * το API του wizard (login/lessons/teacher-notes protection).

Χρήση: /opt/school-portal/venv/bin/python scripts/lessonwizard-test.py
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
PORT = 9334
BASE = "http://127.0.0.1"
LESSON = BASE + "/docs/mathimata/gymnasio-g/pliroforiki/m02-pyrgoi-anoy/"


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=120)
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
        res = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("text", "JS exception"))
        return res.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for(cdp: CDP, expr: str, timeout: float = 30, interval: float = 0.5):
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


def http_json(path: str, data: dict | None = None, cookie: str = ""):
    req = urllib.request.Request(BASE + path)
    if cookie:
        req.add_header("Cookie", cookie)
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, body, timeout=15) as r:
            return r.status, r.headers, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, {}
def main() -> int:
    passed = failed = 0

    def check(label: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        mark = "\033[0;32m✓\033[0m" if ok else "\033[0;31m✗\033[0m"
        print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
        passed += ok
        failed += not ok

    print("== API checks ==")
    st, _, _ = http_json("/lesson-wizard/healthz")
    check("wizard healthz", st == 200)
    st, _, _ = http_json("/lesson-wizard/api/lessons")
    check("api/lessons χωρίς cookie → 401", st == 401)
    st, hdrs, _ = http_json("/lesson-wizard/api/login", {"code": "teacher2026"})
    cookie = ""
    for h in hdrs.get_all("Set-Cookie") or []:
        if h.startswith("lessonwizard_teacher="):
            cookie = h.split(";")[0]
    check("login καθηγητή", st == 200 and bool(cookie))
    st, _, data = http_json("/lesson-wizard/api/lessons", cookie=cookie)
    check("3 ημερήσια μαθήματα πιλότου", st == 200 and len(data.get("lessons", [])) == 3,
          str(len(data.get("lessons", []))))
    st, _, pub = http_json("/lesson-wizard/api/schedule/public")
    check("δημόσιο ωράριο (τμήματα από Excel)", st == 200 and len(pub.get("tmimata", [])) >= 3)

    tn_url = "/docs/mathimata/gymnasio-g/pliroforiki/m02-pyrgoi-anoy/index.teacher.html"
    try:
        with urllib.request.urlopen(BASE + tn_url, timeout=10) as r:
            anon_st = r.status
    except urllib.error.HTTPError as e:
        anon_st = e.code
    check("teacher notes ανώνυμα → 401", anon_st == 401, str(anon_st))
    req = urllib.request.Request(BASE + tn_url)
    req.add_header("Cookie", cookie)
    with urllib.request.urlopen(req, timeout=10) as r:
        check("teacher notes με cookie → 200", r.status == 200)

    if not CHROME:
        print("✗ Δεν βρέθηκε chromium — παράλειψη browser tests")
        return 1 if failed else 0

    print("== Browser checks (headless Chromium) ==")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", f"--remote-debugging-port={PORT}",
         "--window-size=1400,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
        page = next(t for t in targets if t["type"] == "page")
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.send("Page.enable")
        cdp.send("Network.enable")

        # --- Προβολή ΜΑΘΗΤΗ (χωρίς cookie) ---
        cdp.send("Network.clearBrowserCookies")
        cdp.send("Page.navigate", {"url": LESSON})
        ok = wait_for(cdp, "document.querySelectorAll('.lesson-phase[data-phase]').length === 6")
        check("μαθητής: 6 φάσεις ορατές", bool(ok))
        n_notes = cdp.evaluate("document.body.innerHTML.indexOf('Διδακτικοί στόχοι')")
        check("μαθητής: Καμία σημείωση καθηγητή στο DOM", n_notes == -1)
        badges = cdp.evaluate("document.querySelectorAll('.phase-badge').length")
        check("μαθητής: χωρίς badges φάσεων", badges == 0)
        quiz = wait_for(cdp, "!!document.querySelector('.quiz-box .quiz-question')")
        check("κουίζ χτίστηκε", bool(quiz))
        iframe_ok = wait_for(cdp,
            "(function(){var f=document.querySelector('iframe[src=\"anoy.html\"]');"
            "return f && f.contentDocument && f.contentDocument.querySelectorAll('.pole').length===3;})()")
        check("διαδραστικό Ανόι μέσα σε iframe (3 στύλοι)", bool(iframe_ok))
        present_btn = cdp.evaluate("!!document.querySelector('.present-launch')")
        check("κουμπί 🖥️ Παρουσίαση υπάρχει", bool(present_btn))
        cdp.evaluate("document.querySelector('.present-launch').click()")
        opened = wait_for(cdp, "document.querySelector('.present-overlay.is-open') !== null")
        check("fullscreen παρουσίαση ανοίγει", bool(opened))
        title1 = cdp.evaluate("document.querySelector('.present-title').textContent")
        cdp.evaluate("document.querySelector('.present-next').click()")
        time.sleep(0.3)
        title2 = cdp.evaluate("document.querySelector('.present-title').textContent")
        check("πλοήγηση φάσεων (επόμενη)", title1 != title2, f"{title1} → {title2}")
        no_notes_in_present = cdp.evaluate(
            "document.querySelector('.present-body').innerHTML.indexOf('Σημειώσεις Καθηγητή')")
        check("παρουσίαση: χωρίς σημειώσεις καθηγητή", no_notes_in_present == -1)
        cdp.evaluate("document.querySelector('.present-close').click()")
        # --- Dropdown τμήματος & widget ---
        picker = wait_for(cdp, "!!document.querySelector('.tmima-picker select')")
        check("dropdown «Το τμήμα μου» στο header", bool(picker))
        cdp.evaluate(
            "(function(){var s=document.querySelector('.tmima-picker select');"
            "s.value='Γ1'; s.dispatchEvent(new Event('change'));})()")
        time.sleep(0.5)
        ls = cdp.evaluate("localStorage.getItem('school-tmima')")
        check("επιλογή τμήματος αποθηκεύεται", ls == "Γ1")

        # --- Προβολή ΚΑΘΗΓΗΤΗ (με cookie) ---
        cdp.send("Network.setCookie", {"name": "lessonwizard_teacher",
                                       "value": cookie.split("=", 1)[1],
                                       "domain": "127.0.0.1", "path": "/"})
        cdp.send("Page.navigate", {"url": LESSON})
        teacher_ok = wait_for(cdp, "document.body.classList.contains('is-teacher')")
        check("καθηγητής: αναγνωρίζεται (is-teacher)", bool(teacher_ok))
        notes_visible = wait_for(cdp,
            "(function(){var n=document.querySelector('.teacher-notes');"
            "return n && !n.hidden && n.textContent.indexOf('Διδακτικοί στόχοι')!==-1;})()")
        check("καθηγητής: σημειώσεις ορατές inline", bool(notes_visible))
        badges = wait_for(cdp, "document.querySelectorAll('.phase-badge').length === 6")
        check("καθηγητής: 6 badges φάσεων με χρόνους", bool(badges))
        bar = cdp.evaluate("!!document.querySelector('.lesson-plan-bar')")
        check("καθηγητής: μπάρα σχεδίου μαθήματος + link wizard", bool(bar))

        # --- Αρχική: widget ωραρίου ---
        cdp.send("Page.navigate", {"url": BASE + "/docs/"})
        widget = wait_for(cdp,
            "(function(){var w=document.getElementById('tmata-widget');"
            "return w && !w.hidden && w.textContent.indexOf('Γ1')!==-1;})()")
        check("αρχική: widget «Τώρα στο σχολείο» για Γ1", bool(widget))

        # --- Lesson Wizard UI ---
        cdp.send("Page.navigate", {"url": BASE + "/lesson-wizard/"})
        wiz = wait_for(cdp, "document.body.textContent.indexOf('Ημερήσια μαθήματα') !== -1")
        check("wizard UI: λίστα μαθημάτων (authed μέσω cookie)", bool(wiz))
        cards = wait_for(cdp, "document.querySelectorAll('.grid .bg-white').length >= 3", timeout=15)
        check("wizard: 3 κάρτες μαθημάτων", bool(cards))
    finally:
        if cdp:
            cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print(f"\nΑποτέλεσμα: {passed} ✓ / {failed} ✗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())