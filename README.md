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
├── lab-app/                # ΜΕΛΛΟΝΤΙΚΟ — δείτε README.md
├── config/                 # Source of truth για nginx & systemd
│   ├── nginx/school-portal
│   └── systemd/school-{pandoc.service,mkdocs.service,mkdocs.path}
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

## 💾 Κατανάλωση RAM

| Υπηρεσία | Idle RAM | Σημείωση |
| --- | --- | --- |
| Nginx (nginx-light) | ~8 MB | 2 workers |
| `/docs/` (static) | **0 MB** | Καμία διεργασία — απευθείας από τον Nginx |
| Pandoc Studio | ~55 MB | uvicorn, 1 worker, `MemoryMax=320M` |
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