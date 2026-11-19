# 🏫 Architecture Review — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου

> **Ημερομηνία review:** 19 Νοεμβρίου 2026
> **Κατάσταση:** Βήμα 1 (bug fixes) ✅ · Βήμα 2 (κοινό πακέτο `common/`) ✅ — commit `2e0f814`, pushed στο origin/main
> · Task 3 (classroom-hub → APIRouters) ✅ + εκκρεμότητες Βήματος 2 (ενιαίος κωδικός, backup/list_lessons) ✅ — commit `e5b92cc`, pushed στο origin/main (19/11/2026)
> · Task 3 ΟΛΟΚΛΗΡΩΘΗΚΕ: h5p-studio & lesson-wizard → APIRouters ✅ — commit `ebb73b0`, pushed στο origin/main (19/11/2026, ίδιο μοτίβο· ίδια routes/API contracts, όλα τα e2e πράσινα)
> · Task 4 (Αξιοπιστία) ✅: common/nav.py single-owner + flock, lifespan livequiz/weblab, logging παντού, SQLite session() με closing — commit `2e4afab`, pushed στο origin/main (19/11/2026, όλα τα e2e §5 πράσινα)
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
1. ~~Git commit~~ ✅ Έγινε: commit `2e0f814` (31 αρχεία, +1126/−801), pushed στο
   `origin/main` (github.com/mk-ph-loc/school-portal) στις 19/11/2026.
2. ~~**Ενιαίος κωδικός από env**~~ ✅ Έγινε μαζί με το Task 3 (19/11/2026):
   `common/auth.py` → `_load_teacher_code()`: env `TEACHER_PASS` →
   `data/portal.env` (0640 root:www-data, εκτός git — το γράφει το install.sh
   βήμα 8β) → default `teacher2026`. Όλα τα Python units πήραν
   `EnvironmentFile=-/opt/school-portal/data/portal.env`. Το dashboard διαβάζει
   `assets/teacher-code.js` (παράγεται από το install.sh, ίδιος κωδικός·
   παραμένει UX gate, ΟΧΙ ασφάλεια). Tests: `scripts/lib.py` re-exportάρει το
   `common.auth.TEACHER_CODE`· όλα τα e2e/browser scripts + smoke-test.sh το
   χρησιμοποιούν αντί για hardcoded `teacher2026`.
3. **Υπόλοιπα duplications**:
   - ~~`backup_file()`~~ ✅ Νέο `common/fs.py` (`backup_history` flat ή
     mirror-tree + `backup_beside`)· lesson-wizard/bridge/h5p καλούν αυτό.
   - ~~`list_lessons()` των bridge/h5p/app-builder~~ ✅ Στο `common/lessons.py`:
     `list_lessons_grouped()` (mathimata/ + _paradeigma fallback ανά τάξη) &
     `list_lessons_flat()` (όλο το docs/, εκτός assets/teachers) — ίδια outputs.
   - Excel template generation (`make_template_xlsx`) classroom/wizard — μοιράζονται styling helpers. **(Ακόμα ανοιχτό)**

---

## 4. Επόμενα Tasks (οδηγός για νέες συνομιλίες)

> Κάθε task σε **νέα συνομιλία** με φρέσκο context. Prompt εκκίνησης: δώσε την
> αντίστοιχη ενότητα + «διάβασε το /opt/school-portal/ARCHITECTURE-REVIEW.md».
> Μετά από κάθε task: τρέξε τα e2e tests (βλ. §5) και ενημέρωσε την κατάσταση εδώ.

### Task 3 — Διάσπαση μονόλιθων σε APIRouters
**Στόχος:** συντηρησιμότητα, ΟΧΙ αλλαγή αρχιτεκτονικής deployment (ίδια services/ports).

- ~~`apps/classroom-hub/app.py` (~2.000 γραμμές)~~ ✅ **Έγινε 19/11/2026** (μαζί με
  τις εκκρεμότητες 2 & 3 του Βήματος 2 — βλ. §3):
  ```
  apps/classroom-hub/
    app.py            # wiring: FastAPI+lifespan, mounts, σελίδα/join/config-public (181 γρ.)
    state.py          # CONFIG/CLIENTS/ACTIVE_*/EVENTS_FIRED + auth/ident cookies (202 γρ.)
    store.py          # SQLite schema + queries: announcements/mutes/bulk_ids (171 γρ.)
    presence.py       # Client, broadcast, roster, housekeeping, hub_socket /ws (247 γρ.)
    routers/
      commands.py     # announce/random-pick/navigate + διαχείριση ανακοινώσεων
      polls.py        # cmd_poll + CRUD + bulk + ws_poll_vote
      quizzes.py      # cmd_quiz + CRUD + results + ws_quiz_submit
      timers.py       # timers + schedule anchors + events (fire_event)
      chat_forum.py   # chat history/mutes/forum REST + ws_chat/ws_forum_post + roster
      config_xlsx.py  # template generation + parser + upload (457 γρ. Excel)
      catalog.py      # lessons-catalog + announce-links (common.lessons)
  ```
  Συμβάσεις που κρατήθηκαν: ίδια 48 routes/methods (diff πριν/μετά = κενό),
  ο WS handler μένει στο `presence.py` και καλεί τους handlers των routers με
  ΤΕΜΠΕΛΙΚΑ imports (routers→presence μόνο, χωρίς κυκλικά)· όλο το κοινό state
  στο `state.py` (`import state`, ΟΧΙ `from state import CONFIG` — το upload
  αντικαθιστά το dict). Lifespan αντί `@app.on_event` (μέρος του Task 4 για
  classroom). Το `app.parse_config_xlsx` παραμένει ως alias για το e2e test.
  **Επαλήθευση:** classroom-test 69✓ · classroom-browser 28✓ · board-classroom 13✓ ·
  h5p 54/54 · lessonwizard 62/62 · livequiz ✓ · weblab ✓ · appbuilder ✓ (+browser 15✓) ·
  exams-browser 18✓ · custom-apps 25✓ · browser 16✓ · smoke 73/73.
  ⚠️ Προϋπάρχον (ΟΧΙ από το refactor): το `tools-browser-test.py` αποτυγχάνει στα
  checks του παλιού vanilla πίνακα (`redraw`/`.tbtn`) γιατί το /board/ είναι πλέον
  Excalidraw — ίδιο failure και με τον pre-refactor κώδικα· θέλει ενημέρωση του test.
- ~~`h5p-studio/main.py` (~1.700 γραμμές)~~ ✅ **Έγινε 19/11/2026** — ίδιο μοτίβο με classroom-hub:
  ```
  h5p-studio/
    main.py           # wiring: FastAPI, mounts (static/h5p-libraries/library), healthz (67 γρ.)
    state.py          # διαδρομές/σταθερές/TYPE_LIBS/labels/icons/PREVIEW_ID + TeacherAuth (79 γρ.)
    store.py          # SQLite schema+queries (activities/settings) + ai_config/.env.keys (93 γρ.)
    content.py        # dependency closure, build_content ανά τύπο, save/upsert, editor-state ↔ content.json (656 γρ.)
    routers/
      editor.py       # σελίδες index/edit, login/logout, CRUD βιβλιοθήκης, preview, media upload/videos (290 γρ.)
      player.py       # play/preview pages + import/export .h5p (validate_h5p_zip) (174 γρ.)
      wizard.py       # AI suggest/prompts/generate/paste-json + ρυθμίσεις AI (339 γρ.)
      embed.py        # list_lessons (common.lessons) + embed-code + 1-κλικ embed (.bak, common.fs) (100 γρ.)
  ```
  Συμβάσεις: ίδια 27 routes/methods (diff πριν/μετά = κενό)· κοινό state στο `state.py`
  (`import state`, ΟΧΙ `from state import …`)· το `content.py` είναι καθαρή βιβλιοθήκη
  (εξαρτάται μόνο από state/store — κανένα router δεν κάνει import άλλο router).
  Δεν υπήρχαν `@app.on_event`/WS σε αυτό το app (lifespan δεν χρειάζεται).
- ~~`apps/lesson-wizard/app.py` (949 γραμμές)~~ ✅ **Έγινε 19/11/2026**:
  ```
  apps/lesson-wizard/
    app.py            # wiring: FastAPI, mount static, include_router (43 γρ.)
    state.py          # διαδρομές/σταθερές + auth + lesson_dir/list_all_lessons/backup_file/rebuild_nav (134 γρ.)
    routers/
      lessons.py      # σελίδα/auth/check, λίστα & visual editor φάσεων, meta/tags, νέο μάθημα, υλικό (265 γρ.)
      schedule.py     # Excel template/upload, public JSON, active/broadcast, πλέγμα (cell/tmima/periods/move) (295 γρ.)
      fs_browser.py   # γενικός file browser docs/ (fs_path guard, list/read/save/upload/mkdir/delete) (159 γρ.)
      books.py        # 📖 βιβλιοθήκη PDF + rebuild_library_page + link #page=N σε μάθημα (164 γρ.)
  ```
  Συμβάσεις: ίδια 32 routes/methods (diff πριν/μετά = κενό)· `rebuild_nav()`/`backup_file()`
  κοινοί στο `state.py` (τους καλούν lessons/schedule/fs_browser/books — χωρίς κυκλικά).
  Το `scripts/classroom-test.py` §9 πλέον καλεί απευθείας τον `common.schedule.parse_schedule_xlsx`
  (αντί να φορτώνει ολόκληρο το lw app.py ως module — ίδιος parser, ίδια σύγκριση).
  **Επαλήθευση (και τα δύο):** h5p-test 54/54 · lessonwizard-test 62/62 · classroom-test ✓ ·
  livequiz ✓ · weblab ✓ · appbuilder ✓ · smoke 73/73. AST-level diff όλων των συναρτήσεων/
  σταθερών/classes πριν↔μετά: 0 διαφορές (μόνο προσθήκη `state./store./content.` qualifiers).
- **Αποδοχή:** όλα τα e2e tests πράσινα χωρίς αλλαγές στα API contracts. ✅ ΟΛΟΚΛΗΡΩΘΗΚΕ
  (classroom-hub + h5p-studio + lesson-wizard).

### Task 4 — Αξιοπιστία ✅ **Έγινε 19/11/2026**
- ~~**Nav single-owner στο mkdocs.yml**~~ ✅ Νέο `common/nav.py`: folder-driven
  idempotent `rebuild_nav(mkdocs_yml, backup_dir=…)` που ξαναχτίζει ΟΛΟ το μπλοκ
  μεταξύ BEGIN/END AUTO-NAV — Βιβλιοθήκη (αν υπάρχουν PDF) + Μαθήματα
  (`mathimata/`, ίδιες συμβάσεις τίτλων με πριν) + **Παλιό Υλικό** (ΟΛΟΙ οι
  φάκελοι του `_paradeigma/` — Γυμνάσιο/Λύκειο + games/media/teachers με τίτλους
  από τα H1 τους). Το χειροκίνητο `_paradeigma` nav μετακόμισε ΜΕΣΑ στο block
  (αφαιρέθηκε το διπλότυπο εκτός). Κάθε ανάγνωση+εγγραφή κάτω από **flock στο
  `data/nav.lock`**· ατομική εγγραφή (tmp + `os.replace`, 664)· ιστορικό .bak
  στο backups/ του caller (common.fs). Ο wizard (`state.rebuild_nav()`) και το
  MD-Bridge (`add_to_nav()` → γράφει μόνο το .md και καλεί rebuild) είναι πλέον
  λεπτοί wrappers — καμία δική τους λογική nav. Οι δημοσιεύσεις του bridge
  επιβιώνουν κάθε rebuild του wizard (live ad-hoc test ✓)· 8 ταυτόχρονα
  rebuilds από ξεχωριστές διεργασίες → 1 μπλοκ, καμία διαφθορά ✓.
- ~~**Lifespan** αντί deprecated `@app.on_event("startup")`~~ ✅ livequiz &
  weblab πήραν `@asynccontextmanager lifespan` (init_db + cleanup task, cancel
  στο shutdown) — ίδιο μοτίβο με το classroom (Task 3). Δεν έμεινε κανένα
  `on_event` στα δικά μας apps.
- ~~**Logging** σε όλα τα apps~~ ✅ `logging.basicConfig(INFO, stderr)` σε
  exams/livequiz/weblab/h5p/appbuilder/pandoc/mdbridge/lessonwizard/classroom
  (→ journalctl μέσω systemd). Τα σιωπηλά `except Exception: pass` στα
  background loops έγιναν `log.exception(...)`: `_cleanup_loop` livequiz &
  weblab, WS handlers livequiz/weblab (το housekeeping του classroom είχε
  διορθωθεί στο Β6c). Τα αναμενόμενα per-socket send failures μένουν ήσυχα
  (καθαρίζονται στο receive loop — όχι background loop).
- ~~**SQLite connection closing**~~ ✅ `common/db.py`: `session()` /
  `session_ro()` με `contextlib.closing` (commit/rollback όπως πριν + ΠΑΝΤΑ
  close). Οι `db()` των classroom-hub (39 call sites), h5p-studio, exams,
  livequiz, weblab επιστρέφουν πλέον `session(...)` — τα υπάρχοντα
  `with db() as conn:` δεν άλλαξαν καθόλου. Το mdbridge χρησιμοποιεί
  `hedgedoc_session()` (read-only, πάντα close). Verify: closed-after-exit +
  rollback-on-error unit check ✓.
- **Rate-limit tuning**: ΔΕΝ χρειάστηκε αλλαγή — με 30r/m+burst10 όλα τα e2e
  πέρασαν διαδοχικά (με ~60-75s παύση μεταξύ runs, όπως ορίζει το §5).
  Παραμένει η παρακολούθηση για NAT (ένα IP για όλο το σχολείο).
- **Επαλήθευση (live, μέσω Nginx):** classroom ✓ · livequiz ✓ · weblab ✓ ·
  appbuilder ✓ · h5p 54/54 ✓ · lessonwizard 62/62 ✓ · smoke 73/73 ✓ ·
  mkdocs build ✓ (νέο nav με ίδιο περιεχόμενο σελίδων). Ad-hoc: publish-new →
  entry ΜΕΣΑ στο AUTO-NAV block & επιβιώνει rebuild wizard· διαγραφή αρχείου →
  το entry φεύγει αυτόματα (folder-driven)· idempotent 2ο rebuild = no-op.

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