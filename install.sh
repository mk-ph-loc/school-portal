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
EXCALIDRAW_ROOM_DIR="${PORTAL_DIR}/apps/excalidraw-room"   # self-hosted collab για το /board/
EXCALIDRAW_ROOM_PORT="8010"                                # (8007 = HedgeDoc, 8009 = MD-Bridge)
HEDGEDOC_VERSION="1.12.0"                                  # τελευταία stable 1.x (config.json + SQLite)
HEDGEDOC_DIR="${PORTAL_DIR}/apps/hedgedoc"                 # συνεργατικό Markdown στο /md-pad/
HEDGEDOC_PORT="8007"
MDBRIDGE_DIR="${PORTAL_DIR}/apps/hedgedoc-bridge"          # γέφυρα δημοσίευσης στο /md-publish/
MDBRIDGE_PORT="8009"
LESSONWIZARD_DIR="${PORTAL_DIR}/apps/lesson-wizard"        # ημερήσια μαθήματα στο /lesson-wizard/
LESSONWIZARD_PORT="8013"
CLASSROOM_DIR="${PORTAL_DIR}/apps/classroom-hub"           # ζωντανή τάξη στο /classroom/
CLASSROOM_PORT="8014"                                      # παρουσία, εντολές, timers ωραρίου

# --- Εργαστήριο Web HTML/CSS/JS (FastAPI + WebSockets + SQLite, χωρίς Docker) ---
WEBLAB_DIR="${PORTAL_DIR}/web-lab"                         # συνεργατικός editor στο /web-lab/
WEBLAB_PORT="8011"                                         # (8010 = excalidraw-room /board-ws/)
CODEMIRROR_VERSION="5.65.16"                               # τοπικός editor — 100% offline

# --- H5P Studio Διαδραστικών Ασκήσεων (FastAPI + SQLite, χωρίς Docker) ---
H5P_DIR="${PORTAL_DIR}/h5p-studio"                         # visual editor + offline player στο /h5p-studio/
H5P_PORT="8012"                                            # (8011 = Web Lab /web-lab/)

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
mkdir -p "${PORTAL_DIR}"/{dashboard/assets,dashboard/lab,mkdocs-site/docs,pandoc-app/{templates,static,data/templates,data/uploads},exams-app/{submissions,static,templates},live-quiz-app/{static,templates},app-builder/{static,templates},apps/hedgedoc-bridge/templates,web-lab/{static,templates},h5p-studio/{static,templates,library,h5p-libraries,backups},lab-app,custom-apps/_template,apps,config/{nginx,systemd,etherpad},scripts,data/build,data/filebrowser,shared-files}
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
            fastapi "uvicorn[standard]" python-multipart weasyprint jinja2 qrcode
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

# --- Vendor βιβλιοθήκες MkDocs (MathJax / Mermaid / Reveal.js — 100% τοπικά) ---
VENDOR_DIR="${PORTAL_DIR}/mkdocs-site/docs/assets/vendor"
mkdir -p "${VENDOR_DIR}"/{mermaid,mathjax,reveal/theme,reveal/plugin/highlight}
fetch_asset "https://cdn.jsdelivr.net/npm/mermaid@11.12.1/dist/mermaid.min.js" \
            "${VENDOR_DIR}/mermaid/mermaid.min.js" "Mermaid 11 (διαγράμματα)"
fetch_asset "https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg-full.js" \
            "${VENDOR_DIR}/mathjax/tex-svg-full.js" "MathJax 3 (μαθηματικά)"
fetch_asset "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.js" \
            "${VENDOR_DIR}/reveal/reveal.js" "Reveal.js (slides)"
fetch_asset "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/reveal.css" \
            "${VENDOR_DIR}/reveal/reveal.css" "Reveal.css"
fetch_asset "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/theme/white.css" \
            "${VENDOR_DIR}/reveal/theme/white.css" "Reveal theme white"
fetch_asset "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/dist/theme/black.css" \
            "${VENDOR_DIR}/reveal/theme/black.css" "Reveal theme black"
fetch_asset "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/plugin/highlight/highlight.js" \
            "${VENDOR_DIR}/reveal/plugin/highlight/highlight.js" "Reveal highlight plugin"
fetch_asset "https://cdn.jsdelivr.net/npm/reveal.js@5.2.1/plugin/highlight/monokai.css" \
            "${VENDOR_DIR}/reveal/plugin/highlight/monokai.css" "Reveal monokai.css"
# Το πλωτό μενού πλοήγησης σερβίρεται και μέσα από το MkDocs (extra_javascript).
cp -f "${PORTAL_DIR}/dashboard/assets/portal-nav.js" \
      "${PORTAL_DIR}/mkdocs-site/docs/assets/javascripts/portal-nav.js" 2>/dev/null || true
# GIF animation για τη σελίδα «Παράδειγμα Δυνατοτήτων» (Pillow, idempotent).
if [[ -x "${PORTAL_DIR}/venv/bin/python" && -f "${PORTAL_DIR}/scripts/make-demo-assets.py" ]]; then
    "${PORTAL_DIR}/venv/bin/python" "${PORTAL_DIR}/scripts/make-demo-assets.py" >/dev/null 2>&1 || true
fi

# --- CodeMirror 5 για το /web-lab/ (έρχεται από το git· εδώ μόνο fallback) ---
CM_DIR="${WEBLAB_DIR}/static/vendor/codemirror"
CM_BASE="https://cdnjs.cloudflare.com/ajax/libs/codemirror/${CODEMIRROR_VERSION}"
mkdir -p "${CM_DIR}"/{mode/xml,mode/css,mode/javascript,mode/htmlmixed,addon/edit,addon/fold,theme}
for cm_file in codemirror.min.js codemirror.min.css \
               mode/xml/xml.min.js mode/css/css.min.js mode/javascript/javascript.min.js \
               mode/htmlmixed/htmlmixed.min.js addon/edit/closetag.min.js \
               addon/edit/closebrackets.min.js addon/edit/matchbrackets.min.js \
               addon/edit/matchtags.min.js addon/fold/xml-fold.min.js \
               theme/material-darker.min.css theme/eclipse.min.css; do
    fetch_asset "${CM_BASE}/${cm_file}" "${CM_DIR}/${cm_file}" "CodeMirror ${cm_file}"
done

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
# 6ε. Basthon — offline εργαστήριο Python & Turtle στο /apps/basthon/
#     Το static console έρχεται από το git· εδώ μόνο τα τοπικά Pyodide
#     binaries (~57 MB, εκτός git). Idempotent: τρέχει μόνο αν λείπει το
#     marker .complete (όπως το βήμα 6 του Pyodide). FORCE=1 για override.
# ---------------------------------------------------------------------------
if [[ -x "${PORTAL_DIR}/scripts/fetch-basthon-pyodide.py" ]]; then
    if python3 "${PORTAL_DIR}/scripts/fetch-basthon-pyodide.py"; then
        ok "Το εργαστήριο Python Basthon είναι έτοιμο στο /apps/basthon/ (local Pyodide)."
    else
        warn "Αποτυχία λήψης Pyodide για το Basthon — το /apps/basthon/ δεν θα λειτουργεί offline."
    fi
else
    warn "Δεν βρέθηκε scripts/fetch-basthon-pyodide.py — το /apps/basthon/ δεν θα ενημερωθεί."
fi

# ---------------------------------------------------------------------------
# 6στ. CircuitJS1 — προσομοιωτής ηλεκτρονικών κυκλωμάτων στο /circuits/
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
# 6ζ. Blockly Games — εκμάθηση προγραμματισμού με μπλοκ στο /blockly/
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
# 6η. SQL Playground — εργαστήριο βάσεων δεδομένων στο /sql/ (sql.js WASM)
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
# 6θ. PDF Studio — εργαλεία PDF στον browser στο /pdf-tools/ (pdf-lib)
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
# 6ι. FileBrowser — single Go binary στο /share/ (~15 MB RAM)
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
# 6ια. Etherpad Lite — συνεργατικός επεξεργαστής κειμένου τάξης στο /pad/
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
# 6ιβ. Excalidraw Room Server — self-hosted ζωντανή συνεργασία πίνακα (/board-ws/)
#      Node.js + Socket.IO @127.0.0.1:8010, stateless (in-memory rooms, κανένα
#      δεδομένο στον δίσκο — αναμετάδοση end-to-end encrypted blobs μόνο).
#      Το static build του /board/ patchάρεται από το fetch-excalidraw.sh ώστε
#      να συνδέεται εδώ αντί για το oss-collab.excalidraw.com → 100% LAN/offline.
# ---------------------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
    if [[ ! -d "${EXCALIDRAW_ROOM_DIR}/.git" ]]; then
        log "Λήψη excalidraw-room (collaboration server, ~2 MB)…"
        mkdir -p "${PORTAL_DIR}/apps"
        if git clone --depth 1 https://github.com/excalidraw/excalidraw-room.git \
            "${EXCALIDRAW_ROOM_DIR}" >/dev/null 2>&1; then
            ok "Το excalidraw-room κατέβηκε."
        else
            warn "Αποτυχία λήψης excalidraw-room — η συνεργασία του /board/ θα χρησιμοποιεί τον δημόσιο server."
        fi
    else
        ok "Το excalidraw-room υπάρχει ήδη (${EXCALIDRAW_ROOM_DIR})."
    fi

    if [[ -f "${EXCALIDRAW_ROOM_DIR}/package.json" && ! -s "${EXCALIDRAW_ROOM_DIR}/dist/index.js" ]]; then
        log "Χτίσιμο excalidraw-room (npm + tsc)…"
        if (cd "${EXCALIDRAW_ROOM_DIR}" \
            && npm install --omit=dev >/dev/null 2>&1 \
            && npm install --no-save typescript@4.2.3 @types/node@14.14.31 @types/express@4.17.11 @types/debug@4.1.5 >/dev/null 2>&1 \
            && npx tsc >/dev/null 2>&1); then
            ok "Το excalidraw-room χτίστηκε (dist/index.js)."
        else
            warn "Αποτυχία χτισίματος excalidraw-room — το /board-ws/ δεν θα λειτουργεί."
        fi
    fi
    [[ -d "${EXCALIDRAW_ROOM_DIR}" ]] && chown -R www-data:www-data "${EXCALIDRAW_ROOM_DIR}"
else
    warn "Δεν υπάρχει Node.js — παράλειψη excalidraw-room."
fi

# ---------------------------------------------------------------------------
# 6ιγ. HedgeDoc — συνεργατικό Markdown τάξης στο /md-pad/ (ΧΩΡΙΣ Docker)
#      Επίσημο release tarball (προ-χτισμένο frontend) + yarn production deps.
#      Node.js + SQLite @127.0.0.1:8007. Ανώνυμη ελεύθερη επεξεργασία (freely),
#      FreeURL aliases, τοπικά uploads & ελληνικό πρότυπο δυνατοτήτων.
# ---------------------------------------------------------------------------
if command -v node >/dev/null 2>&1; then
    if [[ ! -f "${HEDGEDOC_DIR}/app.js" ]]; then
        log "Λήψη HedgeDoc ${HEDGEDOC_VERSION} (επίσημο release tarball, ~64 MB)…"
        mkdir -p "${HEDGEDOC_DIR}"
        TARBALL="${HEDGEDOC_DIR}/hedgedoc-${HEDGEDOC_VERSION}.tar.gz"
        if curl -fsSL --retry 3 --max-time 600 \
            "https://github.com/hedgedoc/hedgedoc/releases/download/${HEDGEDOC_VERSION}/hedgedoc-${HEDGEDOC_VERSION}.tar.gz" \
            -o "${TARBALL}"; then
            # Το tarball περιέχει φάκελο hedgedoc/ → εξαγωγή απευθείας στο HEDGEDOC_DIR
            tar xzf "${TARBALL}" -C "${HEDGEDOC_DIR}" --strip-components=1
            ok "Το HedgeDoc ${HEDGEDOC_VERSION} κατέβηκε."
        else
            rm -f "${TARBALL}"
            warn "Αποτυχία λήψης HedgeDoc — το /md-pad/ δεν θα λειτουργεί."
        fi
    else
        ok "Το HedgeDoc υπάρχει ήδη (${HEDGEDOC_DIR})."
    fi

    if [[ -f "${HEDGEDOC_DIR}/package.json" ]]; then
        # config.json: 127.0.0.1:8007, urlPath md-pad, SQLite, freely (idempotent —
        # δημιουργείται ΜΟΝΟ αν λείπει, ώστε να μη χαλάει το sessionSecret/ρυθμίσεις)
        if [[ ! -s "${HEDGEDOC_DIR}/config.json" ]]; then
            log "Δημιουργία config.json για το HedgeDoc…"
            HD_SECRET="$(openssl rand -hex 64)"
            cat > "${HEDGEDOC_DIR}/config.json" <<HD_CFG
{
  "production": {
    "domain": "$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)",
    "urlPath": "md-pad",
    "protocolUseSSL": false,
    "useCDN": false,
    "host": "127.0.0.1",
    "port": ${HEDGEDOC_PORT},
    "loglevel": "warn",
    "urlAddPort": false,
    "db": { "dialect": "sqlite", "storage": "${HEDGEDOC_DIR}/hedgedoc.sqlite" },
    "allowAnonymous": true,
    "allowAnonymousEdits": true,
    "allowFreeURL": true,
    "defaultPermission": "freely",
    "enableUploads": "all",
    "imageUploadType": "filesystem",
    "uploadsPath": "${HEDGEDOC_DIR}/public/uploads",
    "defaultNotePath": "${HEDGEDOC_DIR}/welcome.md",
    "docsPath": "./public/docs",
    "sessionName": "hedgedoc.sid",
    "sessionSecret": "${HD_SECRET}",
    "cookiePolicy": "lax",
    "hsts": { "enable": false },
    "csp": { "enable": true, "addDefaults": true, "upgradeInsecureRequests": false, "allowFraming": true, "allowPDFEmbed": true },
    "email": false,
    "allowEmailRegister": false
  }
}
HD_CFG
            ok "Το config.json δημιουργήθηκε."
        fi
        # Πρότυπα: welcome (default note κάθε νέας σημείωσης) & template-demo
        # (έτοιμο προς αντιγραφή + αυτόματο φόρτωμα στο /md-pad/template-demo).
        # Πηγή αλήθειας: config/hedgedoc/ (git) → apps/hedgedoc/ (runtime).
        if [[ -s "${PORTAL_DIR}/config/hedgedoc/welcome.md" ]]; then
            cp "${PORTAL_DIR}/config/hedgedoc/welcome.md" "${HEDGEDOC_DIR}/welcome.md"
            cp "${PORTAL_DIR}/config/hedgedoc/welcome.md" "${HEDGEDOC_DIR}/public/default.md"
        fi
        if [[ -s "${PORTAL_DIR}/config/hedgedoc/template-demo.md" ]]; then
            cp "${PORTAL_DIR}/config/hedgedoc/template-demo.md" "${HEDGEDOC_DIR}/template-demo.md"
            cp "${PORTAL_DIR}/config/hedgedoc/template-demo.md" "${HEDGEDOC_DIR}/public/docs/template-demo.md"
        fi
        # QR code επίδειξης (τοπικός, χωρίς εξωτερική υπηρεσία)
        if [[ ! -s "${HEDGEDOC_DIR}/public/uploads/demo-qr.png" ]] && "${VENV}/bin/python" -c 'import qrcode' 2>/dev/null; then
            HD_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
            [[ -z "${HD_IP}" ]] && HD_IP="localhost"
            "${VENV}/bin/python" - "${HD_IP}" "${HEDGEDOC_DIR}/public/uploads/demo-qr.png" <<'QR_PY'
import sys, qrcode
qrcode.make(f'http://{sys.argv[1]}/md-pad/template-demo', box_size=8, border=2).save(sys.argv[2])
QR_PY
        fi
        # Εξαρτήσεις production via yarn (corepack — όπως ορίζει το bin/setup)
        if [[ ! -d "${HEDGEDOC_DIR}/node_modules" ]]; then
            log "Εγκατάσταση εξαρτήσεων HedgeDoc (yarn workspaces focus --production)…"
            corepack enable >/dev/null 2>&1 || npm install -g corepack >/dev/null 2>&1 || true
            if (cd "${HEDGEDOC_DIR}" && COREPACK_ENABLE_DOWNLOAD_PROMPT=0 yarn workspaces focus --production >/dev/null 2>&1); then
                ok "Οι εξαρτήσεις του HedgeDoc εγκαταστάθηκαν."
            else
                warn "Αποτυχία εγκατάστασης εξαρτήσεων HedgeDoc — το /md-pad/ δεν θα λειτουργεί."
            fi
        fi
        mkdir -p "${HEDGEDOC_DIR}/public/uploads"
        chown -R www-data:www-data "${HEDGEDOC_DIR}"
        chmod 750 "${HEDGEDOC_DIR}"
        [[ -f "${HEDGEDOC_DIR}/config.json" ]] && chmod 640 "${HEDGEDOC_DIR}/config.json"
        chmod 2775 "${HEDGEDOC_DIR}/public/uploads"
    fi
else
    warn "Δεν υπάρχει Node.js — παράλειψη HedgeDoc (το /md-pad/ δεν θα λειτουργεί)."
fi

# ---------------------------------------------------------------------------
# 6ιδ. Γέφυρα Δημοσίευσης HedgeDoc → MkDocs (/md-publish/, FastAPI @8009)
#      Ο κώδικας (apps/hedgedoc-bridge/) έρχεται από το git· εδώ μόνο το
#      .cookie-secret ownership & τα δικαιώματα (όπως στο app-builder).
# ---------------------------------------------------------------------------
if [[ -f "${MDBRIDGE_DIR}/app.py" ]]; then
    chown -R root:www-data "${MDBRIDGE_DIR}"
    chmod 2775 "${MDBRIDGE_DIR}"
    if [[ -f "${MDBRIDGE_DIR}/.cookie-secret" ]]; then
        chown www-data:www-data "${MDBRIDGE_DIR}/.cookie-secret"
        chmod 600 "${MDBRIDGE_DIR}/.cookie-secret"
    fi
    ok "Η γέφυρα MD-Publish είναι έτοιμη."
else
    warn "Λείπει το apps/hedgedoc-bridge/app.py — το /md-publish/ δεν θα λειτουργεί."
fi

# ---------------------------------------------------------------------------
# 6ιε. Lesson Wizard — Ημερήσια Μαθήματα (/lesson-wizard/, FastAPI @8013)
#      Ο κώδικας (apps/lesson-wizard/) έρχεται από το git· εδώ μόνο τα
#      δικαιώματα φακέλων data/backups & .cookie-secret (όπως στο md-bridge).
# ---------------------------------------------------------------------------
if [[ -f "${LESSONWIZARD_DIR}/app.py" ]]; then
    chown -R root:www-data "${LESSONWIZARD_DIR}"
    chmod 2775 "${LESSONWIZARD_DIR}"
    for sub in data backups; do
        mkdir -p "${LESSONWIZARD_DIR}/${sub}"
        chown www-data:www-data "${LESSONWIZARD_DIR}/${sub}"
        chmod 2775 "${LESSONWIZARD_DIR}/${sub}"
    done
    if [[ -f "${LESSONWIZARD_DIR}/.cookie-secret" ]]; then
        chown www-data:www-data "${LESSONWIZARD_DIR}/.cookie-secret"
        chmod 600 "${LESSONWIZARD_DIR}/.cookie-secret"
    fi
    ok "Το Lesson Wizard είναι έτοιμο."
else
    warn "Λείπει το apps/lesson-wizard/app.py — το /lesson-wizard/ δεν θα λειτουργεί."
fi

# ---------------------------------------------------------------------------
# 6ιστ. Classroom Hub — Ζωντανή Τάξη (/classroom/, FastAPI + WS @8014)
#      Παρουσία guest/μαθητή/καθηγητή, εντολές τάξης, timers ωραρίου,
#      ενιαίο Excel ρυθμίσεων. Δικαιώματα όπως στο lesson-wizard.
# ---------------------------------------------------------------------------
if [[ -f "${CLASSROOM_DIR}/app.py" ]]; then
    chown -R root:www-data "${CLASSROOM_DIR}"
    chmod 2775 "${CLASSROOM_DIR}"
    mkdir -p "${CLASSROOM_DIR}/data"
    chown www-data:www-data "${CLASSROOM_DIR}/data"
    chmod 2775 "${CLASSROOM_DIR}/data"
    if [[ -f "${CLASSROOM_DIR}/.cookie-secret" ]]; then
        chown www-data:www-data "${CLASSROOM_DIR}/.cookie-secret"
        chmod 600 "${CLASSROOM_DIR}/.cookie-secret"
    fi
    # Η SQLite βάση πρέπει να είναι group-writable (όπως exams/live-quiz)
    for cr_file in "${CLASSROOM_DIR}/data"/classroom.db*; do
        [[ -e "${cr_file}" ]] && chown www-data:www-data "${cr_file}" && chmod 664 "${cr_file}"
    done
    ok "Το Classroom Hub (Ζωντανή Τάξη) είναι έτοιμο."
else
    warn "Λείπει το apps/classroom-hub/app.py — το /classroom/ δεν θα λειτουργεί."
fi

# ---------------------------------------------------------------------------
# 6ιζ. TurboWarp — offline Scratch editor στο /apps/turbowarp/
#      Το static build (ελληνικά, τοπικά assets βιβλιοθήκης) έρχεται από το git·
#      εδώ μόνο το τοπικό mirror των Scratch library assets (~53 MB, εκτός git).
#      Idempotent: τρέχει μόνο αν λείπει το marker .complete (όπως το Basthon).
#      FORCE=1 για override.
# ---------------------------------------------------------------------------
if [[ -x "${PORTAL_DIR}/scripts/fetch-turbowarp-assets.py" ]]; then
    if python3 "${PORTAL_DIR}/scripts/fetch-turbowarp-assets.py"; then
        ok "Ο Scratch editor TurboWarp είναι έτοιμος στο /apps/turbowarp/ (local assets)."
    else
        warn "Αποτυχία λήψης assets για το TurboWarp — οι βιβλιοθήκες του /apps/turbowarp/ δεν θα λειτουργούν offline."
    fi
else
    warn "Δεν βρέθηκε scripts/fetch-turbowarp-assets.py — το /apps/turbowarp/ δεν θα ενημερωθεί."
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
# ΠΡΟΣΟΧΗ: τα αρχεία της βάσης πρέπει να είναι group-writable (664) — αλλιώς
# η www-data παίρνει "attempt to write a readonly database" σε κάθε INSERT.
for ex_file in "${PORTAL_DIR}/exams-app"/exams.db*; do
    [[ -e "${ex_file}" ]] && chown root:www-data "${ex_file}" && chmod 664 "${ex_file}"
done

# live-quiz-app: η SQLite βάση (livequiz.db) & το .cookie-secret δημιουργούνται
# από τη διεργασία www-data μέσα στον φάκελο της εφαρμογής → setgid group-write.
chown -R root:www-data "${PORTAL_DIR}/live-quiz-app"
chmod 2775 "${PORTAL_DIR}/live-quiz-app"
if [[ -f "${PORTAL_DIR}/live-quiz-app/.cookie-secret" ]]; then
    chmod 660 "${PORTAL_DIR}/live-quiz-app/.cookie-secret"
fi
# Όπως στο exams-app: η βάση (+WAL/SHM) χρειάζεται group-write για τη www-data.
for lq_file in "${PORTAL_DIR}/live-quiz-app"/livequiz.db*; do
    [[ -e "${lq_file}" ]] && chown www-data:www-data "${lq_file}" && chmod 664 "${lq_file}"
done

# web-lab: η SQLite βάση (weblab.db) & το .cookie-secret δημιουργούνται από τη
# διεργασία www-data μέσα στον φάκελο της εφαρμογής → setgid group-write.
chown -R root:www-data "${WEBLAB_DIR}"
chmod 2775 "${WEBLAB_DIR}"
for wl_file in "${WEBLAB_DIR}"/weblab.db*; do
    [[ -e "${wl_file}" ]] && chown www-data:www-data "${wl_file}" && chmod 664 "${wl_file}"
done
if [[ -f "${WEBLAB_DIR}/.cookie-secret" ]]; then
    chown www-data:www-data "${WEBLAB_DIR}/.cookie-secret"
    chmod 660 "${WEBLAB_DIR}/.cookie-secret"
fi

# h5p-studio: η SQLite βάση (h5p.db), το .cookie-secret, η βιβλιοθήκη
# δραστηριοτήτων (library/) & τα backups γράφονται από τη διεργασία www-data.
chown -R www-data:www-data "${H5P_DIR}"
chmod 2775 "${H5P_DIR}" "${H5P_DIR}/library"
for h5_file in "${H5P_DIR}"/h5p.db*; do
    [[ -e "${h5_file}" ]] && chown www-data:www-data "${h5_file}" && chmod 664 "${h5_file}"
done
if [[ -f "${H5P_DIR}/.cookie-secret" ]]; then
    chown www-data:www-data "${H5P_DIR}/.cookie-secret"
    chmod 660 "${H5P_DIR}/.cookie-secret"
fi
# Το AI του H5P Studio διαβάζει το .env.keys της πύλης (Alibaba Qwen API)
if [[ -f "${PORTAL_DIR}/.env.keys" ]]; then
    chgrp www-data "${PORTAL_DIR}/.env.keys"
    chmod 640 "${PORTAL_DIR}/.env.keys"
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
# TLS πιστοποιητικό (HTTPS :443) — απαραίτητο για το Web Crypto API του
# Excalidraw (ζωντανή συνεργασία & Export to Link απαιτούν secure context).
if [[ -x "${PORTAL_DIR}/scripts/make-ssl-cert.sh" ]]; then
    bash "${PORTAL_DIR}/scripts/make-ssl-cert.sh" || warn "Αποτυχία δημιουργίας TLS cert — το HTTPS δεν θα λειτουργεί."
fi
# Κοινά proxy headers για τα rate-limited login locations (school_login zone)
mkdir -p /etc/nginx/snippets
install -m 644 "${PORTAL_DIR}/config/nginx/school-proxy-headers.conf" /etc/nginx/snippets/school-proxy-headers.conf
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
# 8β. ΕΝΙΑΙΟΣ κωδικός καθηγητή — data/portal.env (Βήμα 2 εκκρεμότητα 2)
#     Το common/auth.py διαβάζει TEACHER_PASS από env ή από αυτό το αρχείο·
#     τα systemd units το φορτώνουν με EnvironmentFile=. Έτσι ο ίδιος κωδικός
#     ισχύει για Basic Auth, ΟΛΑ τα apps και το dashboard (assets/teacher-code.js).
# ---------------------------------------------------------------------------
PORTAL_ENV="${PORTAL_DIR}/data/portal.env"
mkdir -p "${PORTAL_DIR}/data"
if [[ ! -f "${PORTAL_ENV}" ]] || [[ "${TEACHER_PASS}" != "teacher2026" ]] \
   || ! grep -q '^TEACHER_PASS=' "${PORTAL_ENV}"; then
    printf 'TEACHER_PASS=%s\n' "${TEACHER_PASS}" > "${PORTAL_ENV}"
    chown root:www-data "${PORTAL_ENV}"
    chmod 640 "${PORTAL_ENV}"
    ok "Ενιαίος κωδικός καθηγητή → data/portal.env (apps + Basic Auth)."
else
    # Χωρίς ρητό TEACHER_PASS, σεβόμαστε τον ήδη αποθηκευμένο κωδικό.
    TEACHER_PASS="$(sed -n 's/^TEACHER_PASS=//p' "${PORTAL_ENV}" | head -1)"
    ok "Ενιαίος κωδικός καθηγητή υπάρχει ήδη (data/portal.env)."
fi
# Dashboard JS: ίδιος κωδικός με τα apps (UX gate — ΟΧΙ μηχανισμός ασφαλείας).
printf '// Παράγεται από το install.sh — ίδιος κωδικός με common/auth.py (data/portal.env).\nconst TEACHER_CODE = %s;\n' \
    "$(printf '%s' "${TEACHER_PASS}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" \
    > "${PORTAL_DIR}/dashboard/assets/teacher-code.js"
chmod 644 "${PORTAL_DIR}/dashboard/assets/teacher-code.js"

# ---------------------------------------------------------------------------
# 9. systemd services
# ---------------------------------------------------------------------------
log "Εγκατάσταση systemd υπηρεσιών…"
# Κοινό πακέτο common/ (auth, classes, lessons, db, schedule) — τα units το
# βρίσκουν μέσω PYTHONPATH=/opt/school-portal (Βήμα 2 architecture review).
if [[ ! -f "${PORTAL_DIR}/common/__init__.py" ]]; then
    die "Λείπει το κοινό πακέτο common/ — κάντε git pull πριν την εγκατάσταση."
fi
install -m 644 "${PORTAL_DIR}/config/systemd/school-pandoc.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-mkdocs.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-mkdocs.path"    /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-filebrowser.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-exams.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-livequiz.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-weblab.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-h5p.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-appbuilder.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-etherpad.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-excalidraw-room.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-hedgedoc.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-mdbridge.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-lessonwizard.service" /etc/systemd/system/
install -m 644 "${PORTAL_DIR}/config/systemd/school-classroom.service" /etc/systemd/system/
systemctl daemon-reload

systemctl enable --now school-pandoc.service
systemctl enable --now school-exams.service
systemctl enable --now school-livequiz.service
if [[ -f "${WEBLAB_DIR}/main.py" ]]; then
    systemctl enable --now school-weblab.service
else
    warn "Παράλειψη school-weblab.service (λείπει το web-lab/main.py)."
fi
if [[ -f "${H5P_DIR}/main.py" ]]; then
    systemctl enable --now school-h5p.service
else
    warn "Παράλειψη school-h5p.service (λείπει το h5p-studio/main.py)."
fi
systemctl enable --now school-appbuilder.service
if [[ -f "${ETHERPAD_DIR}/package.json" ]] && command -v node >/dev/null 2>&1; then
    systemctl enable --now school-etherpad.service
else
    warn "Παράλειψη school-etherpad.service (λείπει το Etherpad ή η Node.js)."
fi
if [[ -s "${EXCALIDRAW_ROOM_DIR}/dist/index.js" ]]; then
    systemctl enable --now school-excalidraw-room.service
else
    warn "Παράλειψη school-excalidraw-room.service (λείπει το build)."
fi
if [[ -f "${HEDGEDOC_DIR}/app.js" && -d "${HEDGEDOC_DIR}/node_modules" ]]; then
    systemctl enable --now school-hedgedoc.service
else
    warn "Παράλειψη school-hedgedoc.service (λείπει το HedgeDoc ή οι εξαρτήσεις του)."
fi
if [[ -f "${MDBRIDGE_DIR}/app.py" ]]; then
    systemctl enable --now school-mdbridge.service
else
    warn "Παράλειψη school-mdbridge.service (λείπει το apps/hedgedoc-bridge/app.py)."
fi
if [[ -f "${LESSONWIZARD_DIR}/app.py" ]]; then
    systemctl enable --now school-lessonwizard.service
else
    warn "Παράλειψη school-lessonwizard.service (λείπει το apps/lesson-wizard/app.py)."
fi
if [[ -f "${CLASSROOM_DIR}/app.py" ]]; then
    systemctl enable --now school-classroom.service
else
    warn "Παράλειψη school-classroom.service (λείπει το apps/classroom-hub/app.py)."
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
check_url "/board-ws/"               200
check_url "/pad/"                    200
check_url "/pad/admin"               401
check_url "/pad/admin/"              200 "${TEACHER_USER}:${TEACHER_PASS}"
check_url "/md-pad/"                 200
check_url "/md-pad/template-demo"    200
check_url "/md-publish/"             200
check_url "/md-publish/healthz"      200
check_url "/md-publish/api/notes"    401
check_url "/lesson-wizard/"          200
check_url "/lesson-wizard/healthz"   200
check_url "/lesson-wizard/api/lessons" 401
check_url "/lesson-wizard/api/check" 401
check_url "/lesson-wizard/api/schedule/public" 200
check_url "/classroom/"              200
check_url "/classroom/healthz"       200
check_url "/classroom/api/roster"    401
check_url "/classroom/api/config/template" 401
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
check_url "/web-lab/"                200
check_url "/web-lab/healthz"         200
check_url "/h5p-studio/"             200
check_url "/h5p-studio/healthz"      200
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
echo "  🌐 Κεντρική Πύλη:      http://${IP_ADDR}/  (και https://${IP_ADDR}/)"
echo "  🔒 ΣΗΜΑΝΤΙΚΟ: Για ζωντανή συνεργασία στο /board/ (Excalidraw) άνοιξε"
echo "     https://${IP_ADDR}/board/ — το Web Crypto API απαιτεί HTTPS."
echo "     (Self-signed cert: αποδέξου την προειδοποίηση του browser μία φορά)"
echo "  📚 Εκπαιδευτικό Υλικό: http://${IP_ADDR}/docs/"
echo "  🎮 Παιχνίδι Δυαδικού:  http://${IP_ADDR}/docs/games/binary-game.html"
echo "  🗓️  Εργαστήριο:         http://${IP_ADDR}/lab/  (υπό κατασκευή)"
echo "  📝 Pandoc Studio:      http://${IP_ADDR}/pandoc/"
echo "  🗝️  Λύσεις Καθηγητή:    http://${IP_ADDR}/docs/teachers/"
echo "  🔐 CyberChef:          http://${IP_ADDR}/crypto/   (static, 0 MB)"
echo "  🛠️  IT-Tools:           http://${IP_ADDR}/tools/    (static, 0 MB)"
echo "  🖍️  Πίνακας Excalidraw: https://${IP_ADDR}/board/   (πλήρες build, static, 0 MB)"
echo "     Ζωντανή συνεργασία: self-hosted excalidraw-room @127.0.0.1:${EXCALIDRAW_ROOM_PORT} (100% LAN)"
echo "  📝 Σημειωματάριο Τάξης: http://${IP_ADDR}/pad/     (Etherpad Lite + SQLite)"
echo "  ✍️  Συνεργατικό Markdown: http://${IP_ADDR}/md-pad/ (HedgeDoc ${HEDGEDOC_VERSION} + SQLite, freely)"
echo "     Πρότυπο δυνατοτήτων: http://${IP_ADDR}/md-pad/template-demo"
echo "  📤 Δημοσίευση → MkDocs: http://${IP_ADDR}/md-publish/ (κωδικός ${TEACHER_PASS})"
echo "  🧙 Lesson Wizard:       http://${IP_ADDR}/lesson-wizard/ (κωδικός ${TEACHER_PASS})"
echo "  🏫 Ζωντανή Τάξη:        http://${IP_ADDR}/classroom/  (guest/μαθητής ελεύθερα· καθηγητής: ${TEACHER_PASS})"
echo "     Ενιαίο Excel ρυθμίσεων: μενού + εργαλειοθήκες + ωράριο + timers + γεγονότα + quiz"
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
echo "  🌐 Εργαστήριο Web:     http://${IP_ADDR}/web-lab/   (HTML/CSS/JS editor + δωμάτια ομάδας)"
echo "     Δημοσίευση έργων:   κωδικός ${TEACHER_PASS} → ζωντανή κάρτα στο Dashboard (/apps/)"
echo "  🎮 H5P Studio:         http://${IP_ADDR}/h5p-studio/ (διαδραστικές ασκήσεις + AI wizard)"
echo "     Δημιουργία/επεξεργασία: κωδικός ${TEACHER_PASS} · αναπαραγωγή μαθητών ελεύθερη"
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
echo "     systemctl status school-weblab.service"
echo "     systemctl status school-h5p.service"
echo "     systemctl status school-appbuilder.service"
echo "     systemctl status school-etherpad.service"
echo "     systemctl status school-excalidraw-room.service"
echo "     systemctl status school-hedgedoc.service"
echo "     systemctl status school-mdbridge.service"
echo "     systemctl status school-lessonwizard.service"
echo "     systemctl status school-classroom.service"
echo "     systemctl start school-mkdocs.service    # rebuild υλικού"
echo "     journalctl -u school-pandoc.service -f"
echo "     sudo ${PORTAL_DIR}/install.sh --update   # ενημέρωση"
echo