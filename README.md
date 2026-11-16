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
| `/crypto/` | CyberChef | Στατικό HTML/JS (0 MB RAM) | Ελεύθερη |
| `/tools/` | IT-Tools | Στατικό SPA (0 MB RAM) | Ελεύθερη |
| `/board/` | Ψηφιακός Πίνακας Excalidraw | Πλήρες static build excalidraw-app, ελληνικά (0 MB RAM) | Ελεύθερη |
| `/board-ws/` | Excalidraw Room Server (ζωντανή συνεργασία) | Node.js + Socket.IO @ `127.0.0.1:8010` (~40 MB, stateless) | Ελεύθερη (E2E encrypted) |
| `/pad/` | Συνεργατικό Σημειωματάριο Τάξης | Etherpad Lite (Node.js 22 + SQLite) @ `127.0.0.1:8006` | Ελεύθερη (μαθητές) |
| `/pad/admin` | Διαχείριση Etherpad | ίδιο service + **Basic Auth** | 🔐 Καθηγητές (`teacher`) |
| `/md-pad/` | Συνεργατικό Markdown (HedgeDoc) | HedgeDoc 1.12.0 (Node.js 22 + SQLite) @ `127.0.0.1:8007` | Ελεύθερη (ανώνυμη επεξεργασία) |
| `/md-publish/` | Δημοσίευση HedgeDoc → MkDocs | FastAPI micro-bridge @ `127.0.0.1:8009`, HMAC cookie | 🔐 Καθηγητές (`teacher2026`) |
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

Αλλαγή κωδικού Basic Auth:
```bash
sudo TEACHER_PASS='νέος_κωδικός' FORCE_HTPASSWD=1 /opt/school-portal/install.sh --no-deps
```

## 📁 Δομή Project

```
/opt/school-portal/
├── dashboard/              # Κεντρική πύλη (/)
│   ├── index.html          # Ζώνη Μαθητών + Ζώνη Καθηγητών
│   ├── lab/index.html      # Placeholder «Υπό Κατασκευή» (/lab/)
│   └── assets/             # Tailwind, Alpine, portal.js (ΤΟΠΙΚΑ)
├── mkdocs-site/            # Εκπαιδευτικό υλικό (/docs/)
│   ├── mkdocs.yml          # language: el, 6 τάξεις, plugins
│   ├── docs/
│   │   ├── gymnasio-{a,b,g}/    # Α', Β', Γ' Γυμνασίου
│   │   ├── lykeio-{a,b,g}/      # Α', Β', Γ' Λυκείου
│   │   ├── teachers/            # 🔐 Λύσεις Καθηγητή
│   │   ├── games/               # binary-game.html + .js
│   │   ├── media/               # Οδηγίες πολυμέσων
│   │   ├── videos/ audio/ pdfs/ slides/
│   │   └── assets/
│   │       ├── javascripts/     # class-filter, glossa, python-run, quiz
│   │       ├── stylesheets/     # extra.css
│   │       └── pyodide/         # Pyodide 314.0.8 (offline)
│   └── overrides/
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

## 💾 Κατανάλωση RAM

| Υπηρεσία | Idle RAM | Σημείωση |
| --- | --- | --- |
| Nginx (nginx-light) | ~8 MB | 2 workers |
| `/docs/` (static) | **0 MB** | Καμία διεργασία — απευθείας από τον Nginx |
| Pandoc Studio | ~55 MB | uvicorn, 1 worker, `MemoryMax=320M` |
| Exams App | ~45 MB | uvicorn, 1 worker, `MemoryMax=256M` |
| Live Quiz | ~45 MB | uvicorn + WebSockets, 1 worker, `MemoryMax=256M` |
| Web Lab | ~45 MB | uvicorn + WebSockets, 1 worker, `MemoryMax=256M` |
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

### Προσθήκη νέου μαθήματος

**Μέσω Studio (προτείνεται):** `/pandoc/` → καρτέλα «🚀 Αποστολή στο MkDocs»

**Χειροκίνητα:**
```bash
nano /opt/school-portal/mkdocs-site/docs/gymnasio-a/neo-mathima.md
# πρόσθεσε τη σελίδα στο nav του mkdocs.yml
sudo systemctl start school-mkdocs.service
```

## 🔧 Τεχνικές Σημειώσεις

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