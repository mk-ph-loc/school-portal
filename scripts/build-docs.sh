#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build-docs.sh — Ανακατασκευή του εκπαιδευτικού υλικού (MkDocs → static HTML)
#
# Χρησιμοποιείται από:
#   - school-mkdocs.service (oneshot)
#   - school-mkdocs.path    (αυτόματα σε αλλαγές αρχείων)
#   - Visual Pandoc Studio  (μετά την αποστολή μαθήματος)
# ---------------------------------------------------------------------------
set -euo pipefail

VENV="/opt/school-portal/venv"
SITE_DIR="/opt/school-portal/mkdocs-site"
OUTPUT_DIR="/var/www/docs"
# Το lock βρίσκεται στον φάκελο του project ώστε να είναι προσβάσιμο
# τόσο από τον root (systemd) όσο και από τον www-data (Pandoc Studio).
LOCK_FILE="/opt/school-portal/data/mkdocs-build.lock"

export NO_MKDOCS_2_WARNING=1
export PYTHONDONTWRITEBYTECODE=1

if [[ ! -x "${VENV}/bin/mkdocs" ]]; then
    echo "ΣΦΑΛΜΑ: Δεν βρέθηκε το mkdocs στο ${VENV}" >&2
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

# Αποτροπή ταυτόχρονων builds (flock, μη-μπλοκάρισμα)
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
    echo "Άλλο build βρίσκεται σε εξέλιξη — παράλειψη."
    exit 0
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Έναρξη ανακατασκευής εκπαιδευτικού υλικού…"
cd "${SITE_DIR}"

# Χτίζουμε σε προσωρινό φάκελο και μετά αντικαθιστούμε ατομικά,
# ώστε οι μαθητές να μη βλέπουν ποτέ ημιτελές site.
BUILD_TMP="/opt/school-portal/data/build"
mkdir -p "${BUILD_TMP}"
chmod 2775 "${BUILD_TMP}" 2>/dev/null || true

# Καθαρισμός υπολειμμάτων από προηγούμενα (πιθανώς root-owned) builds,
# ώστε να μη μπλοκάρουν την αντιγραφή όταν τρέχουμε ως www-data.
find "${BUILD_TMP}" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

# umask 002: όλοι οι φάκελοι/αρχεία δημιουργούνται group-writable,
# ώστε root (systemd) και www-data (Pandoc Studio) να συνεργάζονται.
umask 002
TMP_OUT="$(mktemp -d "${BUILD_TMP}/docs-XXXXXX")"
trap 'rm -rf "${TMP_OUT}"' EXIT
chmod 2775 "${TMP_OUT}" 2>/dev/null || true

"${VENV}/bin/mkdocs" build --clean --site-dir "${TMP_OUT}" --quiet

# Συγχρονισμός στο τελικό σημείο (το --delete αφαιρεί παλιές σελίδες)
# ΣΗΜΕΙΩΣΗ: χρησιμοποιούμε -rlpt (χωρίς -o/-g) ώστε να λειτουργεί και όταν
# το script εκτελείται ως www-data (από το Pandoc Studio), όπου δεν επιτρέπεται
# η διατήρηση/αλλαγή ιδιοκτήτη αρχείων.
if command -v rsync >/dev/null 2>&1; then
    rsync -rlt --delete --no-owner --no-group --chmod=D2775,F664 "${TMP_OUT}/" "${OUTPUT_DIR}/"
else
    find "${OUTPUT_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    # Χωρίς -p: τα modes/ownership προσαρμόζονται παρακάτω (λειτουργεί και ως www-data)
    cp -r "${TMP_OUT}/." "${OUTPUT_DIR}/"
fi

# Τα δικαιώματα αναλαμβάνει το setgid του φακέλου· οι παρακάτω εντολές
# αποτυγχάνουν σιωπηλά όταν τρέχουμε ως μη-root (αναμενόμενο).
if [[ "$(id -u)" == "0" ]]; then
    chown -R www-data:www-data "${OUTPUT_DIR}" 2>/dev/null || true
fi
find "${OUTPUT_DIR}" -type d -exec chmod 2775 {} + 2>/dev/null || true
find "${OUTPUT_DIR}" -type f -exec chmod 664 {} + 2>/dev/null || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Ολοκληρώθηκε → ${OUTPUT_DIR}"