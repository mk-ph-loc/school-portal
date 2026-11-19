#!/opt/school-portal/venv/bin/python
"""Έλεγχος των 4 νέων εργαλείων σε ΠΡΑΓΜΑΤΙΚΟ headless Chromium (CDP)."""
import json, sys, time

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE, check, launch_chrome, results, stop_chrome, wait_for

PORT = 9334  # διαφορετική θύρα από το browser-test.py
BASE = "http://127.0.0.1"


class AsyncCDP:
    """Wrapper του κοινού CDP με awaitPromise=True (async bake/fetch expressions)."""

    def __init__(self, cdp):
        self._cdp = cdp

    def send(self, method, params=None):
        return self._cdp.send(method, params)

    def evaluate(self, expr):
        return self._cdp.evaluate(expr, await_promise=True)

    def click(self, x, y):
        self._cdp.click(x, y)

    def close(self):
        self._cdp.close()


try:
    proc, raw_cdp = launch_chrome(PORT, timeout=120)
except RuntimeError as exc:
    print(f"✗ {exc}")
    sys.exit(1)
cdp = AsyncCDP(raw_cdp)
try:
    cdp.send("Page.enable"); cdp.send("Runtime.enable")

    print("\n=== 1. CyberChef (/crypto/) ===")
    cdp.send("Page.navigate", {"url": f"{BASE}/crypto/"})
    got = wait_for(cdp, "!!document.getElementById('operations') || (window.app && app.manager)", timeout=90)
    check("Το CyberChef φορτώνει (UI)", bool(got), str(got)[:80])
    title = cdp.evaluate("document.title")
    check("Τίτλος σελίδας", title == "CyberChef", title)
    baked = wait_for(cdp, """(async () => {
        if (!(window.app && app.appLoaded)) return false;
        if (!app.manager.recipe.getConfig().length) {
            app.manager.recipe.addOperation('To Base64');
            app.manager.input.setInput('Kalimera');
            await new Promise(r=>setTimeout(r,600));
            document.getElementById('bake').click();
        }
        const el = document.getElementById('output-text');
        return el && el.textContent.trim().startsWith('S2FsaW1lcmE=');
    })()""", timeout=90)
    check("Πραγματικό bake: 'Kalimera' → S2FsaW1lcmE= (Base64)", bool(baked), str(baked)[:40])

    print("\n=== 2. IT-Tools (/tools/) ===")
    cdp.send("Page.navigate", {"url": f"{BASE}/tools/"})
    got = wait_for(cdp, "document.querySelectorAll('#app a[href^=\"/tools/\"]').length", timeout=60)
    check("SPA home: λίστα εργαλείων με links /tools/", bool(got), f"{got} links")
    clicked = cdp.evaluate("const a=document.querySelector('#app a[href=\"/tools/uuid-generator\"]'); a ? (a.click(),'ok') : false")
    got = wait_for(cdp, "location.pathname==='/tools/uuid-generator' && document.querySelectorAll('input,textarea').length>0", timeout=60)
    check("SPA navigation → /tools/uuid-generator (router + lazy chunks)", bool(got), str(clicked))
    cdp.send("Page.navigate", {"url": f"{BASE}/tools/token-generator"})
    got = wait_for(cdp, "location.pathname==='/tools/token-generator' && document.querySelectorAll('input,textarea').length>0", timeout=60)
    check("Direct deep-link /tools/token-generator (nginx SPA fallback)", bool(got))


    print("\n=== 3. Ψηφιακός Πίνακας Excalidraw (/board/) ===")
    # Το /board/ είναι πλέον το πλήρες static build του Excalidraw (αντικατέστησε
    # τον παλιό custom canvas πίνακα) — έλεγχοι με πραγματικά CDP input events,
    # ίδιο μοτίβο με το board-classroom-test.py.
    INK = ("(()=>{const c=document.querySelector('canvas.static');if(!c)return -1;"
           "const ctx=c.getContext('2d');const img=ctx.getImageData(0,0,c.width,c.height).data;"
           "let n=0;for(let i=0;i<img.length;i+=4){const r=img[i],g=img[i+1],b=img[i+2];"
           "if(img[i+3]>0&&(r<240||g<240||b<240))n++}return n})()")

    def stroke(x, y, steps=14):
        cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                              "button": "left", "buttons": 1, "clickCount": 1, "pointerType": "pen"})
        for i in range(1, steps + 1):
            cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x + i * 18, "y": y + i * 7,
                                                  "button": "left", "buttons": 1, "pointerType": "pen", "force": 0.5})
        cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x + steps * 18, "y": y + steps * 7,
                                              "button": "left", "buttons": 0, "clickCount": 1, "pointerType": "pen"})

    cdp.send("Page.navigate", {"url": f"{BASE}/board/"})
    got = wait_for(cdp, "!!document.querySelector('.excalidraw') && !!document.querySelector('canvas.interactive')", timeout=45)
    check("Το Excalidraw φορτώνει (UI + canvases)", bool(got))
    txt = cdp.evaluate("document.body.innerText.slice(0,300)")
    check("ΔΕΝ εμφανίζεται το μήνυμα «I'm not a pretzel!»", "pretzel" not in str(txt))
    time.sleep(2)
    cdp.click(700, 400)   # focus στον καμβά
    time.sleep(0.3)
    # Πλήκτρο 7 = ελεύθερη σχεδίαση (freedraw)
    cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "7", "code": "Digit7", "windowsVirtualKeyCode": 55})
    cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "7", "code": "Digit7", "windowsVirtualKeyCode": 55})
    time.sleep(0.3)
    stroke(300, 300)
    time.sleep(3)
    ink1 = cdp.evaluate(INK)
    check("Σχεδίαση στον καμβά (ink pixels)", isinstance(ink1, int) and ink1 > 100, f"{ink1} px")
    # Ctrl+Z → αναίρεση
    cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "z", "code": "KeyZ", "windowsVirtualKeyCode": 90, "modifiers": 2})
    cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "z", "code": "KeyZ", "windowsVirtualKeyCode": 90, "modifiers": 2})
    time.sleep(2)
    ink_undo = cdp.evaluate(INK)
    check("Αναίρεση (Ctrl+Z) αδειάζει τον καμβά", ink_undo == 0, f"{ink_undo} px")
    # Νέα πινελιά → επιβιώνει μετά από reload (browser storage του Excalidraw)
    stroke(500, 500, steps=11)
    time.sleep(4)
    before = cdp.evaluate(INK)
    cdp.send("Page.navigate", {"url": f"{BASE}/board/"})
    wait_for(cdp, "!!document.querySelector('canvas.static')", timeout=45)
    time.sleep(4)
    after = cdp.evaluate(INK)
    check("Επαναφορά σχεδίων μετά από reload (browser storage)",
          isinstance(before, int) and before > 100 and after == before, f"{before} → {after} px")

    print("\n=== 4. FileBrowser (/share/) ===")
    cdp.send("Page.navigate", {"url": f"{BASE}/share/"})
    got = wait_for(cdp, "document.querySelector('input[type=password]') && document.body.innerText.length > 50", timeout=40)
    check("Φόρμα login εμφανίζεται", bool(got))
    login = cdp.evaluate(f"""(async () => {{
        const r = await fetch('/share/api/login', {{method:'POST', body: JSON.stringify({{username:'admin', password:{json.dumps(TEACHER_CODE)}}})}});
        return r.status;
    }})()""")
    check("Login admin/κοινός κωδικός μέσω nginx", login == 200, f"HTTP {login}")

    print("\n=== 5. Dashboard — κάρτες εργαλείων ===")
    # Η ενότητα μεγάλωσε μετά την αρχική γραφή του test (pad/circuits/blockly/
    # sql/pdf-tools) — ελέγχουμε ότι ΟΛΑ τα βασικά εργαλεία έχουν κάρτα.
    cdp.send("Page.navigate", {"url": f"{BASE}/"})
    got = wait_for(cdp, "document.getElementById('ergaleia') && document.querySelectorAll('#ergaleia a.card-hover').length", timeout=30)
    check("Ενότητα «Εργαλεία & Εφαρμογές Εργαστηρίου» με κάρτες", isinstance(got, int) and got >= 4, f"{got} κάρτες")
    hrefs = cdp.evaluate("[...document.querySelectorAll('#ergaleia a.card-hover')].map(a=>a.getAttribute('href'))")
    expected = ["/crypto/", "/tools/", "/board/", "/share/"]
    check("Κάρτες για crypto/tools/board/share", all(h in hrefs for h in expected), ",".join(hrefs))

finally:
    cdp.close()
    stop_chrome(proc)

r = results()
print(f"\n{'✅ ΟΛΑ ΠΕΡΑΣΑΝ' if r.failed==0 else '⚠️ ΑΠΟΤΥΧΙΕΣ'}: {r.passed}/{r.passed+r.failed}")
sys.exit(r.exit_code())
