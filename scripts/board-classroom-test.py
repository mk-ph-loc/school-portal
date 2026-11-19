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
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import (TEACHER_CODE, check, launch_chrome, new_tab, results,
                 stop_chrome, wait_for)

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


def make_interceptor(cdp):
    """on_event για το κοινό CDP: σερβίρει το δοκιμαστικό bundle αντί του live."""
    def on_event(m):
        if m.get("method") != "Fetch.requestPaused":
            return
        params = m["params"]
        if MAIN_BUNDLE_NAME and MAIN_BUNDLE_NAME in params["request"]["url"]:
            cdp.ws.send(json.dumps({"id": 999999, "method": "Fetch.fulfillRequest", "params": {
                "requestId": params["requestId"], "responseCode": 200,
                "responseHeaders": [{"name": "Content-Type", "value": "application/javascript"}],
                "body": B64}}))
        else:
            cdp.ws.send(json.dumps({"id": 999999, "method": "Fetch.continueRequest",
                                    "params": {"requestId": params["requestId"]}}))
    return on_event


def attach_events(cdp):
    """Δένει τον interceptor σε ήδη δημιουργημένο CDP (launch/new_tab)."""
    if PATCHED_FILE:
        cdp._on_event = make_interceptor(cdp)
    return cdp


A = "document.querySelector('body')._x_dataStack[0]"
FRAME_OK = "(()=>{try{return !!document.getElementById('app-frame').contentDocument.querySelector('.excalidraw')}catch(e){return false}})()"


def frame_pos(cdp, selector):
    """Απόλυτες συντεταγμένες στοιχείου μέσα στο app-frame (για CDP Input)."""
    return cdp.ev(
        "(()=>{const f=document.getElementById('app-frame');const r=f.getBoundingClientRect();"
        f"const b=f.contentDocument.querySelector('{selector}');if(!b)return null;"
        "const br=b.getBoundingClientRect();return [r.left+br.left+br.width/2, r.top+br.top+br.height/2]})()")


def main():
    profile_dir = f"/tmp/chrome-board-test-{PORT}-{int(time.time())}"
    try:
        proc, teacher = launch_chrome(PORT, extra_args=["--ignore-certificate-errors"],
                                      timeout=120)
    except RuntimeError as exc:
        print(f"✗ {exc}")
        return 1
    attach_events(teacher)
    cdps = [teacher]
    try:
        teacher.send("Page.enable"); teacher.send("Runtime.enable")
        if PATCHED_FILE:
            teacher.send("Fetch.enable", {"patterns": [{"urlPattern": f"*{MAIN_BUNDLE_NAME}*"}]})

        print("\n=== 1. Είσοδος καθηγητή & άνοιγμα πίνακα από το μενού ===")
        teacher.send("Page.navigate", {"url": f"{BASE}/classroom/"})
        ok = wait_for(teacher, f"!!({A}) && !!window.Alpine", timeout=30)
        check("Το shell της Ζωντανής Τάξης φορτώνει", bool(ok))
        teacher.ev(f"(()=>{{const a={A};a.joinRole='teacher';a.joinCode='{TEACHER_CODE}';a.joinName='Δοκιμή Πίνακα';a.join();return true}})()")
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
            guest = attach_events(new_tab(PORT, f"{BASE}/classroom/", timeout=120))
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

        r = results()
        print(f"\n{'✓ ΟΛΟΙ οι έλεγχοι πέρασαν — ο πίνακας δουλεύει στη Ζωντανή Τάξη!' if not r.failed else '✗ ΑΠΟΤΥΧΙΑ'} ({r.passed} ✓ / {r.failed} ✗)")
        return r.exit_code()
    finally:
        for c in cdps:
            c.close()
        stop_chrome(proc)
        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
