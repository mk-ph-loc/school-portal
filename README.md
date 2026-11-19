# 🏫 Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

Ολοκληρωμένη πλατφόρμα εκπαιδευτικού υλικού Πληροφορικής για **Γυμνάσιο & Λύκειο**,
στημένη **native** σε Debian 13 LXC container — **χωρίς Docker**, με το Nginx του
συστήματος, ένα Python venv και `systemd` services για **ελάχιστη κατανάλωση RAM**.

## 🚀 Γρήγορη Εγκατάσταση

```bash
sudo /opt/school-portal/install.sh            # πλήρης εγκατάσταση
sudo /opt/school-portal/install.sh --update   # ενημέρωση από git + rebuild
sudo /opt/school-portal/install.sh --no-deps  # γρήγορο re-apply (χωρίς apt/pip)
```

Το script είναι **idempotent** — μπορεί να εκτελεστεί ξανά με ασφάλεια.

## 🗺️ Αρχιτεκτονική (όλα στη θύρα 80)

| Διαδρομή | Υπηρεσία | Τεχνολογία | Πρόσβαση |
| --- | --- | --- | --- |
| `/` | Κεντρικό Dashboard | Στατικό HTML + Tailwind + Alpine | Ελεύθερη |
| `/docs/` | Εκπαιδευτικό Υλικό | Material for MkDocs (static) | Ελεύθερη |
| `/docs/teachers/` | Λύσεις Καθηγητή | static + **Basic Auth** | 🔐 Καθηγητές |
| `/pandoc/` | Visual Pandoc Studio | FastAPI @ `127.0.0.1:8002` + **Basic Auth** | 🔐 Καθηγητές |
| `/lab/` | Διαχείριση Εργαστηρίου | *Placeholder* (μελλοντικά :8001) | Προβολή |
| `/exams/` | Παράδοση Εργασιών & Τεστ | FastAPI + SQLite @ `127.0.0.1:8004` | Ελεύθερη (μαθητές) |
| `/exams/teacher` | Διαχείριση Εργασιών/Διαγωνισμάτων | ίδιο service, HMAC cookie | 🔐 Καθηγητές (`teacher2026`) |
| `/live-quiz/` | Ζωντανό Παιχνίδι Τάξης (Live Quiz) | FastAPI + WebSockets + SQLite @ `127.0.0.1:8005` | Ελεύθερη (είσοδος με PIN) |
| `/live-quiz/teacher` | Live Quiz — Προτζέκτορας | ίδιο service, HMAC cookie | 🔐 Καθηγητές (`teacher2026`) |
| `/web-lab/` | Εργαστήριο Web (HTML / CSS / JS) | FastAPI + WebSockets + SQLite @ `127.0.0.1:8011` | Ελεύθερη (Solo ή δωμάτια με PIN· δημοσίευση: `teacher2026`) |
| `/h5p-studio/` | 🎮 H5P Studio (Διαδραστικές Ασκήσεις) | FastAPI + SQLite + offline h5p-standalone @ `127.0.0.1:8012` | 🔐 Καθηγητές (`teacher2026`) — αναπαραγωγή `/play/<id>/` ελεύθερη |
| `/crypto/` | CyberChef | Στατικό HTML/JS (0 MB RAM) | Ελεύθερη |
| `/tools/` | IT-Tools | Στατικό SPA (0 MB RAM) | Ελεύθερη |
| `/board/` | Ψηφιακός Πίνακας Excalidraw | Πλήρες static build excalidraw-app, ελληνικά (0 MB RAM) | Ελεύθερη |
| `/board-ws/` | Excalidraw Room Server (ζωντανή συνεργασία) | Node.js + Socket.IO @ `127.0.0.1:8010` (~40 MB, stateless) | Ελεύθερη (E2E encrypted) |
| `/pad/` | Συνεργατικό Σημειωματάριο Τάξης | Etherpad Lite (Node.js 22 + SQLite) @ `127.0.0.1:8006` | Ελεύθερη (μαθητές) |
| `/pad/admin` | Διαχείριση Etherpad | ίδιο service + **Basic Auth** | 🔐 Καθηγητές (`teacher`) |
| `/md-pad/` | Συνεργατικό Markdown (HedgeDoc) | HedgeDoc 1.12.0 (Node.js 22 + SQLite) @ `127.0.0.1:8007` | Ελεύθερη (ανώνυμη επεξεργασία) |
| `/md-publish/` | Δημοσίευση HedgeDoc → MkDocs | FastAPI micro-bridge @ `127.0.0.1:8009`, HMAC cookie | 🔐 Καθηγητές (`teacher2026`) |
| `/lesson-wizard/` | 🧙 Lesson Wizard — Ημερήσια Μαθήματα & Ωράριο | FastAPI + openpyxl @ `127.0.0.1:8013`, HMAC cookie | 🔐 Καθηγητές (`teacher2026`) |
| `/classroom/` | 🏫 Ζωντανή Τάξη — Κεντρικό Παράθυρο (παρουσία, εντολές, chat/forum, timers ωραρίου) | FastAPI + WebSockets + SQLite + openpyxl @ `127.0.0.1:8014` | Ελεύθερη (guest/μαθητής) · καθηγητής: `teacher2026` |
| `/circuits/` | CircuitJS1 — Προσομοιωτής Κυκλωμάτων | Στατικό build pfalstad/circuitjs1 (0 MB RAM) | Ελεύθερη |
| `/blockly/` | Blockly Games (ελληνικά) | Επίσημο offline static πακέτο Google (0 MB RAM) | Ελεύθερη |
| `/sql/` | SQL Playground | Στατικό HTML + sql.js/SQLite WASM (0 MB RAM) | Ελεύθερη |
| `/pdf-tools/` | PDF Studio (merge/split/υδατογράφημα) | Στατικό HTML + pdf-lib, 100% τοπικά (0 MB RAM) | Ελεύθερη |
| `/apps/<όνομα>/` | 🚀 Δικές μου Εφαρμογές & Προσομοιώσεις | Στατικά HTML/CSS/JS από `custom-apps/` (0 MB RAM) | Ελεύθερη / κάρτες `teachers` μόνο για καθηγητές |
| `/app-builder/` | 🧙 Δημιουργός Custom Εφαρμογών (App Wizard) | FastAPI @ `127.0.0.1:8008`, HMAC cookie | 🔐 Καθηγητές (`teacher2026`) |
| `/share/` | Κοινόχρηστα Αρχεία | FileBrowser Go binary @ `127.0.0.1:8003` (~15 MB) | 🔐 Login (`admin`) |

### 🤝 Συνεργατικά Εργαλεία Τάξης

- **`/board/`** — Πλήρες **Excalidraw**: ψηφιακός πίνακας με χειρόγραφο στυλ, βιβλιοθήκες
  σχημάτων, εξαγωγή **PNG/SVG/JSON**, dark/light mode και προεπιλεγμένα **Ελληνικά**.
  Είναι το επίσημο static build του `excalidraw-app` (κατεβαίνει από το
  `scripts/fetch-excalidraw.sh` με όλα τα assets/fonts τοπικά για offline LAN,
  χωρίς analytics & service worker). Αναβάθμιση: `FORCE_EXCALIDRAW=1 sudo ./install.sh --no-deps`.
  > 🔒 **Η ζωντανή συνεργασία («Start session») και το «Export to Link» απαιτούν HTTPS!**
  > Το Web Crypto API (`crypto.subtle`) των browsers λειτουργεί μόνο σε *secure context*·
  > σε plain HTTP εμφανίζεται το σφάλμα `Cannot read properties of undefined (reading 'generateKey')`.
  > Άνοιξε **`https://<ip>/board/`** (η κάρτα του dashboard σε οδηγεί αυτόματα εκεί).
  > Ο server έχει self-signed πιστοποιητικό 10ετίας (`scripts/make-ssl-cert.sh`, SAN με όλες
  > τις LAN IP) — αποδέξου την προειδοποίηση του browser μία φορά, ή μοίρασε το
  > `/etc/nginx/ssl/school-portal.crt` στις έμπιστες αρχές των σχολικών υπολογιστών.
  > ✅ **Η ζωντανή συνεργασία είναι 100% self-hosted στο σχολικό LAN** — δεν χρειάζεται Internet!
  > Τρέχει ο επίσημος **`excalidraw-room`** server (`apps/excalidraw-room/`, Node.js + Socket.IO,
  > systemd: `school-excalidraw-room.service` @ `127.0.0.1:8010`, πίσω από το Nginx `/board-ws/`).
  > Το static bundle patchάρεται αυτόματα από το `scripts/fetch-excalidraw.sh` ώστε το
  > «Start session» να συνδέεται στον τοπικό server αντί για το `oss-collab.excalidraw.com`.
  > Ο server είναι **stateless** (in-memory rooms, μηδέν εγγραφές σε δίσκο) και αναμεταδίδει
  > μόνο **end-to-end encrypted** blobs (AES-GCM, το κλειδί μένει στο URL fragment του browser).
  > Μοιράσου το link που παράγει το «Start session» με τους μαθητές — όλοι πρέπει να είναι
  > στο ίδιο LAN και να έχουν αποδεχτεί το πιστοποιητικό HTTPS.
  > 🏫 **Λειτουργεί και μέσα στη Ζωντανή Τάξη (`/classroom/`)**: το upstream build αρνιόταν
  > να τρέξει σε iframe («I'm not a pretzel!»)· το `scripts/fetch-excalidraw.sh` απενεργοποιεί
  > αυτόν τον έλεγχο (βήμα 6β3), οπότε ο πίνακας ανοίγει κανονικά από το μενού της τάξης,
  > μαζί με σχεδίαση & ζωντανή συνεργασία. Έλεγχος: `scripts/board-classroom-test.py`.
- **`/pad/`** — **Etherpad Lite v2.7.3**: συνεργατικός επεξεργαστής κειμένου σε πραγματικό
  χρόνο για όλη την τάξη (χρώματα ανά μαθητή, chat, ιστορικό/timeslider, εξαγωγή txt/html).
  Τρέχει native με **Node.js 22 LTS** (NodeSource) + **SQLite** (`apps/etherpad/var/etherpad.db`,
  χωρίς εξωτερική βάση) στο `127.0.0.1:8006` μέσω του `school-etherpad.service`, και σερβίρεται
  από τον Nginx με WebSockets. Νέο έγγραφο: `http://<ip>/pad/p/<όνομα-ομάδας>`.
  Ρυθμίσεις: `config/etherpad/settings.json` (ελληνικό UI & προεπιλεγμένο κείμενο).
- **`/md-pad/`** — **HedgeDoc 1.12.0**: συνεργατικό περιβάλλον συγγραφής **Markdown** σε
  πραγματικό χρόνο (ζωντανή προεπισκόπηση, LaTeX/MathJax, διαγράμματα **Mermaid**, χρωματισμός
  κώδικα, task lists, εικόνες με drag-n-drop, παρουσιάσεις slides, ιστορικό αναθεωρήσεων).
  Τρέχει native (**χωρίς Docker**) από το επίσημο release tarball στο `apps/hedgedoc/` με
  **Node.js 22 LTS + SQLite** (`apps/hedgedoc/hedgedoc.sqlite`) στο `127.0.0.1:8007` μέσω του
  `school-hedgedoc.service`, πίσω από τον Nginx με WebSockets. Ανώνυμη πρόσβαση & επεξεργασία
  (`freely`), FreeURL aliases: `http://<ip>/md-pad/<όνομα-ομάδας>`. Κάθε νέα σημείωση ξεκινά
  με τον ελληνικό οδηγό `welcome.md`· το πλήρες **πρότυπο δυνατοτήτων** είναι έτοιμο στο
  `/md-pad/template-demo` (πηγή: `config/hedgedoc/`). Uploads: `apps/hedgedoc/public/uploads/`.
- **`/md-publish/`** — **Γέφυρα Δημοσίευσης HedgeDoc → MkDocs** (FastAPI micro-bridge,
  `apps/hedgedoc-bridge/app.py` @ `127.0.0.1:8009`, `school-mdbridge.service`, κωδικός
  `teacher2026`). Ο καθηγητής βλέπει όλες τις σημειώσεις από τη βάση `hedgedoc.sqlite`
  (τίτλος/ID/τροποποίηση), κάνει προεπισκόπηση και δημοσιεύει: **Α)** append στο τέλος
  υπάρχοντος μαθήματος ανά τάξη (κανονικό Markdown ή αναδιπλούμενο `??? info "Συνεργατική
  Σημείωση Τάξης"`) ή **Β)** νέο μάθημα με αυτόματη προσθήκη στο `nav:` του `mkdocs.yml`.
  Πριν από κάθε εγγραφή κρατιέται **backup `.bak`** (+ ιστορικό στο `apps/hedgedoc-bridge/backups/`)
  και η σύνταξη HedgeDoc μετατρέπεται αυτόματα για το Material for MkDocs
  (`:::info` → `!!! info`, YAML/[TOC] cleanup, embeds, εικόνες με μέγεθος).
  Το rebuild του `/docs/` γίνεται αυτόματα από το `school-mkdocs.path`.

### 🧪 Διαδραστικά Εργαστήρια (100% static — 0 MB RAM στον server)

- **`/circuits/`** — CircuitJS1: προσομοίωση ηλεκτρονικών κυκλωμάτων σε πραγματικό χρόνο,
  με 360+ έτοιμα εκπαιδευτικά κυκλώματα (μενού *Circuits*). Mirror του επίσημου στατικού
  build από το `falstad.com/circuit` (repo: `pfalstad/circuitjs1`, χωρίς release zip).
- **`/blockly/`** — Blockly Games της Google: 9 παιχνίδια προγραμματισμού με μπλοκ
  (Παζλ, Λαβύρινθος, Πουλιά, Χελώνα, Ταινία, Μουσική, Νούφαρα). Προεπιλεγμένη γλώσσα
  **Ελληνικά** (`lang=el`), αλλάζει από το μενού γλωσσών κάθε παιχνιδιού.
- **`/sql/`** — SQL Playground: σχολική βάση `ΜΑΘΗΤΕΣ`/`ΜΑΘΗΜΑΤΑ`/`ΒΑΘΜΟΙ` σε SQLite WASM
  (sql.js, τοπικά), επεξεργαστής SQL, έτοιμα παραδείγματα SELECT/WHERE/JOIN/GROUP BY
  με 1 κλικ και κουμπί επαναφοράς της αρχικής βάσης. Πηγή: `config/sql/`.
- **`/pdf-tools/`** — PDF Studio: συγχώνευση πολλών PDF, εξαγωγή σελίδων (π.χ. `1-3,5`)
  και υδατογράφημα/αρίθμηση με ελληνική γραμματοσειρά (DejaVu subset + fontkit).
  Τα αρχεία επεξεργάζονται **αποκλειστικά στον browser** — κανένα upload. Πηγή: `config/pdf-tools/`.

### 🚀 Δικές μου Εφαρμογές (`/apps/` — custom-apps framework)

Πρότυπο μηχανισμός για **τις δικές σου standalone εφαρμογές**: κάθε υποφάκελος του
`custom-apps/` με `index.html` + `app.json` σερβίρεται αυτόματα στο `/apps/<όνομα>/`
από τον Nginx (χωρίς reload) και εμφανίζεται ως κάρτα στο Dashboard μέσω του
`apps-manifest.json` που παράγει το `scripts/build-apps-manifest.py` (ενσωματωμένο
στο `install.sh`). Έτοιμο παράδειγμα: **`/apps/binary-converter/`** (μετατροπέας
δυαδικού με 8 διαδραστικά διακοπτάκια bits).
📖 **Πλήρης οδηγός: [`CUSTOM-APPS-GUIDE.md`](CUSTOM-APPS-GUIDE.md)**

**🧙 App Builder Wizard (`/app-builder/`):** δημιουργία εφαρμογών μέσα από τον browser
χωρίς τερματικό — οδηγός 3 βημάτων (μεταδεδομένα → ZIP/upload ή Quick Paste κώδικα →
δημοσίευση), αυτόματη διόρθωση σχετικών διαδρομών, δικαιώματα & manifest, διαχείριση
(προεπισκόπηση/διαγραφή) και **ενσωμάτωση iframe σε μαθήματα MkDocs** με αντιγραφή snippet
ή άμεση εισαγωγή στο τέλος `.md` με 1 κλικ (auto-rebuild). Κωδικός καθηγητή `teacher2026`.

### 🔐 Πρόσβαση Καθηγητών

- **Dashboard:** κωδικός `teacher2026` (πύλη χρηστικότητας στον browser)
- **Διακομιστής (πραγματική προστασία):** HTTP Basic Auth — `teacher` / `teacher2026`

> ⚠️ Ο κωδικός στο dashboard είναι client-side και **δεν αποτελεί μηχανισμό ασφαλείας**.
> Η ουσιαστική προστασία εφαρμόζεται στον Nginx (`/etc/nginx/.school-htpasswd`).

Αλλαγή κωδικού (ΕΝΙΑΙΟΣ για Basic Auth + ΟΛΑ τα apps + dashboard — γράφεται στο
`data/portal.env`, τα units το φορτώνουν με `EnvironmentFile=`, τα tests το
διαβάζουν μέσω `scripts/lib.py`):
```bash
sudo TEACHER_PASS='νέος_κωδικός' FORCE_HTPASSWD=1 /opt/school-portal/install.sh --no-deps
```

## 📁 Δομή Project

```
/opt/school-portal/
├── common/                 # 🧩 Κοινό πακέτο Python (Βήμα 2 architecture review)
│   ├── auth.py             # TeacherAuth: HMAC cookies καθηγητή (legacy + payload),
│   │                       # TEACHER_CODE (env TEACHER_PASS → data/portal.env → default)
│   ├── classes.py          # οι 6 τάξεις (slug/label) + teachers area + greek_slug()
│   ├── lessons.py          # parse/render φάσεων, front-matter tags/favorite,
│   │                       # κατάλογος μαθημάτων + list_lessons_grouped/flat (dropdowns)
│   ├── db.py               # SQLite connect (WAL/Row/FK), read-only connect, migrations
│   ├── fs.py               # backup_history/backup_beside (.bak πριν από κάθε εγγραφή)
│   └── schedule.py         # ωράριο Excel→JSON, HH:MM, deadlines ±offset, JSON helpers
│   # Τα apps το βρίσκουν μέσω Environment=PYTHONPATH=/opt/school-portal στα units.
│   # Τα δεδομένα (DB, .cookie-secret, schedule.json) μένουν στους φακέλους των apps.
├── dashboard/              # Κεντρική πύλη (/)
│   ├── index.html          # Ζώνη Μαθητών + Ζώνη Καθηγητών
│   ├── lab/index.html      # Placeholder «Υπό Κατασκευή» (/lab/)
│   └── assets/             # Tailwind, Alpine, portal.js (ΤΟΠΙΚΑ)
├── mkdocs-site/            # Εκπαιδευτικό υλικό (/docs/)
│   ├── mkdocs.yml          # language: el, auto-nav Μαθημάτων (Lesson Wizard)
│   ├── hooks/lesson_phases.py   # φάσεις μαθήματος + απόκρυψη σημειώσεων καθηγητή
│   ├── docs/
│   │   ├── mathimata/<τάξη>/<μάθημα>/<ημερήσιο>/  # ΝΕΑ ΔΟΜΗ: 1 φάκελος = 1 μάθημα
│   │   │   └── index.md + aformisi.png + slides.pdf + διαδραστικά.html + …
│   │   ├── _paradeigma/         # 📦 παλιό υλικό (gymnasio-*, lykeio-*, games, teachers)
│   │   ├── videos/ audio/ pdfs/ slides/
│   │   └── assets/
│   │       ├── javascripts/     # class-filter, glossa, python-run, quiz,
│   │       │                    # lesson-phases (fullscreen), schedule (ωράριο)
│   │       ├── stylesheets/     # extra.css
│   │       ├── pyodide/         # Pyodide 314.0.8 (offline)
│   │       └── vendor/          # MathJax / Mermaid / Reveal.js (offline, install.sh)
│   └── overrides/
├── apps/lesson-wizard/     # 🧙 Lesson Wizard (/lesson-wizard/, FastAPI @8013)
│   ├── app.py              # φάσεις CRUD, tags/fav, πλέγμα ωραρίου, broadcast,
│   │                       # file browser docs/, βιβλιοθήκη PDF, /api/check
│   ├── templates/ static/  # Alpine UI: φίλτρα, grid ωραρίου, drag & drop
│   ├── data/               # schedule.json, active-overrides.json, πρότυπο xlsx
│   └── backups/            # .bak πριν από κάθε εγγραφή
├── apps/classroom-hub/     # 🏫 Ζωντανή Τάξη (/classroom/, FastAPI + WS @8014)
│   ├── app.py              # wiring: FastAPI+lifespan, mounts, join/config-public
│   ├── state.py            # κοινό state (CONFIG/CLIENTS/ACTIVE_*), auth cookies
│   ├── store.py            # SQLite schema+queries (chat/forum/polls/quiz/mutes)
│   ├── presence.py         # παρουσία/roster/broadcast, housekeeping, WS /ws
│   ├── routers/            # commands·polls·quizzes·timers·chat_forum·config_xlsx·catalog
│   ├── templates/index.html   # shell: μόνιμο μενού ανά ρόλο + iframe εφαρμογών
│   ├── static/classroom.js    # Alpine: dock⇄float εργαλειοθήκες, WS, confetti
│   └── data/               # classroom.db, config.json, rythmiseis-protypo.xlsx
├── pandoc-app/             # Visual Pandoc Studio (/pandoc/)
│   ├── main.py             # FastAPI + pandoc + WeasyPrint
│   ├── templates/index.html
│   ├── static/             # studio.css, studio.js
│   └── data/templates/     # σχολικά πρότυπα .docx
├── exams-app/              # Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα (/exams/)
│   ├── main.py             # FastAPI + SQLite (ενσωματωμένη sqlite3)
│   ├── exams.db            # Βάση (δημιουργείται αυτόματα, εκτός git)
│   ├── submissions/        # Αρχεία μαθητών ανά δραστηριότητα (εκτός git)
│   ├── templates/          # base/student/teacher.html (Jinja2)
│   └── static/             # student.js, teacher.js (vanilla JS)
├── live-quiz-app/          # Ζωντανό Παιχνίδι Τάξης — Live Quiz (/live-quiz/)
│   ├── main.py             # FastAPI + WebSockets + SQLite (ενσωματωμένη sqlite3)
│   ├── livequiz.db         # Βάση (δημιουργείται αυτόματα, εκτός git)
│   ├── templates/          # base/student/teacher.html (Jinja2)
│   └── static/             # student.js, teacher.js (vanilla JS + WebSocket)
├── web-lab/                # 🌐 Εργαστήριο Web HTML/CSS/JS (/web-lab/)
│   ├── main.py             # FastAPI + WebSockets + SQLite (δωμάτια, broadcast, publish)
│   ├── weblab.db           # Βάση δωματίων (δημιουργείται αυτόματα, εκτός git)
│   ├── templates/index.html   # 3-pane editor + preview + κονσόλα (Tailwind + Alpine)
│   └── static/             # app.js, snippets.js (ελληνικά), vendor/codemirror (offline)
├── h5p-studio/             # 🎮 H5P Studio Διαδραστικών Ασκήσεων (/h5p-studio/)
│   ├── main.py             # FastAPI + SQLite: CRUD, import/export .h5p, AI wizard, embed
│   ├── h5p.db              # Βάση μεταδεδομένων (δημιουργείται αυτόματα, εκτός git)
│   ├── library/<act-id>/   # Έγκυρη δομή H5P: h5p.json + content/content.json + media
│   ├── h5p-libraries/      # Τοπικές βιβλιοθήκες H5P (MultiChoice, QuestionSet, Blanks…)
│   ├── templates/          # index/editor/play.html + partials (Tailwind + Alpine, ελληνικά)
│   └── static/             # studio.js, editor.js, wizard.js + h5p-player/ (offline player)
├── lab-app/                # ΜΕΛΛΟΝΤΙΚΟ — δείτε README.md
├── app-builder/            # 🧙 Δημιουργός Custom Εφαρμογών (/app-builder/)
│   ├── main.py             # FastAPI: create/list/delete/embed API (HMAC cookie)
│   ├── templates/wizard.html  # UI 3 βημάτων (Tailwind + Alpine, ελληνικά)
│   └── static/wizard.js    # Λογική wizard (σχετικά fetch URLs)
├── custom-apps/            # 🚀 Δικές μου εφαρμογές (/apps/<όνομα>/, static, 0 MB)
│   ├── _template/          # Boilerplate: index.html + app.json (δεν σερβίρεται)
│   ├── binary-converter/   # Παράδειγμα: δυαδικό ↔ δεκαδικό ↔ hex με bit switches
│   └── apps-manifest.json  # Παράγεται από scripts/build-apps-manifest.py
├── CUSTOM-APPS-GUIDE.md    # Οδηγός προσθήκης δικών σου εφαρμογών
├── config/                 # Source of truth για nginx & systemd
│   ├── nginx/school-portal
│   └── systemd/school-{pandoc,exams,filebrowser,livequiz}.service, school-mkdocs.{service,path}
├── scripts/build-docs.sh   # Ανακατασκευή MkDocs → /var/www/docs
├── install.sh              # Αυτόματη εγκατάσταση/ενημέρωση
├── requirements.txt        # Pinned εκδόσεις Python
└── venv/                   # Python virtual environment
```
## ⚡ Διαδραστικές Δυνατότητες

| Δυνατότητα | Αρχείο | Περιγραφή |
| --- | --- | --- |
| **Φιλτράρισμα ανά τάξη** | `class-filter.js` | Το μενού δείχνει μόνο τα μαθήματα της τρέχουσας τάξης + selector εναλλαγής |
| **Ελληνική ψευδογλώσσα** | `glossa.js` | Custom highlighter για `ΑΡΧΗ/ΤΕΛΟΣ/ΑΝ/ΓΙΑ/ΟΣΟ…` (δεν υπάρχει έτοιμος lexer) |
| **Python στον browser** | `python-run.js` | Κουμπί **▶ Εκτέλεση** σε κάθε ```python block μέσω Pyodide (lazy load) |
| **Διαδραστικά κουίζ** | `quiz.js` | Άμεση ανατροφοδότηση, σκορ, επεξήγηση λάθους |
| **Παιχνίδι δυαδικού** | `games/binary-game.html` | 3 λειτουργίες: δυαδικό→δεκαδικό, δεκαδικό→δυαδικό, «Άναψε τα Bits» |
| **Lightbox εικόνων** | `mkdocs-glightbox` | Αυτόματη μεγέθυνση όλων των εικόνων |

## 📝 Visual Pandoc Studio

- **Επεξεργαστής Markdown** με ζωντανή προεπισκόπηση και έτοιμα snippets
- **Visual Flags Explorer:** οπτική επιλογή παραμέτρων (`--toc`, `--number-sections`,
  `--reference-doc`, `--highlight-style`, μεταδεδομένα…) με αυτόματη εμφάνιση της εντολής
- **Εξαγωγή:** DOCX · HTML · **PDF (WeasyPrint, ελληνικά χωρίς LaTeX)** · ODT · EPUB · MD · TXT
- **Πρότυπα .docx:** ανέβασμα/διαγραφή/δημιουργία σχολικών προτύπων (`reference-doc`)
- **🚀 Αποστολή στο MkDocs:** δημοσιεύει το μάθημα στην τάξη, ενημερώνει αυτόματα το
  `nav` του `mkdocs.yml` και ανακατασκευάζει το site

## 📤 Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα (`/exams/`)

**Περιβάλλον Μαθητή** (`/exams/` — ελεύθερο, χωρίς εγγραφή):
- Επιλογή τάξης (Α'–Γ' Γυμνασίου, Α'–Γ' Λυκείου) → dropdown με τις **ενεργές** δραστηριότητες
- Ονοματεπώνυμο + Τμήμα (π.χ. «Α2», «Γ1»)
- **Παράδοση αρχείου:** `.py`, `.docx`, `.pdf`, `.zip`, `.txt`, `.sb3`, `.glo` έως 50 MB + προαιρετικό σχόλιο
- **Ηλεκτρονικό διαγώνισμα:** ερωτήσεις πολλαπλής επιλογής & ανάπτυξης/κώδικα,
  χρονόμετρο αντίστροφης μέτρησης με **αυτόματη υποβολή** στον μηδενισμό
  (το deadline ορίζεται στον server· οι απαντήσεις σώζονται προσωρινά στον browser)
- Με την «Οριστική Υποβολή» εμφανίζεται **μοναδικός κωδικός επιβεβαίωσης** (π.χ. `K7M2-9QXD`)

**Περιβάλλον Καθηγητή** (`/exams/teacher` — κωδικός `teacher2026`, server-side HMAC cookie):
- Δημιουργία Εργασίας ή Διαγωνίσματος (τίτλος, τάξη, τύπος, διάρκεια, ερωτήσεις με μονάδες)
- Διακόπτης **Ενεργό / Κλειστό** ανά δραστηριότητα (άνοιγμα μόνο την ώρα του μαθήματος)
- Πίνακας υποβολών: **αυτόματη βαθμολογία** πολλαπλής επιλογής + πεδία βαθμολόγησης ανάπτυξης
- **📦 Λήψη όλων των αρχείων (.ZIP)** — αυτόματη μετονομασία σε `Τμήμα_Ονοματεπώνυμο_αρχείο`
  (Greeklish για συμβατότητα με κάθε unzip)
- **📊 Εξαγωγή Βαθμολογίας (.CSV)** — UTF-8 με BOM, separator `;`, δεκαδικό κόμμα (έτοιμο για Excel)

## 🎯 Ζωντανό Παιχνίδι Τάξης — Live Quiz (`/live-quiz/`)

Κουίζ πραγματικού χρόνου τύπου Kahoot για το τοπικό δίκτυο της τάξης
(FastAPI + WebSockets + SQLite, ~45 MB RAM).

**Οθόνη Καθηγητή / Προτζέκτορα** (`/live-quiz/teacher` — κωδικός `teacher2026`, HMAC cookie):
- Δημιουργία κουίζ: τίτλος + ερωτήσεις πολλαπλής επιλογής 4 απαντήσεων με χρονικό όριο ανά ερώτηση
- **Εισαγωγή JSON/CSV** (`text,option1..4,correct(1-4),time`) ή **3 έτοιμα ελληνικά παραδείγματα**
- Έναρξη Live Session → **4-ψήφιο PIN** στον προτζέκτορα + ζωντανή εμφάνιση ονομάτων μαθητών
- «Επόμενη Ερώτηση» → αντίστροφη μέτρηση → **γράφημα απαντήσεων** → **Top-5 Leaderboard**
- Αυτόματη λήξη ερώτησης όταν απαντήσουν όλοι· πρόωρος τερματισμός & **εξαγωγή αποτελεσμάτων CSV**

**Οθόνη Μαθητή** (`/live-quiz/` — χωρίς κωδικό, από PC/tablet/κινητό):
- Είσοδος με **PIN + Όνομα** (αυτόματη επανασύνδεση σε refresh/διακοπή δικτύου)
- 4 μεγάλα χρωματιστά κουμπιά: 🔺 Κόκκινο / 🔷 Μπλε / 🟡 Κίτρινο / 🟩 Πράσινο
- Άμεση ανατροφοδότηση: σωστό/λάθος, **πόντοι 500–1000 ανά ταχύτητα** και θέση στην κατάταξη

## 🌐 Εργαστήριο Web — HTML / CSS / JS (`/web-lab/`)

Διαδραστικό, συνεργατικό περιβάλλον εκμάθησης ανάπτυξης ιστοσελίδων
(FastAPI + WebSockets + SQLite @ `127.0.0.1:8011`, χωρίς Docker).
**Σημείωση:** η θύρα 8010 ανήκει ήδη στο excalidraw-room (`/board-ws/`).

**Editor (100% offline — CodeMirror τοπικά, Tailwind + Alpine από το `/assets/`):**
- 3 πάνελ **HTML / CSS / JS** με χρωματισμό σύνταξης & αυτόματο κλείσιμο tags
- **Ζωντανή Προεπισκόπηση** `<iframe>` (sandboxed) + **ενσωματωμένη κονσόλα**:
  `console.log/warn/error` και σφάλματα JS εμφανίζονται χωρίς DevTools (F12)
- «▶ Εκτέλεση / Ανανέωση» (Ctrl+Enter) + διακόπτης «⚡ Αυτόματη Ενημέρωση»
- Σκοτεινό/φωτεινό θέμα · **17 έτοιμα ελληνικά snippets** σε 4 κατηγορίες
  (HTML Βασικά, CSS Μορφοποίηση, JS Διαδραστικότητα, 3 Starter Projects)

**Συνεργασία τάξης (WebSockets + SQLite `weblab.db`):**
- **Solo:** αυτόματη αποθήκευση στο `localStorage` του browser
- **Δωμάτιο Ομάδας:** «Δημιουργία Δωματίου Συνεργασίας» → **4-ψήφιο PIN**·
  είσοδος με PIN + όνομα, λίστα συνδεδεμένων, ζωντανός συγχρονισμός κώδικα
  (ο κώδικας επιβιώνει refresh — αποθηκεύεται στη βάση)
- **Καθηγητής** (`teacher2026`, HMAC cookie): «📡 Αποστολή Κώδικα σε Όλους»
  (broadcast βασικής άσκησης) & «🔒 Μόνο Ανάγνωση» (κλείδωμα για προβολή στον πίνακα)

**Εξαγωγή & Δημοσίευση:**
- «💾 Λήψη .HTML»: ενώνει HTML + `<style>` + `<script>` σε ένα αυτόνομο αρχείο
  για παράδοση στο `/exams/`
- «🚀 Δημοσίευση στο Portal» (κωδικός καθηγητή): γράφει `custom-apps/<id>/`
  (`index.html` + `app.json`) και τρέχει το `build-apps-manifest.py` →
  **ζωντανή κάρτα στο Dashboard** στη διεύθυνση `/apps/<id>/`

## 🎮 H5P Studio — Διαδραστικές Ασκήσεις (`/h5p-studio/`)

Πλήρες, αυτόνομο περιβάλλον δημιουργίας, διαχείρισης & αναπαραγωγής ασκήσεων
**H5P** (FastAPI + Uvicorn + SQLite @ `127.0.0.1:8012`, χωρίς Docker).
**Σημείωση:** η θύρα 8011 ανήκει ήδη στο Web Lab (`/web-lab/`).

**Offline Player Engine (καμία εξάρτηση από CDN):**
- Ο **h5p-standalone** player είναι εγκατεστημένος τοπικά στο
  `h5p-studio/static/h5p-player/` και οι επίσημες βιβλιοθήκες H5P στο
  `h5p-studio/h5p-libraries/` (MultiChoice, QuestionSet, Blanks, DragText,
  ImageHotspots, Dialogcards, InteractiveVideo + όλες οι εξαρτήσεις τους,
  με ελληνικά αρχεία γλώσσας `language/el.json` όπου υπάρχουν)
- Κάθε δραστηριότητα αποθηκεύεται σε `library/<activity-id>/` με **έγκυρη δομή
  H5P** (`h5p.json`, `content/content.json`, `content/images|videos/`) + στη
  SQLite `h5p.db` (τίτλος, τύπος, τάξη, μάθημα, στόχος, δυσκολία)
- `/h5p-studio/play/<id>/`: καθαρή responsive σελίδα για μαθητές — με
  `?embed=1` φορτώνει χωρίς μενού μέσα σε `<iframe>` (auto-height postMessage),
  αλλιώς εμφανίζει διακριτική μπάρα επιστροφής

**Visual Editor (Tailwind + Alpine, 100% ελληνικά, split-screen preview):**
- ✅ Πολλαπλής Επιλογής & 📝 Σετ Ερωτήσεων (οπτικές ερωτήσεις/επιλογές,
  σωστές απαντήσεις, εικόνα ερώτησης, feedback & υποδείξεις)
- ✏️ Συμπλήρωση Κενών: μαρκάρεις λέξη → «⭐ Μετατροπή σε Κενό» → `*λέξη:υπόδειξη*`
- 🔀 Σύρε τις Λέξεις: ίδιο pattern + λέξεις-παγίδες (distractors)
- 📍 Εικόνα με Hotspots: ανέβασμα εικόνας & **κλικ πάνω της** → πινέζα με
  αυτόματα X%/Y%, χρώμα/εικονίδιο, τίτλος & επεξήγηση ανά πινέζα
- 🃏 Κάρτες Μνήμης: εμπρός/πίσω όψη, εικόνα κάρτας, υπόδειξη
- 🎬 Διαδραστικό Βίντεο: upload `.mp4/.webm` ή επιλογή από τα `docs/videos/`,
  χρονικά σημεία `MM:SS` με παύση + ερώτηση πολλαπλής ή επεξηγηματικό πλαίσιο
- **Ζωντανή Προεπισκόπηση** δεξιά (ίδια μηχανή με τους μαθητές, auto-refresh)

**AI Οδηγός Δημιουργίας (Wizard 3 βημάτων):**
1. Πλαίσιο μαθήματος: τάξη, μάθημα, κεφάλαιο, διδακτικός στόχος, δυσκολία, σημειώσεις
2. Παιδαγωγικές προτάσεις τύπου H5P ανά στόχο (με εξήγηση αξιοποίησης στην τάξη)
3. Διπλή λειτουργία: **✨ Αυτόματη Δημιουργία με AI** (OpenAI-compatible /
   Alibaba Qwen — ρυθμίσεις από `.env.keys` ή το ⚙️ modal) που ανοίγει έτοιμο
   τον editor, **και** γεννήτρια ελληνικών prompts (περιεχομένου/JSON +
   εικόνας για hotspots) με κουμπιά αντιγραφής, συνδέσμους προς
   NotebookLM/ChatGPT/Claude/Gemini και πεδίο «Επικόλληση JSON → Μετατροπή σε H5P»

**Βιβλιοθήκη & Ενσωμάτωση:**
- Φίλτρα ανά τάξη/μάθημα· προστασία δημιουργίας/επεξεργασίας/διαγραφής με
  `teacher2026` (HMAC cookie όπως στο `/exams/`)
- **📥 Import `.h5p`** (Lumi Desktop / Φωτόδεντρο / h5p.org): αποσυμπίεση,
  επικύρωση `h5p.json` + βιβλιοθηκών, άμεση αναπαραγωγή
- **⬇ Export `.h5p`**: έγκυρο ZIP με όλες τις βιβλιοθήκες μέσα (ανοίγει σε Lumi/Moodle)
- **🧩 Ενσωμάτωση σε Μάθημα MkDocs**: έτοιμος `<iframe>` με αντιγραφή ή dropdown
  με όλα τα `.md` των 6 τάξεων → append με 1 κλικ (+ αυτόματο `.bak` backup,
  ιστορικό στο `h5p-studio/backups/`, άμεσο rebuild του `/docs/`)

```bash
# End-to-end έλεγχος (API + headless Chromium: όλοι οι τύποι, import/export, embed)
venv/bin/python scripts/h5p-test.py
```

## 💾 Κατανάλωση RAM

| Υπηρεσία | Idle RAM | Σημείωση |
| --- | --- | --- |
| Nginx (nginx-light) | ~8 MB | 2 workers |
| `/docs/` (static) | **0 MB** | Καμία διεργασία — απευθείας από τον Nginx |
| Pandoc Studio | ~55 MB | uvicorn, 1 worker, `MemoryMax=320M` |
| Exams App | ~45 MB | uvicorn, 1 worker, `MemoryMax=256M` |
| Live Quiz | ~45 MB | uvicorn + WebSockets, 1 worker, `MemoryMax=256M` |
| Web Lab | ~45 MB | uvicorn + WebSockets, 1 worker, `MemoryMax=256M` |
| H5P Studio | ~45 MB | uvicorn, 1 worker, `MemoryMax=384M` (imports .h5p έως 100 MB) |
| Pyodide | **0 MB** server-side | Τρέχει στον browser του μαθητή |
| **Σύνολο** | **~65 MB** | |

Το `school-mkdocs.service` είναι **oneshot** (χτίζει και τερματίζει), ενώ το
`school-mkdocs.path` παρακολουθεί αλλαγές μέσω inotify → **μηδέν RAM σε ηρεμία**.

## 🛠️ Λειτουργία & Συντήρηση

```bash
# Κατάσταση υπηρεσιών
systemctl status school-pandoc.service school-mkdocs.path nginx

# Ανακατασκευή εκπαιδευτικού υλικού
sudo systemctl start school-mkdocs.service

# Logs
journalctl -u school-pandoc.service -f
tail -f /var/log/nginx/school-portal.error.log

# Έλεγχος διαμόρφωσης Nginx
sudo nginx -t && sudo systemctl reload nginx

# Smoke test όλων των endpoints (HTTP)
bash /opt/school-portal/scripts/smoke-test.sh

# Έλεγχος διαδραστικών σε ΠΡΑΓΜΑΤΙΚΟ browser (headless Chromium + CDP)
# Επαληθεύει: κουμπιά ▶ Εκτέλεση, εκτέλεση Pyodide, glossa, quiz, φίλτρο τάξης
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/browser-test.py

# Έλεγχος πλήρους ροής /exams/ σε browser (υποβολή αρχείου, διαγώνισμα, καθηγητής)
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/exams-browser-test.py

# End-to-end έλεγχος /live-quiz/ (καθηγητής + 2 μαθητές μέσω WebSockets, πόντοι, κατάταξη)
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/livequiz-test.py

# End-to-end έλεγχος /web-lab/ (δωμάτια, sync, broadcast/κλείδωμα, δημοσίευση στο /apps/)
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/weblab-test.py

# Έλεγχος /web-lab/ σε ΠΡΑΓΜΑΤΙΚΟ browser (editors, κονσόλα, snippets, Auto-Run, theme)
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/weblab-browser-test.py
```

> Ο `browser-test.py` απαιτεί `chromium` (`apt install chromium`) και
> `websocket-client` στο venv. Δεν χρειάζεται για τη λειτουργία της πύλης —
> είναι μόνο εργαλείο επαλήθευσης.

### 📚 Ημερήσια Μαθήματα (νέα δομή) & Lesson Wizard

Κάθε ημερήσιο μάθημα = **ένας φάκελος** στο `docs/mathimata/<τάξη>/<μάθημα>/<ημερήσιο>/`
με το `index.md` (σχέδιο μαθήματος) **και όλο το υλικό του** (εικόνες αφόρμησης,
slides.pdf, διαδραστικά .html, φύλλα εργασίας, αποσπάσματα βιβλίου).

Το markdown δομείται σε **διδακτικές φάσεις** με markers:

```markdown
<!-- phase: aformisi | title: Αφόρμηση | duration: 5 -->
## 🎯 … (εικόνα + λίγες περιεκτικές προτάσεις)
<!-- /phase -->
<!-- phase: syzitisi | … --> … <!-- /phase -->
<!-- phase: parousiasi | … --> … <!-- /phase -->
<!-- phase: drastiriotita | … --> … <!-- /phase -->
<!-- phase: aksiologisi | … --> … <!-- /phase -->
<!-- phase: kleisimo | … --> … <!-- /phase -->

<!-- teacher-notes -->
Σημειώσεις ΜΟΝΟ για τον καθηγητή (στόχοι, λύσεις, χρόνοι, διαφοροποίηση).
<!-- /teacher-notes -->
```

- **Μαθητής:** βλέπει το μάθημα καθαρό + κουμπί **🖥️ Παρουσίαση** (fullscreen,
  φάση-φάση με βελάκια). Οι σημειώσεις καθηγητή **δεν υπάρχουν καν στο HTML** —
  εξάγονται σε `index.teacher.html` που ο Nginx σερβίρει μόνο με έγκυρο cookie
  καθηγητή (`auth_request` → `/lesson-wizard/api/check`).
- **Καθηγητής:** μετά την είσοδο στο `/lesson-wizard/` βλέπει στην ίδια σελίδα
  badges φάσεων/χρόνων, μπάρα σχεδίου μαθήματος και τις σημειώσεις inline.
- **🧙 Lesson Wizard (`/lesson-wizard/`):** drag & drop αναδιάταξη φάσεων,
  προσθήκη από παλέτα τύπων, επεξεργασία περιεχομένου, upload υλικού στον
  φάκελο του μαθήματος, δημιουργία νέου μαθήματος από template, αυτόματο
  `nav` + rebuild, `.bak` backup πριν από κάθε εγγραφή.
- **🔎 Φίλτρα / 🏷 Tags / ⭐ Αγαπημένα:** η λίστα μαθημάτων φιλτράρεται ανά
  **τάξη, μάθημα, tag και αναζήτηση κειμένου**· κάθε μάθημα παίρνει tags και
  «αγαπημένο» (μπαίνουν στο front-matter `tags: [...]`, `favorite: true` —
  ταξιδεύουν με το αρχείο/git και φαίνονται ως chips στη σελίδα του μαθητή).
  Από κάθε κάρτα: **▶ Ενεργό τώρα**, **📡 Μετάδοση**, **👁 Μετάβαση** με 1 κλικ.
- **🗓️ Ωράριο — διαδραστικό πλέγμα (τύπου Excel):** γραμμές = ημέρες,
  στήλες = διδακτικές ώρες, κελιά = μάθημα + τμήμα. **Κλικ σε κελί** →
  επεξεργασία / ▶ ενεργό μάθημα / 📡 μετάδοση / 👁 μετάβαση / 🗑 καθαρισμός.
  **Drag & drop** κελιού για μετακίνηση (Ctrl = αντιγραφή), προσθήκη τμημάτων
  & ζωνών ωρών χωρίς Excel. Το **τρέχον μάθημα φωτίζεται πράσινα** με βάση την
  ώρα συστήματος (ανανέωση 20″)· υπάρχει **🧪 εικονική ώρα** (ημέρα+ώρα) για
  πειραματισμούς — επηρεάζει μόνο την προβολή του καθηγητή, όχι τους μαθητές.
  Η εισαγωγή από Excel παραμένει (φύλλα *Τμήματα / Ωρες / Ωραριο*). Ο μαθητής
  δηλώνει το τμήμα του («Το τμήμα μου» στο header) → βλέπει μόνο τα μαθήματα
  της τάξης του + widget **«Τώρα στο σχολείο»** με το ενεργό μάθημα της ώρας.
- **📡 Μετάδοση μαθήματος:** banner «Ο καθηγητής προβάλλει…» εμφανίζεται σε
  όλες τις σελίδες `/docs/` των μαθητών (όλων ή συγκεκριμένου τμήματος, με TTL
  & προαιρετικό μήνυμα) και οδηγεί απευθείας στο μάθημα. Auto-refresh ανά λεπτό.
- **📂 Γενικός File Browser (καρτέλα «Αρχεία»):** περιήγηση σε όλους τους
  φακέλους του `docs/` με breadcrumbs· κλικ σε `.md/.html/.css/.js/…` → inline
  editor με αποθήκευση+backup· τα ημερήσια μαθήματα ανοίγουν στον visual editor
  φάσεων· upload υλικού & δημιουργία φακέλου παντού (αυστηρό path validation).
- **📖 Βιβλιοθήκη βιβλίων (καρτέλα «Βιβλία»):** upload σχολικών PDF →
  [`/docs/vivliothiki/`](http://localhost/docs/vivliothiki/) με αυτόματη σελίδα
  βιβλιοθήκης & nav. Κουμπί **«🔗 Link σε μάθημα»** εισάγει σύνδεσμο που ανοίγει
  το βιβλίο σε **συγκεκριμένη σελίδα**: `[📖 …, σελ. 10](….pdf#page=10)` —
  το `#page=N` είναι το πρότυπο όλων των PDF viewers (το `#pagenumber=` δεν
  αναγνωρίζεται από browsers).
- **🧭 Πλωτό μενού πλοήγησης (παντού):** το `dashboard/assets/portal-nav.js`
  προσθέτει κουμπί 🧭 κάτω-δεξιά σε dashboard, `/docs/` και όλα τα apps
  (wizard, exams, live-quiz, web-lab, h5p, app-builder, md-publish) με γρήγορη
  μετάβαση σε Αρχική / Υλικό / Βιβλιοθήκη / Ωράριο / εργαστήρια (οι περιοχές
  καθηγητή εμφανίζονται μόνο όταν αναγνωρίζεται καθηγητής).

**Πιλότος:** Γ' Γυμνασίου → Πληροφορική → Ε1 Αλγοριθμική (Αναδρομή), 3 ημερήσια
μαθήματα βασισμένα στο βιβλίο ΙΕΠ (σελ. 7–10) και τις οδηγίες διδασκαλίας 2026-27.
Το παλιό υλικό διατηρείται άθικτο στο [`/docs/_paradeigma/`](http://localhost/docs/_paradeigma/).

### 🏫 Ζωντανή Τάξη — Κεντρικό Παράθυρο (`/classroom/`)

Νέο service **Classroom Hub** (`apps/classroom-hub/`, FastAPI + WebSockets + SQLite
@ `127.0.0.1:8014`, systemd `school-classroom.service`) — το «χειριστήριο» της τάξης:

- **Συνεχής παρακολούθηση παρουσίας:** κάθε browser κρατά WebSocket με heartbeat
  ανά 15″· ο server ξέρει ανά πάσα στιγμή **ποιος είναι συνδεδεμένος, με ποιον ρόλο
  (guest / μαθητής / καθηγητής), σε ποιο τμήμα και ποια σελίδα βλέπει**. Ο καθηγητής
  έχει ζωντανό roster (είσοδοι/έξοδοι άμεσα, αποσύνδεση «φαντασμάτων» στα 45″).
- **Ρόλοι:** *Guest* → αυτόματο **παιχνιδιάρικο όνομα τύπου Google Docs**
  («Γενναίος Πάνθηρας» 🐆…) από τις λίστες του Excel. *Μαθητής* → όνομα + τμήμα
  (+ προαιρετικός κωδικός τάξης από το Excel). *Καθηγητής* → `teacher2026`
  (HMAC cookie, ίδιο μοτίβο με όλη την πύλη).
- **Μόνιμο κεντρικό μενού** (📚 Μαθήματα · 📣 Ανακοινώσεις · 💬 Chat · 🗂️ Forum ·
  ❓ Βοήθεια + ό,τι άλλο ορίσετε): **διαμορφώσιμο ανά ρόλο από το Excel** —
  κάθε εφαρμογή ανοίγει **μέσα στο κεντρικό παράθυρο (iframe)** χωρίς να χάνεται
  το μενού (όλα τα apps της πύλης είναι same-origin).
- **Εργαλειοθήκες dock ⇄ float:** κουμπωμένες στην αριστερή μπάρα ή πλωτές
  (drag από την κεφαλίδα, resize από τη γωνία)· οι θέσεις αποθηκεύονται ανά χρήστη.
  Τα ζωντανά widgets (chat κ.λπ.) **μετακινούνται χωρίς απώλεια περιεχομένου**
  μεταξύ dock/float (κρατιούνται ζωντανές αναφορές των nodes).
- **Εντολές τάξης (καθηγητής → επιλεγμένο κοινό/τμήμα):** 📣 ανακοινώσεις,
  🎉 συγχαρητήρια & 🏆 βραβεία (προσωποποιημένα, με confetti), 🎲 **τυχαία επιλογή**
  από τους συνδεδεμένους, 📊 **poll** με διακόπτη «βλέπουν όλοι τα αποτελέσματα»
  (αλλιώς μόνο ο καθηγητής — στο κλείσιμο όλοι βλέπουν το τελικό), ➡️ **υποχρεωτική
  μετάβαση** μαθητών/guests σε συγκεκριμένη σελίδα, 📝 **quiz** — στους μαθητές
  **καταγράφεται** το αποτέλεσμα (SQLite, όνομα+τμήμα+σκορ), στους guests γίνεται
  **μόνο εξάσκηση**. Η βαθμολόγηση γίνεται στον server (το `correct` δεν φεύγει ποτέ
  στους πελάτες). Poll/quiz έχουν **🔚 αυτόματο κλείσιμο όταν απαντήσουν όλοι**
  οι συνδεδεμένοι του κοινού + προαιρετικό **χρονικό όριο**· όποιος απάντησε
  **δεν τα ξαναβλέπει** ούτε μετά από επανασύνδεση.
- **📣 Σύνθετη ανακοίνωση (2η επιλογή δίπλα στην απλή):** είδος + κείμενο +
  **σύνδεσμοι μαθημάτων** από τον κατάλογο του mkdocs-site με φίλτρα
  **⭐ αγαπημένα / 🏷 tags / τάξη / αναζήτηση**, προεπιλεγμένοι σύνδεσμοι εφαρμογών
  και **διαμορφώσιμοι δικοί σας σύνδεσμοι** (αποθηκεύονται στο config)· οι σύνδεσμοι
  εμφανίζονται ως κουμπιά σε toast & σελίδα Ανακοινώσεων, με προαιρετική
  **➡️ άμεση μετάβαση** όλων στον 1ο σύνδεσμο.
- **🗄️ Κονσόλα Διαχείρισης (μόνο καθηγητής, μενού «Διαχείριση»):** ανακοινώσεις,
  δημοσκοπήσεις (με ψήφους), quiz & αποτελέσματα και chat **αποθηκεύονται μόνιμα**
  (SQLite — επιβιώνουν restart) και διαχειρίζονται με **μεμονωμένες ενέργειες**
  (✏️ επεξεργασία, 🗑 διαγραφή, 🔒 κλείσιμο, ✕ διαγραφή αποτελέσματος μαθητή) και
  **μαζικές** (checkboxes + «Όλα», διαγραφή/κλείσιμο επιλεγμένων, καθαρισμός
  παλαιότερων των N ημερών, εκκαθάριση όλου του chat). Όλες οι αλλαγές
  συγχρονίζονται **ζωντανά** σε όλους τους συνδεδεμένους.
- **⏱️ Χρονομετρητές ιδιωτικοί ή δημόσιοι**, απλοί ή **συγχρονισμένοι με το ωράριο**:
  anchor σε έναρξη/λήξη διδακτικής ώρας **+ offset ±λεπτών** που ορίζετε εσείς.
  Το ✕ είναι διαθέσιμο **σε όλους** (μαθητής: τοπική απόκρυψη· καθηγητής: διακοπή
  για όλους) και υπάρχει client-side watchdog ώστε κανένα timer να μη «κολλάει».
  **Γεγονότα** στο τέλος ημέρας/ώρας (ανακοίνωση, συγχαρητήρια, βραβείο, μετάβαση)
  πυροδοτούνται αυτόματα μία φορά/ημέρα από background task.
- **💬 Chat τάξης & 🗂️ Forum** (νήματα, απαντήσεις, κλείδωμα/διαγραφή από καθηγητή,
  δικαιώματα guest από το Excel) πάνω στο ίδιο WebSocket + SQLite.
  **🔇 Moderation chat:** ο καθηγητής επιβάλλει **σιωπή (mute)** ανά χρήστη με
  διάρκεια (roster 🔇 ή κονσόλα· ισχύει και στο forum, ο μαθητής βλέπει σχετική
  ειδοποίηση) και **σβήνει ανάρμοστα μηνύματα** μεμονωμένα (🗑 hover στο chat)
  ή μαζικά — η διαγραφή αφαιρεί το μήνυμα ζωντανά από όλους.
- **📊 ΕΝΙΑΙΟ πρότυπο Excel `rythmiseis-protypo.xlsx` (12 καρτέλες)** για ΟΛΕΣ τις
  ρυθμίσεις, με χρωματικούς κώδικες (🟦 κεφαλίδες μην αγγίζετε · 🟨 υποχρεωτικά ·
  🟩 προαιρετικά · 🟥 ευαίσθητοι κωδικοί), dropdowns ΝΑΙ/ΟΧΙ & οδηγίες:
  *Οδηγίες, Τμήματα, Ωρες, Ωραριο* (**αυτούσιες με το πρότυπο του Lesson Wizard** —
  το ίδιο αρχείο ανεβαίνει και στα δύο apps), *Μενού, Εργαλειοθήκες, Ρόλοι,
  Ονόματα Guest, Timers, Γεγονότα, Μηνύματα, Poll-Quiz*. Άγνωστες καρτέλες
  αγνοούνται → το αρχείο επεκτείνεται μελλοντικά χωρίς αλλαγές κώδικα.
  Upload από την εργαλειοθήκη «🎛️ Εντολές Τάξης» → εφαρμόζεται **ζωντανά σε όλους**.
- **✏️ Edit σελίδας μαθήματος από το /docs/** (`assets/javascripts/lesson-edit.js`,
  μόνο καθηγητής — αναγνώριση μέσω `/lesson-wizard/api/check`): FAB «✏️» κάτω-αριστερά
  με 3 επιλογές — **⚡ Γρήγορη επεξεργασία** raw markdown σε modal (wizard
  `api/fs/read|save`, αυτόματο `.bak` + auto-rebuild), **🧙 Visual editor φάσεων**
  (deep-link `/lesson-wizard/#edit=<τάξη>/<μάθημα>/<slug>`) και **📝 Συνεργατικό
  Markdown** (νέα σημείωση HedgeDoc με το περιεχόμενο της σελίδας → δημοσίευση
  από `/md-publish/`). Δουλεύει και μέσα στο iframe της Ζωντανής Τάξης.
- **Έλεγχοι:** `scripts/classroom-test.py` (end-to-end μέσω Nginx: ρόλοι, roster,
  εντολές, poll ορατότητα/auto-close/όχι-επανεμφάνιση, quiz καταγραφή & διαχείριση,
  timers, μόνιμες ανακοινώσεις + edit/delete/bulk, σύνθετη ανακοίνωση & κατάλογος
  μαθημάτων, chat mute/διαγραφή, Excel round-trip με τον parser του Lesson Wizard)
  και `scripts/classroom-browser-test.py` (πραγματικός headless Chromium: είσοδοι,
  iframe, dock⇄float **με διατήρηση περιεχομένων**, ζωντανές ανακοινώσεις,
  timer-dismiss από guest, poll reconnect, κονσόλα διαχείρισης & φίλτρα ⭐/tags)
  και `scripts/board-classroom-test.py` (ο Ψηφιακός Πίνακας μέσα στην τάξη: άνοιγμα
  `/board/` σε iframe χωρίς το «I'm not a pretzel!», Start session, σχεδίαση &
  ζωντανή αναμετάδοση πινελιών σε 2ο χρήστη μέσω του self-hosted excalidraw-room).

### 🎪 Παράδειγμα ΟΛΩΝ των δυνατοτήτων MkDocs

Η σελίδα [`/docs/paradeigma-dynatotiton/`](http://localhost/docs/paradeigma-dynatotiton/)
είναι ζωντανή βιτρίνα κάθε δυνατότητας — **100% offline**:

- **Μαθηματικά LaTeX** → MathJax 3 τοπικά (`assets/vendor/mathjax/`, lazy load).
- **Διαγράμματα Mermaid** (flowchart, sequence, class, state, ER, gantt, pie,
  mindmap) → τοπικό `assets/vendor/mermaid/`. ⚠️ Το ενσωματωμένο mermaid του
  Material τραβάει από CDN — το `mermaid-init.js` «αρπάζει» τα μπλοκ πριν τον
  handler του Material και τα αποδίδει με την τοπική βιβλιοθήκη (light/dark sync).
- **Slides Reveal.js** (`<div class="slides-source" markdown="1">` με `---`) →
  fullscreen παρουσίαση από το `mkdocs-extras.js` (τοπικό `assets/vendor/reveal/`).
- **GIF animation** (παράγεται με Pillow: `scripts/make-demo-assets.py`),
  admonitions όλων των τύπων, tabs, task lists, annotations κώδικα, snippets,
  footnotes, emoji, glightbox zoom, Pyodide Python, ψευδογλώσσα, κουίζ, iframes.
- Ό,τι **δεν** είναι κατεστημένο επισημαίνεται με 🔧 και τις εντολές εγκατάστασης:
  **Marp CLI** (`npm i -g @marp-team/marp-cli`), **PlantUML** (`apt install
  default-jre graphviz` + `pip install plantuml-markdown`), **ffmpeg**, texlive.

Τα vendor assets κατεβαίνουν από το `install.sh` (όπως Alpine/Tailwind/Pyodide).

**Έλεγχος πιλότου σε πραγματικό browser:**
```bash
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/lessonwizard-test.py
```

**Χειροκίνητη προσθήκη (χωρίς wizard):**
```bash
mkdir -p /opt/school-portal/mkdocs-site/docs/mathimata/gymnasio-g/pliroforiki/m04-titlos
nano .../m04-titlos/index.md   # με τα phase markers παραπάνω
# το nav ενημερώνεται αυτόματα από το wizard (ή πρόσθεσέ το μεταξύ των δεικτών AUTO-NAV)
sudo systemctl start school-mkdocs.service
```

## 🔧 Τεχνικές Σημειώσεις

- **Architecture Review:** Το πλήρες review αρχιτεκτονικής (bugs που διορθώθηκαν,
  κοινό πακέτο `common/`, επόμενα tasks refactor & οδηγός επαλήθευσης) είναι στο
  [`ARCHITECTURE-REVIEW.md`](ARCHITECTURE-REVIEW.md) — ενημερώνεται μετά από κάθε βήμα.
- **Κοινό πακέτο `common/`:** Η αυθεντικοποίηση καθηγητή (HMAC cookies), οι
  λίστες τάξεων, το parsing μαθημάτων/ωραρίου και οι συνδέσεις SQLite ζουν στο
  `common/` (auth, classes, lessons, db, schedule) αντί να είναι αντιγραμμένα
  σε κάθε app. Κάθε app περνά τον δικό του φάκελο (`TeacherAuth(BASE_DIR, …)`),
  οπότε τα `.cookie-secret`/βάσεις παραμένουν ανά app και τα υπάρχοντα cookies
  συνεχίζουν να ισχύουν. Τα systemd units ορίζουν
  `Environment=PYTHONPATH=/opt/school-portal` για να βρίσκεται το πακέτο· για
  χειροκίνητη εκτέλεση: `PYTHONPATH=/opt/school-portal venv/bin/uvicorn main:app …`.
- **Ελληνικά PDF:** WeasyPrint + DejaVu/Liberation fonts (Type0/CID με ToUnicode →
  αναζητήσιμο κείμενο). Δεν απαιτείται LaTeX (~2 GB εξοικονόμηση).
- **Offline-first:** Tailwind, Alpine και Pyodide φιλοξενούνται τοπικά. Η πύλη
  λειτουργεί χωρίς σύνδεση Internet.
- **Αναζήτηση MkDocs:** Το `theme.language: el` δίνει πλήρη ελληνική διεπαφή.
  Ο lunr δεν διαθέτει ελληνικό stemmer, επομένως χρησιμοποιείται `lang: en`
  που διατηρεί τους ελληνικούς χαρακτήρες ανέπαφους.
- **DOM selectors:** Το Pygments βάζει την κλάση γλώσσας στο **wrapper**
  (`div.language-python.highlight > pre > code`), όχι στο `<code>`. Οι
  `python-run.js` / `glossa.js` ψάχνουν και τις δύο μορφές. Το marker
  idempotency μπαίνει στο `<code>` (που δεν μετακινείται), αλλιώς η διπλή
  κλήση της `apply()` (DOMContentLoaded + `document$`) δημιουργεί διπλά κουμπιά.
- **Hardening:** `ProtectSystem=strict`, `PrivateTmp`, `NoNewPrivileges`,
  `CapabilityBoundingSet=` κ.ά. Το `RestrictSUIDSGID` παραλείπεται σκόπιμα
  (μπλοκάρει τα setgid directories που χρειάζεται το rebuild).
- **Άδεια εκτέλεσης:** Το Pandoc Studio τρέχει ως `www-data`. Οι φάκελοι
  `mkdocs-site`, `data` και `/var/www/docs` έχουν setgid (2775) με ομάδα `www-data`.

## 📌 Εκκρεμότητες

- **`/lab/` — Διαχείριση Εργαστηρίου:** δεν υλοποιήθηκε (όπως ζητήθηκε).
  Πλήρεις προδιαγραφές, σχήμα SQLite και βήματα ενεργοποίησης στο
  [`lab-app/README.md`](lab-app/README.md).