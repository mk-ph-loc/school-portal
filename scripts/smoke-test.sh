#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# smoke-test.sh — Έλεγχος λειτουργίας της Ψηφιακής Πύλης στη θύρα 80
# Χρήση: bash /opt/school-portal/scripts/smoke-test.sh
# ---------------------------------------------------------------------------
set -uo pipefail

TEACHER_USER="${TEACHER_USER:-teacher}"
TEACHER_PASS="${TEACHER_PASS:-teacher2026}"
BASE="http://127.0.0.1"
PASS=0; FAIL=0

G=$'\033[0;32m'; R=$'\033[0;31m'; B=$'\033[0;36m'; N=$'\033[0m'

check() {
    local path="$1" expect="$2" auth="${3:-}" code
    if [[ -n "$auth" ]]; then
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 -u "$auth" "${BASE}${path}" || echo 000)
    else
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "${BASE}${path}" || echo 000)
    fi
    if [[ "$code" == "$expect" ]]; then
        printf '  %s✓%s %-46s %s\n' "$G" "$N" "$path" "$code"; PASS=$((PASS+1))
    else
        printf '  %s✗%s %-46s %s (αναμενόταν %s)\n' "$R" "$N" "$path" "$code" "$expect"; FAIL=$((FAIL+1))
    fi
}

echo
echo "${B}=== 1. Υπηρεσίες systemd ===${N}"
for svc in nginx school-pandoc.service school-mkdocs.path; do
    state=$(systemctl is-active "$svc" 2>/dev/null || echo unknown)
    if [[ "$state" == "active" ]]; then
        printf '  %s✓%s %-30s %s\n' "$G" "$N" "$svc" "$state"; PASS=$((PASS+1))
    else
        printf '  %s✗%s %-30s %s\n' "$R" "$N" "$svc" "$state"; FAIL=$((FAIL+1))
    fi
done

echo
echo "${B}=== 2. Δημόσιες διαδρομές ===${N}"
check "/"                              200
check "/healthz"                       200
check "/assets/portal.js"              200
check "/assets/tailwind.min.js"        200
check "/assets/alpine.min.js"          200
check "/lab/"                          200

echo
echo "${B}=== 3. Εκπαιδευτικό υλικό (6 τάξεις) ===${N}"
check "/docs/"                         200
for c in gymnasio-a gymnasio-b gymnasio-g lykeio-a lykeio-b lykeio-g; do
    check "/docs/$c/"                  200
done

echo
echo "${B}=== 4. Διαδραστικά στοιχεία ===${N}"
check "/docs/games/binary-game.html"   200
check "/docs/games/binary-game.js"     200
check "/docs/assets/javascripts/class-filter.js" 200
check "/docs/assets/javascripts/glossa.js"       200
check "/docs/assets/javascripts/python-run.js"   200
check "/docs/assets/javascripts/quiz.js"         200
check "/docs/assets/pyodide/pyodide.js"          200
check "/docs/assets/pyodide/pyodide.asm.wasm"    200
check "/docs/lykeio-a/quiz/"           200

echo
echo "${B}=== 5. Προστασία περιοχών καθηγητών ===${N}"
check "/pandoc/"                       401
check "/pandoc/"                       200 "$TEACHER_USER:$TEACHER_PASS"
check "/docs/teachers/"                401
check "/docs/teachers/"                200 "$TEACHER_USER:$TEACHER_PASS"
check "/pandoc/"                       401 "$TEACHER_USER:wrongpass"

echo
echo "${B}=== 6. Λειτουργίες Pandoc Studio ===${N}"
AUTH="$TEACHER_USER:$TEACHER_PASS"

cmd=$(curl -s --max-time 25 -u "$AUTH" -H 'Content-Type: application/json' \
      -d '{"format":"docx","flags":{"toc":true}}' "${BASE}/pandoc/api/command")
if [[ "$cmd" == *"--toc"* ]]; then
    printf '  %s✓%s Visual Flags Explorer (command builder)\n' "$G" "$N"; PASS=$((PASS+1))
else
    printf '  %s✗%s Visual Flags Explorer\n' "$R" "$N"; FAIL=$((FAIL+1))
fi

MD='# Δοκιμή\n\nΕλληνικά: αβγδεζηθικλμνξοπρστυφχψω ΆΈΉΊΌΎΏ.\n'
for fmt in pdf docx html odt epub; do
    out="/tmp/smoke-$fmt.out"
    code=$(curl -s --max-time 90 -u "$AUTH" -H 'Content-Type: application/json' \
        -d "{\"markdown\":\"$MD\",\"format\":\"$fmt\",\"filename\":\"smoke\",\"flags\":{\"standalone\":true}}" \
        "${BASE}/pandoc/api/convert" -o "$out" -w '%{http_code}')
    size=$(stat -c%s "$out" 2>/dev/null || echo 0)
    if [[ "$code" == "200" && "$size" -gt 100 ]]; then
        printf '  %s✓%s Μετατροπή → %-6s (%s bytes)\n' "$G" "$N" "$fmt" "$size"; PASS=$((PASS+1))
    else
        printf '  %s✗%s Μετατροπή → %-6s HTTP %s, %s bytes\n' "$R" "$N" "$fmt" "$code" "$size"; FAIL=$((FAIL+1))
    fi
    rm -f "$out"
done

rb=$(curl -s --max-time 150 -u "$AUTH" -X POST "${BASE}/pandoc/api/rebuild")
if [[ "$rb" == *'"ok":true'* ]]; then
    printf '  %s✓%s Ανακατασκευή MkDocs μέσω API\n' "$G" "$N"; PASS=$((PASS+1))
else
    printf '  %s✗%s Ανακατασκευή MkDocs: %s\n' "$R" "$N" "${rb:0:150}"; FAIL=$((FAIL+1))
fi

echo
echo "${B}=== 7. Κατανάλωση πόρων ===${N}"
mem=$(systemctl show school-pandoc.service -p MemoryCurrent --value 2>/dev/null || echo 0)
printf '  Pandoc Studio RAM: %s MB\n' "$(( ${mem:-0} / 1048576 ))"
printf '  Μέγεθος /var/www/docs: %s\n' "$(du -sh /var/www/docs 2>/dev/null | cut -f1)"
free -m | awk '/^Mem:/ {printf "  Σύστημα: %s MB used / %s MB total (%s MB available)\n",$3,$2,$7}'

echo
echo "==========================================================="
if [[ "$FAIL" -eq 0 ]]; then
    printf '  %s✅ ΟΛΟΙ ΟΙ ΕΛΕΓΧΟΙ ΠΕΡΑΣΑΝ (%s/%s)%s\n' "$G" "$PASS" "$((PASS+FAIL))" "$N"
else
    printf '  %s⚠️  %s αποτυχίες σε %s ελέγχους%s\n' "$R" "$FAIL" "$((PASS+FAIL))" "$N"
fi
echo "==========================================================="
echo
exit "$FAIL"