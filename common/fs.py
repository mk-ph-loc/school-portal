"""
common.fs — Αντίγραφα ασφαλείας αρχείων πριν από κάθε εγγραφή.

Ενοποιεί τις 3 παραλλαγές backup_file() που ζούσαν σε lesson-wizard /
hedgedoc-bridge / h5p-studio (εκκρεμότητα 3 του Βήματος 2):

  * backup_history(): ιστορικό με timestamp στο <app>/backups/ —
    - flat ονόματα «<stamp>__<rel-path>.bak» (lesson-wizard, για ΟΠΟΙΟδήποτε
      αρχείο της πύλης: .md, mkdocs.yml, schedule.json…),
    - ή καθρέφτης της δομής docs/ «<stem>.<stamp>.md.bak» (bridge/h5p).
  * backup_beside(): το πιο πρόσφατο .bak ΔΙΠΛΑ στο αρχείο (bridge/h5p) —
    οι μαθητές/καθηγητές το βρίσκουν αμέσως στον φάκελο του μαθήματος.

Καθαρή βιβλιοθήκη: κάθε app περνάει τους δικούς του φακέλους· τα δικαιώματα
(664/2775) τακτοποιούνται προαιρετικά από τον caller (fix_md_permissions).
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_history(path: Path, backup_dir: Path, *, relative_to: Path | None = None,
                   mirror_tree: bool = False) -> Path | None:
    """Ιστορικό αντίγραφο στο backup_dir (mkdir αυτόματα)· None αν δεν υπάρχει.

    relative_to=None → επίπεδο όνομα «<stamp>__<πλήρης-διαδρομή>.bak»
    (μορφή lesson-wizard, ασφαλής για αρχεία εκτός docs/ όπως το mkdocs.yml).
    mirror_tree=True → κρατά τη δομή φακέλων κάτω από το relative_to και
    ονομάζει «<stem>.<stamp><suffix>.bak» (μορφή bridge/h5p για μαθήματα).
    """
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = Path(backup_dir)
    stamp = _stamp()
    if mirror_tree and relative_to is not None:
        rel = path.relative_to(relative_to)
        dest_dir = backup_dir / rel.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{path.stem}.{stamp}{path.suffix}.bak"
    else:
        backup_dir.mkdir(parents=True, exist_ok=True)
        base = path.relative_to(relative_to) if relative_to is not None else path
        rel = base.as_posix().lstrip("/").replace("/", "__")
        dest = backup_dir / f"{stamp}__{rel}.bak"
    shutil.copy2(path, dest)
    return dest


def backup_beside(path: Path) -> Path:
    """Πάντα το πιο πρόσφατο αντίγραφο «<όνομα>.bak» δίπλα στο αρχείο."""
    path = Path(path)
    bak = path.with_name(path.name + ".bak")
    shutil.copy2(path, bak)
    return bak