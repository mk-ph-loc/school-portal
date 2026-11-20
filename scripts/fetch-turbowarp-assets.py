#!/usr/bin/env python3
"""
fetch-turbowarp-assets.py — Τοπικό mirror assets για το offline TurboWarp (/apps/turbowarp/).

Το static build του TurboWarp (custom-apps/turbowarp/) περιέχει τον editor ΑΛΛΑ
ΟΧΙ τα assets της βιβλιοθήκης (sprites/costumes/sounds/backdrops) — κανονικά
φορτώνονται από το assets.scratch.mit.edu. Εδώ κατεβάζουμε ΟΛΑ τα μοναδικά
md5ext που αναφέρονται στα src/lib/libraries/{costumes,sounds,backdrops,sprites}.json
(committed αντίγραφα στο scripts/turbowarp-libraries/) ώστε οι βιβλιοθήκες να
δουλεύουν 100% offline στο σχολικό LAN (όπως το βήμα 6ε του Basthon).

Τι κάνει (μόνο stdlib, μοτίβο fetch-basthon-pyodide.py):
  1. Διαβάζει τα 4 JSON βιβλιοθηκών & συλλέγει τα μοναδικά md5ext
     (πεδία md5ext σε top-level items ΚΑΙ σε nested costumes/sounds των sprites).
  2. Κατεβάζει κάθε asset από
     https://assets.scratch.mit.edu/internalapi/asset/<md5>.<ext>/get/
     → custom-apps/turbowarp/scratch-assets/<md5>.<ext>  (flat layout —
     ίδιο με το patched storage.js getAssetGetConfig του build).
     Parallel 8 threads, retry 3, skip όσα υπάρχουν ήδη με σωστό μέγεθος.
  3. ΕΠΑΛΗΘΕΥΕΙ ότι το md5 του περιεχομένου = το όνομα του αρχείου
     (το Scratch αποθηκεύει τα assets content-addressed).

Idempotent: αν υπάρχει marker .complete με το sha256 των 4 JSON βιβλιοθηκών,
δεν ξανατρέχει. FORCE=1 για override (π.χ. αναβάθμιση build με νέες βιβλιοθήκες).

Χρήση:  python3 /opt/school-portal/scripts/fetch-turbowarp-assets.py
Exit codes: 0 = OK (ή ήδη complete), 1 = αποτυχία.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent
LIBRARIES_DIR = PORTAL_DIR / "scripts" / "turbowarp-libraries"
DEST = PORTAL_DIR / "custom-apps" / "turbowarp" / "scratch-assets"
MARKER = DEST / ".complete"

LIBRARY_NAMES = ("costumes", "sounds", "backdrops", "sprites")
ASSET_URL = "https://assets.scratch.mit.edu/internalapi/asset/{md5ext}/get/"
THREADS = 8
RETRIES = 3

C_OK, C_INFO, C_WARN, C_OFF = "\033[0;32m", "\033[0;36m", "\033[0;33m", "\033[0m"


def log(msg):  print(f"{C_INFO}[•]{C_OFF} {msg}")
def ok(msg):   print(f"{C_OK}[✓]{C_OFF} {msg}")
def warn(msg): print(f"{C_WARN}[!]{C_OFF} {msg}")
def collect_md5ext() -> tuple[list[str], str]:
    """Μοναδικά md5ext από τις 4 βιβλιοθήκες + sha256 των JSON (marker idempotence)."""
    md5exts: set[str] = set()
    digest = hashlib.sha256()
    for name in LIBRARY_NAMES:
        path = LIBRARIES_DIR / f"{name}.json"
        raw = path.read_bytes()
        digest.update(raw)
        for item in json.loads(raw):
            if "md5ext" in item:
                md5exts.add(item["md5ext"])
            # sprites.json: nested costumes & sounds ανά sprite
            for key in ("costumes", "sounds"):
                for sub in item.get(key, []):
                    if "md5ext" in sub:
                        md5exts.add(sub["md5ext"])
    return sorted(md5exts), digest.hexdigest()


def valid_existing(path: Path) -> bool:
    """Υπάρχει ήδη με σωστό μέγεθος (>0) και md5 περιεχομένου = όνομα αρχείου."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    expected_md5 = path.name.split(".")[0]
    return hashlib.md5(path.read_bytes()).hexdigest() == expected_md5


def fetch_asset(md5ext: str) -> tuple[str, bool, str]:
    """Κατεβάζει ένα asset με retry 3 & επαλήθευση md5. (md5ext, ok, detail)."""
    out = DEST / md5ext
    if valid_existing(out):
        return md5ext, True, "skip (υπάρχει)"
    url = ASSET_URL.format(md5ext=md5ext)
    last_err = "άγνωστο σφάλμα"
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "school-portal-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            actual = hashlib.md5(data).hexdigest()
            if actual != md5ext.split(".")[0]:
                last_err = f"md5 mismatch ({actual[:12]}…)"
            else:
                tmp = out.with_suffix(out.suffix + ".part")
                tmp.write_bytes(data)
                os.replace(tmp, out)
                out.chmod(0o644)
                return md5ext, True, f"{len(data)} bytes"
        except Exception as exc:
            last_err = str(exc)[:120]
        if attempt < RETRIES:
            time.sleep(1.5 * attempt)
    return md5ext, False, last_err
def main() -> int:
    force = os.environ.get("FORCE") == "1"
    if not LIBRARIES_DIR.is_dir():
        warn(f"Δεν βρέθηκε ο φάκελος {LIBRARIES_DIR} (committed βιβλιοθήκες).")
        return 1
    md5exts, libs_sha = collect_md5ext()
    log(f"{len(md5exts)} μοναδικά assets από τις βιβλιοθήκες {', '.join(LIBRARY_NAMES)}.")

    if MARKER.exists() and not force:
        if MARKER.read_text(encoding="utf-8").strip() == libs_sha:
            ok("Το τοπικό mirror assets υπάρχει ήδη (marker .complete) — παράλειψη.")
            return 0
        log("Άλλαξαν οι βιβλιοθήκες — ενημέρωση του mirror…")

    DEST.mkdir(parents=True, exist_ok=True)
    failed: list[tuple[str, str]] = []
    done = skipped = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futures = {pool.submit(fetch_asset, m): m for m in md5exts}
        for fut in as_completed(futures):
            md5ext, good, detail = fut.result()
            if good:
                done += 1
                if detail.startswith("skip"):
                    skipped += 1
            else:
                failed.append((md5ext, detail))
            n = done + len(failed)
            if n % 100 == 0 or n == len(md5exts):
                log(f"[{n}/{len(md5exts)}] {done} OK ({skipped} skip), {len(failed)} αποτυχίες")

    if failed:
        for md5ext, err in failed[:10]:
            warn(f"ΑΠΕΤΥΧΕ {md5ext}: {err}")
        warn(f"{len(failed)} assets δεν κατέβηκαν — το mirror είναι ΑΤΕΛΕΣ (ξανατρέξε το script).")
        return 1

    MARKER.write_text(libs_sha + "\n", encoding="utf-8")
    MARKER.chmod(0o644)
    size_mb = sum(f.stat().st_size for f in DEST.iterdir() if f.is_file()) / (1 << 20)
    ok(f"{done} assets στο {DEST} (~{size_mb:.0f} MB, {time.time() - t0:.0f}s, 100% offline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())