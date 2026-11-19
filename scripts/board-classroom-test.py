#!/opt/school-portal/venv/bin/python
"""board-classroom-test.py — Ο Ψηφιακός Πίνακας μέσα στη Ζωντανή Τάξη.

Πραγματικός headless Chromium (CDP, ίδιο μοτίβο με το classroom-browser-test.py):
είσοδος καθηγητή, άνοιγμα /board/ από το μενού σε iframe, ζωντανή συνεργασία
(Start session), σχεδίαση στον καμβά και 2ος χρήστης (guest) που βλέπει τις
πινελιές του καθηγητή ζωντανά μέσω του self-hosted excalidraw-room (/board-ws/).

Εκτέλεση (στο live bundle):
    /opt/school-portal/venv/bin/python scripts/board-classroom-test.py
Προαιρετικά --patched <αρχείο.js>: σερβίρει δοκιμαστικό bundle μέσω CDP
interception χωρίς να πειράξει τα αρχεία του server (για επαλήθευση patch).
"""
import base64
import json
import pathlib
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request

import websocket

CHROME = shutil.which("chromium") or shutil.which("chromium-browser")
PORT = 9381
BASE = "https://127.0.0.1"

PATCHED_FILE = None
B64 = None
MAIN_BUNDLE_NAME = None
if "--patched" in sys.argv:
    PATCHED_FILE = pathlib.Path(sys.argv[sys.argv.index("--patched") + 1])
    B64 = base64.b64encode(PATCHED_FILE.read_bytes()).decode()
    # Βρες το όνομα του κύριου bundle από το live index.html
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(f"{BASE}/board/", context=ctx, timeout=10) as r:
        html = r.read().decode()
    m = re.search(r'assets/(index-[A-Za-z0-9_-]+\.js)', html)
    MAIN_BUNDLE_NAME = m.group(1) if m else None
    if not MAIN_BUNDLE_NAME:
        print('✗ Δεν βρέθηκε το κύριο bundle στο /board/ index.html')
        sys.exit(1)

PASSED = FAILED = 0


def check(label, ok, detail=""):
    global PASSED, FAILED
    print(("  ✓ " if ok else "  ✗ ") + label + (f" — {detail}" if detail else ""))
    if ok:
        PASSED += 1
    else:
        FAILED += 1


def intercept(ws, msg_id, params):
    """Σερβίρει το δοκιμαστικό bundle αντί του live (μόνο με --patched)."""
    if MAIN_BUNDLE_NAME and MAIN_BUNDLE_NAME in params['request']['url']:
        ws.send(json.dumps({"id": msg_id, "method": "Fetch.fulfillRequest", "params": {
            "requestId": params["requestId"], "responseCode": 200,
            "responseHeaders": [{"name": "Content-Type", "value": "application/javascript"}],
            "body": B64}}))
    else:
        ws.send(json.dumps({"id": msg_id, "method": "Fetch.continueRequest",
                            "params": {"requestId": params["requestId"]}}))


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=120)
        self._id = 0

    def send(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if PATCHED_FILE and m.get("method") == "Fetch.requestPaused":
                intercept(self.ws, 999999, m["params"])
                continue
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def ev(self, expression):
        r = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return r.get("result", {}).get("value")

    def click(self, x, y):
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for(cdp, expr, timeout=30, interval=0.5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = cdp.ev(expr)
            if last:
                return last
        except Exception as exc:
            last = str(exc)
        time.sleep(interval)
    return last


A = "document.querySelector('body')._x_dataStack[0]"
FRAME_OK = "(()=>{try{return !!document.getElementById('app-frame').contentDocument.querySelector('.excalidraw')}catch(e){return false}})()"


def frame_pos(cdp, selector):
    """Απόλυτες συντεταγμένες στοιχείου μέσα στο app-frame (για CDP Input)."""
    return cdp.ev(
        "(()=>{const f=document.getElementById('app-frame');const r=f.getBoundingClientRect();"
        f"const b=f.contentDocument.querySelector('{selector}');if(!b)return null;"
        "const br=b.getBoundingClientRect();return [r.left+br.left+br.width/2, r.top+br.top+br.height/2]})()")


def main():
    if not CHROME:
        print("✗ Δεν βρέθηκε chromium")
        return 1
    profile_dir = f"/tmp/chrome-board-test-{PORT}-{int(time.time())}"
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
         "--ignore-certificate-errors", f"--remote-debugging-port={PORT}",
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
        teacher = CDP(page["webSocketDebuggerUrl"])
        cdps.append(teacher)
        teacher.send("Page.enable"); teacher.send("Runtime.enable")
        if PATCHED_FILE:
            teacher.send("Fetch.enable", {"patterns": [{"urlPattern": f"*{MAIN_BUNDLE_NAME}*"}]})

        print("\n=== 1. Είσοδος καθηγητή & άνοιγμα πίνακα από το μενού ===")
        teacher.send("Page.navigate", {"url": f"{BASE}/classroom/"})
        ok = wait_for(teacher, f"!!({A}) && !!window.Alpine", timeout=30)
        check("Το shell της Ζωντανής Τάξης φορτώνει", bool(ok))
        teacher.ev(f"(()=>{{const a={A};a.joinRole='teacher';a.joinCode='teacher2026';a.joinName='Δοκιμή Πίνακα';a.join();return true}})()")
        role = wait_for(teacher, f"{A}.role==='teacher'", timeout=15)
        check("Είσοδος καθηγητή", bool(role))
        opened = teacher.ev(f"(()=>{{const a={A};const m=a.menu.find(x=>x.url==='/board/');if(m)a.openMenu(m);return !!m}})()")
        if opened:
            check("Το /board/ υπάρχει στο μενού & ανοίγει", True)
        else:
            # Το μενού είναι διαμορφώσιμο ανά σχολείο (Excel) — αν λείπει η καταχώριση,
            # ανοίγουμε τον πίνακα απευθείας στο ίδιο iframe (ίδια λειτουργία).
            teacher.ev(f"(()=>{{const a={A};a.navigateTo('/board/','🖍️ Πίνακας');return true}})()")
            check("Άνοιγμα /board/ στο iframe (εκτός μενού — προσαρμοσμένο Excel)", True)
        has = wait_for(teacher, FRAME_OK, timeout=45)
        check("Ο πίνακας Excalidraw φαίνεται μέσα στο iframe", bool(has))
        txt = teacher.ev("(()=>{try{return document.getElementById('app-frame').contentDocument.body.innerText.slice(0,200)}catch(e){return ''}})()")
        check("ΔΕΝ εμφανίζεται το μήνυμα «I'm not a pretzel!»", "pretzel" not in str(txt))
        collab = wait_for(teacher, "(()=>{try{return !!document.getElementById('app-frame').contentDocument.querySelector('.collab-button')}catch(e){return false}})()", timeout=15)
        check("Κουμπί ζωντανής συνεργασίας ορατό στο iframe", bool(collab))

        print("\n=== 2. Ζωντανή συνεργασία: Start session μέσα από την τάξη ===")
        time.sleep(2)
        cb = frame_pos(teacher, ".collab-button")
        check("Κουμπί Share (πάνω-δεξιά) στον πίνακα", bool(cb))
        link = None
        if cb:
            teacher.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": cb[0], "y": cb[1], "button": "left", "clickCount": 1})
            teacher.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": cb[0], "y": cb[1], "button": "left", "clickCount": 1})
            time.sleep(1.5)
            sb = teacher.ev(
                "(()=>{const f=document.getElementById('app-frame');const r=f.getBoundingClientRect();"
                "const d=f.contentDocument;const b=[...d.querySelectorAll('.Dialog button')]"
                ".find(x=>/Start session/.test(x.textContent));if(!b)return null;"
                "const br=b.getBoundingClientRect();return [r.left+br.left+br.width/2, r.top+br.top+br.height/2]})()")
            check("Κουμπί Start session στο dialog", bool(sb))
            if sb:
                teacher.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": sb[0], "y": sb[1], "button": "left", "clickCount": 1})
                teacher.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": sb[0], "y": sb[1], "button": "left", "clickCount": 1})
                for _ in range(30):
                    time.sleep(0.5)
                    link = teacher.ev(
                        "(()=>{const d=document.getElementById('app-frame').contentDocument;"
                        "const inp=[...d.querySelectorAll('.Dialog input')].find(i=>String(i.value).includes('#room='));"
                        "return inp?String(inp.value):null})()")
                    if link:
                        break
        check("Δημιουργία room link (HTTPS) μέσα από την τάξη", bool(link), str(link)[:80])

        print("\n=== 3. Σχεδίαση στον καμβά μέσα στο iframe ===")
        # Κλείσε το collab dialog με click στο overlay (έξω από το modal)
        ov = teacher.ev(
            "(()=>{const f=document.getElementById('app-frame');const r=f.getBoundingClientRect();"
            "const d=f.contentDocument;const o=d.querySelector('.Modal__background, .Overlay, .Modal');"
            "if(!o)return null;return [r.left+15, r.top+15]})()")
        if ov:
            teacher.click(ov[0], ov[1])
            time.sleep(0.8)
        rect = teacher.ev("(()=>{const f=document.getElementById('app-frame');const r=f.getBoundingClientRect();return [r.left,r.top]})()")
        fx, fy = rect
        teacher.ev("document.getElementById('app-frame').contentWindow.focus()")
        teacher.click(fx + 600, fy + 400)
        time.sleep(0.3)
        teacher.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "7", "code": "Digit7", "windowsVirtualKeyCode": 55})
        teacher.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "7", "code": "Digit7", "windowsVirtualKeyCode": 55})
        time.sleep(0.3)
        teacher.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": fx + 300, "y": fy + 300, "button": "left", "clickCount": 1, "pointerType": "pen"})
        for i in range(1, 15):
            teacher.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": fx + 300 + i * 18, "y": fy + 300 + i * 7, "button": "left", "buttons": 1, "pointerType": "pen", "force": 0.5})
        teacher.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": fx + 552, "y": fy + 398, "button": "left", "clickCount": 1, "pointerType": "pen"})
        time.sleep(4)
        t_ink = teacher.ev(
            "(()=>{try{const d=document.getElementById('app-frame').contentDocument;"
            "const c=d.querySelector('canvas.static');const ctx=c.getContext('2d');"
            "const img=ctx.getImageData(0,0,c.width,c.height).data;let n=0;"
            "for(let i=0;i<img.length;i+=4){const r=img[i],g=img[i+1],b=img[i+2],a=img[i+3];"
            "if(a>0&&(r<240||g<240||b<240))n++}return n}catch(e){return 'ERR:'+e}})()")
        check("Σχεδίαση στον καμβά μέσα στο iframe (ink pixels)",
              isinstance(t_ink, int) and t_ink > 100, f"{t_ink} px")

        print("\n=== 4. Guest μπαίνει στο room & βλέπει τις πινελιές ζωντανά ===")
        if link:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{BASE}/classroom/", method="PUT")
            with urllib.request.urlopen(req, timeout=10) as r:
                t2 = json.load(r)
            guest = CDP(t2["webSocketDebuggerUrl"])
            cdps.append(guest)
            guest.send("Page.enable"); guest.send("Runtime.enable")
            if PATCHED_FILE:
                guest.send("Fetch.enable", {"patterns": [{"urlPattern": f"*{MAIN_BUNDLE_NAME}*"}]})
            wait_for(guest, f"!!({A}) && !!window.Alpine", timeout=30)
            guest.ev(f"(()=>{{const a={A};a.joinRole='guest';a.join();return true}})()")
            time.sleep(3)
            room_path = link.split("127.0.0.1", 1)[1]
            guest.ev(f"(()=>{{const a={A};a.navigateTo('{room_path}','Πίνακας — ζωντανή συνεργασία');return true}})()")
            wait_for(guest, FRAME_OK, timeout=45)
            # Ο καθηγητής σχεδιάζει κι άλλο → ζωντανή αναμετάδοση στον guest
            time.sleep(2)
            teacher.ev("document.getElementById('app-frame').contentWindow.focus()")
            teacher.click(fx + 600, fy + 400)
            time.sleep(0.3)
            teacher.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "7", "code": "Digit7", "windowsVirtualKeyCode": 55})
            teacher.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "7", "code": "Digit7", "windowsVirtualKeyCode": 55})
            time.sleep(0.3)
            teacher.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": fx + 700, "y": fy + 250, "button": "left", "clickCount": 1, "pointerType": "pen"})
            for i in range(1, 12):
                teacher.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": fx + 700 + i * 14, "y": fy + 250 + i * 9, "button": "left", "buttons": 1, "pointerType": "pen", "force": 0.5})
            teacher.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": fx + 854, "y": fy + 349, "button": "left", "clickCount": 1, "pointerType": "pen"})
            badge_t = wait_for(teacher, "(()=>{try{const el=document.getElementById('app-frame').contentDocument.querySelector('.CollabButton-collaborators');return el?el.textContent:null}catch(e){return null}})()", timeout=20)
            check("Ο καθηγητής βλέπει 2 συνεργάτες", str(badge_t) == "2", str(badge_t))
            badge_g = wait_for(guest, "(()=>{try{const el=document.getElementById('app-frame').contentDocument.querySelector('.CollabButton-collaborators');return el?el.textContent:null}catch(e){return null}})()", timeout=20)
            check("Ο guest βλέπει 2 συνεργάτες", str(badge_g) == "2", str(badge_g))
            time.sleep(3)
            g_ink = guest.ev(
                "(()=>{try{const d=document.getElementById('app-frame').contentDocument;"
                "const c=d.querySelector('canvas.static');const ctx=c.getContext('2d');"
                "const img=ctx.getImageData(0,0,c.width,c.height).data;let n=0;"
                "for(let i=0;i<img.length;i+=4){const r=img[i],g=img[i+1],b=img[i+2],a=img[i+3];"
                "if(a>0&&(r<240||g<240||b<240))n++}return n}catch(e){return 'ERR:'+e}})()")
            check("Ο guest βλέπει τις πινελιές του καθηγητή (canvas ink)",
                  isinstance(g_ink, int) and g_ink > 100, f"{g_ink} px")

        print(f"\n{'✓ ΟΛΟΙ οι έλεγχοι πέρασαν — ο πίνακας δουλεύει στη Ζωντανή Τάξη!' if not FAILED else '✗ ΑΠΟΤΥΧΙΑ'} ({PASSED} ✓ / {FAILED} ✗)")
        return 1 if FAILED else 0
    finally:
        for c in cdps:
            c.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
