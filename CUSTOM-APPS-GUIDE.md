# 🚀 Οδηγός: Δικές μου Εφαρμογές & Προσομοιώσεις (`custom-apps/`)

Πλήρης οδηγός για το πώς προσθέτεις τις **δικές σου standalone εφαρμογές** (HTML/CSS/JavaScript)
στη Ψηφιακή Πύλη Σχολείου, ώστε:

- να τις σερβίρει **απευθείας ο Nginx** στη διεύθυνση `http://192.168.1.58/apps/<όνομα>/`
  (**0 MB RAM** στον server — καμία διαδικασία, κανένα Docker, κανένας Python),
- να εμφανίζονται **αυτόματα ως κάρτες** στο κεντρικό Dashboard (`/`), στην ενότητα
  **«Δικές μου Εφαρμογές & Προσομοιώσεις»**,
- να ελέγχεται η ορατότητά τους ανά ρόλο (`access: "all"` ή `"teachers"`),
- να αποθηκεύονται όλες στο **Git** μαζί με την υπόλοιπη πύλη.

> 📌 **Η ιδέα σε μία πρόταση:** κάθε υποφάκελος του `custom-apps/` με ένα `index.html` και ένα
> `app.json` είναι αυτόματα μια ζωντανή εφαρμογή στο `/apps/<όνομα-φακέλου>/` — δεν χρειάζεται
> **καμία** αλλαγή ή επανεκκίνηση του Nginx για κάθε νέα εφαρμογή.

---

## 🗺️ Πώς λειτουργεί (αρχιτεκτονική)

```
custom-apps/
├── _template/              ← πρότυπο (boilerplate) — ΔΕΝ σερβίρεται, ΔΕΝ μπαίνει στο manifest
│   ├── index.html          ← καθαρό HTML + Tailwind + μπάρα «← Επιστροφή στο Portal»
│   └── app.json            ← μεταδεδομένα κάρτας Dashboard
├── binary-converter/       ← παράδειγμα: μετατροπέας δυαδικού με 8 διακοπτάκια bits
│   ├── index.html
│   ├── app.js
│   └── app.json
├── my-app/                 ← Η ΔΙΚΗ ΣΟΥ εφαρμογή (όσες θέλεις…)
│   ├── index.html
│   ├── style.css           ← προαιρετικά
│   ├── app.js              ← προαιρετικά
│   └── app.json
└── apps-manifest.json      ← ΠΑΡΑΓΕΤΑΙ ΑΥΤΟΜΑΤΑ από το script — μην το επεξεργάζεσαι χειροκίνητα
```

Η ροή είναι:

1. **Nginx** (`config/nginx/school-portal`, ενότητα 5η) έχει ένα *γενικό* location:

   ```nginx
   location /apps/ {
       alias /opt/school-portal/custom-apps/;
       index index.html;
       try_files $uri $uri/ =404;
       add_header Cache-Control "no-cache";
   }
   ```

   Ό,τι μπει σε υποφάκελο του `custom-apps/` σερβίρεται **άμεσα** — ο φάκελος
   `my-app/` ανοίγει στο `/apps/my-app/` χωρίς reload. (Το `_template/` επιστρέφει 404.)

2. **`scripts/build-apps-manifest.py`** σαρώνει τα `app.json` όλων των υποφακέλων
   (αγνοώντας το `_template` και φακέλους που ξεκινούν με `_` ή `.`) και γράφει το
   `custom-apps/apps-manifest.json`.

3. **Το Dashboard** (`dashboard/index.html` + `dashboard/assets/portal.js`) κάνει fetch το
   `/apps/apps-manifest.json` κατά τη φόρτωση και σχεδιάζει δυναμικά τις κάρτες με Alpine.js.
   Οι κάρτες με `access: "teachers"` εμφανίζονται **μόνο** όταν είναι ενεργή η
   «Λειτουργία Καθηγητή» (κωδικός `teacher2026`).

---

## 🧙 Ο πιο εύκολος τρόπος: App Builder Wizard (χωρίς τερματικό!)

Στο **`http://192.168.1.58/app-builder/`** (κάρτα «Δημιουργός Εφαρμογών» στη Ζώνη Καθηγητών,
κωδικός `teacher2026`) υπάρχει ένας οδηγός 3 βημάτων που αυτοματοποιεί **όλα** τα παρακάτω:

1. **Βήμα 1 — Μεταδεδομένα:** id, τίτλος, περιγραφή, κατηγορία (6 τάξεις + ελεύθερη εισαγωγή),
   emoji, πρόσβαση (`all`/`teachers`), επιλογή «Αντικατάσταση υπάρχουσας».
2. **Βήμα 2 — Αρχεία ή Κώδικας:** ανέβασμα ενός `.zip` (αφαιρείται αυτόματα ο ενιαίος root
   φάκελος) ή πολλαπλών αρχείων, Ή επικόλληση HTML/CSS/JS (με χρήση του `_template` αν δώσεις
   μόνο το περιεχόμενο του `<main>`). Οι απόλυτες διαδρομές (`/style.css`) διορθώνονται
   αυτόματα σε `./style.css` και τα δικαιώματα/manifest ενημερώνονται μόνα τους.
3. **Βήμα 3 — Δημοσίευση & Ενσωμάτωση:** προεπισκόπηση, έτοιμο **snippet iframe για MkDocs**
   με κουμπί «Αντιγραφή Κώδικα», και **Άμεση Εισαγωγή** στο τέλος οποιουδήποτε μαθήματος
   (`.md`) με 1 κλικ — το υλικό ανακατασκευάζεται αυτόματα.

Εκεί βρίσκεις επίσης τη **λίστα των εγκατεστημένων εφαρμογών** με κουμπιά Προεπισκόπησης,
Διαγραφής και Ενσωμάτωσης σε Μάθημα. Οι χειροκίνητοι τρόποι που ακολουθούν παραμένουν
διαθέσιμοι για όποιον προτιμά τον πλήρη έλεγχο.

---

## ➕ Βήμα-βήμα: προσθήκη νέας εφαρμογής (χειροκίνητα)

### Τρόπος Α — Μέσω VS Code (προτεινόμενος)

1. Άνοιξε τον φάκελο `/opt/school-portal` στο VS Code (τοπικά ή με Remote-SSH στον server).
2. Στο file explorer, κάνε **αντιγραφή** του φακέλου `custom-apps/_template/` και
   **επικόλληση** μέσα στο `custom-apps/`. Μετονόμασε τον νέο φάκελο, π.χ. `my-app`.
   - ⚠️ Όνομα φακέλου: **πεζά λατινικά, ψηφία και παύλες** μόνο (π.χ. `quiz-grammatiki`,
     `physics-pendulum`). Όχι ελληνικά, όχι κενά, όχι underscores στην αρχή.
3. Άνοιξε το `my-app/app.json` και συμπλήρωσε τα πεδία (βλ. παρακάτω).
4. Άνοιξε το `my-app/index.html` και αντικατέστησε το περιεχόμενο του `<main>` με τη δική σου
   εφαρμογή. Άλλαξε και τον τίτλο στο `<title>` και στο `<h1>` της μπάρας πλοήγησης.
5. Πρόσθεσε όσα αρχεία θέλεις (`style.css`, `app.js`, εικόνες, υποφακέλους `assets/` κ.λπ.) —
   πάντα με **σχετικές διαδρομές** (βλ. επόμενη ενότητα).
6. Τρέξε στο τερματικό του VS Code (στον server):

   ```bash
   python3 /opt/school-portal/scripts/build-apps-manifest.py
   ```

7. Άνοιξε `http://192.168.1.58/apps/my-app/` — η εφαρμογή είναι ήδη ζωντανή!
   Κάνε ανανέωση στο `http://192.168.1.58/` και η κάρτα εμφανίζεται αυτόματα.
8. Αποθήκευσε στο Git (βλ. τελευταία ενότητα).

### Τρόπος Β — Μέσω τερματικού (SSH)

```bash
cd /opt/school-portal/custom-apps
cp -r _template my-app                     # 1. αντιγραφή προτύπου
nano my-app/app.json                       # 2. συμπλήρωσε τα μεταδεδομένα
nano my-app/index.html                     # 3. γράψε την εφαρμογή σου
python3 ../scripts/build-apps-manifest.py  # 4. ενημέρωση λίστας Dashboard
# 5. δοκιμή: http://192.168.1.58/apps/my-app/
```

> 💡 Αν δημιουργείς αρχεία ως root, φρόντισε να είναι αναγνώσιμα από τον Nginx:
> `chmod 644 αρχεία && chmod 755 φάκελοι` (το `install.sh` το διορθώνει αυτόματα συνολικά).

---

## 📋 Το αρχείο `app.json` — μεταδεδομένα της κάρτας

```json
{
  "id": "my-app",
  "title": "Ο Τίτλος της Εφαρμογής μου",
  "description": "Σύντομη περιγραφή 1–2 προτάσεων που φαίνεται στην κάρτα.",
  "category": "Β' Γυμνασίου / Πληροφορική",
  "icon": "🧮",
  "access": "all"
}
```

| Πεδίο | Υποχρεωτικό | Τιμές / Σημειώσεις |
|---|---|---|
| `id` | ✅ | **Πανομοιότυπο με το όνομα του φακέλου** (`my-app`). Μόνο πεζά λατινικά/ψηφία/παύλες. |
| `title` | ✅ | Ο τίτλος που εμφανίζεται στην κάρτα και προτείνεται για τη μπάρα της εφαρμογής. |
| `description` | – | Σύντομη περιγραφή για την κάρτα (αν λείπει, η κάρτα δείχνει μόνο τίτλο). |
| `category` | – | Ελεύθερο κείμενο-badge, π.χ. `"Γενικά / Μάθημα"`, `"Α' Λυκείου / Φυσική"`. Default: `Γενικά`. |
| `icon` | – | Ένα emoji, π.χ. `🚀 🔢 ⚡ 🧪 🎮`. Default: `🚀`. |
| `access` | – | `"all"` (όλοι, default) ή `"teachers"` (κάρτα ορατή μόνο σε Λειτουργία Καθηγητή). |

Το script **επικυρώνει** τα πάντα: αν κάποιο `app.json` είναι λάθος (μη έγκυρο JSON, `id` ≠ όνομα
φακέλου, λείπει `index.html` κ.λπ.), τυπώνει ακριβώς τι φταίει και **δεν χαλάει** το υπάρχον manifest:

```bash
python3 scripts/build-apps-manifest.py --check   # έλεγχος χωρίς εγγραφή
python3 scripts/build-apps-manifest.py           # έλεγχος + παραγωγή manifest
```

> 🔐 **Σημαντικό για το `access: "teachers"`:** όπως και στη «Ζώνη Καθηγητών» του Dashboard,
> πρόκειται για **πύλη χρηστικότητας (UX), όχι μηχανισμό ασφαλείας** — η απόκρυψη γίνεται στον
> browser και κάποιος που ξέρει το URL `/apps/my-app/` μπορεί να το ανοίξει απευθείας.
> **Μην βάζεις ευαίσθητο περιεχόμενο** (λύσεις διαγωνισμάτων κ.λπ.) σε custom apps. Για πραγματική
> προστασία χρησιμοποίησε τις περιοχές με HTTP Basic Auth (`/docs/teachers/`, `/pandoc/`).

---

## 🔗 Σχετικές διαδρομές (relative paths) — ΤΟ ΠΙΟ ΣΗΜΑΝΤΙΚΟ

Η εφαρμογή σου ζει σε **subpath**: `/apps/my-app/` — όχι στη ρίζα `/`. Γι' αυτό:

### ✅ ΣΩΣΤΟ — σχετικά με τον φάκελο της εφαρμογής

```html
<link rel="stylesheet" href="./style.css">
<script src="./app.js"></script>
<img src="./images/logo.png" alt="Λογότυπο">
<script src="./assets/data.js"></script>
```

```js
// fetch μέσα από την εφαρμογή:
fetch('./data/questions.json')
```

### ❌ ΛΑΘΟΣ — απόλυτες διαδρομές προς δικά σου αρχεία

```html
<link rel="stylesheet" href="/style.css">   <!-- ψάχνει στο dashboard/style.css → 404 -->
<script src="app.js"></script>              <!-- σπάει αν ανοίξεις /apps/my-app (χωρίς /) -->
```

### Εξαίρεση: κοινόχρηστα assets της πύλης (κατά σύμβαση με `/`)

Το Tailwind και το favicon της πύλης σερβίρονται τοπικά (λειτουργία **χωρίς Internet**) και τα
αναφέρουμε με απόλυτη διαδρομή γιατί ανήκουν στη *ρίζα* της πύλης, όχι στην εφαρμογή:

```html
<script src="/assets/tailwind.min.js"></script>
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
```

### ⚠️ Πάντα τελική κάθετος στο URL

Άνοιξε την εφαρμογή **με** τελική `/`: `http://192.168.1.58/apps/my-app/`.
Χωρίς αυτήν (`/apps/my-app`) ο Nginx κάνει μεν redirect, αλλά οι σχετικές διαδρομές τύπου
`app.js` (χωρίς `./`) θα έλυναν λάθος. Με `./style.css` είσαι καλυμμένος και στις δύο περιπτώσεις.

### 💡 Δοκιμή και τοπικά πριν ανεβάσεις

Επειδή όλα είναι σχετικά, μπορείς να ανοίξεις το `index.html` τοπικά στον υπολογιστή σου
(διπλό κλικ ή Live Server του VS Code) και να δουλέψεις offline. Μόνο το Tailwind από το
`/assets/` δεν θα φορτώσει τοπικά — για πλήρη δοκιμή χρησιμοποίησε τον server.

---

## 🔄 Ενημέρωση της λίστας καρτών του Dashboard

Κάθε φορά που **προσθέτεις / αφαιρείς / μετονομάζεις** εφαρμογή ή αλλάζεις το `app.json` της:

```bash
python3 /opt/school-portal/scripts/build-apps-manifest.py
```

Το script:
- σαρώνει όλους τους υποφακέλους του `custom-apps/` (αγνοεί `_template`, `_…`, `.…`),
- επικυρώνει κάθε `app.json` (id = όνομα φακέλου, έγκυρο `access`, ύπαρξη `index.html`),
- γράφει το `custom-apps/apps-manifest.json` ταξινομημένο αλφαβητικά κατά τίτλο,
- σε περίπτωση λάθους **δεν πειράζει** το υπάρχον manifest και σου λέει ακριβώς τι να διορθώσεις.

Μετά απλά κάνε **ανανέωση (F5)** στο Dashboard — οι κάρτες φορτώνονται δυναμικά με fetch,
δεν χρειάζεται κανένα build ή restart. Η ίδια εντολή τρέχει αυτόματα και μέσα από το
`install.sh` (βήμα 5β), οπότε μετά από `git pull` + `sudo ./install.sh --update` όλα συγχρονίζονται.

**Αφαίρεση εφαρμογής:** διέγραψε τον φάκελό της και ξανατρέξε το script:

```bash
rm -rf /opt/school-portal/custom-apps/my-app
python3 /opt/school-portal/scripts/build-apps-manifest.py
```

---

## 💾 Αποθήκευση στο Git

Ο φάκελος `custom-apps/` (μαζί με το παραγόμενο `apps-manifest.json`) **παρακολουθείται κανονικά
από το Git** — έτσι κάθε εφαρμογή σου ταξιδεύει μαζί με την πύλη και επανεγκαθίσταται αυτόματα.

```bash
cd /opt/school-portal

# 1. Δες τι άλλαξε
git status

# 2. Πρόσθεσε τη νέα εφαρμογή + το ανανεωμένο manifest
git add custom-apps/my-app custom-apps/apps-manifest.json
#    (ή συνολικά, αφού ελέγξεις το git status: git add .)

# 3. Commit με περιγραφικό μήνυμα
git commit -m "Added my-app: διαδραστική προσομοίωση εκκρεμούς"

# 4. Ανέβασε στο απομακρυσμένο repository (GitHub)
git push
```

Σε άλλον server / μετά από reinstall:

```bash
cd /opt/school-portal
sudo ./install.sh --update   # git pull + rebuild manifest + nginx reload + smoke tests
```

> ⚠️ Μην βάζεις στα custom apps αρχεία που καλύπτονται από το `.gitignore` (π.χ. `*.db`, `*.log`)
> ή πολύ μεγάλα binaries (>50 MB). Για μεγάλα κοινόχρηστα αρχεία υπάρχει το `/share/`.

---

## ✅ Έλεγχοι & αντιμετώπιση προβλημάτων

| Σύμπτωμα | Αιτία / Λύση |
|---|---|
| **404** στο `/apps/my-app/` | Λείπει `index.html`, ή λάθος όνομα φακέλου, ή άνοιξες `/apps/_template/` (μπλοκάρεται σκόπιμα). |
| **403 Forbidden** | Ο Nginx (`www-data`) δεν διαβάζει τα αρχεία: `chmod 755` στους φακέλους, `chmod 644` στα αρχεία. |
| Η εφαρμογή ανοίγει **χωρίς στυλ** | Απόλυτες διαδρομές (`/style.css`) αντί για σχετικές (`./style.css`). Έλεγξε την κονσόλα του browser (F12 → Network → 404). |
| Η κάρτα **δεν εμφανίζεται** | Δεν έτρεξες το `build-apps-manifest.py`, ή το `app.json` έχει λάθος (τρέξε το με `--check`), ή η κάρτα είναι `teachers` και δεν έχεις ξεκλειδώσει. |
| Παλιά έκδοση εφαρμογής | Σκληρή ανανέωση **Ctrl+Shift+R**. Ο Nginx στέλνει `Cache-Control: no-cache` για το `/apps/`, οπότε συνήθως αρκεί ένα F5. |
| Αλλαγές στο Nginx config | Μόνο αν πειράξεις το ίδιο το config: `sudo nginx -t && sudo systemctl reload nginx`. Για νέες εφαρμογές **δεν χρειάζεται ποτέ**. |

Χρήσιμες εντολές επαλήθευσης:

```bash
# Γρήγορος HTTP έλεγχος
curl -I http://192.168.1.58/apps/my-app/

# Πλήρης έλεγχος μηχανισμού σε πραγματικό browser (Dashboard + binary-converter)
/opt/school-portal/venv/bin/python /opt/school-portal/scripts/custom-apps-test.py

# Συνολικό smoke test της πύλης
bash /opt/school-portal/scripts/smoke-test.sh
```

---

## 📦 Έτοιμες εκπαιδευτικές εφαρμογές

Η πύλη συνοδεύεται πλέον από **10 έτοιμες εφαρμογές** (όλες static, **0 MB RAM** στον
server, 100% offline στο σχολικό LAN). Οι 4 με 📌 είναι **pinned** («Επιλεγμένο») και
εμφανίζονται πρώτες στο Dashboard· οι υπόλοιπες ακολουθούν αλφαβητικά κατά τίτλο.

| id | Τίτλος | Κατηγορία | Πηγή / upstream version | Μέγεθος | Ιδιαιτερότητες / γλώσσα UI |
|---|---|---|---|---|---|
| `drawio` 📌 | Διαγράμματα & Κυκλώματα (draw.io) | Τεχνολογία & ΤΝ | jgraph/drawio v32.7.4 (static build) | ~63 MB | Ελληνικά UI, χωρίς cloud/telemetry |
| `basthon` 📌 | Εργαστήριο Python (Basthon) | Προγραμματισμός | console.basthon.fr, kernel 0.92.0 + Pyodide 0.26.4 | ~65 MB* | UI Γαλλικά/Αγγλικά· το **Pyodide mirror κατεβαίνει από το `install.sh`** (βήμα 6ε, `scripts/fetch-basthon-pyodide.py`, εκτός git) |
| `binary-converter` 📌 | Μετατροπέας Δυαδικού & Βάρη Bits | Υλικό & Δεδομένα | δική μας ανάπτυξη (πρότυπο ποιότητας) | ~28 KB | Ελληνικά, καθαρό HTML/JS χωρίς εξαρτήσεις |
| `turbowarp` 📌 | Προγραμματισμός με Μπλοκ (TurboWarp) | Προγραμματισμός | TurboWarp/pentapod static build (turbowarp.org) | ~80 MB* | Ελληνικά UI· το **Scratch assets mirror (~53 MB) κατεβαίνει από το `install.sh`** (βήμα 6ιζ, `scripts/fetch-turbowarp-assets.py`, εκτός git) |
| `piskel` | Pixel Art & Κινούμενα Σχέδια (Piskel) | Γραφικά & Πολυμέσα | piskelapp.com packaged build (piskel/piskel) | ~2.3 MB | Αγγλικά UI, static χωρίς εξαρτήσεις |
| `screen-resolution-wizard` | Pixel, Ανάλυση Οθόνης & PPI | Γραφικά & Πολυμέσα | δική μας ανάπτυξη | ~28 KB | Ελληνικά, οδηγός 4 βημάτων |
| `minipaint` | Επεξεργασία Εικόνας (miniPaint) | Γραφικά & Πολυμέσα | viliusle/miniPaint (dist bundle) | ~5 MB | Ελληνικά UI (`?lang=el`) |
| `tf-playground` | Παιχνιδότοπος Νευρωνικών Δικτύων | Τεχνολογία & ΤΝ | tensorflow/playground (static build) | ~548 KB | Αγγλικά UI, τοπικές γραμματοσειρές/icons (χωρίς googleapis) |
| `snap` | Προχωρημένα Μπλοκ (Snap!) | Προγραμματισμός | jmoenig/Snap! v12.4.0 | ~69 MB | Ελληνικά UI (default), χωρίς telemetry/cloud |
| `bipes` | Ρομποτική & Μικροελεγκτές (BIPES) | Τεχνολογία & ΤΝ | BIPES/BIPES master (ui/, vendored Blockly) | ~19 MB | Ελληνικά UI (`msg/el.js`), χωρίς GA/appspot/CDN· σύνδεση πλακέτας WebSerial/WebUSB μόνο σε **HTTPS/localhost**, WebREPL και σε HTTP |

\* Το συνολικό μέγεθος **με** τα τοπικά mirrors που κατεβάζει το `install.sh`.

**Σημειώσεις για τα pinned & τα mirrors:**

- Το `pinned: true` στο `app.json` βάζει την κάρτα πρώτη με badge «📌 Επιλεγμένο» —
  η σειρά του manifest διατηρείται αυτούσια από το Dashboard (pinned-first, μετά
  αλφαβητικά κατά τίτλο). Αλλαγή pinned → ξανατρέξε `build-apps-manifest.py`.
- Τα mirrors των `basthon` (Pyodide) και `turbowarp` (Scratch assets) **δεν μπαίνουν
  στο git** (`.gitignore`) — κατεβαίνουν idempotent από το `install.sh` με marker
  `.complete` (FORCE=1 για αναγκαστική ανανέωση). Σε νέο server αρκεί
  `sudo ./install.sh --update`.
- Όλες οι εφαρμογές έχουν κουμπί **«← Portal»** επιστροφής (`portal-back.js`) και
  ελέγχονται από browser tests: `scripts/custom-apps-test.py`, `graphics-apps-test.py`,
  `basthon-test.py`, `turbowarp-test.py`, `snap-tf-test.py`, `bipes-test.py`.

---

## 📚 Το έτοιμο παράδειγμα: `binary-converter`

Στο `/apps/binary-converter/` υπάρχει μια πλήρης εκπαιδευτική εφαρμογή
**«Μετατροπέας Δυαδικού & Βάρη Bits»** (Β' Γυμνασίου / Α' Λυκείου):

- 8 οπτικά **διακοπτάκια bits** με τα βάρη 128…1 — ο μαθητής πατάει και βλέπει ζωντανά
  δεκαδικό, δυαδικό (ομαδοποιημένο ανά 4) και δεκαεξαδικό,
- **άθροισμα ενεργών βαρών** (π.χ. `32 + 2 = 34`) και πίνακας δυνάμεων του 2,
- αντίστροφη μετατροπή: γράφεις αριθμό σε οποιαδήποτε βάση και τα bits ρυθμίζονται μόνα τους,
- κουμπιά «Όλα ON / Όλα OFF / Αντιστροφή / Τυχαίος», επικύρωση εισόδου με ελληνικά μηνύματα.

Χρησιμοποίησέ το ως **αναφορά ποιότητας/δομής** για τις δικές σου εφαρμογές
(`index.html` + ξεχωριστό `app.js` + `app.json`).

Καλή δημιουργία! 🎓