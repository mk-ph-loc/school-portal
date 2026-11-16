#!/opt/school-portal/venv/bin/python
"""
End-to-end έλεγχος του App Builder Wizard (/app-builder/) μέσω Nginx (θύρα 80).

Ελέγχει: προστασία με κωδικό καθηγητή, Quick Paste δημιουργία (με χρήση του
_template), αυτόματη διόρθωση απόλυτων διαδρομών, upload ZIP με ενιαίο root
φάκελο & πολλαπλά αρχεία, αντικατάσταση υπάρχουσας, λίστα/manifest/προεπισκόπηση,
MkDocs embed snippet + άμεση εισαγωγή σε μάθημα, διαγραφή & καθαρισμός.

Χρήση: /opt/school-portal/venv/bin/python scripts/appbuilder-test.py
"""
import io
import json
import sys
import time
import urllib.request
import urllib.error
import http.cookiejar
import uuid
import zipfile
from pathlib import Path

BASE = "http://127.0.0.1/app-builder/"
PORTAL = Path("/opt/school-portal")
FAILED = 0


def check(label, cond, detail=""):
    global FAILED
    print(("  ✓ " if cond else "  ✗ ") + label + (f" — {detail}" if detail else ""))
    if not cond:
        FAILED += 1


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=60) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def multipart(self, path, fields, files=()):
        """files: λίστα (field_name, filename, bytes)."""
        boundary = uuid.uuid4().hex
        buf = io.BytesIO()
        for k, v in fields.items():
            buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for field, fname, data in files:
            buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{fname}\"\r\n"
                      f"Content-Type: application/octet-stream\r\n\r\n".encode())
            buf.write(data)
            buf.write(b"\r\n")
        buf.write(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(BASE + path, data=buf.getvalue(), method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with self.opener.open(req, timeout=120) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


def get_url(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    anon = Client()
    t = Client()

    print("\n=== 1. Προστασία πρόσβασης ===")
    code, _ = anon.call("api/list")
    check("GET /api/list χωρίς login → 401", code == 401, str(code))
    code, body = t.call("api/login", {"password": "wrong"})
    check("Λάθος κωδικός → 401", code == 401, str(code))
    code, body = t.call("api/login", {"password": "teacher2026"})
    check("Σωστός κωδικός → 200 + HMAC cookie", code == 200 and
          any(c.name == "appbuilder_teacher" for c in t.jar))
    code, page = get_url(BASE)
    check("Η σελίδα wizard φορτώνει (200)", code == 200 and "App Builder Wizard" in page)

    print("\n=== 2. Επικύρωση πεδίων ===")
    base_fields = {"title": "Δοκιμή", "mode": "paste", "paste_html": "<p>γεια</p>"}
    code, body = t.multipart("api/create", {**base_fields, "id": "Bad_Name!"})
    check("Μη έγκυρο id → 400", code == 400, str(code))
    code, body = t.multipart("api/create", {**base_fields, "id": "_template"})
    check("id '_template' → 400", code == 400, str(code))
    code, body = t.multipart("api/create", {**base_fields, "id": "ok-id", "title": ""})
    check("Κενός τίτλος → 400", code == 400, str(code))
    code, body = t.multipart("api/create", {**base_fields, "id": "binary-converter"})
    check("Υπάρχον id χωρίς replace → 409", code == 409, str(code))

    print("\n=== 3. Quick Paste δημιουργία (πρότυπο _template) ===")
    fields = {
        "id": "e2e-paste-app", "title": "E2E Παράδειγμα", "description": "δοκιμαστική",
        "category": "Β' Γυμνασίου / Πληροφορική", "icon": "🧪", "access": "all",
        "mode": "paste",
        "paste_html": '<h2 id="hello">Αρχικό</h2>\n<link rel="stylesheet" href="/style.css">\n<img src="/assets/favicon.svg">',
        "paste_css": "h2 { color: teal; }",
        "paste_js": "document.getElementById('hello').textContent = 'Γεια τάξη!';",
    }
    code, body = t.multipart("api/create", fields)
    check("Δημιουργία → 200", code == 200, str(code) + " " + str(body.get("detail", "")))
    app_dir = PORTAL / "custom-apps" / "e2e-paste-app"
    idx = (app_dir / "index.html").read_text(encoding="utf-8")
    check("Χρήση _template (μπάρα επιστροφής)", "← Επιστροφή στο Portal" in idx)
    check("Ο τίτλος αντικατέστησε το placeholder", "E2E Παράδειγμα" in idx and "Τίτλος Εφαρμογής" not in idx)
    check("Το <main> περιεχόμενο μπήκε", 'id="hello"' in idx)
    check("CSS inline στο head", "color: teal" in idx)
    check("JS αποθηκεύτηκε ως ./app.js", (app_dir / "app.js").is_file() and 'src="./app.js"' in idx)
    check("Απόλυτο /style.css → ./style.css", 'href="./style.css"' in idx and 'href="/style.css"' not in idx)
    check("Κοινόχρηστο /assets/… έμεινε ανέπαφο", 'src="/assets/favicon.svg"' in idx)
    check("Προειδοποίηση διορθώσεων επέστρεψε", any("Διορθώθηκαν" in w for w in body.get("warnings", [])))
    meta = json.loads((app_dir / "app.json").read_text(encoding="utf-8"))
    check("app.json σωστό", meta["id"] == "e2e-paste-app" and meta["icon"] == "🧪" and meta["access"] == "all")
    st = app_dir.stat()
    check("Δικαιώματα φακέλου 755", oct(st.st_mode)[-3:] == "755", oct(st.st_mode)[-3:])
    check("Δικαιώματα αρχείου 644", oct((app_dir / "index.html").stat().st_mode)[-3:] == "644")
    code, manifest = get_url("http://127.0.0.1/apps/apps-manifest.json")
    check("Manifest ενημερώθηκε αυτόματα", code == 200 and "e2e-paste-app" in manifest)
    code, html = get_url("http://127.0.0.1/apps/e2e-paste-app/")
    check("Η εφαρμογή ανοίγει στο /apps/… (200)", code == 200)
    check("Embed snippet παράγεται", 'src="/apps/e2e-paste-app/"' in body.get("embed", "") and "custom-app-embed" in body.get("embed", ""))

    print("\n=== 4. Upload ZIP με ενιαίο root φάκελο ===")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("my-zip-root/index.html",
                   '<!DOCTYPE html><html lang="el"><head><meta charset="utf-8"><title>ZIP</title>'
                   '<script src="/app.js"></script></head><body><h1>ZIP εφαρμογή</h1></body></html>')
        z.writestr("my-zip-root/app.js", "console.log('zip ok');")
        z.writestr("my-zip-root/assets/pic.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>")
        z.writestr("__MACOSX/._junk", "junk")
    code, body = t.multipart("api/create", {
        "id": "e2e-zip-app", "title": "E2E ZIP", "mode": "upload", "access": "teachers",
    }, files=[("files", "app.zip", zbuf.getvalue())])
    check("ZIP δημιουργία → 200", code == 200, str(code) + " " + str(body.get("detail", "")))
    zdir = PORTAL / "custom-apps" / "e2e-zip-app"
    check("Ο root φάκελος αφαιρέθηκε (index.html στη ρίζα)", (zdir / "index.html").is_file())
    check("Υποφάκελοι διατηρήθηκαν", (zdir / "assets" / "pic.svg").is_file())
    check("__MACOSX αγνοήθηκε", not (zdir / "__MACOSX").exists())
    zidx = (zdir / "index.html").read_text(encoding="utf-8")
    check("src=/app.js → ./app.js", 'src="./app.js"' in zidx)
    check("access teachers στο app.json", json.loads((zdir / "app.json").read_text())["access"] == "teachers")

    # Zip-slip απόρριψη
    zbad = io.BytesIO()
    with zipfile.ZipFile(zbad, "w") as z:
        z.writestr("../evil.txt", "bad")
    code, body = t.multipart("api/create", {"id": "e2e-evil", "title": "x", "mode": "upload"},
                             files=[("files", "evil.zip", zbad.getvalue())])
    check("Zip-slip (../) → 400", code == 400, str(code))
    check("Δεν δημιουργήθηκε φάκελος evil", not (PORTAL / "custom-apps" / "e2e-evil").exists())

    print("\n=== 5. Πολλαπλά αρχεία & αντικατάσταση ===")
    code, body = t.multipart("api/create", {
        "id": "e2e-multi-app", "title": "E2E Multi", "mode": "upload",
    }, files=[
        ("files", "index.html", b'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><p>v1</p><link href="style.css" rel="stylesheet"></body></html>'),
        ("files", "style.css", b"p{color:red}"),
    ])
    check("Πολλαπλά αρχεία → 200", code == 200, str(code))
    code, body = t.multipart("api/create", {
        "id": "e2e-multi-app", "title": "E2E Multi v2", "mode": "upload", "replace": "true",
    }, files=[
        ("files", "index.html", b'<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><p>v2</p></body></html>'),
    ])
    check("Αντικατάσταση με replace=true → 200", code == 200, str(code))
    mdir = PORTAL / "custom-apps" / "e2e-multi-app"
    check("Το περιεχόμενο αντικαταστάθηκε (v2)", "v2" in (mdir / "index.html").read_text())
    check("Παλιά αρχεία αφαιρέθηκαν (style.css)", not (mdir / "style.css").exists())

    print("\n=== 6. Λίστα & embed generator ===")
    code, body = t.call("api/list")
    ids = [a["id"] for a in body.get("apps", [])]
    check("Η λίστα περιέχει τις νέες εφαρμογές", all(i in ids for i in ("e2e-paste-app", "e2e-zip-app", "e2e-multi-app")), str(ids))
    check("Το _template εξαιρείται", "_template" not in ids)
    code, body = t.call("api/embed/e2e-paste-app")
    check("GET /api/embed/{id} → snippet", code == 200 and 'iframe src="/apps/e2e-paste-app/"' in body.get("embed", ""))
    code, body = t.call("api/lessons")
    lessons = [l["path"] for l in body.get("lessons", [])]
    check("Λίστα μαθημάτων .md", code == 200 and "gymnasio-b/dyadiko.md" in lessons, f"{len(lessons)} μαθήματα")
    check("Εκτός assets/teachers", not any(l.startswith(("assets/", "teachers/")) for l in lessons))

    print("\n=== 7. Άμεση εισαγωγή σε μάθημα MkDocs ===")
    lesson_file = PORTAL / "mkdocs-site" / "docs" / "gymnasio-b" / "dyadiko.md"
    original = lesson_file.read_text(encoding="utf-8")
    try:
        code, body = t.call("api/embed-into-lesson", {"id": "e2e-paste-app", "lesson": "gymnasio-b/dyadiko.md"})
        check("Εισαγωγή → 200", code == 200, str(code) + " " + str(body.get("detail", "")))
        new_text = lesson_file.read_text(encoding="utf-8")
        check("Το block προστέθηκε στο τέλος", new_text.rstrip().endswith("</div>") and 'src="/apps/e2e-paste-app/"' in new_text)
        check("Το αρχικό περιεχόμενο διατηρήθηκε", new_text.startswith(original.rstrip()[:100]))
        code, body = t.call("api/embed-into-lesson", {"id": "e2e-paste-app", "lesson": "gymnasio-b/dyadiko.md"})
        check("Διπλή εισαγωγή → 409", code == 409, str(code))
        code, body = t.call("api/embed-into-lesson", {"id": "e2e-paste-app", "lesson": "../../etc/passwd"})
        check("Path traversal → 400/404", code in (400, 404), str(code))
        code, body = t.call("api/embed-into-lesson", {"id": "e2e-paste-app", "lesson": "teachers/lyseis.md"})
        check("Προστατευμένη περιοχή teachers → 400", code == 400, str(code))
        # Αναμονή αυτόματου rebuild (inotify path unit ή άμεσο trigger)
        rebuilt = False
        for _ in range(40):
            time.sleep(1)
            c, page = get_url("http://127.0.0.1/docs/gymnasio-b/dyadiko/")
            if c == 200 and "custom-app-embed" in page and 'src="/apps/e2e-paste-app/"' in page:
                rebuilt = True
                break
        check("Το μάθημα ανακατασκευάστηκε αυτόματα με τον iframe", rebuilt)
    finally:
        lesson_file.write_text(original, encoding="utf-8")

    print("\n=== 8. Διαγραφή & καθαρισμός ===")
    for app_id in ("e2e-paste-app", "e2e-zip-app", "e2e-multi-app"):
        code, body = t.call("api/delete/" + app_id, method="DELETE")
        check(f"Διαγραφή {app_id} → 200", code == 200, str(code))
        check(f"Ο φάκελος {app_id} αφαιρέθηκε", not (PORTAL / "custom-apps" / app_id).exists())
    code, manifest = get_url("http://127.0.0.1/apps/apps-manifest.json")
    check("Manifest χωρίς τις e2e εφαρμογές", code == 200 and "e2e-" not in manifest)
    check("Το binary-converter παραμένει", "binary-converter" in manifest)
    code, _ = anon.call("api/delete/binary-converter", method="DELETE")
    check("Διαγραφή χωρίς login → 401", code == 401, str(code))
    code, _ = t.call("api/logout", {})
    check("Logout → 200", code == 200)
    code, _ = t.call("api/list")
    check("Μετά το logout → 401", code == 401, str(code))

    print(f"\n{'✓ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ' if FAILED == 0 else '✗ ΥΠΑΡΧΟΥΝ ΑΠΟΤΥΧΙΕΣ'} ({FAILED} αποτυχίες)")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())