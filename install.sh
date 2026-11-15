#!/usr/bin/env bash
# ===========================================================================
#  Ψηφιακή Πύλη Σχολείου & Εργαστηρίου — Script αυτόματης εγκατάστασης
#
#  Χρήση:
#     sudo ./install.sh              # πλήρης εγκατάσταση / ενημέρωση
#     sudo ./install.sh --update     # ενημέρωση κώδικα από git + rebuild
#     sudo ./install.sh --no-deps    # παράλειψη apt/pip (γρήγορο re-apply)
#     sudo ./install.sh --help
#
#  Idempotent: μπορεί να εκτελεστεί ξανά με ασφάλεια.
# ===========================================================================
set -euo pipefail

PORTAL_DIR="/opt/school-portal"
VENV="${PORTAL_DIR}/venv"
DOCS_OUT="/var/www/docs"
TEACHER_USER="teacher"
TEACHER_PASS="${TEACHER_PASS:-teacher2026}"
HTPASSWD_FILE="/etc/nginx/.school-htpasswd"

PYODIDE_VERSION="314.0.8"
ALPINE_VERSION="3.14.9"
TAILWIND_VERSION="4.1.11"

SKIP_DEPS=0
DO_UPDATE=0

C_OK=$'\033[0;32m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_WARN=$'\033[0;33m'; C_OFF=$'\033[0m'
log()  { echo "${C_INFO}[•]${C_OFF} $*"; }
ok()   { echo "${C_OK}[✓]${C_OFF} $*"; }
warn() { echo "${C_WARN}[!]${C_OFF} $*"; }
die()  { echo "${C_ERR}[✗]${C_OFF} $*" >&2; exit 1; }

usage() {
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

for arg in "$@"; do
    case "$arg" in
        --update)  DO_UPDATE=1 ;;
        --no-deps) SKIP_DEPS=1 ;;
        --help|-h) usage ;;
        *) die "Άγνωστη παράμετρος: $arg (δοκίμασε --help)" ;;
    esac
done

[[ "$(id -u)" == "0" ]] || die "Απαιτούνται δικαιώματα root (sudo)."
cd "${PORTAL_DIR}"

echo
echo "==========================================================="
echo "  🏫 Ψηφιακή Πύλη Σχολείου & Εργαστηρίου — Εγκατάσταση"
echo "==========================================================="
echo

# ---------------------------------------------------------------------------
# 1. Ενημέρωση κώδικα από git (προαιρετικά)
# ---------------------------------------------------------------------------
if [[ "${DO_UPDATE}" == "1" ]]; then
    log "Ενημέρωση κώδικα από το git repository…"
    if git rev-parse --git-dir >/dev/null 2>&1; then
        git fetch --all --quiet || warn "Αποτυχία git fetch (συνεχίζουμε με τον τοπικό κώδικα)."
        if git diff --quiet && git diff --cached --quiet; then
            git pull --ff-only --quiet || warn "Αποτυχία git pull — συνεχίζουμε."
            ok "Ο κώδικας ενημερώθηκε."
        else
            warn "Υπάρχουν τοπικές αλλαγές — παράλειψη του git pull."
        fi
    else
        warn "Δεν βρέθηκε git repository — παράλειψη."
    fi
fi

# ---------------------------------------------------------------------------
# 2. Πακέτα συστήματος (apt)
# ---------------------------------------------------------------------------
if [[ "${SKIP_DEPS}" == "0" ]]; then
    log "Εγκατάσταση πακέτων συστήματος…"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends \
        nginx-light pandoc sqlite3 python3-venv python3-pip \
        fonts-dejavu fonts-liberation2 fontconfig \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
        libjpeg62-turbo libopenjp2-7 libffi8 shared-mime-info \
        curl ca-certificates bzip2 tar openssl rsync
    ok "Τα πακέτα συστήματος είναι έτοιμα."
else
    warn "Παράλειψη apt (--no-deps)."
fi

# ---------------------------------------------------------------------------
# 3. Δομή φακέλων
# ---------------------------------------------------------------------------
log "Δημιουργία δομής φακέλων…"
mkdir -p "${PORTAL_DIR}"/{dashboard/assets,dashboard/lab,mkdocs-site/docs,pandoc-app/{templates,static,data/templates,data/uploads},lab-app,config/{nginx,systemd},scripts,data/build}
mkdir -p "${DOCS_OUT}"
ok "Η δομή φακέλων δημιουργήθηκε."

# ---------------------------------------------------------------------------
# 4. Python virtual environment + βιβλιοθήκες
# ---------------------------------------------------------------------------
if [[ ! -x "${VENV}/bin/python" ]]; then
    log "Δημιουργία Python virtual environment στο ${VENV}…"
    python3 -m venv "${VENV}"
    ok "Το venv δημιουργήθηκε."
else
    log "Το venv υπάρχει ήδη."
fi

if [[ "${SKIP_DEPS}" == "0" ]]; then
    log "Εγκατάσταση Python βιβλιοθηκών (mkdocs-material, fastapi, weasyprint…)"
    "${VENV}/bin/pip" install --quiet --upgrade pip wheel setuptools
    if [[ -f "${PORTAL_DIR}/requirements.txt" ]]; then
        "${VENV}/bin/pip" install --quiet -r "${PORTAL_DIR}/requirements.txt"
    else
        "${VENV}/bin/pip" install --quiet \
            mkdocs-material mkdocs-glightbox \
            fastapi "uvicorn[standard]" python-multipart weasyprint jinja2
    fi
    ok "Οι Python βιβλιοθήκες εγκαταστάθηκαν."
else
    warn "Παράλειψη pip (--no-deps)."
fi
# ---------------------------------------------------------------------------
# 5. Frontend assets (τοπικά — λειτουργία χωρίς Internet)
# ---------------------------------------------------------------------------
log "Έλεγχος τοπικών frontend assets…"
fetch_asset() {
    local url="$1" dest="$2" name="$3"
    if [[ -s "${dest}" ]]; then
        ok "${name} υπάρχει ήδη."
    else
        log "Λήψη ${name}…"
        if curl -fsSL --max-time 180 -o "${dest}" "${url}"; then
            ok "${name} κατέβηκε."
        else
            rm -f "${dest}"
            warn "Αποτυχία λήψης ${name} — η διεπαφή ενδέχεται να μην εμφανίζεται σωστά."
        fi
    fi
}
fetch_asset "https://cdn.jsdelivr.net/npm/alpinejs@${ALPINE_VERSION}/dist/cdn.min.js" \
            "${PORTAL_DIR}/dashboard/assets/alpine.min.js" "Alpine.js"
fetch_asset "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@${TAILWIND_VERSION}/dist/index.global.js" \
            "${PORTAL_DIR}/dashboard/assets/tailwind.min.js" "Tailwind CSS"

# ---------------------------------------------------------------------------
# 6. Pyodide (εκτέλεση Python στον browser, τοπικά)
# ---------------------------------------------------------------------------
PYODIDE_DIR="${PORTAL_DIR}/mkdocs-site/docs/assets/pyodide"
if [[ -s "${PYODIDE_DIR}/pyodide.js" ]]; then
    ok "Το Pyodide υπάρχει ήδη (${PYODIDE_DIR})."
else
    log "Λήψη Pyodide ${PYODIDE_VERSION} (~6.4 MB)…"
    TMP_PY="$(mktemp -d)"
    if curl -fsSL --max-time 600 -o "${TMP_PY}/pyodide.tar.bz2" \
        "https://github.com/pyodide/pyodide/releases/download/${PYODIDE_VERSION}/pyodide-core-${PYODIDE_VERSION}.tar.bz2"; then
        mkdir -p "${PORTAL_DIR}/mkdocs-site/docs/assets"
        tar xjf "${TMP_PY}/pyodide.tar.bz2" -C "${PORTAL_DIR}/mkdocs-site/docs/assets/"
        ok "Το Pyodide εγκαταστάθηκε τοπικά."
    else
        warn "Αποτυχία λήψης Pyodide — η εκτέλεση Python στον browser δεν θα λειτουργεί."
    fi
    rm -rf "${TMP_PY}"
fi

# ---------------------------------------------------------------------------
# 7. Δικαιώματα (setgid ώστε root & www-data να συνεργάζονται)
# ---------------------------------------------------------------------------
log "Ρύθμιση δικαιωμάτων…"
chown -R root:www-data "${PORTAL_DIR}/mkdocs-site"
find "${PORTAL_DIR}/mkdocs-site" -type d -exec chmod 2775 {} +
find "${PORTAL_DIR}/mkdocs-site" -type f -exec chmod 664 {} +

chown -R www-data:www-data "${PORTAL_DIR}/pandoc-app/data" "${PORTAL_DIR}/data" "${DOCS_OUT}"
chmod 2775 "${PORTAL_DIR}/data" "${DOCS_OUT}"
touch "${PORTAL_DIR}/data/mkdocs-build.lock"
chown root:www-data "${PORTAL_DIR}/data/mkdocs-build.lock"
chmod 664 "${PORTAL_DIR}/data/mkdocs-build.lock"

chmod 755 "${PORTAL_DIR}/scripts/"*.sh 2>/dev/null || true
chmod 755 "${PORTAL_DIR}/install.sh"
# Προστασία μυστικών
[[ -f "${PORTAL_DIR}/.env.keys" ]] && chmod 600 "${PORTAL_DIR}/.env.keys"
ok "Τα δικαιώματα ρυθμίστηκαν."

# ---------------------------------------------------------------------------
# 8. Nginx
# ---------------------------------------------------------------------------
log "Ρύθμιση Nginx…"
install -m 644 "${PORTAL_DIR}/config/nginx/school-portal" /etc/nginx/sites-available/school-portal
ln -sf /etc/nginx/sites-available/school-portal /etc/nginx/sites-enabled/school-portal
rm -f /etc/nginx/sites-enabled/default

# Basic Auth για τις περιοχές καθηγητών (χωρίς επιπλέον πακέτα)
if [[ ! -f "${HTPASSWD_FILE}" ]] || [[ "${FORCE_HTPASSWD:-0}" == "1" ]]; then
    log "Δημιουργία αρχείου Basic Auth…"
    HASH="$(printf '%s' "${TEACHER_PASS}" | openssl passwd -apr1 -stdin)"
    printf '%s:%s\n' "${TEACHER_USER}" "${HASH}" > "${HTPASSWD_FILE}"
    chown root:www-data "${HTPASSWD_FILE}"
    chmod 640 "${HTPASSWD_FILE}"
    ok "Το Basic Auth δημιουργήθηκε (χρήστης: ${TEACHER_USER})."
else
    ok "Το Basic Auth υπάρχει ήδη (FORCE_HTPASSWD=1 για αναδημιουργία)."
fi

nginx -t || die "Σφάλμα στη διαμόρφωση του Nginx."
systemctl enable nginx >/dev/null 2>&1 || true
systemctl restart nginx
ok "Ο Nginx τρέχει στη θύρα 80."

# ---------------------------------------------------------------------------
# 9. systemd services
# ---------------------------------------------------------------------------
log "Εγκατάσταση systemd υπηρεσιών…"
install -m 644 "${PORTAL_DIR}/config/systemd/school-pandoc.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-mkdocs.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-mkdocs.path"    /etc/systemd/system/
systemctl daemon-reload

systemctl enable --now school-pandoc.service
systemctl enable --now school-mkdocs.path
systemctl start school-mkdocs.service
ok "Οι υπηρεσίες ενεργοποιήθηκαν."

# ---------------------------------------------------------------------------
# 10. Ανακατασκευή εκπαιδευτικού υλικού
# ---------------------------------------------------------------------------
log "Ανακατασκευή εκπαιδευτικού υλικού…"
bash "${PORTAL_DIR}/scripts/build-docs.sh"
ok "Το εκπαιδευτικό υλικό είναι έτοιμο στο ${DOCS_OUT}."
# ---------------------------------------------------------------------------
# 11. Smoke test — επαλήθευση στη θύρα 80
# ---------------------------------------------------------------------------
log "Έλεγχος λειτουργίας (smoke test)…"
sleep 2
FAILED=0

check_url() {
    local path="$1" expect="$2" auth="${3:-}"
    local code
    if [[ -n "${auth}" ]]; then
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -u "${auth}" "http://127.0.0.1${path}" || echo 000)"
    else
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "http://127.0.0.1${path}" || echo 000)"
    fi
    if [[ "${code}" == "${expect}" ]]; then
        printf '    %s✓%s %-42s %s\n' "${C_OK}" "${C_OFF}" "${path}" "${code}"
    else
        printf '    %s✗%s %-42s %s (αναμενόταν %s)\n' "${C_ERR}" "${C_OFF}" "${path}" "${code}" "${expect}"
        FAILED=$((FAILED + 1))
    fi
}

check_url "/"                        200
check_url "/healthz"                 200
check_url "/assets/portal.js"        200
check_url "/docs/"                   200
check_url "/docs/gymnasio-a/"        200
check_url "/docs/lykeio-g/"          200
check_url "/docs/games/binary-game.html" 200
check_url "/lab/"                    200
check_url "/pandoc/"                 401
check_url "/pandoc/"                 200 "${TEACHER_USER}:${TEACHER_PASS}"
check_url "/docs/teachers/"          401
check_url "/docs/teachers/"          200 "${TEACHER_USER}:${TEACHER_PASS}"

echo
if [[ "${FAILED}" -eq 0 ]]; then
    ok "Όλοι οι έλεγχοι πέρασαν επιτυχώς!"
else
    warn "${FAILED} έλεγχοι απέτυχαν — δες: journalctl -u school-pandoc.service -n 50"
fi

# ---------------------------------------------------------------------------
# 12. Σύνοψη
# ---------------------------------------------------------------------------
IP_ADDR="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "${IP_ADDR}" ]] && IP_ADDR="localhost"

RAM_USED="$(systemctl show school-pandoc.service -p MemoryCurrent --value 2>/dev/null || echo 0)"
RAM_MB="$(( ${RAM_USED:-0} / 1048576 ))"

echo
echo "==========================================================="
echo "  ${C_OK}✅ Η εγκατάσταση ολοκληρώθηκε!${C_OFF}"
echo "==========================================================="
echo
echo "  🌐 Κεντρική Πύλη:      http://${IP_ADDR}/"
echo "  📚 Εκπαιδευτικό Υλικό: http://${IP_ADDR}/docs/"
echo "  🎮 Παιχνίδι Δυαδικού:  http://${IP_ADDR}/docs/games/binary-game.html"
echo "  🗓️  Εργαστήριο:         http://${IP_ADDR}/lab/  (υπό κατασκευή)"
echo "  📝 Pandoc Studio:      http://${IP_ADDR}/pandoc/"
echo "  🗝️  Λύσεις Καθηγητή:    http://${IP_ADDR}/docs/teachers/"
echo
echo "  🔐 Πρόσβαση καθηγητών:"
echo "     Dashboard:  κωδικός ${TEACHER_PASS}"
echo "     Basic Auth: ${TEACHER_USER} / ${TEACHER_PASS}"
echo
echo "  💾 Κατανάλωση RAM (Pandoc Studio): ~${RAM_MB} MB"
echo "     Το /docs/ είναι static → 0 MB σε ηρεμία."
echo
echo "  🛠️  Χρήσιμες εντολές:"
echo "     systemctl status school-pandoc.service"
echo "     systemctl start school-mkdocs.service    # rebuild υλικού"
echo "     journalctl -u school-pandoc.service -f"
echo "     sudo ${PORTAL_DIR}/install.sh --update   # ενημέρωση"
echo