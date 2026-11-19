# 🏫 Architecture Review — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

> **Ημερομηνία review:** 19 Νοεμβρίου 2026
> **Κατάσταση:** Βήμα 1 (bug fixes) ✅ · Βήμα 2 (κοινό πακέτο `common/`) ✅ — μη committed ακόμα
> **Σκοπός αρχείου:** αρχειακή καταγραφή του review + αυτόνομος οδηγός για τα επόμενα tasks
> (κάθε ενότητα «Task» μπορεί να δοθεί αυτούσια ως prompt σε νέα συνομιλία).

---

## 1. Συνολική εκτίμηση

Το βασικό σχήμα — **Nginx στη :80/:443 → ανεξάρτητα FastAPI/Node services σε localhost
ports → SQLite ανά app → static όπου γίνεται** — είναι η ιδανική επιλογή για σχολικό
LAN σε Debian LXC χωρίς Docker. **Δεν χρειάζεται αναρχιτεκτόνηση.**

### Δυνατά σημεία (να διατηρηθούν)
- **Απομόνωση ανά εφαρμογή**: systemd units με `ProtectSystem=strict`, `ReadWritePaths`
  μόνο στον φάκελο κάθε app, `MemoryMax=256M`. Crash ενός app δεν επηρεάζει τα άλλα.
- **Static-first**: MkDocs build σε προσωρινό φάκελο + ατομικό rsync (`build-docs.sh`
  με flock) → 0 MB RAM σε ηρεμία, ποτέ ημιτελές site στους μαθητές.
- **Security θεμέλια**: HMAC-signed cookies (όχι απλό flag), `hmac.compare_digest`,
  HttpOnly/SameSite, path-traversal guards, server-side βαθμολόγηση quiz (το `correct`
  δεν φεύγει στον client), server-defined deadlines διαγωνισμάτων.
- **Πλούσια e2e κάλυψη**: 17 test scripts + smoke test ενσωματωμένο στο install.
- **Idempotent install** με `--update` / `--no-deps`.

### Τι ΔΕΝ αλλάζουμε
- Όχι Docker/K8s, όχι Postgres, όχι message broker — SQLite+WAL ανά app επαρκεί για ≤60 χρήστες/τάξη.
- Όχι ενοποίηση των apps σε ένα μεγάλο FastAPI — η απομόνωση ανά service είναι feature.
- Όχι SPA framework — Tailwind+Alpine vanilla ταιριάζει στο offline-LAN constraint.
- Το regex patch του Excalidraw (`fetch-excalidraw.sh` βήμα 6β3) είναι εύθραυστο εκ
  φύσεως αλλά έχει fallback warning + δικό του e2e test — αποδεκτό, με pinned version.

---

## 2. Bugs που βρέθηκαν & διορθώθηκαν (Βήμα 1 ✅)

| # | Bug | Fix | Αρχεία |
|---|-----|-----|--------|
| Β1 | H5P «1-click embed» σπασμένο: η `list_lessons()` έψαχνε `docs/<class>/` (ανύπαρκτοι μετά τη μετακόμιση σε `mathimata/`+`_paradeigma/`) → άδειο dropdown· ο validator απέρριπτε τα νέα paths με 400 | Listing με `mathimata/` + `_paradeigma/` fallback· validator δέχεται και τα δύο prefixes· σωστό `docs_url` για `index.md` | `h5p-studio/main.py` |
| Β2 | MD-Bridge publish-append: η λίστα επέστρεφε `mathimata/...` paths αλλά η `validate_lesson_path()` απαιτούσε `parts[0] in CLASS_SLUGS` → 400 σε κάθε επιλογή | Validator δέχεται `mathimata/`+`_paradeigma/` prefixes (ίδια με της λίστας UI) | `apps/hedgedoc-bridge/app.py` |
| Β3 | Προσωπικά βραβεία/συγχαρητήρια (`target_uid`) διέρρεαν σε ΟΛΟΥΣ μετά από refresh/reconnect μέσω `config/public` & WS welcome | Νέα `visible_announcements()` — φιλτράρει ανά ρόλο/audience/tmima/target_uid | `apps/classroom-hub/app.py` |
| Β4 | Mute παρακάμπτονταν από το REST `POST /api/forum/threads` (ο έλεγχος υπήρχε μόνο στο WS) | `active_mute()` check και στο REST endpoint → 403 | `apps/classroom-hub/app.py` |
| Β5 | Classroom SQLite χωρίς `timeout` (default 5s) και χωρίς `PRAGMA foreign_keys=ON` (τα CASCADE δεν ίσχυαν) | `timeout=15` + `foreign_keys=ON` (ευθυγράμμιση με exams/live-quiz) | `apps/classroom-hub/app.py` |
| Β6a | `compare_digest(str, str)` σε exams/mdbridge/appbuilder logins → TypeError/500 με μη-ASCII κωδικούς | `.encode()` παντού (όπως ήδη σε h5p/weblab/livequiz) | `exams-app/main.py`, `apps/hedgedoc-bridge/app.py`, `app-builder/main.py` |
| Β6b | Καθόλου rate limiting στα teacher logins → brute-force του κοινόχρηστου κωδικού | nginx `limit_req_zone school_login` (30r/m, burst=10 nodelay → 429) σε exact-match locations ΟΛΩΝ των login endpoints· κοινό snippet headers | `config/nginx/school-portal`, `config/nginx/school-proxy-headers.conf`, `install.sh` |
| Β6c | Το `housekeeping()` κατάπινε σιωπηλά κάθε exception (`except: pass`), κανένα logging | `log.exception(...)` — ίχνος στο journalctl | `apps/classroom-hub/app.py` |
| Bonus | App-builder: ο teachers-guard έπιανε μόνο root-level `teachers/`, όχι `_paradeigma/teachers/` | Έλεγχος `"teachers" in rel_parts` σε οποιοδήποτε βάθος + εξαίρεση από τη λίστα μαθημάτων | `app-builder/main.py` |
| Bonus | Παλιά paths στο appbuilder e2e test (`gymnasio-b/dyadiko.md`) | Ενημέρωση σε `_paradeigma/gymnasio-b/dyadiko.md` | `scripts/appbuilder-test.py` |

**Επαλήθευση (live, μέσω Nginx):** classroom-test ✓ · h5p-test 54/54 ✓ ·
lessonwizard 62/62 ✓ · livequiz ✓ · weblab ✓ · appbuilder ✓ · smoke 73/73 ✓.
Επιπλέον ad-hoc live tests: ξένο βραβείο αόρατο σε άλλον μαθητή / ορατό σε παραλήπτη
& καθηγητή· muted REST νήμα → 403· μη-ASCII login → 401· 12 γρήγορα λάθη → 429 μετά
το burst· σωστός κωδικός συνεχίζει να δουλεύει.

**⚠️ Σημείωση rate-limit:** αρχικά 6r/m ήταν πολύ αυστηρό (έκοβε διαδοχικά e2e runs
από ίδιο IP) → χαλάρωσε σε 30r/m+burst10. Αν όλα τα σχολικά PCs βγαίνουν από ένα
NAT IP, ίσως χρειαστεί περαιτέρω χαλάρωμα — παρακολούθηση στην πράξη. Τα student
joins/PIN δεν περνούν από τα login locations (εκτός του `/classroom/api/join` που
έχει burst=20).

---

## 3. Βήμα 2 ✅ — Κοινό πακέτο `common/` (υλοποιήθηκε, εκκρεμεί commit)

Το duplication drift (~8 αντίγραφα auth/db/classes/lessons σε κάθε app) ήταν η
**ρίζα** των Β1/Β2/Β5/Β6. Δημιουργήθηκε `/opt/school-portal/common/`:

| Module | Περιεχόμενο |
|--------|-------------|
| `auth.py` | `TeacherAuth(BASE_DIR, COOKIE_NAME)` — HMAC cookies καθηγητή. Legacy token `<expires>.<sig>` (7 apps) + payload token `<expires>:<b64url>.<sig>` (Classroom Hub, ελληνικά ονόματα latin-1 safe). `TEACHER_CODE`, `COOKIE_MAX_AGE`. Το `.cookie-secret` μένει **ανά app** → τα υπάρχοντα cookies ΔΕΝ ακυρώνονται. |
| `classes.py` | Οι 6 τάξεις (`CLASS_GROUPS/CLASS_SLUGS/CLASS_LABELS`), teachers area, `SLUG_RE`, `greek_slug()`. |
| `lessons.py` | `parse_lesson`/`render_lesson` (φάσεις), `fm_meta`/`set_fm_meta` (tags/favorite), `valid_lesson_path`, `list_all_lessons`, `lessons_catalog` — single source of truth για τη δομή `mathimata/`. |
| `db.py` | `connect(db_path, foreign_keys=True, timeout=15)` (WAL/Row/FK), `connect_ro` (π.χ. hedgedoc.sqlite), `add_columns` (ήπιες migrations). |
| `schedule.py` | `parse_schedule_xlsx` (Τμήματα/Ωρες/Ωραριο — το ΕΝΙΑΙΟ Excel), `hhmm`, `schedule_deadline`/`event_deadline` (±offset), `load_json`/`save_json`. |

**Integration:** όλα τα apps κάνουν `from common.… import …`· τα systemd units πήραν
`Environment=PYTHONPATH=/opt/school-portal`· χειροκίνητη εκτέλεση:
`PYTHONPATH=/opt/school-portal venv/bin/uvicorn main:app …`.
Τα δεδομένα (DB, secrets, schedule.json) παραμένουν στους φακέλους των apps.
Αποτέλεσμα: **−801 γραμμές duplication** (+313 νέες, κυρίως το common/ + README).

**Επαλήθευση μετά το migration:** classroom ✓ · lessonwizard 62/62 ✓ · h5p 54/54 ✓ ·
livequiz ✓ · smoke 73/73 ✓ (όλα τα services active με τον νέο κώδικα).

### ⚠️ Εκκρεμότητες Βήματος 2
1. **Git commit** — ΟΛΕΣ οι αλλαγές (Βήμα 1+2) είναι στο working tree, μη committed
   (23 αρχεία + `common/` + `config/nginx/school-proxy-headers.conf`).
2. **Ενιαίος κωδικός από env**: το `common/auth.py` έχει ακόμα hardcoded
   `TEACHER_CODE = "teacher2026"`. Το `TEACHER_PASS` του install.sh αλλάζει μόνο το
   Basic Auth, ΟΧΙ τα apps. Θέλει: `TEACHER_CODE = os.environ.get("TEACHER_PASS", "teacher2026")`
   + `Environment=TEACHER_PASS=…` στα units (ή κοινό `data/portal.env` με `EnvironmentFile=`)
   + ενημέρωση dashboard JS/tests ώστε να διαβάζουν τον ίδιο κωδικό.
3. **Υπόλοιπα duplications που ΔΕΝ μπήκαν στο common ακόμα**:
   - `backup_file()` — 3 παραλλαγές (lesson-wizard: μόνο backups/· bridge/h5p: .bak δίπλα + ιστορικό). Ενοποίηση σε `common/lessons.py` ή νέο `common/fs.py`.
   - `list_lessons()` των bridge/h5p/app-builder (grouped ανά τάξη με `_paradeigma` fallback) — παραλλαγές της `common.lessons`.
   - Excel template generation (`make_template_xlsx`) classroom/wizard — μοιράζονται styling helpers.

---

## 4. Επόμενα Tasks (οδηγός για νέες συνομιλίες)

> Κάθε task σε **νέα συνομιλία** με φρέσκο context. Prompt εκκίνησης: δώσε την
> αντίστοιχη ενότητα + «διάβασε το /opt/school-portal/ARCHITECTURE-REVIEW.md».
> Μετά από κάθε task: τρέξε τα e2e tests (βλ. §5) και ενημέρωσε την κατάσταση εδώ.

### Task 3 — Διάσπαση μονόλιθων σε APIRouters
**Στόχος:** συντηρησιμότητα, ΟΧΙ αλλαγή αρχιτεκτονικής deployment (ίδια services/ports).

- `apps/classroom-hub/app.py` (~2.000 γραμμές, ~70 routes, 6 domains) →
  ```
  apps/classroom-hub/
    app.py            # wiring: FastAPI, lifespan, mounts (~100 γραμμές)
    store.py          # SQLite schema + queries (ή common.db)
    presence.py       # Client, CLIENTS, broadcast, roster, housekeeping
    routers/
      commands.py     # announce/random-pick/navigate (+ visible_announcements)
      polls.py        # cmd_poll + CRUD + bulk + ws vote
      quizzes.py      # cmd_quiz + CRUD + results + ws submit
      timers.py       # timers + schedule anchors + events
      chat_forum.py   # chat history/mutes/forum (REST+WS)
      config_xlsx.py  # template generation + upload (~450 γραμμές Excel)
      catalog.py      # lessons-catalog (καλεί common.lessons)
  ```
  Προσοχή: το WS handler (`hub_socket`) dispatchάρει σε poll/quiz/chat/forum —
  κράτα το στο `presence.py` ή `app.py` και κάνε import τους handlers από τα routers.
  Το global `CONFIG`/`CLIENTS`/`ACTIVE_*` state θέλει ένα module (π.χ. `state.py`)
  για αποφυγή κυκλικών imports.
- `h5p-studio/main.py` (~1.700 γραμμές) → 4 routers: editor/library, player/import-export,
  AI wizard, MkDocs embed.
- `apps/lesson-wizard/app.py` → lessons, schedule, fs-browser, books.
- **Αποδοχή:** όλα τα e2e tests πράσινα χωρίς αλλαγές στα API contracts.

### Task 4 — Αξιοπιστία (μικρό, μπορεί μαζί με Task 3)
- **Nav single-owner στο mkdocs.yml**: σήμερα γράφουν 2 writers με διαφορετική λογική —
  Lesson Wizard `rebuild_nav()` (block rewrite μεταξύ BEGIN/END AUTO-NAV) και
  MD-Bridge `add_to_nav()` (text insertion ΕΚΤΟΣ block → κίνδυνος απώλειας σε rebuild +
  race χωρίς lock). Λύση: ένα `common/nav.py` με folder-driven idempotent
  `rebuild_nav()`· όλοι γράφουν αρχεία και το καλούν· `flock` στο `data/nav.lock`
  γύρω από κάθε yml write.
- **Lifespan** αντί deprecated `@app.on_event("startup")` (classroom, livequiz, weblab).
- **Logging** σε όλα τα apps (stderr → journalctl)· καθόλου σιωπηλά `except: pass`
  σε background loops.
- **SQLite connection closing**: το `with db() as conn:` κάνει commit αλλά ΔΕΝ κλείνει
  τη σύνδεση (39 call sites στο classroom). Wrapper με `contextlib.closing` στο
  `common/db.py` (π.χ. `@contextmanager def session(path)`).
- **Rate-limit tuning** αν χρειαστεί (βλ. §2 σημείωση NAT).

### Task 5 — Ποιότητα ζωής (τελευταίο, χαμηλού ρίσκου)
- **Test harness**: 17 scripts με copy-pasted `Client/check/cookiejar` boilerplate και
  hardcoded `teacher2026` → `scripts/lib.py` (ή pytest με markers smoke/e2e/browser)
  + κοινό config που διαβάζει τον ίδιο κωδικό με τα apps. Θα έπιανε αυτόματα τα Β1/Β2.
- **Ενιαίος κωδικός** (αν δεν γίνει στο Βήμα 2): βλ. §3 εκκρεμότητα 2.
- **Αναδιοργάνωση φακέλων** (προαιρετικό): δικά μας apps στο `apps/`, vendored upstream
  (etherpad, hedgedoc, excalidraw-room) σε `vendor/`. Κοστίζει αλλαγές σε
  systemd/nginx/install — μόνο αν συνδυαστεί με άλλο refactor.
- **README split**: 638 γραμμές → ξεχωριστά docs ανά ενότητα αν μεγαλώσει κι άλλο.

---

## 5. Πώς επαληθεύουμε (μετά από ΚΑΘΕ αλλαγή)

```bash
cd /opt/school-portal
venv/bin/python scripts/classroom-test.py        # Ζωντανή Τάξη (WS+REST+Excel)
venv/bin/python scripts/h5p-test.py              # H5P (API+browser, 54 checks)
venv/bin/python scripts/lessonwizard-test.py     # Lesson Wizard (62 checks)
venv/bin/python scripts/livequiz-test.py         # Live Quiz (WS game flow)
venv/bin/python scripts/weblab-test.py           # Web Lab
venv/bin/python scripts/appbuilder-test.py       # App Builder
bash scripts/smoke-test.sh                       # 73 checks όλων των URLs/services
```

- Μετά από αλλαγές nginx: `nginx -t && systemctl reload nginx`
  (προσοχή: `limit_req_zone` ΜΟΝΟ σε http context, εκτός `server{}`).
- Μετά από αλλαγές Python: `systemctl restart school-<app>.service`.
- **Rate-limit προσοχή στα tests**: διαδοχικά runs από ίδιο IP μπορεί να φάνε 429 —
  περίμενε ~60s μεταξύ runs που κάνουν πολλά logins.
- Deployment nginx config: `config/nginx/school-portal` →
  `/etc/nginx/sites-available/school-portal` (symlink από sites-enabled) +
  `config/nginx/school-proxy-headers.conf` → `/etc/nginx/snippets/`.

## 6. Χαρτογράφηση υπηρεσιών (αναφορά)

| Path | Service | Port | Stack |
|------|---------|------|-------|
| `/` | dashboard | — | static HTML+Tailwind+Alpine |
| `/docs/` | mkdocs (oneshot+path unit) | — | static, build via `build-docs.sh` |
| `/pandoc/` | school-pandoc | 8002 | FastAPI + Basic Auth |
| `/share/` | school-filebrowser | 8003 | Go binary |
| `/exams/` | school-exams | 8004 | FastAPI+SQLite |
| `/live-quiz/` | school-livequiz | 8005 | FastAPI+WS+SQLite |
| `/pad/` | school-etherpad | 8006 | Node 22+SQLite (vendored) |
| `/md-pad/` | school-hedgedoc | 8007 | HedgeDoc 1.12 (vendored) |
| `/app-builder/` | school-appbuilder | 8008 | FastAPI |
| `/md-publish/` | school-mdbridge | 8009 | FastAPI (HedgeDoc→MkDocs bridge) |
| `/board-ws/` | school-excalidraw-room | 8010 | Node+Socket.IO (vendored) |
| `/web-lab/` | school-weblab | 8011 | FastAPI+WS+SQLite |
| `/h5p-studio/` | school-h5p | 8012 | FastAPI+SQLite+offline player |
| `/lesson-wizard/` | school-lessonwizard | 8013 | FastAPI+openpyxl |
| `/classroom/` | school-classroom | 8014 | FastAPI+WS+SQLite+openpyxl |
| `/board/`, `/crypto/`, `/tools/`, `/circuits/`, `/blockly/`, `/sql/`, `/pdf-tools/`, `/apps/` | — | — | 100% static |

**Κοινές συμβάσεις:** κωδικός καθηγητή `teacher2026` (HMAC cookie ανά app,
`<app>_teacher`)· ωράριο/ρυθμίσεις μέσω ΕΝΙΑΙΟΥ Excel (12 καρτέλες, μοιράζεται
wizard↔classroom)· μαθήματα σε `mkdocs-site/docs/mathimata/<τάξη>/<μάθημα>/<lesson>/index.md`
(παλιό υλικό: `_paradeigma/`)· προστασία σημειώσεων καθηγητή: `*.teacher.html` με
nginx `auth_request` → lesson-wizard `/api/check`.