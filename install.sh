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

# --- Εργαλεία Εργαστηρίου (static + single binary, χωρίς Docker) ---
TOOLS_OUT="/var/www/school-tools"
CYBERCHEF_VERSION="v11.5.0"
CYBERCHEF_ZIP="CyberChef_8cd426dd4f40f1423912d5fad91b578a86a65112.zip"
ITTOOLS_VERSION="v2024.10.22-7ca5933"
ITTOOLS_ZIP="it-tools-2024.10.22-7ca5933.zip"
FILEBROWSER_VERSION="v2.63.23"
FB_DB="${PORTAL_DIR}/data/filebrowser/filebrowser.db"
FB_USER="admin"
FB_PASS="${FB_PASS:-teacher2026}"

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
        curl ca-certificates bzip2 tar openssl rsync unzip util-linux
    ok "Τα πακέτα συστήματος είναι έτοιμα."
else
    warn "Παράλειψη apt (--no-deps)."
fi

# ---------------------------------------------------------------------------
# 3. Δομή φακέλων
# ---------------------------------------------------------------------------
log "Δημιουργία δομής φακέλων…"
mkdir -p "${PORTAL_DIR}"/{dashboard/assets,dashboard/lab,mkdocs-site/docs,pandoc-app/{templates,static,data/templates,data/uploads},exams-app/{submissions,static,templates},lab-app,config/{nginx,systemd},scripts,data/build,data/filebrowser,shared-files}
mkdir -p "${DOCS_OUT}" "${TOOLS_OUT}"/{cyberchef,it-tools,board}
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
# 6β. CyberChef — static HTML/JS στο /crypto/ (0 MB RAM στον server)
# ---------------------------------------------------------------------------
if [[ -s "${TOOLS_OUT}/cyberchef/index.html" ]]; then
    ok "Το CyberChef υπάρχει ήδη (${TOOLS_OUT}/cyberchef)."
else
    log "Λήψη CyberChef ${CYBERCHEF_VERSION} (~83 MB zip)…"
    TMP_CC="$(mktemp -d)"
    if curl -fsSL --retry 3 --max-time 600 -o "${TMP_CC}/cyberchef.zip" \
        "https://github.com/gchq/CyberChef/releases/download/${CYBERCHEF_VERSION}/${CYBERCHEF_ZIP}"; then
        unzip -qo "${TMP_CC}/cyberchef.zip" -d "${TOOLS_OUT}/cyberchef/"
        # Μετονομασία του κύριου CyberChef_v*.html σε index.html
        CC_HTML="$(find "${TOOLS_OUT}/cyberchef" -maxdepth 1 -name 'CyberChef_v*.html' | head -1)"
        [[ -n "${CC_HTML}" ]] && mv -f "${CC_HTML}" "${TOOLS_OUT}/cyberchef/index.html"
        ok "Το CyberChef εγκαταστάθηκε στο /crypto/."
    else
        warn "Αποτυχία λήψης CyberChef — το /crypto/ δεν θα λειτουργεί."
    fi
    rm -rf "${TMP_CC}"
fi

# ---------------------------------------------------------------------------
# 6γ. IT-Tools — static SPA στο /tools/ (0 MB RAM, χωρίς Node.js)
#     Το επίσημο dist είναι χτισμένο με base "/"· προσαρμόζεται στο /tools/.
# ---------------------------------------------------------------------------
if [[ -s "${TOOLS_OUT}/it-tools/index.html" ]]; then
    ok "Το IT-Tools υπάρχει ήδη (${TOOLS_OUT}/it-tools)."
else
    log "Λήψη IT-Tools ${ITTOOLS_VERSION} (~4 MB zip)…"
    TMP_IT="$(mktemp -d)"
    if curl -fsSL --retry 3 --max-time 300 -o "${TMP_IT}/it-tools.zip" \
        "https://github.com/CorentinTh/it-tools/releases/download/${ITTOOLS_VERSION}/${ITTOOLS_ZIP}"; then
        unzip -qo "${TMP_IT}/it-tools.zip" -d "${TMP_IT}/x"
        cp -a "${TMP_IT}/x/dist/." "${TOOLS_OUT}/it-tools/"
        # Προσαρμογή base path "/" → "/tools/" (index, router, service worker)
        IT_INDEX_JS="$(grep -l 'loadEnv({BASE_URL:"/"' "${TOOLS_OUT}/it-tools/assets/"index-*.js | head -1)"
        if [[ -n "${IT_INDEX_JS}" ]]; then
            # Router base, service worker path/scope και Vite asset URL builder
            sed -i 's|loadEnv({BASE_URL:"/"|loadEnv({BASE_URL:"/tools/"|' "${IT_INDEX_JS}"
            sed -i 's|"/sw.js"|"/tools/sw.js"|g; s|new p("/tools/sw.js",{scope:"/"|new p("/tools/sw.js",{scope:"/tools/"|' "${IT_INDEX_JS}"
            sed -i 's|function(e){return"/"+e}|function(e){return"/tools/"+e}|g' "${IT_INDEX_JS}"
            sed -i 's|"/assets/|"/tools/assets/|g' "${IT_INDEX_JS}"
        fi
        sed -i 's|"/assets/|"/tools/assets/|g; s|href="/manifest.webmanifest"|href="/tools/manifest.webmanifest"|' \
            "${TOOLS_OUT}/it-tools/index.html"
        python3 - "${TOOLS_OUT}/it-tools/manifest.webmanifest" <<'PYEOF'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
m["start_url"] = "/tools/?utm_source=pwa&utm_medium=pwa"
m["scope"] = "/tools/"
for i in m.get("icons", []):
    if i["src"].startswith("/") and not i["src"].startswith("/tools/"):
        i["src"] = "/tools" + i["src"]
json.dump(m, open(p, "w"), ensure_ascii=False)
PYEOF
        ok "Το IT-Tools εγκαταστάθηκε στο /tools/."
    else
        warn "Αποτυχία λήψης IT-Tools — το /tools/ δεν θα λειτουργεί."
    fi
    rm -rf "${TMP_IT}"
fi

# ---------------------------------------------------------------------------
# 6δ. Ψηφιακός Πίνακας Τάξης — static canvas whiteboard στο /board/
# ---------------------------------------------------------------------------
if [[ -s "${PORTAL_DIR}/config/board/index.html" ]]; then
    install -m 644 "${PORTAL_DIR}/config/board/index.html" "${TOOLS_OUT}/board/index.html"
    ok "Ο Ψηφιακός Πίνακας εγκαταστάθηκε στο /board/."
elif [[ -s "${TOOLS_OUT}/board/index.html" ]]; then
    ok "Ο Ψηφιακός Πίνακας υπάρχει ήδη."
else
    warn "Δεν βρέθηκε config/board/index.html — το /board/ δεν θα λειτουργεί."
fi

# ---------------------------------------------------------------------------
# 6ε. FileBrowser — single Go binary στο /share/ (~15 MB RAM)
# ---------------------------------------------------------------------------
if [[ -x /usr/local/bin/filebrowser ]]; then
    ok "Το filebrowser binary υπάρχει ήδη ($(/usr/local/bin/filebrowser version 2>/dev/null | head -1))."
else
    log "Λήψη FileBrowser ${FILEBROWSER_VERSION} (linux-amd64, ~16 MB)…"
    TMP_FB="$(mktemp -d)"
    if curl -fsSL --retry 3 --max-time 300 -o "${TMP_FB}/fb.tar.gz" \
        "https://github.com/filebrowser/filebrowser/releases/download/${FILEBROWSER_VERSION}/linux-amd64-filebrowser.tar.gz"; then
        tar xzf "${TMP_FB}/fb.tar.gz" -C "${TMP_FB}" filebrowser
        install -m 755 "${TMP_FB}/filebrowser" /usr/local/bin/filebrowser
        ok "Το FileBrowser εγκαταστάθηκε στο /usr/local/bin/filebrowser."
    else
        warn "Αποτυχία λήψης FileBrowser — το /share/ δεν θα λειτουργεί."
    fi
    rm -rf "${TMP_FB}"
fi

# Αρχικοποίηση βάσης (idempotent). Η βάση ζει στο data/filebrowser/ ώστε ο
# root φάκελος να παραμένει root-owned (απαραίτητο για το hardening του
# systemd)· το /opt/school-portal/filebrowser.db είναι symlink προς αυτήν.
chown www-data:www-data "${PORTAL_DIR}/data/filebrowser" "${PORTAL_DIR}/shared-files"
chmod 2775 "${PORTAL_DIR}/data/filebrowser" "${PORTAL_DIR}/shared-files"
ln -sfn data/filebrowser/filebrowser.db "${PORTAL_DIR}/filebrowser.db"
if [[ -x /usr/local/bin/filebrowser ]]; then
    if [[ ! -s "${FB_DB}" ]]; then
        log "Αρχικοποίηση βάσης FileBrowser (--baseURL /share)…"
        runuser -u www-data -- /usr/local/bin/filebrowser config init \
            --database "${FB_DB}" --address 127.0.0.1 --port 8003 \
            --baseURL /share --root "${PORTAL_DIR}/shared-files" --locale el >/dev/null
        # Ο κωδικός teacher2026 είναι 11 χαρακτήρες (< default όριο 12)
        runuser -u www-data -- /usr/local/bin/filebrowser config set \
            --database "${FB_DB}" --minimumPasswordLength 8 \
            --branding.name "Κοινόχρηστα Αρχεία Σχολείου" >/dev/null
        runuser -u www-data -- /usr/local/bin/filebrowser users add \
            "${FB_USER}" "${FB_PASS}" --perm.admin --locale el --database "${FB_DB}" >/dev/null
        ok "Η βάση δημιουργήθηκε (χρήστης: ${FB_USER})."
    else
        ok "Η βάση FileBrowser υπάρχει ήδη."
    fi
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

# exams-app: η SQLite βάση (exams.db) & το .cookie-secret δημιουργούνται από
# τη διεργασία www-data μέσα στον φάκελο της εφαρμογής → setgid group-write.
chown -R root:www-data "${PORTAL_DIR}/exams-app"
chmod 2775 "${PORTAL_DIR}/exams-app" "${PORTAL_DIR}/exams-app/submissions"
if [[ -f "${PORTAL_DIR}/exams-app/.cookie-secret" ]]; then
    chmod 660 "${PORTAL_DIR}/exams-app/.cookie-secret"
fi
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
install -m 644 "${PORTAL_DIR}/config/systemd/school-filebrowser.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-exams.service" /etc/systemd/system/
systemctl daemon-reload

systemctl enable --now school-pandoc.service
systemctl enable --now school-exams.service
systemctl enable --now school-mkdocs.path
systemctl start school-mkdocs.service
if [[ -x /usr/local/bin/filebrowser ]]; then
    systemctl enable --now school-filebrowser.service
else
    warn "Παράλειψη school-filebrowser.service (λείπει το binary)."
fi
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
check_url "/crypto/"                 200
check_url "/tools/"                  200
check_url "/board/"                  200
check_url "/share/"                  200
check_url "/exams/"                  200
check_url "/exams/teacher"           200
check_url "/exams/api/activities"    200
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
echo "  🔐 CyberChef:          http://${IP_ADDR}/crypto/   (static, 0 MB)"
echo "  🛠️  IT-Tools:           http://${IP_ADDR}/tools/    (static, 0 MB)"
echo "  🖍️  Πίνακας Τάξης:      http://${IP_ADDR}/board/    (static, 0 MB)"
echo "  📁 Κοινόχρηστα Αρχεία: http://${IP_ADDR}/share/    (${FB_USER} / ${FB_PASS})"
echo "  📤 Εργασίες & Τεστ:    http://${IP_ADDR}/exams/    (μαθητές χωρίς κωδικό)"
echo "     Περιβάλλον καθηγητή: http://${IP_ADDR}/exams/teacher  (κωδικός ${TEACHER_PASS})"
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
echo "     systemctl status school-filebrowser.service"
echo "     systemctl status school-exams.service"
echo "     systemctl start school-mkdocs.service    # rebuild υλικού"
echo "     journalctl -u school-pandoc.service -f"
echo "     sudo ${PORTAL_DIR}/install.sh --update   # ενημέρωση"
echo