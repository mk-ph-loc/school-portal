#!/usr/bin/env python3
"""
build-apps-manifest.py — Σάρωση του custom-apps/ και παραγωγή apps-manifest.json.

Διαβάζει το app.json κάθε υποφακέλου του /opt/school-portal/custom-apps/
(αγνοώντας το _template και ό,τι ξεκινά με "_" ή ".") και γράφει το συγκεντρωτικό
custom-apps/apps-manifest.json που καταναλώνει δυναμικά το κεντρικό Dashboard
(ενότητα «Δικές μου Εφαρμογές & Προσομοιώσεις»).

Χρήση:
    python3 /opt/school-portal/scripts/build-apps-manifest.py
    python3 scripts/build-apps-manifest.py --check   # έλεγχος εγκυρότητας χωρίς εγγραφή

Exit codes: 0 = OK, 1 = μη έγκυρα app.json (το manifest ΔΕΝ αλλάζει).
Καμία εξωτερική βιβλιοθήκη — μόνο stdlib (τρέχει και εκτός venv).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

PORTAL_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = PORTAL_DIR / "custom-apps"
MANIFEST = APPS_DIR / "apps-manifest.json"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VALID_ACCESS = {"all", "teachers"}


def load_app(app_dir: Path) -> tuple[dict | None, list[str]]:
    """Διαβάζει & επικυρώνει το app.json ενός υποφακέλου. Επιστρέφει (entry, errors)."""
    errors: list[str] = []
    meta_file = app_dir / "app.json"
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{app_dir.name}: λείπει το app.json"]
    except json.JSONDecodeError as exc:
        return None, [f"{app_dir.name}/app.json: μη έγκυρο JSON ({exc})"]

    if not isinstance(meta, dict):
        return None, [f"{app_dir.name}/app.json: αναμενόταν JSON object"]

    app_id = str(meta.get("id", "")).strip()
    title = str(meta.get("title", "")).strip()
    description = str(meta.get("description", "")).strip()
    category = str(meta.get("category", "")).strip() or "Γενικά"
    icon = str(meta.get("icon", "")).strip() or "🚀"
    access = str(meta.get("access", "all")).strip()
    pinned_raw = meta.get("pinned", False)

    if not ID_RE.match(app_id):
        errors.append(f"{app_dir.name}: το id '{app_id}' πρέπει να είναι lowercase λατινικά/ψηφία/παύλες")
    if app_id != app_dir.name:
        errors.append(f"{app_dir.name}: το id '{app_id}' πρέπει να ταυτίζεται με το όνομα του φακέλου")
    if not title:
        errors.append(f"{app_dir.name}: λείπει το πεδίο title")
    if access not in VALID_ACCESS:
        errors.append(f"{app_dir.name}: το access πρέπει να είναι 'all' ή 'teachers' (βρέθηκε '{access}')")
    if not isinstance(pinned_raw, bool):
        errors.append(f"{app_dir.name}: το pinned πρέπει να είναι boolean true/false (βρέθηκε {pinned_raw!r})")
    if not (app_dir / "index.html").is_file():
        errors.append(f"{app_dir.name}: λείπει το index.html")

    entry = {
        "id": app_id,
        "title": title,
        "description": description,
        "category": category,
        "icon": icon,
        "access": access,
        "pinned": pinned_raw is True,
        "url": f"/apps/{app_dir.name}/",
    }
    return entry, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Παραγωγή custom-apps/apps-manifest.json")
    parser.add_argument("--check", action="store_true", help="έλεγχος εγκυρότητας χωρίς εγγραφή αρχείου")
    args = parser.parse_args()

    if not APPS_DIR.is_dir():
        print(f"✗ Δεν υπάρχει ο φάκελος {APPS_DIR}", file=sys.stderr)
        return 1

    entries: list[dict] = []
    all_errors: list[str] = []
    seen_ids: set[str] = set()

    for app_dir in sorted(APPS_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not app_dir.is_dir() or app_dir.name.startswith(("_", ".")):
            continue  # _template, .git κ.λπ.
        entry, errors = load_app(app_dir)
        all_errors.extend(errors)
        if errors or entry is None:
            continue
        if entry["id"] in seen_ids:
            all_errors.append(f"{app_dir.name}: διπλότυπο id '{entry['id']}'")
            continue
        seen_ids.add(entry["id"])
        entries.append(entry)

    if all_errors:
        for err in all_errors:
            print(f"✗ {err}", file=sys.stderr)
        print("Το apps-manifest.json ΔΕΝ ενημερώθηκε — διόρθωσε τα παραπάνω και ξανατρέξε.", file=sys.stderr)
        return 1

    # Σταθερή σειρά εμφάνισης στο Dashboard: pinned πρώτα («Εργαλείο Ημέρας»),
    # μετά αλφαβητικά κατά τίτλο (ελληνικά). Το Dashboard ΔΙΑΤΗΡΕΙ αυτή τη σειρά.
    entries.sort(key=lambda e: (not e["pinned"], e["title"].casefold()))
    payload = {"apps": entries}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        print(f"✓ {len(entries)} εφαρμογές έγκυρες (--check: δεν γράφτηκε αρχείο)")
        return 0

    # Ατομική εγγραφή (temp + replace): λειτουργεί και όταν το υπάρχον αρχείο
    # είναι root-owned 644, αρκεί ο φάκελος να είναι group-writable (2775) —
    # π.χ. όταν το script τρέχει ως www-data από τον App Builder Wizard.
    tmp = MANIFEST.with_name(f".apps-manifest.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.chmod(0o644)
    os.replace(tmp, MANIFEST)
    print(f"✓ apps-manifest.json: {len(entries)} εφαρμογές → {MANIFEST}")
    for e in entries:
        badge = "καθηγητές" if e["access"] == "teachers" else "όλοι"
        pin = " 📌" if e["pinned"] else ""
        print(f"    {e['icon']} {e['title']}{pin}  →  {e['url']}  [{badge}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())