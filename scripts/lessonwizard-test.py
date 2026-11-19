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

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE                            # ίδιος κωδικός με τα apps

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
    st, hdrs, _ = http_json("/lesson-wizard/api/login", {"code": TEACHER_CODE})
    cookie = ""
    for h in hdrs.get_all("Set-Cookie") or []:
        if h.startswith("lessonwizard_teacher="):
            cookie = h.split(";")[0]
    check("login καθηγητή", st == 200 and bool(cookie))
    st, _, data = http_json("/lesson-wizard/api/lessons", cookie=cookie)
    lessons = data.get("lessons", [])
    check("≥3 ημερήσια μαθήματα πιλότου", st == 200 and len(lessons) >= 3, str(len(lessons)))
    check("lessons: πεδία tags/favorite", all("tags" in l and "favorite" in l for l in lessons))
    st, _, pub = http_json("/lesson-wizard/api/schedule/public")
    check("δημόσιο ωράριο (τμήματα από Excel)", st == 200 and len(pub.get("tmimata", [])) >= 3)
    check("public API: πεδίο broadcast", "broadcast" in pub)

    # --- Νέα APIs: meta (tags/fav), πλέγμα ωραρίου, fs, books ---
    key = "gymnasio-g/pliroforiki/m01-anadromi-aformisi-spiral"
    st, _, m = http_json(f"/lesson-wizard/api/meta/{key}",
                         {"tags": ["test-tag"], "favorite": True}, cookie=cookie)
    check("api/meta: tags & favorite", st == 200 and m.get("favorite") is True
          and "test-tag" in m.get("tags", []))
    st, _, cell = http_json("/lesson-wizard/api/schedule/cell",
                            {"tmima": "Γ1", "day": "Δευτέρα", "period": "1",
                             "title": "TEST", "url": "/docs/"}, cookie=cookie)
    ok_cell = st == 200 and cell["schedule"]["timetable"]["Γ1"]["Δευτέρα"]["1"]["title"] == "TEST"
    check("api/schedule/cell: εγγραφή κελιού", ok_cell)
    st, _, mv = http_json("/lesson-wizard/api/schedule/move",
                          {"from": {"tmima": "Γ1", "day": "Δευτέρα", "period": "1"},
                           "to": {"tmima": "Γ1", "day": "Τρίτη", "period": "1"}}, cookie=cookie)
    tt = mv.get("schedule", {}).get("timetable", {}).get("Γ1", {})
    check("api/schedule/move: drag&drop μετακίνηση",
          st == 200 and "1" not in tt.get("Δευτέρα", {}) and tt.get("Τρίτη", {}).get("1", {}).get("title") == "TEST")
    st, _, _ = http_json("/lesson-wizard/api/schedule/cell",
                         {"tmima": "Γ1", "day": "Τρίτη", "period": "1", "clear": True}, cookie=cookie)
    check("api/schedule/cell: καθαρισμός", st == 200)
    st, _, bad = http_json("/lesson-wizard/api/schedule/cell",
                           {"tmima": "XXX", "day": "Δευτέρα", "period": "1", "title": "X"}, cookie=cookie)
    check("api/schedule/cell: άγνωστο τμήμα → 400", st == 400)
    st, _, bc = http_json("/lesson-wizard/api/broadcast",
                          {"title": "TEST BC", "url": "/docs/", "minutes": 5}, cookie=cookie)
    check("api/broadcast: έναρξη", st == 200 and bc.get("broadcast", {}).get("title") == "TEST BC")
    st, _, pub2 = http_json("/lesson-wizard/api/schedule/public")
    check("broadcast ορατό στους μαθητές", (pub2.get("broadcast") or {}).get("title") == "TEST BC")
    st, _, _ = http_json("/lesson-wizard/api/broadcast", {"clear": True}, cookie=cookie)
    check("api/broadcast: διακοπή", st == 200)
    st, _, fs = http_json("/lesson-wizard/api/fs/list?path=mathimata/gymnasio-g/pliroforiki/m02-pyrgoi-anoy",
                          cookie=cookie)
    check("api/fs/list: φάκελος μαθήματος + lesson_key",
          st == 200 and fs.get("lesson_key") == "gymnasio-g/pliroforiki/m02-pyrgoi-anoy"
          and any(f["name"] == "index.md" for f in fs.get("files", [])))
    st, _, _ = http_json("/lesson-wizard/api/fs/list?path=/etc", cookie=cookie)
    check("api/fs: απόλυτη διαδρομή εκτός docs → 400", st == 400)
    st, _, bks = http_json("/lesson-wizard/api/books", cookie=cookie)
    check("api/books: λίστα βιβλίων", st == 200 and isinstance(bks.get("books"), list))

    # --- lesson-edit.js: το νέο script σερβίρεται στα static assets ---
    try:
        with urllib.request.urlopen(BASE + "/docs/assets/javascripts/lesson-edit.js", timeout=10) as r:
            le_src = r.read().decode("utf-8", errors="ignore")
        check("lesson-edit.js διαθέσιμο στο /docs/assets/", r.status == 200 and "lesson-edit-fab" in le_src)
    except Exception as exc:
        check("lesson-edit.js διαθέσιμο στο /docs/assets/", False, str(exc))

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

        # --- ✏️ lesson-edit FAB (μόνο καθηγητής) & γρήγορη επεξεργασία ---
        fab = wait_for(cdp, "!!document.getElementById('lesson-edit-fab')", timeout=15)
        check("καθηγητής: FAB ✏️ επεξεργασίας στη σελίδα μαθήματος", bool(fab))
        if fab:
            # Το Material instant navigation μπορεί να ξαναχτίσει το FAB λίγο
            # μετά την εμφάνιση — περιμένουμε να σταθεροποιηθεί πριν το click.
            time.sleep(1.5)
            cdp.evaluate("document.getElementById('lesson-edit-fab').click()")
            menu_open = wait_for(cdp, "document.getElementById('lesson-edit-menu').classList.contains('open')")
            visual_link = wait_for(cdp,
                "(function(){var a=document.querySelector('#lesson-edit-menu a');"
                "return a ? a.getAttribute('href') : null;})()", timeout=10)
            check("μενού ✏️: link προς wizard #edit=<lesson>",
                  bool(menu_open) and visual_link == "/lesson-wizard/#edit=gymnasio-g/pliroforiki/m02-pyrgoi-anoy",
                  str(visual_link))
            cdp.evaluate("[...document.querySelectorAll('#lesson-edit-menu button')].find(b=>b.textContent.includes('Γρήγορη')).click()")
            loaded_md = wait_for(cdp,
                "(function(){var t=document.getElementById('lesson-edit-textarea');"
                "return t && t.value.indexOf('<!-- phase:')!==-1;})()", timeout=15)
            check("γρήγορη επεξεργασία: φορτώνει το raw markdown του μαθήματος", bool(loaded_md))
            cdp.evaluate("document.getElementById('lesson-edit-close').click()")

        # --- Deep-link #edit ανοίγει τον visual editor του wizard ---
        cdp.send("Page.navigate", {"url": BASE + "/lesson-wizard/#edit=gymnasio-g/pliroforiki/m02-pyrgoi-anoy"})
        deep_ok = wait_for(cdp,
            "(function(){var b=document.body._x_dataStack && document.body._x_dataStack[0];"
            "return b && b.editing === 'gymnasio-g/pliroforiki/m02-pyrgoi-anoy';})()", timeout=20)
        check("wizard deep-link #edit: ανοίγει κατευθείαν το μάθημα", bool(deep_ok))

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
        check("wizard: ≥3 κάρτες μαθημάτων", bool(cards))

        # --- Φίλτρα & αγαπημένα ---
        fav_btn = wait_for(cdp, "(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Αγαπημένα')); if(b){b.click(); return true;} return false;})()")
        time.sleep(0.4)
        only_favs = cdp.evaluate("(function(){var cards=[...document.querySelectorAll('.grid > div')].filter(d=>d.className.includes('shadow-sm')); return cards.length>=1 && cards.every(d=>d.className.includes('ring-amber'));})()")
        check("φίλτρο ⭐ Αγαπημένα: μόνο αγαπημένες κάρτες", bool(fav_btn) and bool(only_favs))
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='καθαρισμός'); if(b)b.click();})()")
        time.sleep(0.3)
        tag_filter = cdp.evaluate("(function(){var s=[...document.querySelectorAll('select')].find(x=>x.innerHTML.includes('tags')); return !!s;})()")
        check("μπάρα φίλτρων με dropdown tags", bool(tag_filter))

        # --- Πλέγμα ωραρίου ---
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('nav button')].find(x=>x.textContent.includes('Ωράριο')); b.click();})()")
        grid = wait_for(cdp, "document.querySelectorAll('.sched-grid tbody tr').length === 5 && document.querySelectorAll('.sched-grid thead th').length >= 8")
        check("ωράριο: πλέγμα 5 ημερών × 7 ωρών", bool(grid))
        filled = cdp.evaluate("document.querySelectorAll('.sched-cell.filled').length >= 1")
        check("ωράριο: γεμάτα κελιά με μάθημα", bool(filled))
        # Εικονική ώρα → το σωστό κελί γίνεται 'now'
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Εικονική ώρα')); b.click();})()")
        time.sleep(0.3)
        vnow = wait_for(cdp, "(function(){var sel=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>o.value==='Τετάρτη')&&s.closest('.bg-amber-50')); if(!sel) return false; sel.value='Τετάρτη'; sel.dispatchEvent(new Event('change')); var t=document.querySelector('.bg-amber-50 input[type=time]'); t.value='12:30'; t.dispatchEvent(new Event('input')); var ap=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Εφαρμογή'); ap.click(); return true;})()")
        time.sleep(0.5)
        now_cell = cdp.evaluate("document.querySelectorAll('.sched-cell.now').length === 1")
        badge = cdp.evaluate("document.body.textContent.includes('ΕΙΚΟΝΙΚΗ')")
        check("εικονική ώρα: 1 κελί «τώρα» + badge", bool(vnow) and bool(now_cell) and bool(badge))
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Πραγματική ώρα')); if(b)b.click();})()")
        # Κλικ σε γεμάτο κελί → popover ενεργειών
        pop = wait_for(cdp, "(function(){var c=document.querySelector('.sched-cell.filled'); if(!c) return false; c.click(); return true;})()")
        time.sleep(0.4)
        pop_ok = cdp.evaluate("(function(){var t=document.body.textContent; return t.includes('Επεξεργασία κελιού') && t.includes('Ενεργό τώρα') && t.includes('Μετάδοση');})()")
        check("κελί: popover edit/ενεργό/μετάδοση/μετάβαση", bool(pop) and bool(pop_ok))
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Κλείσιμο'); if(b)b.click();})()")
        # --- Καρτέλα Αρχεία (file browser) ---
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('nav button')].find(x=>x.textContent.includes('Αρχεία')); b.click();})()")
        fs_ok = wait_for(cdp, "[...document.querySelectorAll('.divide-y > div')].some(x=>x.textContent.includes('mathimata'))")
        check("file browser: λίστα ρίζας docs/", bool(fs_ok))
        nav_in = wait_for(cdp, "(function(){var d=[...document.querySelectorAll('.divide-y > div')].find(x=>x.textContent.includes('mathimata')); if(!d) return false; d.click(); return true;})()")
        # Μπήκαμε στο mathimata/ → breadcrumb «mathimata» + υποφάκελος gymnasio-g στη λίστα
        crumbs = wait_for(cdp, "(function(){var crumb=[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='mathimata'); var sub=[...document.querySelectorAll('.divide-y > div')].some(x=>x.textContent.includes('gymnasio-g')); return crumb && sub;})()", timeout=10)
        check("file browser: πλοήγηση σε υποφάκελο + breadcrumbs", bool(nav_in) and bool(crumbs))

        # --- Καρτέλα Βιβλία ---
        cdp.evaluate("(function(){var b=[...document.querySelectorAll('nav button')].find(x=>x.textContent.includes('Βιβλία')); b.click();})()")
        books_ok = wait_for(cdp, "document.body.textContent.includes('Βιβλιοθήκη βιβλίων') && document.body.textContent.includes('#page=N')")
        check("βιβλία: καρτέλα με υπόδειξη #page=N", bool(books_ok))

        # --- 🧭 Floating menu (wizard) ---
        fab = wait_for(cdp, "!!document.getElementById('portal-nav-fab')")
        check("floating menu: FAB υπάρχει στο wizard", bool(fab))
        cdp.evaluate("document.getElementById('portal-nav-fab').click()")
        menu_ok = wait_for(cdp, "(function(){var m=document.getElementById('portal-nav-menu'); return m && m.classList.contains('open') && m.textContent.includes('Αρχική Πύλη');})()")
        check("floating menu: ανοίγει με βασικούς προορισμούς", bool(menu_ok))

        # --- 🎪 Σελίδα δυνατοτήτων: MathJax / Mermaid / Slides / GIF ---
        cdp.send("Page.navigate", {"url": BASE + "/docs/paradeigma-dynatotiton/"})
        mj = wait_for(cdp, "document.querySelectorAll('.arithmatex svg, mjx-container').length >= 3", timeout=45)
        check("MathJax: μαθηματικά αποδίδονται (SVG)", bool(mj))
        mm = wait_for(cdp, "document.querySelectorAll('pre.mmd-local[data-processed=true] svg').length >= 8", timeout=60)
        check("Mermaid: ≥8 διαγράμματα αποδίδονται", bool(mm))
        gif = cdp.evaluate("(function(){var i=document.querySelector('img[src*=animation]'); return i && i.complete && i.naturalWidth>0;})()")
        check("GIF animation φορτώνει", bool(gif))
        slides_btn = cdp.evaluate("!!document.querySelector('.slides-launch')")
        check("Reveal slides: κουμπί παρουσίασης", bool(slides_btn))
        cdp.evaluate("document.querySelector('.slides-launch').click()")
        reveal_ok = wait_for(cdp, "(function(){var o=document.querySelector('.slides-overlay'); return o && o.querySelectorAll('.reveal .slides section').length>=4;})()", timeout=30)
        check("Reveal slides: fullscreen με ≥4 διαφάνειες", bool(reveal_ok))
        cdp.evaluate("(function(){var b=document.querySelector('.slides-close'); if(b)b.click();})()")
        chips = cdp.evaluate("document.querySelectorAll('.lesson-chip').length >= 1")
        check("tags chips στη σελίδα (front-matter)", bool(chips))
        fab2 = wait_for(cdp, "!!document.getElementById('portal-nav-fab')")
        check("floating menu: FAB υπάρχει στο /docs/", bool(fab2))

        # --- 📡 Broadcast banner στους μαθητές ---
        http_json("/lesson-wizard/api/broadcast",
                  {"title": "BC TEST", "url": "/docs/", "minutes": 5}, cookie=cookie)
        cdp.send("Network.clearBrowserCookies")
        cdp.send("Page.navigate", {"url": BASE + "/docs/?bctest=1"})
        banner = wait_for(cdp, "(function(){var b=document.getElementById('teacher-broadcast'); return b && b.textContent.includes('BC TEST');})()", timeout=20)
        check("broadcast: banner «Ο καθηγητής προβάλλει» στον μαθητή", bool(banner))
        http_json("/lesson-wizard/api/broadcast", {"clear": True}, cookie=cookie)
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