"""
scripts/lib.py — Κοινές σταθερές για τα e2e/browser tests της πύλης.

Ο κωδικός καθηγητή διαβάζεται από την ΙΔΙΑ πηγή με τα apps (common.auth:
env TEACHER_PASS → data/portal.env → default), ώστε αλλαγή κωδικού μέσω
install.sh να μην σπάει τα tests. Χρήση:

    from lib import TEACHER_CODE          # scripts που τρέχουν από το scripts/
    # ή (όταν το script αλλάζει sys.path):
    sys.path.insert(0, "/opt/school-portal/scripts")
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/opt/school-portal")

from common.auth import TEACHER_CODE  # noqa: E402,F401  (re-export)