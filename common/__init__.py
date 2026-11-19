"""
common — Κοινόχρηστος κώδικας της Ψηφιακής Πύλης (Βήμα 2 architecture review).

Ενιαία υλοποίηση των μοτίβων που ήταν αντιγραμμένα σε κάθε app:

  * common.auth     — HMAC teacher cookies (login/logout/require_teacher),
                      ταυτότητα σύνδεσης (Classroom Hub) & κοινές σταθερές.
  * common.classes  — οι 6 τάξεις του mkdocs-site (slug/label) + greeklish slug.
  * common.lessons  — parsing/render ημερήσιων μαθημάτων (φάσεις, front-matter,
                      tags/favorite) & κατάλογος από το docs/mathimata/.
  * common.db       — SQLite connections (WAL, Row factory) & ήπιες migrations.
  * common.schedule — ωράριο σχολείου: Excel → JSON, HH:MM normalization,
                      deadlines διδακτικών ωρών ±offset, JSON helpers.

Καθαρή βιβλιοθήκη: ΚΑΜΙΑ ενέργεια κατά το import (ούτε αρχεία, ούτε βάσεις).
Κάθε app περνάει τον δικό του φάκελο/διαδρομές, ώστε τα δεδομένα (DB,
.cookie-secret, schedule.json) να μένουν στους φακέλους των apps όπως πριν.

Τα apps τρέχουν με WorkingDirectory τον φάκελό τους· το πακέτο βρίσκεται μέσω
του Environment=PYTHONPATH=/opt/school-portal στα systemd units (βλ. install.sh).
"""
