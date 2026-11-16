#!/usr/bin/env bash
# ===========================================================================
#  Self-signed TLS πιστοποιητικό για τη σχολική πύλη (HTTPS στη θύρα 443)
#
#  Γιατί χρειάζεται: το Web Crypto API (crypto.subtle) των browsers είναι
#  διαθέσιμο ΜΟΝΟ σε "secure context" (HTTPS ή localhost). Χωρίς HTTPS, η
#  ζωντανή συνεργασία & το "Export to Link" του Excalidraw (/board/) αποτυγχάνουν
#  με "Cannot read properties of undefined (reading 'generateKey')".
#
#  Το πιστοποιητικό περιλαμβάνει ΟΛΕΣ τις τοπικές IP του server ως SAN, ώστε
#  https://<ip>/ να δουλεύει από κάθε υπολογιστή του σχολικού LAN. Οι browsers
#  θα δείξουν προειδοποίηση self-signed την πρώτη φορά ("Αποδοχή κινδύνου &
#  συνέχεια") — εναλλακτικά, μοίρασε το /etc/nginx/ssl/school-portal.crt στις
#  έμπιστες αρχές πιστοποιητικών των σχολικών υπολογιστών.
#
#  Idempotent: δημιουργεί νέο cert μόνο αν λείπει ή αν αλλάξαν οι IP (FORCE=1
#  για αναδημιουργία). Διάρκεια: 10 χρόνια.
# ===========================================================================
set -euo pipefail

CERT_DIR="/etc/nginx/ssl"
CRT="${CERT_DIR}/school-portal.crt"
KEY="${CERT_DIR}/school-portal.key"
FORCE="${FORCE:-0}"

C_OK=$'\033[0;32m'; C_INFO=$'\033[0;36m'; C_WARN=$'\033[0;33m'; C_OFF=$'\033[0m'
log() { echo "${C_INFO}[•]${C_OFF} $*"; }
ok()  { echo "${C_OK}[✓]${C_OFF} $*"; }

command -v openssl >/dev/null || { echo "${C_WARN}[!]${C_OFF} Λείπει το openssl."; exit 1; }

# Συγκέντρωση όλων των IPv4 του server + localhost ονόματα
IPS="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' | sort -u || true)"
SAN="IP:127.0.0.1,DNS:localhost,DNS:school-portal"
for ip in ${IPS}; do
    SAN="${SAN},IP:${ip}"
done

# Αν υπάρχει ήδη cert που καλύπτει όλες τις τρέχουσες IP, δεν το ξαναφτιάχνουμε
if [[ -s "${CRT}" && -s "${KEY}" && "${FORCE}" != "1" ]]; then
    EXISTING_SAN="$(openssl x509 -in "${CRT}" -noout -ext subjectAltName 2>/dev/null || true)"
    NEEDS_NEW=0
    for ip in ${IPS}; do
        echo "${EXISTING_SAN}" | grep -q "IP Address:${ip}\b" || NEEDS_NEW=1
    done
    if [[ "${NEEDS_NEW}" == "0" ]]; then
        ok "Το TLS πιστοποιητικό υπάρχει ήδη (${CRT})."
        exit 0
    fi
    log "Αλλαγή IP στο server — αναδημιουργία πιστοποιητικού…"
fi

mkdir -p "${CERT_DIR}"
log "Δημιουργία self-signed πιστοποιητικού (SAN: ${SAN})…"
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
    -keyout "${KEY}" -out "${CRT}" \
    -subj "/CN=school-portal/O=School Portal/C=GR" \
    -addext "subjectAltName=${SAN}" 2>/dev/null
chmod 600 "${KEY}"
chmod 644 "${CRT}"
ok "Το TLS πιστοποιητικό δημιουργήθηκε (λήγει: $(openssl x509 -in "${CRT}" -noout -enddate | cut -d= -f2))."