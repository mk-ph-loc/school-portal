#!/opt/school-portal/venv/bin/python
"""Έλεγχος των 4 νέων εργαλείων σε ΠΡΑΓΜΑΤΙΚΟ headless Chromium (CDP)."""
import json, shutil, subprocess, sys, time, urllib.request
import websocket

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE                            # ίδιος κωδικός με τα apps

CHROME = shutil.which("chromium")
PORT = 9334  # διαφορετική θύρα από το browser-test.py
BASE = "http://127.0.0.1"

class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=120)
        self._id = 0
    def send(self, method, params=None):
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg: raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
    def evaluate(self, expression):
        res = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in res:
            raise RuntimeError(json.dumps(res["exceptionDetails"])[:400])
        return res.get("result", {}).get("value")

def wait_for(cdp, expr, timeout=60, interval=0.5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = cdp.evaluate(expr)
            if last: return last
        except Exception as exc:
            last = str(exc)
        time.sleep(interval)
    return last

passed = failed = 0
def check(label, ok, detail=""):
    global passed, failed
    mark = "\033[0;32m✓\033[0m" if ok else "\033[0;31m✗\033[0m"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    passed += ok; failed += (not ok)

proc = subprocess.Popen(
    [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
     f"--remote-debugging-port={PORT}", "--window-size=1400,1000", "about:blank"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    targets = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=3) as r:
                targets = json.load(r)
            if targets: break
        except Exception: time.sleep(0.5)
    page = next(t for t in targets if t["type"] == "page")
    cdp = CDP(page["webSocketDebuggerUrl"])
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


    print("\n=== 3. Ψηφιακός Πίνακας (/board/) ===")
    cdp.send("Page.navigate", {"url": f"{BASE}/board/"})
    got = wait_for(cdp, "typeof redraw==='function' && document.getElementById('board').width>0", timeout=30)
    check("Canvas αρχικοποιείται", bool(got))
    n_tools = cdp.evaluate("document.querySelectorAll('.tbtn[data-tool]').length")
    check("7 εργαλεία σχεδίασης", n_tools == 7, f"{n_tools}")
    draw = cdp.evaluate("""(() => {
        const cv=document.getElementById('board'), r=cv.getBoundingClientRect();
        function pe(type,x,y){cv.dispatchEvent(new PointerEvent(type,{pointerId:1,pointerType:'mouse',button:0,clientX:r.left+x,clientY:r.top+y,bubbles:true}));}
        setTool('pen'); pe('pointerdown',50,50); pe('pointermove',120,90); pe('pointermove',200,140); pe('pointerup',200,140);
        setTool('arrow'); pe('pointerdown',60,200); pe('pointermove',260,240); pe('pointerup',260,240);
        setTool('rect'); pe('pointerdown',300,60); pe('pointermove',420,160); pe('pointerup',420,160);
        setTool('text'); pe('pointerdown',80,300); pe('pointerup',80,300);
        const ti=document.getElementById('textInput'); ti.value='Γεια σου τάξη!';
        ti.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
        return shapes.map(s=>s.tool);
    })()""")
    check("Σχεδίαση pen/arrow/rect/text μέσω pointer events", draw == ["pen","arrow","rect","text"], str(draw))
    saved = wait_for(cdp, "JSON.parse(localStorage.getItem('school-board-v1')||'null')?.shapes?.length", timeout=10)
    check("Autosave στο localStorage", saved == 4, f"{saved} αντικείμενα")
    undo_ok = cdp.evaluate("undo(); shapes.length")
    check("Αναίρεση (undo)", undo_ok == 3, f"{undo_ok} αντικείμενα")
    erased = cdp.evaluate("setTool('eraser'); eraseAt({x:120,y:90}); shapes.length")
    check("Σβήστρα (object eraser)", erased == 2, f"{erased} αντικείμενα")
    time.sleep(1.2)  # αναμονή για το debounced autosave πριν το reload
    png = cdp.evaluate("""(() => {
        const out=document.createElement('canvas'); out.width=canvas.width; out.height=canvas.height;
        const c=out.getContext('2d'); c.setTransform(dpr,0,0,dpr,0,0);
        c.fillStyle='#fff'; c.fillRect(0,0,out.width/dpr,out.height/dpr);
        for(const s of shapes) drawShape(c,s);
        return out.toDataURL('image/png').slice(0,22);
    })()""")
    check("Εξαγωγή PNG (data URL)", png == "data:image/png;base64,", str(png))
    cdp.send("Page.navigate", {"url": f"{BASE}/board/"})
    restored = wait_for(cdp, "typeof shapes!=='undefined' && shapes.length===2", timeout=20)
    check("Επαναφορά σχεδίων μετά από reload", bool(restored))
    vh = cdp.evaluate("Math.abs(document.body.getBoundingClientRect().height - window.innerHeight) < 2")
    check("Πλήρης οθόνη 100vh", bool(vh))

    print("\n=== 4. FileBrowser (/share/) ===")
    cdp.send("Page.navigate", {"url": f"{BASE}/share/"})
    got = wait_for(cdp, "document.querySelector('input[type=password]') && document.body.innerText.length > 50", timeout=40)
    check("Φόρμα login εμφανίζεται", bool(got))
    login = cdp.evaluate(f"""(async () => {{
        const r = await fetch('/share/api/login', {{method:'POST', body: JSON.stringify({{username:'admin', password:{json.dumps(TEACHER_CODE)}}})}});
        return r.status;
    }})()""")
    check("Login admin/κοινός κωδικός μέσω nginx", login == 200, f"HTTP {login}")

    print("\n=== 5. Dashboard — 4 νέες κάρτες ===")
    cdp.send("Page.navigate", {"url": f"{BASE}/"})
    got = wait_for(cdp, "document.getElementById('ergaleia') && document.querySelectorAll('#ergaleia a.card-hover').length", timeout=30)
    check("Ενότητα «Εργαλεία & Εφαρμογές Εργαστηρίου» με 4 κάρτες", got == 4, f"{got} κάρτες")
    hrefs = cdp.evaluate("[...document.querySelectorAll('#ergaleia a.card-hover')].map(a=>a.getAttribute('href')).join(',')")
    check("Σωστά links καρτών", hrefs == "/crypto/,/tools/,/board/,/share/", hrefs)

finally:
    proc.terminate()
    try: proc.wait(timeout=10)
    except Exception: proc.kill()

print(f"\n{'✅ ΟΛΑ ΠΕΡΑΣΑΝ' if failed==0 else '⚠️ ΑΠΟΤΥΧΙΕΣ'}: {passed}/{passed+failed}")
sys.exit(1 if failed else 0)
