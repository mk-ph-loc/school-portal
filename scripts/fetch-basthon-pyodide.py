#!/usr/bin/env python3
"""
fetch-basthon-pyodide.py — Τοπικό Pyodide για το offline εργαστήριο Basthon (/apps/basthon/).

Το επίσημο basthon-console.tgz (console.basthon.fr) περιέχει το React console +
τον kernel 0.92.0 ΑΛΛΑ ΟΧΙ τα Pyodide binaries — μόνο το lockfile
assets/0.92.0/python3/pyodide-lock.json (Pyodide 0.26.4, Python 3.12.1).
Ο kernel φορτώνει local-first από <rootPath>/0.92.0/python3/pyodide/pyodide.js
και μετά δοκιμάζει CDN fallbacks — εδώ κατεβάζουμε τα πάντα τοπικά ώστε το
εργαστήριο να δουλεύει 100% offline στο σχολικό LAN (όπως το βήμα 6 του install.sh).

Τι κάνει (μόνο stdlib, μοτίβο fetch-excalidraw.sh):
  1. Διαβάζει το pyodide-lock.json και υπολογίζει το dependency closure
     (PEP503 canonical names, όπως το make.py του basthon-desktop):
     κρατά stdlib packages + basthon modules ({basthonRoot}) + matplotlib +
     numpy + τις εξαρτήσεις τους· εξαιρεί test packages και όσα δεν υπάρχουν
     στο lockfile. Αναμενόμενο: 29 πακέτα / 19 εξωτερικά αρχεία.
  2. Κατεβάζει το pyodide-core-<ver>.tar.bz2 από τα GitHub releases (~5.3 MB)
     → pyodide.js, pyodide.asm.js, pyodide.asm.wasm, python_stdlib.zip.
  3. Κατεβάζει κάθε εξωτερικό πακέτο από το jsdelivr CDN του Pyodide
     (fallback: ολόκληρο το pyodide-<ver>.tar από τα GitHub releases),
     ΕΠΑΛΗΘΕΥΟΝΤΑΣ το sha256 από το lockfile.
  4. ΞΑΝΑΓΡΑΦΕΙ το lockfile με ΜΟΝΟ τα kept packages (ώστε ο kernel να μη
     ζητά αγνοούμενα πακέτα). Το πρωτότυπο αποθηκεύεται ως
     pyodide-lock.original.json (πηγή του marker & εκκίνηση του FORCE=1).

Idempotent: αν υπάρχει marker .complete με το sha256 του ΑΡΧΙΚΟΥ lockfile,
δεν ξανατρέχει. FORCE=1 για override (π.χ. αναβάθμιση kernel).

Χρήση:  python3 /opt/school-portal/scripts/fetch-basthon-pyodide.py
Exit codes: 0 = OK (ή ήδη complete), 1 = αποτυχία.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent
PY3_DIR = PORTAL_DIR / "custom-apps" / "basthon" / "console" / "assets" / "0.92.0" / "python3"
LOCKFILE = PY3_DIR / "pyodide-lock.json"
ORIGINAL_LOCK = PY3_DIR / "pyodide-lock.original.json"
DEST = PY3_DIR / "pyodide"
MARKER = DEST / ".complete"

# Τα 4 αρχεία που χρειάζεται ο loader του Pyodide 0.26.x (όχι .mjs/.d.ts/package.json).
CORE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip")

C_OK, C_INFO, C_WARN, C_OFF = "\033[0;32m", "\033[0;36m", "\033[0;33m", "\033[0m"


def log(msg):  print(f"{C_INFO}[•]{C_OFF} {msg}")
def ok(msg):   print(f"{C_OK}[✓]{C_OFF} {msg}")
def warn(msg): print(f"{C_WARN}[!]{C_OFF} {msg}")


def canon(name: str) -> str:
    """PEP503 canonical name (όπως το make.py του basthon-desktop)."""
    return re.sub(r"[-_.]+", "-", name).lower()


TEST_RE = re.compile(r"(^|-)tests?\d*$|-test-py$")


def compute_closure(lock: dict) -> tuple[set[str], list[str]]:
    """Κρατά stdlib + basthon modules + matplotlib/numpy + το dependency closure τους."""
    pkgs = lock["packages"]
    by_canon = {canon(k): k for k in pkgs}
    keep: set[str] = set()
    stack: list[str] = []
    for name, meta in pkgs.items():
        is_stdlib = meta.get("install_dir") == "stdlib"
        is_basthon = "{basthonRoot}" in str(meta.get("file_name", ""))
        if (is_stdlib or is_basthon) and not TEST_RE.search(canon(name)):
            stack.append(name)
    for extra in ("matplotlib", "numpy"):
        if extra in by_canon:
            stack.append(by_canon[extra])
    while stack:
        name = stack.pop()
        if name in keep:
            continue
        keep.add(name)
        for dep in pkgs[name].get("depends", []):
            c = canon(dep)
            # εξαιρούνται test packages & όσα δεν υπάρχουν στο lockfile
            if c in by_canon and not TEST_RE.search(c) and by_canon[c] not in keep:
                stack.append(by_canon[c])
    external = sorted({pkgs[k]["file_name"] for k in keep
                       if "{basthonRoot}" not in pkgs[k]["file_name"]})
    return keep, external
def download(url: str, out: Path, timeout: int = 300, retries: int = 3) -> bool:
    """Λήψη με retries (μοτίβο curl --retry του fetch-excalidraw.sh)."""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "school-portal-fetch"})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(out, "wb") as f:
                shutil.copyfileobj(resp, f)
            return True
        except Exception as exc:
            out.unlink(missing_ok=True)
            if attempt == retries:
                warn(f"Αποτυχία λήψης {url} ({exc})")
            else:
                time.sleep(2)
    return False


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    force = os.environ.get("FORCE", "0") == "1"

    if not LOCKFILE.is_file():
        warn(f"Λείπει το {LOCKFILE} — τρέξε πρώτα την εξαγωγή του basthon-console.tgz.")
        return 1

    # Πρωτότυπο lockfile: αποθηκεύεται μία φορά (πηγή αλήθειας για marker/FORCE).
    if not ORIGINAL_LOCK.is_file():
        shutil.copyfile(LOCKFILE, ORIGINAL_LOCK)
    original_sha = sha256_of(ORIGINAL_LOCK)

    if MARKER.is_file() and MARKER.read_text(encoding="utf-8").strip() == original_sha and not force:
        ok(f"Το Pyodide του Basthon υπάρχει ήδη στο {DEST} (FORCE=1 για ενημέρωση).")
        return 0

    lock = json.loads(ORIGINAL_LOCK.read_text(encoding="utf-8"))
    version = lock["info"]["version"]
    keep, external = compute_closure(lock)
    log(f"Pyodide {version}: {len(keep)} πακέτα στο subset, {len(external)} εξωτερικά αρχεία.")

    DEST.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="basthon-pyodide."))
    full_tar: Path | None = None  # lazy fallback για όσα αποτύχουν στο CDN
    try:
        # --- 1. Pyodide core (GitHub releases tarball) -----------------------
        core_url = (f"https://github.com/pyodide/pyodide/releases/download/"
                    f"{version}/pyodide-core-{version}.tar.bz2")
        log(f"Λήψη {core_url} …")
        core_tar = tmp / f"pyodide-core-{version}.tar.bz2"
        if not download(core_url, core_tar):
            return 1
        extracted = 0
        with tarfile.open(core_tar, "r:bz2") as tf:
            for member in tf.getmembers():
                base = Path(member.name).name
                if member.isfile() and base in CORE_FILES:
                    target = DEST / base
                    with tf.extractfile(member) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    target.chmod(0o644)
                    extracted += 1
        if extracted != len(CORE_FILES):
            warn(f"Το core tarball περιείχε {extracted}/{len(CORE_FILES)} αρχεία — άλλαξε το upstream;")
            return 1
        ok(f"Pyodide core: {', '.join(CORE_FILES)}")
        # --- 2. Εξωτερικά πακέτα (jsdelivr CDN, fallback GitHub full tar) ----
        def from_full_tar(file_name: str, out: Path) -> bool:
            nonlocal full_tar
            if full_tar is None:
                full_url = (f"https://github.com/pyodide/pyodide/releases/download/"
                            f"{version}/pyodide-{version}.tar")
                log(f"Fallback: λήψη ολόκληρου του {full_url} (~250 MB)…")
                candidate = tmp / f"pyodide-{version}.tar"
                full_tar = candidate if download(full_url, candidate, timeout=900) else False
            if not full_tar:
                return False
            with tarfile.open(full_tar, "r:") as tf:
                for member in tf:
                    if member.isfile() and Path(member.name).name == file_name:
                        with tf.extractfile(member) as src, open(out, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        return True
            return False

        cdn = f"https://cdn.jsdelivr.net/pyodide/v{version}/full/"
        for i, file_name in enumerate(external, 1):
            expected = next(lock["packages"][k]["sha256"] for k in keep
                            if lock["packages"][k]["file_name"] == file_name)
            out = DEST / file_name
            log(f"[{i}/{len(external)}] {file_name}")
            if not download(cdn + file_name, out) and not from_full_tar(file_name, out):
                warn(f"Δεν κατέβηκε το {file_name} — ατελές Pyodide.")
                return 1
            actual = sha256_of(out)
            if actual != expected:
                out.unlink(missing_ok=True)
                warn(f"sha256 mismatch για {file_name}: {actual[:12]}… ≠ {expected[:12]}…")
                return 1
            out.chmod(0o644)
        ok(f"{len(external)} πακέτα κατέβηκαν & επαληθεύτηκαν (sha256).")

        # --- 3. Lockfile subset (ΜΟΝΟ τα kept packages) ----------------------
        subset = {"info": lock["info"],
                  "packages": {k: lock["packages"][k] for k in sorted(keep)}}
        text = json.dumps(subset, ensure_ascii=False, indent=1) + "\n"
        tmp_lock = LOCKFILE.with_suffix(".json.tmp")
        tmp_lock.write_text(text, encoding="utf-8")
        tmp_lock.chmod(0o644)
        os.replace(tmp_lock, LOCKFILE)
        ok(f"pyodide-lock.json: ξαναγράφηκε με {len(keep)} πακέτα (subset).")

        # --- 4. Marker idempotence -------------------------------------------
        MARKER.write_text(original_sha + "\n", encoding="utf-8")
        MARKER.chmod(0o644)
        size_mb = sum(f.stat().st_size for f in DEST.iterdir() if f.is_file()) / (1 << 20)
        ok(f"Το Pyodide {version} εγκαταστάθηκε στο {DEST} (~{size_mb:.0f} MB, 100% offline).")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())