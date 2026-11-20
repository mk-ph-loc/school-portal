#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# smoke-test.sh — Έλεγχος λειτουργίας της Ψηφιακής Πύλης στη θύρα 80
# Χρήση: bash /opt/school-portal/scripts/smoke-test.sh
# ---------------------------------------------------------------------------
set -uo pipefail

TEACHER_USER="${TEACHER_USER:-teacher}"
# Ενιαίος κωδικός: env TEACHER_PASS → data/portal.env (install.sh) → default.
if [[ -z "${TEACHER_PASS:-}" && -r /opt/school-portal/data/portal.env ]]; then
    TEACHER_PASS="$(sed -n 's/^TEACHER_PASS=//p' /opt/school-portal/data/portal.env | head -1)"
fi
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
for svc in nginx school-pandoc.service school-mkdocs.path school-filebrowser.service school-exams.service; do
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
echo "${B}=== 2β. Εργαλεία Εργαστηρίου ===${N}"
check "/crypto/"                       200
check "/crypto/assets/main.js"         200
check "/tools/"                        200
check "/tools/uuid-generator"          200
check "/board/"                        200

echo
echo "${B}=== 2γ. Δικές μου Εφαρμογές (custom-apps) ===${N}"
check "/apps/apps-manifest.json"       200
check "/apps/binary-converter/"        200
check "/apps/binary-converter/app.js"  200
check "/apps/drawio/"                  200
check "/apps/drawio/app/js/app.min.js" 200
check "/apps/minipaint/"               200
check "/apps/minipaint/dist/bundle.js" 200
check "/apps/piskel/"                  200
check "/apps/basthon/"                 200
check "/apps/basthon/console/index.html" 200
check "/apps/turbowarp/"               200
check "/apps/turbowarp/editor.html"    200
check "/apps/_template/"               404
check "/app-builder/"                  200
check "/app-builder/healthz"           200

check "/share/"                        200
fb_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 -X POST \
    -d '{"username":"admin","password":"'"$TEACHER_PASS"'"}' "${BASE}/share/api/login")
if [[ "$fb_code" == "200" ]]; then
    printf '  %s✓%s FileBrowser login (admin)                      %s\n' "$G" "$N" "$fb_code"; PASS=$((PASS+1))
else
    printf '  %s✗%s FileBrowser login (admin)                      %s\n' "$R" "$N" "$fb_code"; FAIL=$((FAIL+1))
fi

echo
echo "${B}=== 3. Εκπαιδευτικό υλικό (νέα δομή + παλιό παράδειγμα) ===${N}"
check "/docs/"                         200
check "/docs/mathimata/gymnasio-g/pliroforiki/" 200
for m in m01-anadromi-aformisi-spiral m02-pyrgoi-anoy m03-trigono-sierpinski; do
    check "/docs/mathimata/gymnasio-g/pliroforiki/$m/" 200
done
check "/docs/_paradeigma/"             200
for c in gymnasio-a gymnasio-b gymnasio-g lykeio-a lykeio-b lykeio-g; do
    check "/docs/_paradeigma/$c/"      200
done

echo
echo "${B}=== 4. Διαδραστικά στοιχεία ===${N}"
check "/docs/_paradeigma/games/binary-game.html" 200
check "/docs/_paradeigma/games/binary-game.js"   200
check "/docs/assets/javascripts/class-filter.js" 200
check "/docs/assets/javascripts/glossa.js"       200
check "/docs/assets/javascripts/python-run.js"   200
check "/docs/assets/javascripts/quiz.js"         200
check "/docs/assets/javascripts/lesson-phases.js" 200
check "/docs/assets/javascripts/schedule.js"     200
check "/docs/assets/pyodide/pyodide.js"          200
check "/docs/assets/pyodide/pyodide.asm.wasm"    200
check "/docs/_paradeigma/lykeio-a/quiz/" 200
check "/docs/mathimata/gymnasio-g/pliroforiki/m02-pyrgoi-anoy/anoy.html" 200

echo
echo "${B}=== 5. Προστασία περιοχών καθηγητών ===${N}"
check "/pandoc/"                       401
check "/pandoc/"                       200 "$TEACHER_USER:$TEACHER_PASS"
check "/docs/_paradeigma/teachers/"    401
check "/docs/_paradeigma/teachers/"    200 "$TEACHER_USER:$TEACHER_PASS"
# Σημειώσεις καθηγητή ημερήσιων μαθημάτων: 401 χωρίς cookie καθηγητή
check "/docs/mathimata/gymnasio-g/pliroforiki/m02-pyrgoi-anoy/index.teacher.html" 401
# Lesson Wizard API
check "/lesson-wizard/healthz"         200
check "/lesson-wizard/api/lessons"     401
check "/lesson-wizard/api/schedule/public" 200
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
echo "${B}=== 6β. Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα (/exams/) ===${N}"
check "/exams/"                        200
check "/exams/teacher"                 200
check "/exams/static/student.js"       200
check "/exams/api/activities"          200
check "/exams/api/teacher/activities"  401

# Πλήρης ροή: login καθηγητή → δημιουργία → υποβολή μαθητή → βαθμολογία → διαγραφή
EJ="/tmp/exams-smoke-cookies.txt"; rm -f "$EJ"
login_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 -c "$EJ" \
    -H 'Content-Type: application/json' -d '{"password":"'"$TEACHER_PASS"'"}' \
    "${BASE}/exams/api/teacher/login")
if [[ "$login_code" == "200" ]]; then
    printf '  %s✓%s Login καθηγητή (exams)                          %s\n' "$G" "$N" "$login_code"; PASS=$((PASS+1))
else
    printf '  %s✗%s Login καθηγητή (exams)                          %s\n' "$R" "$N" "$login_code"; FAIL=$((FAIL+1))
fi

act=$(curl -s --max-time 25 -b "$EJ" -H 'Content-Type: application/json' \
    -d '{"title":"SMOKE TEST προσωρινό","class_slug":"gymnasio-a","kind":"test","duration":5,"active":true,"questions":[{"type":"mc","text":"2+2;","options":["3","4"],"correct":1,"points":2}]}' \
    "${BASE}/exams/api/teacher/activities")
# Το "id" είναι το ΠΡΩΤΟ πεδίο του JSON· το anchor ^ αποτρέπει greedy match σε άλλα ids.
act_id=$(printf '%s' "$act" | sed -n 's/^{"id":\([0-9]*\).*/\1/p')
if [[ -n "$act_id" ]]; then
    printf '  %s✓%s Δημιουργία διαγωνίσματος (id=%s)\n' "$G" "$N" "$act_id"; PASS=$((PASS+1))
    st=$(curl -s --max-time 25 -H 'Content-Type: application/json' \
        -d '{"fullname":"Μαθητής Δοκιμής","section":"Α2"}' \
        "${BASE}/exams/api/activities/${act_id}/start")
    sub_id=$(printf '%s' "$st" | sed -n 's/^{"submission_id":\([0-9]*\).*/\1/p')
    sb=$(curl -s --max-time 25 -H 'Content-Type: application/json' \
        -d '{"answers":{"0":1},"auto":false}' \
        "${BASE}/exams/api/submissions/${sub_id}/submit-test")
    if [[ "$sb" == *'"code"'* ]]; then
        printf '  %s✓%s Υποβολή διαγωνίσματος με κωδικό επιβεβαίωσης\n' "$G" "$N"; PASS=$((PASS+1))
    else
        printf '  %s✗%s Υποβολή διαγωνίσματος: %s\n' "$R" "$N" "${sb:0:120}"; FAIL=$((FAIL+1))
    fi
    csv_out=$(curl -s --max-time 25 -b "$EJ" "${BASE}/exams/api/teacher/activities/${act_id}/csv")
    if [[ "$csv_out" == *"Μαθητής Δοκιμής"* && "$csv_out" == *"2"* ]]; then
        printf '  %s✓%s Αυτόματη βαθμολογία MC & εξαγωγή CSV\n' "$G" "$N"; PASS=$((PASS+1))
    else
        printf '  %s✗%s Βαθμολογία/CSV: %s\n' "$R" "$N" "${csv_out:0:120}"; FAIL=$((FAIL+1))
    fi
    curl -s -o /dev/null --max-time 25 -b "$EJ" -X DELETE "${BASE}/exams/api/teacher/activities/${act_id}"
else
    printf '  %s✗%s Δημιουργία διαγωνίσματος: %s\n' "$R" "$N" "${act:0:120}"; FAIL=$((FAIL+1))
fi
rm -f "$EJ"

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