#!/usr/bin/env bash
# ===========================================================================
#  Λήψη πλήρους static build του Excalidraw για το /board/ της σχολικής πύλης
#
#  Το επίσημο excalidraw-app (github.com/excalidraw/excalidraw) δημοσιεύεται
#  ως έτοιμο static Vite build στο https://excalidraw.com. Αντί να χτίζουμε
#  από την πηγή (απαιτεί ~2 GB RAM & yarn), κατεβάζουμε το ίδιο ακριβώς build
#  και το προσαρμόζουμε για self-hosting σε υποδιαδρομή (/board/):
#
#    * όλα τα assets/chunks/fonts γίνονται τοπικά (offline σχολικό LAN)
#    * EXCALIDRAW_ASSET_PATH → /board/ (όχι το CDN της DigitalOcean)
#    * αφαίρεση analytics (SimpleAnalytics) & service worker που θα
#      «έπιανε» όλο το scope "/" της πύλης
#    * προεπιλεγμένη γλώσσα: Ελληνικά (el-GR), dark/light mode διατηρείται
#
#  Χρήση:  sudo ./fetch-excalidraw.sh [στόχος]   (default /var/www/school-tools/board)
#  Idempotent: αν το index.html υπάρχει ήδη, δεν ξανακατεβάζει (FORCE=1 για override).
# ===========================================================================
set -euo pipefail

BASE_URL="https://excalidraw.com"
DEST="${1:-/var/www/school-tools/board}"
SUBPATH="/board/"
FORCE="${FORCE:-0}"

C_OK=$'\033[0;32m'; C_INFO=$'\033[0;36m'; C_WARN=$'\033[0;33m'; C_OFF=$'\033[0m'
log()  { echo "${C_INFO}[•]${C_OFF} $*"; }
ok()   { echo "${C_OK}[✓]${C_OFF} $*"; }
warn() { echo "${C_WARN}[!]${C_OFF} $*"; }

if [[ -s "${DEST}/index.html" && "${FORCE}" != "1" ]]; then
    ok "Το Excalidraw υπάρχει ήδη στο ${DEST} (FORCE=1 για ενημέρωση)."
    exit 0
fi

command -v curl >/dev/null || { warn "Λείπει το curl."; exit 1; }
command -v python3 >/dev/null || { warn "Λείπει η python3."; exit 1; }

TMP="$(mktemp -d /tmp/excalidraw.XXXXXX)"
trap 'rm -rf "${TMP}"' EXIT
mkdir -p "${TMP}/assets/locales" "${TMP}/fonts"

fetch() {  # fetch <url> <τοπικό αρχείο> [υποχρεωτικό=1]
    local url="$1" out="$2" required="${3:-1}"
    mkdir -p "$(dirname "${out}")"
    if curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -o "${out}" "${url}"; then
        return 0
    fi
    rm -f "${out}"
    [[ "${required}" == "1" ]] && { warn "Αποτυχία λήψης ${url}"; return 1; }
    return 0
}

log "Λήψη Excalidraw static build από το ${BASE_URL}…"
fetch "${BASE_URL}/" "${TMP}/index.raw.html"

# --- 1. Κύρια JS/CSS bundles που αναφέρει το index.html ---------------------
mapfile -t MAIN_ASSETS < <(grep -oE '(src|href)="/assets/[^"]+\.(js|css)"' "${TMP}/index.raw.html" \
    | grep -oE '/assets/[^"]+' | sort -u)
[[ "${#MAIN_ASSETS[@]}" -ge 2 ]] || { warn "Δεν βρέθηκαν τα κύρια assets — άλλαξε το upstream;"; exit 1; }
for a in "${MAIN_ASSETS[@]}"; do
    fetch "${BASE_URL}${a}" "${TMP}${a}"
done
MAIN_JS="$(printf '%s\n' "${MAIN_ASSETS[@]}" | grep -E '/assets/index-[^/]+\.js$' | head -1)"
[[ -n "${MAIN_JS}" ]] || { warn "Δεν βρέθηκε το κύριο index-*.js."; exit 1; }

# --- 2. Όλα τα lazy chunks & locales που αναφέρονται στο κύριο bundle ------
#      (Vite hashed filenames: name-XXXXXXXX.js· τα locales έχουν .json- μέσα)
mapfile -t CHUNKS < <(grep -oE '[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8}\.js' "${TMP}${MAIN_JS}" \
    | sort -u | grep -v "^$(basename "${MAIN_JS}")$")
log "Λήψη ${#CHUNKS[@]} lazy chunks/locales…"
for c in "${CHUNKS[@]}"; do
    if [[ "${c}" == *json-* ]]; then
        fetch "${BASE_URL}/assets/locales/${c}" "${TMP}/assets/locales/${c}" 0 || true
    else
        fetch "${BASE_URL}/assets/${c}" "${TMP}/assets/${c}" 0 || true
    fi
done

# --- 2β. Δευτερογενή imports (chunks που εισάγουν άλλους chunks, π.χ. minimap)
for pass in 1 2; do
    mapfile -t NESTED < <(cat "${TMP}"/assets/*.js 2>/dev/null \
        | grep -oE '"\./[A-Za-z0-9_.-]+-[A-Za-z0-9_-]{8}\.js"' | tr -d '"' | sed 's|^\./||' | sort -u)
    for c in "${NESTED[@]}"; do
        [[ -f "${TMP}/assets/${c}" ]] && continue
        fetch "${BASE_URL}/assets/${c}" "${TMP}/assets/${c}" 0 || true
    done
done

# --- 3. Mermaid-to-Excalidraw chunks (λίστα JSON στο meta του index.html) ---
MERMAID_JSON="$(grep -oE 'name="mermaid-chunks" content="[^"]+"' "${TMP}/index.raw.html" \
    | sed 's/.*content="//;s/"//' || true)"
if [[ -n "${MERMAID_JSON}" ]]; then
    fetch "${BASE_URL}/${MERMAID_JSON}" "${TMP}/${MERMAID_JSON}" 0 || true
    if [[ -s "${TMP}/${MERMAID_JSON}" ]]; then
        while read -r m; do
            [[ -n "${m}" ]] && { fetch "${BASE_URL}/${m}" "${TMP}/${m}" 0 || true; }
        done < <(grep -oE 'assets/[A-Za-z0-9_.-]+\.js' "${TMP}/${MERMAID_JSON}" | sort -u)
    fi
fi

# --- 4. Γραμματοσειρές canvas (Excalifont/Nunito/… — όλες εκτός Xiaolai CJK)
#      Οι Xiaolai (209 κινέζικα subsets, ~30 MB) ΔΕΝ χρειάζονται για ελληνικά·
#      αν κάποιος γράψει κινέζικα, φορτώνονται από το επίσημο CDN fallback.
mapfile -t FONTS < <(grep -oE 'fonts/[A-Za-z0-9_./-]+\.woff2' "${TMP}${MAIN_JS}" \
    | sort -u | grep -v '^fonts/Xiaolai/')
log "Λήψη ${#FONTS[@]} γραμματοσειρών canvas…"
for f in "${FONTS[@]}"; do
    fetch "${BASE_URL}/${f}" "${TMP}/${f}" 0 || true
done

# --- 4β. Fonts που αναφέρονται στο ίδιο το index.html (preload links —
#         μπορεί να είναι απόλυτα CDN URLs ή σχετικά /fonts/ paths) ----------
CDN_PREFIX="https://excalidraw.nyc3.cdn.digitaloceanspaces.com/oss/"
while read -r f; do
    rel="${f#${CDN_PREFIX}}"          # CDN URL → σχετικό path
    rel="${rel#/}"                    # /fonts/... → fonts/...
    case "${rel}" in
        fonts/Xiaolai/*) continue ;;  # CJK subsets — δεν χρειάζονται
        fonts/*) fetch "${BASE_URL}/${rel}" "${TMP}/${rel}" 0 || true ;;
    esac
done < <(grep -oE 'href="[^"]+\.woff2"' "${TMP}/index.raw.html" | sed 's|href="||;s|"||' | sort -u)

# --- 5. UI fonts του CSS (Assistant) + εικονίδια PWA -------------------------
CSS_FILE="$(printf '%s\n' "${MAIN_ASSETS[@]}" | grep -E '\.css$' | head -1)"
if [[ -n "${CSS_FILE}" ]]; then
    while read -r f; do
        fetch "${BASE_URL}/assets/${f}" "${TMP}/assets/${f}" 0 || true
    done < <(grep -oE 'url\(\./[^)]+\.woff2\)' "${TMP}${CSS_FILE}" | sed 's|url(\./||;s|)||' | sort -u)
fi
for icon in favicon-16x16.png favicon-32x32.png apple-touch-icon.png android-chrome-192x192.png; do
    fetch "${BASE_URL}/${icon}" "${TMP}/${icon}" 0 || true
done

# --- 6. Προσαρμογή του index.html για self-hosting στο /board/ --------------
python3 - "${TMP}/index.raw.html" "${TMP}/index.html" "${SUBPATH}" <<'PYEOF'
import re, sys, pathlib

src, out, subpath = sys.argv[1], sys.argv[2], sys.argv[3]
html = pathlib.Path(src).read_text(encoding="utf-8")

# 6α. Assets & fonts: όλα τοπικά κάτω από το /board/ (offline LAN).
#     Το επίσημο CDN παραμένει ΜΟΝΟ ως έσχατο fallback (π.χ. CJK fonts).
html = re.sub(
    r'window\.EXCALIDRAW_ASSET_PATH\s*=\s*\[[^\]]*\]',
    f'window.EXCALIDRAW_ASSET_PATH = ["{subpath}", "https://excalidraw.nyc3.cdn.digitaloceanspaces.com/oss/"]',
    html, count=1)
html = html.replace('https://excalidraw.nyc3.cdn.digitaloceanspaces.com/oss/fonts/', f'{subpath}fonts/')

# 6β. Απόλυτα paths των bundles/icons → κάτω από το /board/
html = re.sub(r'(src|href)="/(assets/|favicon|apple-touch-icon|android-chrome)',
              lambda m: f'{m.group(1)}="{subpath}{m.group(2)}', html)
html = html.replace('href="/manifest.webmanifest"', f'href="{subpath}manifest.webmanifest"')

# 6γ. Αφαίρεση analytics (SimpleAnalytics) — ιδιωτικότητα σχολικού LAN
html = re.sub(r'<script>// need to load this script dynamically.*?</script>', '', html, flags=re.S)

# 6δ. Αφαίρεση Google Fonts preconnect (όλα τα fonts είναι πλέον τοπικά)
html = re.sub(r'<link rel="preconnect"[^>]*>', '', html)

# 6ε. Ο upstream service worker έχει scope "/" και θα cached-αρε ΟΛΗ την
#     πύλη· τον απενεργοποιούμε (guard στο παρακάτω snippet) και κρύβουμε
#     το meta των mermaid-chunks που προϋποθέτει ενεργό SW controller.
html = html.replace('<meta name="mermaid-chunks"', '<meta name="mermaid-chunks-disabled"')

# 6ε2. Self-hosted collaboration: το URL του room server γίνεται runtime
#      override (window.EXCALIDRAW_WS_SERVER_URL) ώστε να δείχνει στον τοπικό
#      excalidraw-room (/board-ws/) αντί για το oss-collab.excalidraw.com.
#      Το ίδιο origin → δουλεύει με όποια IP/hostname ανοίξει η πύλη, σε
#      HTTP & HTTPS, χωρίς rebuild. Το πραγματικό patch του bundle γίνεται
#      παρακάτω (βήμα 6β2) στα JS αρχεία.
ws_override = (
    '<script>'
    'window.EXCALIDRAW_WS_SERVER_URL=\"/board-ws\";'
    '</script>'
)
html = html.replace('</title>', '</title>' + ws_override, 1)

# 6στ. Ελληνικά ως προεπιλογή + τίτλος πύλης + no-op serviceWorker guard.
#      Το i18next διαβάζει πρώτα το localStorage["i18nextLng"]· αν δεν έχει
#      οριστεί ρητά από τον χρήστη, το θέτουμε el-GR πριν φορτώσει το app.
inject = (
    '<script>'
    'try{if(!localStorage.getItem("i18nextLng")){localStorage.setItem("i18nextLng","el-GR");}}catch(e){}'
    'try{Object.defineProperty(navigator,"serviceWorker",{get:function(){return undefined;}});}catch(e){}'
    '</script>'
)
html = html.replace('</title>', '</title>' + inject, 1)
html = html.replace('<title>Excalidraw Whiteboard</title>',
                    '<title>Ψηφιακός Πίνακας Excalidraw — Ψηφιακή Πύλη</title>')
html = html.replace('<html lang="en">', '<html lang="el">')

pathlib.Path(out).write_text(html, encoding='utf-8')
print(f'[✓] index.html προσαρμόστηκε για το {subpath} (ελληνικά, τοπικά assets, χωρίς analytics/SW)')
PYEOF

# --- 6β2. Patch του κύριου bundle: self-hosted room server ------------------
# Το excalidraw-app έχει hardcoded το "https://oss-collab.excalidraw.com" ως
# default του VITE_APP_WS_SERVER_URL. Αντικαθιστούμε ΜΟΝΟ την κλήση σύνδεσης
# (portal.open) με runtime έκφραση που διαβάζει window.EXCALIDRAW_WS_SERVER_URL
# (ορίζεται στο index.html παραπάνω → ίδιο origin + /board-ws). Έτσι η ζωντανή
# συνεργασία μένει 100% μέσα στο σχολικό LAN (excalidraw-room @127.0.0.1:8007).
python3 - "${TMP}${MAIN_JS}" <<'PYEOF'
import sys, pathlib

p = pathlib.Path(sys.argv[1])
js = p.read_text(encoding="utf-8")

# Ο socket.io client βγάζει το path από το URL namespace ("/socket.io"),
# αγνοώντας το pathname του server URL — γι' αυτό περνάμε ρητά το
# path: "/board-ws/socket.io" στο options object της connect().
old_call = ('this.portal.open(r("https://oss-collab.excalidraw.com",'
            '{transports:["websocket","polling"]})')
new_call = ('this.portal.open(r(window.EXCALIDRAW_WS_SERVER_URL?window.location.origin:'
            '"https://oss-collab.excalidraw.com",'
            '{path:(window.EXCALIDRAW_WS_SERVER_URL||"")+"/socket.io",'
            'transports:["websocket","polling"]})')
n = js.count(old_call)
if n == 1:
    js = js.replace(old_call, new_call)
    # Και το default του env object (χρησιμοποιείται αλλού ως fallback)
    js = js.replace(
        'VITE_APP_WS_SERVER_URL:"https://oss-collab.excalidraw.com"',
        'VITE_APP_WS_SERVER_URL:window.EXCALIDRAW_WS_SERVER_URL||"https://oss-collab.excalidraw.com"')
    p.write_text(js, encoding="utf-8")
    print('[✓] Bundle patch: collaboration → self-hosted /board-ws/ (excalidraw-room)')
else:
    print(f'[!] Προσοχή: βρέθηκαν {n} σημεία σύνδεσης (αναμενόταν 1) — '
          'το upstream άλλαξε· η συνεργασία θα χρησιμοποιεί τον δημόσιο server.')
PYEOF

# PWA manifest με σωστό scope/start_url για το /board/
cat > "${TMP}/manifest.webmanifest" <<MANIFEST_EOF
{"name":"Ψηφιακός Πίνακας — Excalidraw","short_name":"Πίνακας","start_url":"${SUBPATH}","scope":"${SUBPATH}","display":"standalone","background_color":"#ffffff","theme_color":"#121212","lang":"el","icons":[{"src":"android-chrome-192x192.png","sizes":"192x192","type":"image/png"},{"src":"apple-touch-icon.png","sizes":"180x180","type":"image/png"},{"src":"favicon-32x32.png","sizes":"32x32","type":"image/png"},{"src":"favicon-16x16.png","sizes":"16x16","type":"image/png"}]}
MANIFEST_EOF

# --- 7. Εγκατάσταση στον προορισμό ------------------------------------------
mkdir -p "${DEST}"
# Καθαρισμός παλιού custom πίνακα/assets (κρατάμε τυχόν .excalidraw exports χρηστών)
find "${DEST}" -mindepth 1 -maxdepth 1 ! -name '*.excalidraw' -exec rm -rf {} +
cp -a "${TMP}/." "${DEST}/"
rm -f "${DEST}/index.raw.html"
chown -R root:root "${DEST}"
find "${DEST}" -type d -exec chmod 755 {} +
find "${DEST}" -type f -exec chmod 644 {} +

SIZE_MB="$(du -sm "${DEST}" | awk '{print $1}')"
ok "Το πλήρες Excalidraw εγκαταστάθηκε στο ${DEST} (~${SIZE_MB} MB, static — 0 MB RAM)."