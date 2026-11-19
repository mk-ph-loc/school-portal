#!/opt/school-portal/venv/bin/python
"""
h5p-test.py — Έλεγχος του H5P Studio (/h5p-studio/) μέσω API + πραγματικού browser.

Ελέγχει: login/προστασία, δημιουργία 7 τύπων, έγκυρη δομή H5P στον δίσκο,
αναπαραγωγή χωρίς login, export/import .h5p round-trip, preview, wizard
prompts/ρυθμίσεις, paste-JSON, ενσωμάτωση σε MkDocs (+.bak) και απόδοση
του offline player σε headless Chromium (CDP).

Χρήση: /opt/school-portal/venv/bin/python scripts/h5p-test.py
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import (TEACHER_CODE, Client as HTTPClient, check,
                 launch_chrome, multipart_body, results, stop_chrome)

BASE = "http://127.0.0.1/h5p-studio"
PORTAL = Path("/opt/school-portal")


class Client(HTTPClient):
    """Κοινό harness Client — το call() εδώ γυρίζει bytes (exports/uploads)."""

    def __init__(self):
        super().__init__(BASE, timeout=300)

    def call(self, path, payload=None, method=None, raw=None, ctype="application/json"):
        return self.raw(path, payload, method, raw=raw, ctype=ctype)


def upload(t, path, filename, blob, mime):
    """Upload ενός αρχείου (πεδίο 'file') → (status, dict)."""
    body, ctype = multipart_body(files=[("file", filename, blob, mime)])
    return t.json(path, raw=body, ctype=ctype)

SAMPLES = {
    "multichoice": {"question": "Πόσα bits έχει ένα byte;", "answers": [
        {"text": "8", "correct": True, "feedback": "Σωστά!"},
        {"text": "4", "correct": False, "feedback": "Όχι."},
        {"text": "16", "correct": False, "feedback": "Όχι."}]},
    "questionset": {"intro": "Δοκιμαστικό quiz", "passPercentage": 60, "questions": [
        {"question": "Ε1;", "answers": [{"text": "Ναι", "correct": True}, {"text": "Όχι", "correct": False}]},
        {"question": "Ε2;", "answers": [{"text": "Ναι", "correct": True}, {"text": "Όχι", "correct": False}]}]},
    "blanks": {"questions": ["<p>Η πρωτεύουσα είναι η *Αθήνα:Παρθενώνας*.</p>",
                              "<p>1 byte = *8* bits.</p>"]},
    "dragtext": {"textField": "Ο Ήλιος είναι *αστέρας*.\nΗ Γη είναι *πλανήτης*.",
                 "distractors": "*δορυφόρος*"},
    "dialogcards": {"cards": [{"front": "RAM", "back": "Μνήμη τυχαίας προσπέλασης"},
                               {"front": "CPU", "back": "Κεντρική μονάδα επεξεργασίας"}]},
}

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da63fcffff3f0300050001a5f645400000000049454e44ae426082")
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 64


def main() -> int:
    anon = Client()
    t = Client()

    print("\n=== 1. Health & Login ===")
    code, d = anon.json("healthz")
    check("healthz → 200", code == 200 and d.get("status") == "ok")
    code, _ = anon.json("api/login", {"password": "λάθος"})
    check("Λάθος κωδικός → 401", code == 401)
    code, _ = t.json("api/login", {"password": TEACHER_CODE})
    check("Σωστός κωδικός → 200 + cookie", code == 200 and t.cookie("h5pstudio_teacher"))
    code, _ = anon.json("api/activities", {"type": "multichoice", "title": "x", "data": {}})
    check("Δημιουργία χωρίς login → 401", code == 401)

    print("\n=== 2. Δημιουργία 7 τύπων ===")
    ids = {}
    for typ, data in SAMPLES.items():
        code, d = t.json("api/activities", {"type": typ, "title": f"TEST {typ}",
                                            "class_slug": "gymnasio-a", "subject": "Πληροφορική",
                                            "data": data})
        ok = code == 200 and d.get("id")
        check(f"Δημιουργία {typ}", ok, str(d))
        if ok:
            ids[typ] = d["id"]

    # Hotspots & video με dummy media (upload στο preview-tmp → μεταφορά)
    code, d = upload(t, "api/upload/preview-tmp", "test.png", PNG, "image/png")
    check("Upload εικόνας στο preview-tmp", code == 200 and d.get("path"), str(d))
    img_path = d.get("path", "")
    code, d = t.json("api/activities", {"type": "hotspots", "title": "TEST hotspots",
        "data": {"image": {"path": img_path, "mime": "image/png", "width": 1, "height": 1},
                 "hotspots": [{"x": 30, "y": 40, "header": "Σημείο 1", "content": "Επεξήγηση"}]}})
    check("Δημιουργία hotspots (με μεταφορά media)", code == 200 and d.get("id"), str(d))
    if code == 200:
        ids["hotspots"] = d["id"]
        p = PORTAL / "h5p-studio/library" / d["id"] / "content" / img_path
        check("Το media μεταφέρθηκε στον μόνιμο φάκελο", p.is_file())

    code, d = upload(t, "api/upload/preview-tmp", "test.mp4", MP4, "video/mp4")
    check("Upload βίντεο στο preview-tmp", code == 200 and d.get("path"), str(d))
    vid_path = d.get("path", "")
    code, d = t.json("api/activities", {"type": "video", "title": "TEST video",
        "data": {"video": {"path": vid_path, "mime": "video/mp4"},
                 "interactions": [
                     {"time": 5, "kind": "mc", "pause": True, "label": "Ερώτηση",
                      "question": "Σωστό;", "answers": [{"text": "Ναι", "correct": True},
                                                        {"text": "Όχι", "correct": False}]},
                     {"time": 10, "kind": "text", "pause": True, "label": "Σημείωση",
                      "text": "Επεξηγηματικό πλαίσιο"}]}})
    check("Δημιουργία interactive video", code == 200 and d.get("id"), str(d))
    if code == 200:
        ids["video"] = d["id"]

    print("\n=== 3. Δομή H5P & αναπαραγωγή μαθητή ===")
    for typ, aid in ids.items():
        adir = PORTAL / "h5p-studio/library" / aid
        h5pj = json.loads((adir / "h5p.json").read_text())
        cj = json.loads((adir / "content/content.json").read_text())
        main_ok = any(dep["machineName"] == h5pj["mainLibrary"]
                      for dep in h5pj["preloadedDependencies"])
        check(f"{typ}: έγκυρο h5p.json+content.json", main_ok and isinstance(cj, dict))
        code, body = anon.call(f"play/{aid}/")
        check(f"{typ}: /play/ ανοιχτό χωρίς login", code == 200 and b"h5p-container" in body)

    print("\n=== 4. Export & Import .h5p ===")
    aid = ids["multichoice"]
    code, body = t.call(f"api/export/{aid}")
    check("Export → 200 ZIP", code == 200 and body[:2] == b"PK")
    zf = zipfile.ZipFile(io.BytesIO(body))
    names = zf.namelist()
    check("Export περιέχει h5p.json+content+βιβλιοθήκες",
          "h5p.json" in names and "content/content.json" in names
          and any(n.startswith("H5P.MultiChoice-1.16/") for n in names))
    check("Export δεν περιέχει editor-state.json", "content/editor-state.json" not in names)

    imported_id = None
    code, d = upload(t, "api/import", "roundtrip.h5p", body, "application/zip")
    check("Import του export (round-trip)", code == 200 and d.get("id"), str(d))
    imported_id = d.get("id")
    if imported_id:
        code, body2 = anon.call(f"play/{imported_id}/")
        check("Το imported παίζει αμέσως", code == 200)

    bad = io.BytesIO()
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("random.txt", "not h5p")
    code, d = upload(t, "api/import", "bad.h5p", bad.getvalue(), "application/zip")
    check("Import άκυρου .h5p → 400 με μήνυμα", code == 400 and "h5p.json" in str(d.get("detail", "")))


    print("\n=== 5. Preview & Wizard ===")
    code, d = t.json("api/preview", {"title": "Προεπισκόπηση",
                                     "data": dict(SAMPLES["multichoice"], type="multichoice")})
    check("Preview endpoint", code == 200)
    code, body = t.call("play/preview-tmp/")
    check("Preview page (καθηγητής)", code == 200)
    code, _ = anon.call("play/preview-tmp/")
    check("Preview page χωρίς login → 401", code == 401)

    code, d = t.json("api/wizard/suggest", {"goal": "assessment"})
    check("Wizard suggest (assessment → questionset πρώτο)",
          code == 200 and d["suggestions"][0]["type"] == "questionset")
    code, d = t.json("api/wizard/prompts", {"goal": "visual", "type": "hotspots",
                                            "chapter": "Το κύτταρο", "class_slug": "gymnasio-a",
                                            "subject": "Βιολογία"})
    check("Wizard prompts (περιεχομένου + εικόνας για hotspots)",
          code == 200 and "JSON" in d.get("content_prompt", "") and d.get("image_prompt"))
    code, d = t.json("api/settings")
    check("Ρυθμίσεις AI (configured από .env.keys)", code == 200 and d.get("configured") is True,
          str(d))

    paste = json.dumps({"type": "dialogcards", "title": "TEST paste-json",
                        "cards": [{"front": "Α", "back": "Β"}]}, ensure_ascii=False)
    code, d = t.json("api/wizard/paste-json", {"json_text": "```json\n" + paste + "\n```"})
    check("Paste JSON (με markdown fences) → νέα δραστηριότητα", code == 200 and d.get("id"), str(d))
    paste_id = d.get("id")

    print("\n=== 6. Ενσωμάτωση σε MkDocs (+backup) ===")
    code, d = t.json("api/lessons")
    lessons = [l for g in d.get("groups", []) for l in g["lessons"]]
    check("Λίστα μαθημάτων .md", code == 200 and len(lessons) > 0)
    if lessons:
        lesson = lessons[0]["path"]
        target = PORTAL / "mkdocs-site/docs" / lesson
        original = target.read_bytes()
        code, d = t.json(f"api/embed-code/{aid}?height=550")
        check("Embed code iframe", code == 200 and "iframe" in d.get("code", "")
              and f"/h5p-studio/play/{aid}/?embed=1" in d["code"])
        code, d = t.json(f"api/embed/{aid}", {"lesson": lesson, "height": 550})
        check("1 κλικ ενσωμάτωση", code == 200, str(d))
        check(".bak backup δημιουργήθηκε", target.with_name(target.name + ".bak").is_file())
        code, d = t.json(f"api/embed/{aid}", {"lesson": lesson})
        check("Διπλή ενσωμάτωση → 409", code == 409)
        # Επαναφορά του μαθήματος (καθαρισμός τεστ)
        target.write_bytes(original)
        target.with_name(target.name + ".bak").unlink(missing_ok=True)

    print("\n=== 7. Browser: offline player αποδίδει πραγματικά ===")
    run_browser_test(ids)

    print("\n=== 8. Καθαρισμός δοκιμαστικών ===")
    all_ids = list(ids.values()) + [i for i in (imported_id, paste_id) if i]
    for a in all_ids:
        t.json(f"api/activities/{a}", method="DELETE")
    code, d = t.json("api/activities")
    leftover = [a for a in d.get("activities", []) if a["title"].startswith("TEST")]
    check("Όλα τα TEST διαγράφηκαν", not leftover)

    r = results()
    print(f"\n{'='*50}\nΑΠΟΤΕΛΕΣΜΑ: {r.passed} επιτυχίες, {r.failed} αποτυχίες\n{'='*50}")
    return r.exit_code()



def run_browser_test(ids: dict) -> None:
    try:
        proc, cdp = launch_chrome(9351, window="1280,900", timeout=60)
    except RuntimeError as exc:
        print(f"  ⚠️ {exc} — παράλειψη browser test")
        return
    try:
        def ev(expr):
            return cdp.evaluate(expr, await_promise=True)

        cdp.send("Page.enable")
        cdp.send("Runtime.enable")
        # Ο h5p-standalone φορτώνει το περιεχόμενο σε about:blank iframe —
        # η επιθεώρηση γίνεται μέσω contentDocument (same-origin).
        inner = ("(()=>{const f=document.querySelector('iframe.h5p-iframe');"
                 "const d=f&&f.contentDocument;"
                 "return d?(d.body.innerHTML+d.body.innerText):'';})()")
        for typ, marker in (("multichoice", "h5p-question-check-answer"),
                            ("dragtext", "h5p-drag-text"),
                            ("dialogcards", "h5p-dialogcards"),
                            ("blanks", "h5p-blanks"),
                            ("questionset", "questionset"),
                            ("hotspots", "h5p-image-hotspots")):
            if typ not in ids:
                continue
            cdp.send("Page.navigate", {"url": f"{BASE}/play/{ids[typ]}/?embed=1"})
            found = False
            for _ in range(40):
                time.sleep(0.5)
                html = ev(inner) or ""
                err = ev("(document.querySelector('#h5p-error:not([hidden])')||{}).textContent||''")
                if marker in html or err:
                    found = True
                    break
            check(f"Browser: {typ} αποδίδεται από τον offline player",
                  bool(found and marker in (html or "") and not err), err or "(timeout)")
        # Ελληνικό UI check στο multichoice
        if "multichoice" in ids:
            cdp.send("Page.navigate", {"url": f"{BASE}/play/{ids['multichoice']}/?embed=1"})
            greek = False
            for _ in range(30):
                time.sleep(0.5)
                if "Έλεγχος" in (ev(inner) or ""):
                    greek = True
                    break
            check("Browser: ελληνικό κουμπί «Έλεγχος»", greek)
        cdp.close()
    finally:
        stop_chrome(proc, timeout=5)


if __name__ == "__main__":
    sys.exit(main())

