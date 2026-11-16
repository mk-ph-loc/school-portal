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

# --- Διαδραστικά Εργαστήρια (static, 0 MB RAM στον server) ---
CIRCUITJS_BASE="https://www.falstad.com/circuit"          # επίσημο στατικό build του pfalstad/circuitjs1
CIRCUITJS_BUNDLE="circuitjs116"                            # φάκελος hashed Vite bundle (άλλαξε αν ενημερωθεί το upstream)
CIRCUITJS_JS="circuitjs-D4ylC0oc.js"
CIRCUITJS_CSS="circuitjs-C9R-4DXA.css"
BLOCKLY_BASE="https://blockly-games.appspot.com"           # επίσημο static deployment των Google Blockly Games
SQLJS_VERSION="1.13.0"
PDFLIB_VERSION="1.17.1"
FONTKIT_VERSION="1.1.1"
ACE_VERSION="1.32.0"                                       # ίδιο με το ace build του Blockly Games

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

# --- Συνεργατικά εργαλεία τάξης (Node.js LTS, χωρίς Docker) ---
NODE_MAJOR="22"                                            # NodeSource LTS (Debian 13)
ETHERPAD_VERSION="v2.7.3"                                  # τελευταία stable που υποστηρίζει Node 22
ETHERPAD_DIR="${PORTAL_DIR}/apps/etherpad"
ETHERPAD_PORT="8006"
PNPM_VERSION="11.0.6"                                      # όπως δηλώνει το packageManager του Etherpad

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
        curl ca-certificates bzip2 tar openssl rsync unzip util-linux \
        git build-essential
    ok "Τα πακέτα συστήματος είναι έτοιμα."

    # --- Node.js LTS (NodeSource) για το Etherpad Lite ---
    NODE_OK=0
    if command -v node >/dev/null 2>&1; then
        NODE_CUR_MAJOR="$(node --version | sed 's/^v//;s/\..*//')"
        if [[ "${NODE_CUR_MAJOR}" == "20" || "${NODE_CUR_MAJOR}" == "22" ]]; then
            NODE_OK=1
            ok "Το Node.js $(node --version) (LTS) υπάρχει ήδη."
        fi
    fi
    if [[ "${NODE_OK}" == "0" ]]; then
        log "Εγκατάσταση Node.js ${NODE_MAJOR} LTS από το NodeSource (Debian 13)…"
        if curl -fsSL --retry 3 --max-time 120 "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource_setup.sh \
            && bash /tmp/nodesource_setup.sh >/dev/null 2>&1 \
            && apt-get install -y nodejs; then
            ok "Το Node.js $(node --version) εγκαταστάθηκε."
        else
            warn "Αποτυχία εγκατάστασης Node.js — το /pad/ (Etherpad) δεν θα λειτουργεί."
        fi
        rm -f /tmp/nodesource_setup.sh
    fi
else
    warn "Παράλειψη apt (--no-deps)."
fi

# ---------------------------------------------------------------------------
# 3. Δομή φακέλων
# ---------------------------------------------------------------------------
log "Δημιουργία δομής φακέλων…"
mkdir -p "${PORTAL_DIR}"/{dashboard/assets,dashboard/lab,mkdocs-site/docs,pandoc-app/{templates,static,data/templates,data/uploads},exams-app/{submissions,static,templates},live-quiz-app/{static,templates},app-builder/{static,templates},lab-app,custom-apps/_template,apps,config/{nginx,systemd,etherpad},scripts,data/build,data/filebrowser,shared-files}
mkdir -p "${DOCS_OUT}" "${TOOLS_OUT}"/{cyberchef,it-tools,board,circuits,blockly,sql/vendor,pdf-tools/vendor/fonts}
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
# 5β. Δικές μου εφαρμογές (custom-apps/) — manifest για το Dashboard
#     Σαρώνει τα app.json των υποφακέλων (αγνοεί το _template) και παράγει
#     το custom-apps/apps-manifest.json. Οδηγός: CUSTOM-APPS-GUIDE.md
# ---------------------------------------------------------------------------
log "Ενημέρωση manifest δικών μου εφαρμογών (custom-apps/)…"
if python3 "${PORTAL_DIR}/scripts/build-apps-manifest.py"; then
    ok "Το apps-manifest.json ενημερώθηκε."
else
    warn "Μη έγκυρα app.json στο custom-apps/ — διόρθωσέ τα και τρέξε: python3 scripts/build-apps-manifest.py"
fi

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
# 6δ. Ψηφιακός Πίνακας Excalidraw — πλήρες static build στο /board/ (0 MB RAM)
#     Κατεβαίνει το επίσημο excalidraw-app build (βιβλιοθήκες σχημάτων,
#     εξαγωγή PNG/SVG/JSON, dark/light mode) και προσαρμόζεται για ελληνικά
#     & τοπικά assets. FORCE_EXCALIDRAW=1 για αναβάθμιση σε νέο upstream build.
# ---------------------------------------------------------------------------
if [[ -x "${PORTAL_DIR}/scripts/fetch-excalidraw.sh" ]]; then
    if FORCE="${FORCE_EXCALIDRAW:-0}" bash "${PORTAL_DIR}/scripts/fetch-excalidraw.sh" "${TOOLS_OUT}/board"; then
        ok "Ο Ψηφιακός Πίνακας Excalidraw είναι έτοιμος στο /board/."
    else
        warn "Αποτυχία λήψης Excalidraw — το /board/ ενδέχεται να μην λειτουργεί."
    fi
else
    warn "Δεν βρέθηκε scripts/fetch-excalidraw.sh — το /board/ δεν θα ενημερωθεί."
fi

# ---------------------------------------------------------------------------
# 6ε. CircuitJS1 — προσομοιωτής ηλεκτρονικών κυκλωμάτων στο /circuits/
#     Στατικό build (HTML/JS/CSS + έτοιμα κυκλώματα) από το επίσημο site
#     του pfalstad/circuitjs1. Δεν υπάρχει release zip → mirror των αρχείων.
# ---------------------------------------------------------------------------
if [[ -s "${TOOLS_OUT}/circuits/${CIRCUITJS_BUNDLE}/${CIRCUITJS_JS}" ]]; then
    ok "Το CircuitJS1 υπάρχει ήδη (${TOOLS_OUT}/circuits)."
else
    log "Λήψη CircuitJS1 (στατικό web build, ~2 MB + κυκλώματα)…"
    CJ="${TOOLS_OUT}/circuits"
    mkdir -p "${CJ}/${CIRCUITJS_BUNDLE}/font" "${CJ}/${CIRCUITJS_BUNDLE}/circuits" \
             "${CJ}/circuitjs1/img/subcircuits" "${CJ}/font"
    if curl -fsSL --retry 3 --max-time 120 -o "${CJ}/circuitjs.html" "${CIRCUITJS_BASE}/circuitjs.html"; then
        # Αφαίρεση εξωτερικού Dropbox script & διόρθωση manifest path
        sed -i '/dropbox/d; s|href="/circuit/manifest.json"|href="manifest.json"|' "${CJ}/circuitjs.html"
        for f in "${CIRCUITJS_JS}" "${CIRCUITJS_CSS}" setuplist.txt; do
            curl -fsSL --retry 3 --max-time 300 -o "${CJ}/${CIRCUITJS_BUNDLE}/${f}" \
                "${CIRCUITJS_BASE}/${CIRCUITJS_BUNDLE}/${f}" || warn "Αποτυχία λήψης ${f}."
        done
        for f in fontello.css fontello.eot fontello.woff2 fontello.woff fontello.ttf fontello.svg; do
            curl -fsSL --retry 2 --max-time 120 -o "${CJ}/${CIRCUITJS_BUNDLE}/font/${f}" \
                "${CIRCUITJS_BASE}/${CIRCUITJS_BUNDLE}/font/${f}" || warn "Αποτυχία λήψης font/${f}."
        done
        # Βοηθητικές σελίδες (About, υποκυκλώματα, calculators) & εικονίδια PWA
        for f in iframe.html manifest.json about.html crystal.html customfunction.html \
                 customlogic.html customtransformer.html diodecalc.html mosfet-beta.html \
                 opampreal.html subcircuits.html icon512.png icon1024.png; do
            curl -fsSL --retry 2 --max-time 60 -o "${CJ}/${f}" "${CIRCUITJS_BASE}/${f}" || true
        done
        [[ -f "${CJ}/about.html" ]] && sed -i '/flagcounter/d' "${CJ}/about.html"
        curl -fsSL --max-time 60 -o "${CJ}/font/webfontlicense.html" "${CIRCUITJS_BASE}/font/webfontlicense.html" || true
        # Έτοιμα εκπαιδευτικά κυκλώματα από τη setuplist.txt (μενού Circuits)
        awk '{for(i=1;i<=NF;i++) if($i ~ /^[a-zA-Z0-9_-]+\.txt$/) print $i}' \
            "${CJ}/${CIRCUITJS_BUNDLE}/setuplist.txt" | sort -u | while read -r c; do
            curl -fsSL --retry 2 --max-time 60 -o "${CJ}/${CIRCUITJS_BUNDLE}/circuits/${c}" \
                "${CIRCUITJS_BASE}/${CIRCUITJS_BUNDLE}/circuits/${c}" || rm -f "${CJ}/${CIRCUITJS_BUNDLE}/circuits/${c}"
        done
        curl -fsSL --max-time 60 -o "${CJ}/${CIRCUITJS_BUNDLE}/circuits/blank.txt" \
            "${CIRCUITJS_BASE}/${CIRCUITJS_BUNDLE}/circuits/blank.txt" || true
        # Manifest PWA → scope /circuits/
        python3 - "${CJ}/manifest.json" <<'PYEOF' || true
import json, sys
p = sys.argv[1]
m = json.load(open(p))
m["start_url"] = "/circuits/circuitjs.html"
m["scope"] = "/circuits/"
for i in m.get("icons", []):
    i["src"] = i["src"].replace("/circuit/", "/circuits/")
json.dump(m, open(p, "w"), indent=2)
PYEOF
        ok "Το CircuitJS1 εγκαταστάθηκε στο /circuits/."
    else
        warn "Αποτυχία λήψης CircuitJS1 — το /circuits/ δεν θα λειτουργεί."
    fi
fi
# Ελληνικό wrapper με μπάρα πλοήγησης (πηγή στο config/circuits/)
if [[ -s "${PORTAL_DIR}/config/circuits/index.html" ]]; then
    install -m 644 "${PORTAL_DIR}/config/circuits/index.html" "${TOOLS_OUT}/circuits/index.html"
fi

# ---------------------------------------------------------------------------
# 6στ. Blockly Games — εκμάθηση προγραμματισμού με μπλοκ στο /blockly/
#      Επίσημο offline static πακέτο της Google (bundles + ελληνικά msg).
# ---------------------------------------------------------------------------
if [[ -s "${TOOLS_OUT}/blockly/maze/generated/compressed.js" ]]; then
    ok "Το Blockly Games υπάρχει ήδη (${TOOLS_OUT}/blockly)."
else
    log "Λήψη Blockly Games (offline static πακέτο με ελληνικά, ~9 MB)…"
    BG="${TOOLS_OUT}/blockly"
    BG_GAMES="index puzzle maze bird turtle movie music pond/tutor pond/duck"
    mkdir -p "${BG}/common" "${BG}/third-party/JS-Interpreter" \
             "${BG}/third-party/blockly/media" "${BG}/third-party/SoundJS" \
             "${BG}/third-party/ace/ext"
    # HTML σελίδες παιχνιδιών (extensionless URLs του επίσημου deployment)
    for g in ${BG_GAMES}; do
        page="$(echo "${g}" | tr '/' '-')"
        [[ "${g}" == "index" ]] && url="${BLOCKLY_BASE}/?lang=el" || url="${BLOCKLY_BASE}/${page}?lang=el"
        curl -fsSL --retry 2 --max-time 60 -o "${BG}/${page}.html" "${url}" || warn "Αποτυχία λήψης ${page}.html."
        mkdir -p "${BG}/${g}/generated/msg"
        curl -fsSL --retry 2 --max-time 120 -o "${BG}/${g}/generated/compressed.js" \
            "${BLOCKLY_BASE}/${g}/generated/compressed.js" || warn "Αποτυχία λήψης bundle ${g}."
        for lang in el en; do
            curl -fsSL --retry 2 --max-time 60 -o "${BG}/${g}/generated/msg/${lang}.js" \
                "${BLOCKLY_BASE}/${g}/generated/msg/${lang}.js" || warn "Αποτυχία λήψης msg/${lang} (${g})."
        done
        curl -fsSL --retry 2 --max-time 60 -o "${BG}/${g}/style.css" "${BLOCKLY_BASE}/${g}/style.css" || true
    done
    curl -fsSL --max-time 60 -o "${BG}/pond/style.css" "${BLOCKLY_BASE}/pond/style.css" || true
    # Κοινά αρχεία & βιβλιοθήκες τρίτων
    for f in common/boot.js common/back.js common/common.css common/prettify.css common/prettify.js \
             common/1x1.gif common/help.png common/icons.png common/loading.gif \
             third-party/JS-Interpreter/compressed.js third-party/SoundJS/soundjs.min.js \
             third-party/babel.min.js music/notes.png index/title.svg; do
        curl -fsSL --retry 2 --max-time 180 -o "${BG}/${f}" "${BLOCKLY_BASE}/${f}" || warn "Αποτυχία λήψης ${f}."
    done
    for f in ace.js mode-javascript.js theme-chrome.js worker-javascript.js; do
        curl -fsSL --retry 2 --max-time 90 -o "${BG}/third-party/ace/${f}" \
            "${BLOCKLY_BASE}/third-party/ace/${f}" || warn "Αποτυχία λήψης ace/${f}."
    done
    curl -fsSL --retry 2 --max-time 90 -o "${BG}/third-party/ace/ext/language_tools.js" \
        "https://cdn.jsdelivr.net/npm/ace-builds@${ACE_VERSION}/src-min-noconflict/ext-language_tools.js" || true
    # Media Blockly (ήχοι/sprites)
    for f in sprites.png click.mp3 click.ogg click.wav delete.mp3 delete.ogg delete.wav \
             disconnect.mp3 disconnect.ogg disconnect.wav; do
        curl -fsSL --retry 2 --max-time 60 -o "${BG}/third-party/blockly/media/${f}" \
            "${BLOCKLY_BASE}/third-party/blockly/media/${f}" || true
    done
    # Εικόνες/ήχοι παιχνιδιών: εξαγωγή όλων των asset paths από τα bundles
    cat "${BG}"/*/generated/compressed.js "${BG}"/pond/*/generated/compressed.js 2>/dev/null \
        | grep -oE '"[a-zA-Z0-9_./-]+\.(mp3|ogg|wav|png|jpg|svg|gif)"' | tr -d '"' | sort -u \
        | while read -r a; do
            case "${a}" in */*) ;; *) continue;; esac
            mkdir -p "${BG}/$(dirname "${a}")"
            curl -fsSL --retry 2 --max-time 90 -o "${BG}/${a}" "${BLOCKLY_BASE}/${a}" || rm -f "${BG}/${a}"
        done
    # Εικονίδια παιχνιδιών στην κεντρική σελίδα
    for g in puzzle maze bird turtle movie music pond-tutor pond-duck; do
        curl -fsSL --retry 2 --max-time 60 -o "${BG}/index/${g}.png" "${BLOCKLY_BASE}/index/${g}.png" || true
    done
    # Ειδικά assets: εικόνες ζώων του Παζλ & demo πάπιες του Pond
    for f in puzzle/bee.jpg puzzle/cat.jpg puzzle/duck.jpg puzzle/snail.jpg pond/duck/default-ducks.js; do
        curl -fsSL --retry 2 --max-time 60 -o "${BG}/${f}" "${BLOCKLY_BASE}/${f}" || warn "Αποτυχία λήψης ${f}."
    done
    # Soundfonts για το παιχνίδι Μουσική (8 όργανα × 13 νότες)
    for inst in piano trumpet violin drum flute banjo guitar choir; do
        mkdir -p "${BG}/third-party/soundfonts/${inst}"
        for note in C3 D3 E3 F3 G3 A3 B3 C4 D4 E4 F4 G4 A4; do
            curl -fsSL --retry 2 --max-time 60 -o "${BG}/third-party/soundfonts/${inst}/${note}.mp3" \
                "${BLOCKLY_BASE}/third-party/soundfonts/${inst}/${note}.mp3" || rm -f "${BG}/third-party/soundfonts/${inst}/${note}.mp3"
        done
    done
    ok "Το Blockly Games εγκαταστάθηκε στο /blockly/."
fi
# Προεπιλογή ελληνικής γλώσσας (αλλάζει από το μενού γλωσσών του παιχνιδιού)
python3 - "${TOOLS_OUT}/blockly" <<'PYEOF' || true
import pathlib, sys
root = pathlib.Path(sys.argv[1])
for p in root.glob('*.html'):
    s = p.read_text(encoding='utf-8')
    if 'school-lang-default' in s:
        continue
    inject = ('<script>/* school-lang-default: προεπιλογή Ελληνικών */\n'
              "if(!/[?&]lang=/.test(location.search)){location.search+=(location.search?'&':'?')+'lang=el';}</script>\n  ")
    s = s.replace('<script src="common/boot.js"></script>', inject + '<script src="common/boot.js"></script>')
    p.write_text(s, encoding='utf-8')
PYEOF

# ---------------------------------------------------------------------------
# 6ζ. SQL Playground — εργαστήριο βάσεων δεδομένων στο /sql/ (sql.js WASM)
# ---------------------------------------------------------------------------
fetch_asset "https://cdn.jsdelivr.net/npm/sql.js@${SQLJS_VERSION}/dist/sql-wasm.js" \
            "${TOOLS_OUT}/sql/vendor/sql-wasm.js" "sql.js (SQLite WASM loader)"
fetch_asset "https://cdn.jsdelivr.net/npm/sql.js@${SQLJS_VERSION}/dist/sql-wasm.wasm" \
            "${TOOLS_OUT}/sql/vendor/sql-wasm.wasm" "sql.js (SQLite WASM binary)"
fetch_asset "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@${TAILWIND_VERSION}/dist/index.global.js" \
            "${TOOLS_OUT}/sql/vendor/tailwind.min.js" "Tailwind CSS (SQL)"
if [[ -s "${PORTAL_DIR}/config/sql/index.html" ]]; then
    install -m 644 "${PORTAL_DIR}/config/sql/index.html" "${PORTAL_DIR}/config/sql/app.js" "${TOOLS_OUT}/sql/"
    ok "Το SQL Playground εγκαταστάθηκε στο /sql/."
else
    warn "Δεν βρέθηκε config/sql/ — το /sql/ δεν θα λειτουργεί."
fi

# ---------------------------------------------------------------------------
# 6η. PDF Studio — εργαλεία PDF στον browser στο /pdf-tools/ (pdf-lib)
# ---------------------------------------------------------------------------
fetch_asset "https://cdn.jsdelivr.net/npm/pdf-lib@${PDFLIB_VERSION}/dist/pdf-lib.min.js" \
            "${TOOLS_OUT}/pdf-tools/vendor/pdf-lib.min.js" "pdf-lib"
fetch_asset "https://cdn.jsdelivr.net/npm/@pdf-lib/fontkit@${FONTKIT_VERSION}/dist/fontkit.umd.min.js" \
            "${TOOLS_OUT}/pdf-tools/vendor/fontkit.umd.min.js" "fontkit (Unicode γραμματοσειρές)"
fetch_asset "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@${TAILWIND_VERSION}/dist/index.global.js" \
            "${TOOLS_OUT}/pdf-tools/vendor/tailwind.min.js" "Tailwind CSS (PDF)"
# Γραμματοσειρά για ελληνικό υδατογράφημα/αρίθμηση: subset της DejaVu Sans
# (Greek + Latin, ~64 KB αντί ~760 KB) από τα τοπικά fonts-dejavu.
if [[ ! -s "${TOOLS_OUT}/pdf-tools/vendor/fonts/DejaVuSans-el.ttf" ]]; then
    PYFTSUBSET="$(command -v pyftsubset || true)"
    [[ -z "${PYFTSUBSET}" && -x "${VENV}/bin/pyftsubset" ]] && PYFTSUBSET="${VENV}/bin/pyftsubset"
    if [[ -s /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ]] && [[ -n "${PYFTSUBSET}" ]]; then
        "${PYFTSUBSET}" /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
            --output-file="${TOOLS_OUT}/pdf-tools/vendor/fonts/DejaVuSans-el.ttf" \
            --unicodes="U+0020-007E,U+00A0-00FF,U+0370-03FF,U+1F00-1FFF,U+2010-2027,U+20AC" \
            --layout-features='*' --name-IDs='*' --notdef-outline \
            && ok "Η ελληνική γραμματοσειρά (DejaVu subset) δημιουργήθηκε." \
            || warn "Αποτυχία subset γραμματοσειράς — δοκιμή ολόκληρης TTF."
    fi
    if [[ ! -s "${TOOLS_OUT}/pdf-tools/vendor/fonts/DejaVuSans-el.ttf" ]] \
        && [[ -s /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ]]; then
        install -m 644 /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
            "${TOOLS_OUT}/pdf-tools/vendor/fonts/DejaVuSans-el.ttf"
    fi
fi
if [[ -s "${PORTAL_DIR}/config/pdf-tools/index.html" ]]; then
    install -m 644 "${PORTAL_DIR}/config/pdf-tools/index.html" "${PORTAL_DIR}/config/pdf-tools/app.js" "${TOOLS_OUT}/pdf-tools/"
    ok "Το PDF Studio εγκαταστάθηκε στο /pdf-tools/."
else
    warn "Δεν βρέθηκε config/pdf-tools/ — το /pdf-tools/ δεν θα λειτουργεί."
fi

# ---------------------------------------------------------------------------
# 6θ. FileBrowser — single Go binary στο /share/ (~15 MB RAM)
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
# 6ι. Etherpad Lite — συνεργατικός επεξεργαστής κειμένου τάξης στο /pad/
#     Node.js + SQLite (ueberdb2), ακούει ΜΟΝΟ στο 127.0.0.1:8006 πίσω από
#     τον Nginx. Η πηγή αλήθειας των ρυθμίσεων είναι το config/etherpad/.
# ---------------------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
    if [[ ! -d "${ETHERPAD_DIR}/.git" ]]; then
        log "Λήψη Etherpad Lite ${ETHERPAD_VERSION} (~30 MB)…"
        mkdir -p "${PORTAL_DIR}/apps"
        if git clone --depth 1 --branch "${ETHERPAD_VERSION}" \
            https://github.com/ether/etherpad-lite.git "${ETHERPAD_DIR}" >/dev/null 2>&1; then
            ok "Το Etherpad Lite ${ETHERPAD_VERSION} κατέβηκε."
        else
            warn "Αποτυχία λήψης Etherpad — το /pad/ δεν θα λειτουργεί."
        fi
    else
        ok "Το Etherpad Lite υπάρχει ήδη (${ETHERPAD_DIR})."
    fi

    if [[ -f "${ETHERPAD_DIR}/package.json" ]]; then
        # pnpm (το επίσημο εργαλείο build του Etherpad 2.x)
        if ! command -v pnpm >/dev/null 2>&1; then
            log "Εγκατάσταση pnpm ${PNPM_VERSION}…"
            npm install -g "pnpm@${PNPM_VERSION}" >/dev/null 2>&1 \
                && ok "Το pnpm εγκαταστάθηκε." \
                || warn "Αποτυχία εγκατάστασης pnpm."
        fi
        # Ρυθμίσεις: 127.0.0.1:8006, SQLite, ελληνικά (από το config/etherpad/)
        if [[ -s "${PORTAL_DIR}/config/etherpad/settings.json" ]]; then
            install -m 644 "${PORTAL_DIR}/config/etherpad/settings.json" "${ETHERPAD_DIR}/settings.json"
        fi
        # Εξαρτήσεις (idempotent — το pnpm skip-άρει ό,τι υπάρχει). Χρειάζονται
        # και τα dev deps του admin/ui workspace για το χτίσιμο του admin UI.
        if command -v pnpm >/dev/null 2>&1; then
            log "Εγκατάσταση εξαρτήσεων Etherpad (pnpm)…"
            if (cd "${ETHERPAD_DIR}" && CI=true pnpm install --recursive --config.confirmModulesPurge=false >/dev/null 2>&1); then
                # esbuild: τα postinstall scripts μπλοκάρονται από default στο pnpm 10+
                (cd "${ETHERPAD_DIR}" && pnpm rebuild esbuild >/dev/null 2>&1 || true)
                ok "Οι εξαρτήσεις του Etherpad εγκαταστάθηκαν."
            else
                warn "Αποτυχία εγκατάστασης εξαρτήσεων Etherpad — το /pad/ δεν θα λειτουργεί."
            fi
            # Admin UI (Vite build → src/templates/admin/) — μία φορά, όχι σε κάθε boot
            if [[ ! -s "${ETHERPAD_DIR}/src/templates/admin/index.html" ]]; then
                log "Χτίσιμο του Etherpad admin UI…"
                if (cd "${ETHERPAD_DIR}/admin" && CI=true pnpm run build-copy >/dev/null 2>&1); then
                    ok "Το admin UI χτίστηκε."
                else
                    warn "Αποτυχία χτισίματος admin UI — το /pad/admin δεν θα λειτουργεί."
                fi
            fi
        fi
        chown -R www-data:www-data "${ETHERPAD_DIR}"
    fi
else
    warn "Δεν υπάρχει Node.js — παράλειψη Etherpad (το /pad/ δεν θα λειτουργεί)."
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

# live-quiz-app: η SQLite βάση (livequiz.db) & το .cookie-secret δημιουργούνται
# από τη διεργασία www-data μέσα στον φάκελο της εφαρμογής → setgid group-write.
chown -R root:www-data "${PORTAL_DIR}/live-quiz-app"
chmod 2775 "${PORTAL_DIR}/live-quiz-app"
if [[ -f "${PORTAL_DIR}/live-quiz-app/.cookie-secret" ]]; then
    chmod 660 "${PORTAL_DIR}/live-quiz-app/.cookie-secret"
fi
touch "${PORTAL_DIR}/data/mkdocs-build.lock"
chown root:www-data "${PORTAL_DIR}/data/mkdocs-build.lock"
chmod 664 "${PORTAL_DIR}/data/mkdocs-build.lock"

chmod 755 "${PORTAL_DIR}/scripts/"*.sh 2>/dev/null || true
chmod 755 "${PORTAL_DIR}/scripts/build-apps-manifest.py" 2>/dev/null || true
chmod 755 "${PORTAL_DIR}/install.sh"

# custom-apps: static εφαρμογές που σερβίρει ο Nginx (www-data). Ο App Builder
# Wizard δημιουργεί/διαγράφει υποφακέλους ως www-data → setgid group-write
# στον γονικό φάκελο· τα υπάρχοντα αρχεία μένουν 755/644 (ο οδηγός & ο wizard
# τηρούν τα ίδια modes). Τα αρχεία παρακολουθούνται από το git.
chown -R root:www-data "${PORTAL_DIR}/custom-apps"
find "${PORTAL_DIR}/custom-apps" -type d -exec chmod 755 {} +
find "${PORTAL_DIR}/custom-apps" -type f -exec chmod 644 {} +
chmod 2775 "${PORTAL_DIR}/custom-apps"

# app-builder: το .cookie-secret δημιουργείται από τη διεργασία www-data μέσα
# στον φάκελο της εφαρμογής → setgid group-write (όπως exams/live-quiz).
chown -R root:www-data "${PORTAL_DIR}/app-builder"
chmod 2775 "${PORTAL_DIR}/app-builder"
if [[ -f "${PORTAL_DIR}/app-builder/.cookie-secret" ]]; then
    chmod 660 "${PORTAL_DIR}/app-builder/.cookie-secret"
fi
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
install -m 644 "${PORTAL_DIR}/config/systemd/school-livequiz.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-appbuilder.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-etherpad.service" /etc/systemd/system/
systemctl daemon-reload

systemctl enable --now school-pandoc.service
systemctl enable --now school-exams.service
systemctl enable --now school-livequiz.service
systemctl enable --now school-appbuilder.service
if [[ -f "${ETHERPAD_DIR}/package.json" ]] && command -v node >/dev/null 2>&1; then
    systemctl enable --now school-etherpad.service
else
    warn "Παράλειψη school-etherpad.service (λείπει το Etherpad ή η Node.js)."
fi
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
check_url "/pad/"                    200
check_url "/pad/admin"               401
check_url "/pad/admin/"              200 "${TEACHER_USER}:${TEACHER_PASS}"
check_url "/circuits/"               200
check_url "/circuits/circuitjs.html" 200
check_url "/blockly/"                200
check_url "/blockly/maze/generated/msg/el.js" 200
check_url "/sql/"                    200
check_url "/sql/vendor/sql-wasm.wasm" 200
check_url "/pdf-tools/"              200
check_url "/pdf-tools/vendor/pdf-lib.min.js" 200
check_url "/apps/apps-manifest.json" 200
check_url "/apps/binary-converter/"  200
check_url "/apps/_template/"         404
check_url "/app-builder/"            200
check_url "/app-builder/healthz"     200
check_url "/share/"                  200
check_url "/exams/"                  200
check_url "/exams/teacher"           200
check_url "/exams/api/activities"    200
check_url "/live-quiz/"              200
check_url "/live-quiz/teacher"       200
check_url "/live-quiz/healthz"       200
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
echo "  🖍️  Πίνακας Excalidraw: http://${IP_ADDR}/board/    (πλήρες build, static, 0 MB)"
echo "  📝 Σημειωματάριο Τάξης: http://${IP_ADDR}/pad/     (Etherpad Lite + SQLite)"
echo "  ⚡ Κυκλώματα:          http://${IP_ADDR}/circuits/ (CircuitJS1, static, 0 MB)"
echo "  🧩 Blockly Games:      http://${IP_ADDR}/blockly/  (ελληνικά, static, 0 MB)"
echo "  🗄️  SQL Playground:     http://${IP_ADDR}/sql/      (SQLite WASM, static, 0 MB)"
echo "  📄 PDF Studio:         http://${IP_ADDR}/pdf-tools/ (pdf-lib, static, 0 MB)"
echo "  🚀 Δικές μου Εφαρμογές: http://${IP_ADDR}/apps/<όνομα>/ (custom-apps/, static, 0 MB)"
echo "     Παράδειγμα:         http://${IP_ADDR}/apps/binary-converter/"
echo "     Οδηγός προσθήκης:   ${PORTAL_DIR}/CUSTOM-APPS-GUIDE.md"
echo "  🧙 App Builder Wizard: http://${IP_ADDR}/app-builder/ (κωδικός ${TEACHER_PASS})"
echo "  📁 Κοινόχρηστα Αρχεία: http://${IP_ADDR}/share/    (${FB_USER} / ${FB_PASS})"
echo "  📤 Εργασίες & Τεστ:    http://${IP_ADDR}/exams/    (μαθητές χωρίς κωδικό)"
echo "     Περιβάλλον καθηγητή: http://${IP_ADDR}/exams/teacher  (κωδικός ${TEACHER_PASS})"
echo "  🎯 Live Quiz Τάξης:    http://${IP_ADDR}/live-quiz/ (είσοδος μαθητών με PIN)"
echo "     Προτζέκτορας:       http://${IP_ADDR}/live-quiz/teacher  (κωδικός ${TEACHER_PASS})"
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
echo "     systemctl status school-livequiz.service"
echo "     systemctl status school-appbuilder.service"
echo "     systemctl status school-etherpad.service"
echo "     systemctl start school-mkdocs.service    # rebuild υλικού"
echo "     journalctl -u school-pandoc.service -f"
echo "     sudo ${PORTAL_DIR}/install.sh --update   # ενημέρωση"
echo