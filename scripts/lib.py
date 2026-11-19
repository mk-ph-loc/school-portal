"""
scripts/lib.py — Κοινό test harness για τα e2e/browser tests της πύλης (Task 5).

Ενοποιεί το copy-pasted boilerplate των 17 scripts:
  * TEACHER_CODE — ο κωδικός διαβάζεται από την ΙΔΙΑ πηγή με τα apps
    (common.auth: env TEACHER_PASS → data/portal.env → default), ώστε αλλαγή
    κωδικού μέσω install.sh να μην σπάει τα tests.
  * Reporter/check()/finish() — ✓/✗ εκτύπωση + μέτρηση επιτυχιών/αποτυχιών.
  * Client — HTTP με cookiejar ανά «χρήστη» (call/json/multipart/raw/get_url).
  * WSClient / ws_recv — WebSocket με cookies & αναμονή μηνύματος ανά τύπο.
  * CDP / launch_chrome / wait_for — ελάχιστο DevTools Protocol client πάνω σε
    headless Chromium (ίδιο μοτίβο σε όλα τα browser tests).

Χρήση (κάθε script τρέχει αυτόνομα όπως πριν):
    sys.path.insert(0, "/opt/school-portal/scripts")
    from lib import TEACHER_CODE, Client, check, ...
"""
from __future__ import annotations

import http.cookiejar
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, "/opt/school-portal")

from common.auth import TEACHER_CODE  # noqa: E402,F401  (re-export)

PORTAL = "/opt/school-portal"
BASE_URL = "http://127.0.0.1"


# ---------------------------------------------------------------------------
# Καταγραφή αποτελεσμάτων — ίδιο ✓/✗ output με πριν, ένα σημείο μέτρησης
# ---------------------------------------------------------------------------
class Reporter:
    """Μετρητής ελέγχων ενός test run (passed/failed)."""

    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, label, ok, detail=""):
        ok = bool(ok)
        print(("  ✓ " if ok else "  ✗ ") + str(label) + (f" — {detail}" if detail else ""))
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

    def summary(self, ok_msg="✓ ΟΛΟΙ οι έλεγχοι πέρασαν!", fail_msg=None):
        print()
        if self.failed:
            print(fail_msg or f"✗ {self.failed} έλεγχοι ΑΠΕΤΥΧΑΝ ({self.passed} ✓)")
        else:
            print(f"{ok_msg} ({self.passed} ✓)")

    def exit_code(self):
        return 1 if self.failed else 0


_reporter = Reporter()


def check(label, ok, detail=""):
    """Κοινός έλεγχος του τρέχοντος script (module-level reporter)."""
    return _reporter.check(label, ok, detail)


def results():
    """Πρόσβαση στα συγκεντρωτικά (π.χ. results().failed στο τέλος του main)."""
    return _reporter


def finish(ok_msg="✓ ΟΛΟΙ οι έλεγχοι πέρασαν!", fail_msg=None):
    """Τελική σύνοψη + sys.exit(0/1) — κοινό τέλος όλων των scripts."""
    _reporter.summary(ok_msg, fail_msg)
    sys.exit(_reporter.exit_code())


# ---------------------------------------------------------------------------
# HTTP client με cookiejar (ένας ανά προσομοιωμένο χρήστη)
# ---------------------------------------------------------------------------
def multipart_body(fields=None, files=()):
    """Σώμα multipart/form-data. files: iterable (field_name, filename, bytes[, mime]).
    Επιστρέφει (body_bytes, content_type_header)."""
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in (fields or {}).items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for f in files:
        field, fname, data = f[:3]
        mime = f[3] if len(f) > 3 else "application/octet-stream"
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\n"
                  f"Content-Type: {mime}\r\n\r\n".encode())
        buf.write(data)
        buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


class Client:
    """HTTP πελάτης με αυτόματο cookiejar (HMAC cookies καθηγητή/μαθητή).

    base: πρόθεμα URL, π.χ. "http://127.0.0.1/classroom/" — τα paths των call()
    είναι σχετικά ("api/join")· απόλυτα URLs και paths με αρχικό "/" επιτρέπονται
    επίσης (ενώνονται με το origin του base). Τα calls επιστρέφουν
    (status, decoded_json) εκτός από raw()/get_url() που δίνουν bytes/κείμενο.
    """

    def __init__(self, base=BASE_URL + "/", timeout=15):
        self.base = base if base.endswith("/") else base + "/"
        self.timeout = timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def url(self, path):
        if path.startswith(("http://", "https://")):
            return path
        if path.startswith("/"):
            from urllib.parse import urlsplit
            s = urlsplit(self.base)
            return f"{s.scheme}://{s.netloc}{path}"
        return self.base + path

    def _request(self, path, data=None, method=None, ctype=None, timeout=None):
        req = urllib.request.Request(self.url(path), data=data, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as res:
                return res.status, res.read(), res.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def call(self, path, payload=None, method=None, timeout=None):
        """JSON API call → (status, dict). Κενό/μη-JSON σώμα → {}."""
        data = json.dumps(payload).encode() if payload is not None else None
        code, body, _ = self._request(path, data=data, method=method,
                                      ctype="application/json", timeout=timeout)
        try:
            return code, json.loads(body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return code, {}

    def raw(self, path, payload=None, method=None, raw=None,
            ctype="application/json", timeout=None):
        """Call με αυθαίρετο σώμα (bytes) → (status, bytes). Για exports/uploads."""
        data = raw if raw is not None else (
            json.dumps(payload).encode() if payload is not None else None)
        code, body, _ = self._request(path, data=data,
                                      method=method or ("POST" if data is not None else None),
                                      ctype=ctype if data is not None else None, timeout=timeout)
        return code, body

    def json(self, path, payload=None, method=None, raw=None,
             ctype="application/json", timeout=None):
        """Όπως raw() αλλά με JSON decoding → (status, dict)."""
        code, body = self.raw(path, payload, method, raw=raw, ctype=ctype, timeout=timeout)
        try:
            return code, json.loads(body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return code, {}

    def multipart(self, path, fields=None, files=(), timeout=None):
        """POST multipart/form-data → (status, dict)."""
        body, ctype = multipart_body(fields, files)
        code, resp, _ = self._request(path, data=body, method="POST", ctype=ctype,
                                      timeout=timeout or max(self.timeout, 120))
        try:
            return code, json.loads(resp or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return code, {}

    def get_url(self, path, timeout=None):
        """GET σελίδας/αρχείου → (status, text) με decode utf-8 (errors=replace)."""
        code, body, _ = self._request(path, timeout=timeout or max(self.timeout, 30))
        return code, body.decode("utf-8", errors="replace")

    def cookie(self, name):
        return next((c.value for c in self.jar if c.name == name), None)

    def cookie_header(self):
        return "; ".join(f"{c.name}={c.value}" for c in self.jar)


def get_url(url, timeout=30):
    """Ανώνυμο GET απόλυτου URL → (status, text)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# WebSocket helpers (websocket-client, ήδη στο venv)
# ---------------------------------------------------------------------------
def ws_recv(ws, types, timeout=15):
    """Διαβάζει μηνύματα μέχρι να βρει έναν από τους ζητούμενους τύπους."""
    end = time.time() + timeout
    while time.time() < end:
        ws.settimeout(max(0.5, end - time.time()))
        msg = json.loads(ws.recv())
        if msg.get("type") in types:
            return msg
    raise TimeoutError(f"Δεν ελήφθη μήνυμα {types}")


class WSClient(Client):
    """HTTP Client + μία WebSocket σύνδεση με τα ίδια cookies (Ζωντανή Τάξη).

    Τα roster κρατιούνται πάντα ενημερωμένα στο last_roster ώστε να μην χάνονται
    ενημερώσεις όσο περιμένουμε άλλους τύπους μηνυμάτων.
    """

    def __init__(self, base, ws_url, timeout=15):
        super().__init__(base, timeout=timeout)
        self.ws_url = ws_url
        self.ws = None
        self.last_roster = None

    def connect(self):
        from websocket import create_connection
        self.ws = create_connection(self.ws_url, timeout=self.timeout,
                                    header={"Cookie": self.cookie_header()})
        return self.ws

    def send(self, obj):
        self.ws.send(json.dumps(obj))

    def recv(self, types, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            self.ws.settimeout(max(0.5, end - time.time()))
            msg = json.loads(self.ws.recv())
            if msg.get("type") == "roster":
                self.last_roster = msg
            if msg.get("type") in types:
                return msg
        raise TimeoutError(f"Δεν ελήφθη μήνυμα {types}")

    def wait_roster(self, pred, timeout=10):
        """Περιμένει roster που να ικανοποιεί τη συνθήκη (τρέχον ή επόμενο)."""
        if self.last_roster and pred(self.last_roster):
            return self.last_roster
        end = time.time() + timeout
        while time.time() < end:
            msg = self.recv(["roster"], timeout=max(0.5, end - time.time()))
            if pred(msg):
                return msg
        raise TimeoutError("Το roster δεν ικανοποίησε τη συνθήκη")

    def close(self):
        try:
            self.ws and self.ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Headless Chromium μέσω DevTools Protocol (κοινό σε ΟΛΑ τα browser tests)
# ---------------------------------------------------------------------------
CHROME = shutil.which("chromium") or shutil.which("chromium-browser")


class CDP:
    """Ελάχιστο CDP client πάνω από WebSocket.

    on_event: προαιρετικό callback(msg) για κάθε εισερχόμενο μήνυμα που ΔΕΝ
    απαντά στο τρέχον request (π.χ. Fetch.requestPaused για interception).
    """

    def __init__(self, ws_url, timeout=60, on_event=None):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=timeout)
        self._id = 0
        self._on_event = on_event

    def _command(self, method, params=None, session_id=None):
        self._id += 1
        mid = self._id
        msg = {"id": mid, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        self.ws.send(json.dumps(msg))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            if self._on_event:
                self._on_event(m)

    def send(self, method, params=None):
        return self._command(method, params)

    def send_session(self, session_id, method, params=None):
        """Εντολή σε attached target (π.χ. out-of-process iframe)."""
        return self._command(method, params, session_id=session_id)

    def evaluate(self, expression, await_promise=False):
        res = self.send("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(json.dumps(res["exceptionDetails"], ensure_ascii=False)[:400])
        return res.get("result", {}).get("value")

    # Σύντομο alias (συμβατότητα με scripts που έγραφαν cdp.ev)
    ev = evaluate

    def click(self, x, y):
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                               "button": "left", "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                               "button": "left", "clickCount": 1})

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def launch_chrome(port, window="1400,1000", extra_args=(), timeout=60, on_event=None):
    """Ξεκινά headless Chromium & επιστρέφει (proc, cdp) στο πρώτο page target.

    RuntimeError αν λείπει το chromium ή δεν ξεκινήσει το CDP endpoint.
    Το stop_chrome(proc) παραμένει ευθύνη του caller (finally block).
    """
    if not CHROME:
        raise RuntimeError("Δεν βρέθηκε chromium")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--disable-dev-shm-usage", *extra_args, f"--remote-debugging-port={port}",
         f"--window-size={window}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    targets = None
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                targets = json.load(r)
            if targets:
                break
        except Exception:
            time.sleep(0.5)
    if not targets:
        stop_chrome(proc)
        raise RuntimeError("Το Chromium δεν ξεκίνησε")
    page = next((t for t in targets if t["type"] == "page"), targets[0])
    return proc, CDP(page["webSocketDebuggerUrl"], timeout=timeout, on_event=on_event)


def new_tab(port, url, timeout=60, on_event=None):
    """Νέα καρτέλα στο ίδιο Chromium → CDP client (2ος χρήστης σε browser tests)."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        t = json.load(r)
    return CDP(t["webSocketDebuggerUrl"], timeout=timeout, on_event=on_event)


def stop_chrome(proc, timeout=10):
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except Exception:
        proc.kill()


def wait_for(cdp, expr, timeout=30, interval=0.5):
    """Περιμένει μέχρι η JS έκφραση να γίνει truthy· επιστρέφει την τελευταία τιμή."""
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