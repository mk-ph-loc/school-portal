#!/opt/school-portal/venv/bin/python
"""
classroom-browser-test.py — Έλεγχος της Ζωντανής Τάξης σε ΠΡΑΓΜΑΤΙΚΟ browser.

Headless Chromium (CDP, ίδιο μοτίβο με το browser-test.py): είσοδος guest με
παιχνιδιάρικο όνομα, μόνιμο μενού ανά ρόλο, άνοιγμα εφαρμογής σε iframe μέσα
στο κεντρικό παράθυρο, dock⇄float εργαλειοθήκες, είσοδος καθηγητή & αποστολή
ανακοίνωσης που εμφανίζεται ζωντανά στον guest. Εκτέλεση:
    /opt/school-portal/venv/bin/python scripts/classroom-browser-test.py
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
PORT = 9345
BASE = "http://127.0.0.1"


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=60)
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


def wait_for(cdp: CDP, expr: str, timeout: float = 30, interval: float = 0.4):
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


PASSED = FAILED = 0


def check(label, ok, detail=""):
    global PASSED, FAILED
    print(("  ✓ " if ok else "  ✗ ") + label + (f" — {detail}" if detail else ""))
    if ok:
        PASSED += 1
    else:
        FAILED += 1


def alpine(cdp):
    """Πρόσβαση στο Alpine component του shell."""
    return "document.querySelector('body')._x_dataStack[0]"



def main() -> int:
    if not CHROME:
        print("✗ Δεν βρέθηκε chromium")
        return 1
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", f"--remote-debugging-port={PORT}",
         "--window-size=1400,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cdps = []
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
        guest = CDP(page["webSocketDebuggerUrl"])
        cdps.append(guest)
        guest.send("Page.enable"); guest.send("Runtime.enable")

        print("\n=== 1. Είσοδος guest & παιχνιδιάρικο όνομα ===")
        guest.send("Page.navigate", {"url": f"{BASE}/classroom/"})
        ok = wait_for(guest, f"!!({alpine(guest)}) && !!window.Alpine", timeout=30)
        check("Το shell φορτώνει (Alpine)", bool(ok))
        guest.evaluate(f"{alpine(guest)}.joinRole='guest'; {alpine(guest)}.join()")
        ident = wait_for(guest, f"{alpine(guest)}.identity && {alpine(guest)}.identity.name", timeout=15)
        check("Guest όνομα τύπου Google Docs", bool(ident and " " in str(ident)), str(ident))
        ok = wait_for(guest, f"{alpine(guest)}.wsOk === true", timeout=15)
        check("WebSocket συνδέθηκε (heartbeat)", bool(ok))
        menu = guest.evaluate(f"{alpine(guest)}.menu.map(m=>m.id)")
        check("Μενού guest: χωρίς Forum", "forum" not in menu and "mathimata" in menu, str(menu))

        print("\n=== 2. Εφαρμογή σε iframe ΜΕ μόνιμο μενού ===")
        guest.evaluate(f"{alpine(guest)}.openMenu({alpine(guest)}.menu.find(m=>m.url==='/docs/'))")
        ok = wait_for(guest, "document.getElementById('app-frame') && document.getElementById('app-frame').src.includes('/docs/')")
        check("Το /docs/ ανοίγει σε iframe", bool(ok))
        header_visible = guest.evaluate(
            "(()=>{const h=document.querySelector('header');const r=h.getBoundingClientRect();"
            "return r.height>0 && getComputedStyle(h).display!=='none'})()")
        check("Το κεντρικό μενού παραμένει ορατό", bool(header_visible))
        loaded = wait_for(guest,
            "(()=>{try{const d=document.getElementById('app-frame').contentDocument;"
            "return d && d.readyState==='complete' && d.body && d.body.innerHTML.length>500}catch(e){return false}})()",
            timeout=30)
        check("Το iframe φορτώνει πραγματικό περιεχόμενο (same-origin)", bool(loaded))

        print("\n=== 3. Εργαλειοθήκες dock ⇄ float ===")
        try:  # καθαρισμός τυχόν αποθηκευμένων θέσεων από προηγούμενη εκτέλεση
            guest.evaluate("localStorage.removeItem('classroom.panels')")
            guest.evaluate(f"{alpine(guest)}.loadConfig()")
            time.sleep(1.0)
        except Exception:
            pass
        panels = guest.evaluate(f"{alpine(guest)}.panels.map(p=>({{id:p.id,mode:p.mode}}))")
        check("Ο guest έχει εργαλειοθήκες από το config", len(panels) >= 1, str(panels))
        di = guest.evaluate(f"{alpine(guest)}.panels.findIndex(p=>p.mode==='dock')")
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.toggleMode(a.panels[{di}])}})()")
        time.sleep(0.8)
        mode = guest.evaluate(f"{alpine(guest)}.panels[{di}].mode")
        floated = guest.evaluate("!!document.querySelector('.tb-panel')")
        check("Ξεκούμπωμα → πλωτή εργαλειοθήκη (float)", mode == "float" and floated, mode)
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.panels[{di}].x=300;a.panels[{di}].y=200}})()")
        time.sleep(0.5)
        pos = guest.evaluate(f"(()=>{{const a={alpine(guest)};const el=document.getElementById('float-'+a.panels[{di}].id);if(!el)return null;const r=el.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top)]}})()")
        check("Η πλωτή εργαλειοθήκη τοποθετείται ελεύθερα", pos == [300, 200], str(pos))
        guest.evaluate(f"(()=>{{const a={alpine(guest)};a.toggleMode(a.panels[{di}])}})()")
        time.sleep(0.5)
        check("Ξανακούμπωμα → dock", guest.evaluate(f"{alpine(guest)}.panels[{di}].mode") == "dock")


        print("\n=== 4. Καθηγητής σε 2η καρτέλα: roster & ανακοίνωση ζωντανά ===")
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{BASE}/classroom/", method="PUT")
        with urllib.request.urlopen(req, timeout=10) as r:
            t2 = json.load(r)
        teacher = CDP(t2["webSocketDebuggerUrl"])
        cdps.append(teacher)
        teacher.send("Page.enable"); teacher.send("Runtime.enable")
        wait_for(teacher, f"!!({alpine(teacher)})", timeout=30)
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.joinRole='teacher';a.joinCode='teacher2026';a.joinName='Καθηγητής UI';a.join()}})()")
        ok = wait_for(teacher, f"{alpine(teacher)}.role==='teacher' && {alpine(teacher)}.wsOk", timeout=15)
        check("Είσοδος καθηγητή από το UI", bool(ok))
        roster_ok = wait_for(teacher, f"{alpine(teacher)}.roster.some(c=>c.role==='guest')", timeout=15)
        check("Ο καθηγητής βλέπει τον guest στο roster", bool(roster_ok))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.cmd.text='Καλημέρα από το UI test!';a.cmd.audience='all';a.sendAnnounce('announce')}})()")
        toast = wait_for(guest, f"{alpine(guest)}.toasts.some(t=>t.text.includes('Καλημέρα από το UI test'))", timeout=15)
        check("Ο guest βλέπει την ανακοίνωση ζωντανά (toast)", bool(toast))
        teacher.evaluate(f"(()=>{{const a={alpine(teacher)};a.cmd.timerLabel='UI Timer';a.cmd.timerMin=1;a.cmd.timerVis='public';a.sendTimer()}})()")
        timer_ok = wait_for(guest, f"{alpine(guest)}.activeTimers.some(t=>t.label==='UI Timer')", timeout=15)
        check("Δημόσιος timer εμφανίζεται στον guest", bool(timer_ok))
        countdown = guest.evaluate(f"(()=>{{const a={alpine(guest)};const t=a.activeTimers.find(x=>x.label==='UI Timer');return a.fmtLeft(a.timerLeft(t))}})()")
        check("Αντίστροφη μέτρηση σε μορφή mm:ss", bool(countdown and ":" in str(countdown)), str(countdown))

        print(f"\n{'✓ ΟΛΟΙ οι browser έλεγχοι πέρασαν' if not FAILED else '✗ ΑΠΟΤΥΧΙΑ'} ({PASSED} ✓ / {FAILED} ✗)")
        return 1 if FAILED else 0
    finally:
        for c in cdps:
            c.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
