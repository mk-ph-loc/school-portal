# 🧪 Διαχείριση Εργαστηρίου & Εξοπλισμού — ΜΕΛΛΟΝΤΙΚΗ ΥΛΟΠΟΙΗΣΗ

> **Κατάσταση:** Προγραμματισμένο, **δεν έχει υλοποιηθεί ακόμα**.
> Η διαδρομή `/lab/` εξυπηρετεί προσωρινά μια στατική σελίδα «Υπό Κατασκευή»
> (βρίσκεται στο `dashboard/lab/index.html`).

## Προδιαγραφές (για τη μελλοντική υλοποίηση)

**Στοίβα:** FastAPI + Uvicorn + SQLite
**Θύρα:** `127.0.0.1:8001`
**systemd unit:** `school-lab.service`
**Διαδρομή μέσω Nginx:** `/lab/`

### Καρτέλες λειτουργιών

| Καρτέλα | Λειτουργίες |
| --- | --- |
| 🗓️ **Κρατήσεις** | Κράτηση αίθουσας ανά ώρα/τμήμα, έλεγχος συγκρούσεων, εβδομαδιαία προβολή |
| 🔧 **Βλάβες** | Αναφορά βλάβης, σοβαρότητα, κατάσταση αποκατάστασης, ιστορικό |
| 💻 **Δανεισμός Εξοπλισμού** | Καταγραφή δανεισμού, ημερομηνία επιστροφής, υπεύθυνος, ειδοποιήσεις εκπρόθεσμων |

### Προτεινόμενο σχήμα βάσης (SQLite)

```sql
CREATE TABLE rooms (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,              -- π.χ. "Εργαστήριο Πληροφορικής 1"
    capacity INTEGER
);

CREATE TABLE bookings (
    id INTEGER PRIMARY KEY,
    room_id INTEGER REFERENCES rooms(id),
    teacher TEXT NOT NULL,
    class_section TEXT,              -- π.χ. "Β2"
    date TEXT NOT NULL,              -- ISO: YYYY-MM-DD
    hour_slot INTEGER NOT NULL,      -- 1..8 (σχολικές ώρες)
    subject TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(room_id, date, hour_slot)
);

CREATE TABLE equipment (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,              -- π.χ. "Laptop Dell #12"
    category TEXT,                   -- laptop / tablet / projector / other
    serial TEXT,
    status TEXT DEFAULT 'available'  -- available / loaned / broken
);

CREATE TABLE faults (
    id INTEGER PRIMARY KEY,
    equipment_id INTEGER REFERENCES equipment(id),
    reported_by TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT DEFAULT 'medium',  -- low / medium / high
    status TEXT DEFAULT 'open',      -- open / in_progress / resolved
    reported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE TABLE loans (
    id INTEGER PRIMARY KEY,
    equipment_id INTEGER REFERENCES equipment(id),
    borrower TEXT NOT NULL,
    loaned_at TEXT DEFAULT CURRENT_TIMESTAMP,
    due_date TEXT NOT NULL,
    returned_at TEXT
);
```

### Αρχικά ελληνικά δεδομένα (seed)

- **Αίθουσες:** «Εργαστήριο Πληροφορικής 1» (24 θέσεις), «Εργαστήριο Πληροφορικής 2» (20 θέσεις), «Αίθουσα Ρομποτικής» (16 θέσεις)
- **Εξοπλισμός:** 20 laptops, 10 tablets, 2 προβολείς, 4 σετ Arduino, 2 εκτυπωτές 3D
- **Ωράριο:** 8 σχολικές ώρες (08:15–14:00)

## Βήματα ενεργοποίησης (όταν υλοποιηθεί)

1. Δημιούργησε την εφαρμογή στο `lab-app/main.py` (FastAPI + SQLite).
2. Αντέγραψε το `config/systemd/school-lab.service` στο `/etc/systemd/system/`.
3. Στο `config/nginx/school-portal`, αντικατέστησε το μπλοκ `location ^~ /lab/`
   με τη σχολιασμένη εκδοχή `proxy_pass http://127.0.0.1:8001/`.
4. Εκτέλεσε:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now school-lab.service
   sudo nginx -t && sudo systemctl reload nginx
   ```

## Σημείωση για την πρόσβαση μαθητών

Η κάρτα **«Πρόγραμμα Εργαστηρίου (Προβολή)»** στο dashboard πρέπει να οδηγεί σε
λειτουργία **μόνο ανάγνωσης** (read-only) για τους μαθητές, ενώ οι καρτέλες
διαχείρισης θα προστατεύονται με Basic Auth όπως το `/pandoc/`.