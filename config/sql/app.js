/* =========================================================================
 * SQL Playground — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου
 * SQLite στον browser μέσω sql.js (WebAssembly). 100% τοπική εκτέλεση.
 * ========================================================================= */
'use strict';

// --- Αρχική εκπαιδευτική σχολική βάση ------------------------------------
const SEED_SQL = `
CREATE TABLE ΜΑΘΗΤΕΣ (
  ID INTEGER PRIMARY KEY,
  ΟΝΟΜΑΤΕΠΩΝΥΜΟ TEXT NOT NULL,
  ΤΑΞΗ TEXT NOT NULL,
  ΤΜΗΜΑ TEXT NOT NULL,
  ΗΜΕΡΟΜΗΝΙΑ_ΕΓΓΡΑΦΗΣ TEXT
);

CREATE TABLE ΜΑΘΗΜΑΤΑ (
  ID INTEGER PRIMARY KEY,
  ΤΙΤΛΟΣ TEXT NOT NULL,
  ΚΑΘΗΓΗΤΗΣ TEXT NOT NULL,
  ΩΡΕΣ_ΕΒΔΟΜΑΔΑΣ INTEGER
);

CREATE TABLE ΒΑΘΜΟΙ (
  ID INTEGER PRIMARY KEY,
  ΜΑΘΗΤΗΣ_ID INTEGER NOT NULL REFERENCES ΜΑΘΗΤΕΣ(ID),
  ΜΑΘΗΜΑ_ID INTEGER NOT NULL REFERENCES ΜΑΘΗΜΑΤΑ(ID),
  ΒΑΘΜΟΣ REAL NOT NULL CHECK (ΒΑΘΜΟΣ >= 0 AND ΒΑΘΜΟΣ <= 20),
  ΤΕΤΡΑΜΗΝΟ TEXT NOT NULL
);

INSERT INTO ΜΑΘΗΤΕΣ VALUES
 (1,'Γιώργος Παπαδόπουλος','Α','Α1','2025-09-11'),
 (2,'Μαρία Ιωάννου','Α','Α1','2025-09-11'),
 (3,'Νίκος Αλεξίου','Α','Α2','2025-09-11'),
 (4,'Ελένη Δημητρίου','Α','Α2','2025-09-11'),
 (5,'Κώστας Γεωργίου','Β','Β1','2024-09-11'),
 (6,'Σοφία Νικολάου','Β','Β1','2024-09-11'),
 (7,'Δημήτρης Κωνσταντίνου','Β','Β2','2024-09-11'),
 (8,'Αικατερίνη Βασιλείου','Γ','Γ1','2023-09-11'),
 (9,'Παναγιώτης Σταυρόπουλος','Γ','Γ1','2023-09-11'),
 (10,'Χριστίνα Αντωνίου','Γ','Γ2','2023-09-11');

INSERT INTO ΜΑΘΗΜΑΤΑ VALUES
 (1,'Πληροφορική','κ. Παππάς',2),
 (2,'Μαθηματικά','κα Οικονόμου',4),
 (3,'Φυσική','κ. Λέκκας',2),
 (4,'Γλώσσα','κα Μαυρίδου',4),
 (5,'Ιστορία','κ. Σακελλαρίου',2);

INSERT INTO ΒΑΘΜΟΙ VALUES
 (1,1,1,18.5,'Α'),(2,1,2,14,'Α'),(3,1,3,15.5,'Α'),(4,1,4,16,'Α'),
 (5,2,1,19,'Α'),(6,2,2,17.5,'Α'),(7,2,4,18,'Α'),
 (8,3,1,12,'Α'),(9,3,2,11,'Α'),(10,3,3,13.5,'Α'),(11,3,5,15,'Α'),
 (12,4,1,16.5,'Α'),(13,4,2,18,'Α'),(14,4,4,19.5,'Α'),
 (15,5,1,14,'Α'),(16,5,2,13,'Α'),(17,5,3,12.5,'Α'),(18,5,5,14.5,'Α'),
 (19,6,1,17,'Α'),(20,6,2,16.5,'Α'),(21,6,4,17,'Α'),(22,6,5,18,'Α'),
 (23,7,1,9.5,'Α'),(24,7,2,10,'Α'),(25,7,3,11,'Α'),
 (26,8,1,19.5,'Α'),(27,8,2,18.5,'Α'),(28,8,3,19,'Α'),(29,8,4,17.5,'Α'),
 (30,9,1,15,'Α'),(31,9,2,14.5,'Α'),(32,9,5,16,'Α'),
 (33,10,1,13.5,'Α'),(34,10,2,15,'Α'),(35,10,4,16.5,'Α'),(36,10,5,15.5,'Α'),
 (37,1,1,19,'Β'),(38,2,1,20,'Β'),(39,3,1,14,'Β'),(40,5,2,15,'Β'),
 (41,7,1,12,'Β'),(42,8,3,19.5,'Β'),(43,9,2,16,'Β'),(44,10,4,17,'Β');
`;

// --- Έτοιμα παραδείγματα (φόρτωση + εκτέλεση με 1 κλικ) -------------------
const EXAMPLES = [
  { label: 'SELECT — Όλοι οι μαθητές',
    sql: 'SELECT * FROM ΜΑΘΗΤΕΣ;' },
  { label: 'WHERE — Μαθητές της Α΄ τάξης',
    sql: "SELECT ΟΝΟΜΑΤΕΠΩΝΥΜΟ, ΤΜΗΜΑ\nFROM ΜΑΘΗΤΕΣ\nWHERE ΤΑΞΗ = 'Α'\nORDER BY ΟΝΟΜΑΤΕΠΩΝΥΜΟ;" },
  { label: 'WHERE — Άριστες επιδόσεις (≥ 18)',
    sql: 'SELECT *\nFROM ΒΑΘΜΟΙ\nWHERE ΒΑΘΜΟΣ >= 18\nORDER BY ΒΑΘΜΟΣ DESC;' },
  { label: 'JOIN — Βαθμοί με ονόματα & μαθήματα',
    sql: 'SELECT Μ.ΟΝΟΜΑΤΕΠΩΝΥΜΟ, Θ.ΤΙΤΛΟΣ, Β.ΒΑΘΜΟΣ, Β.ΤΕΤΡΑΜΗΝΟ\nFROM ΒΑΘΜΟΙ Β\nJOIN ΜΑΘΗΤΕΣ Μ ON Μ.ID = Β.ΜΑΘΗΤΗΣ_ID\nJOIN ΜΑΘΗΜΑΤΑ Θ ON Θ.ID = Β.ΜΑΘΗΜΑ_ID\nORDER BY Β.ΒΑΘΜΟΣ DESC\nLIMIT 10;' },
  { label: 'GROUP BY — Μέσος όρος ανά μάθημα',
    sql: 'SELECT Θ.ΤΙΤΛΟΣ,\n       ROUND(AVG(Β.ΒΑΘΜΟΣ), 2) AS ΜΕΣΟΣ_ΟΡΟΣ,\n       COUNT(*) AS ΠΛΗΘΟΣ_ΒΑΘΜΩΝ\nFROM ΒΑΘΜΟΙ Β\nJOIN ΜΑΘΗΜΑΤΑ Θ ON Θ.ID = Β.ΜΑΘΗΜΑ_ID\nGROUP BY Θ.ΤΙΤΛΟΣ\nORDER BY ΜΕΣΟΣ_ΟΡΟΣ DESC;' },
  { label: 'GROUP BY — Μέσος όρος ανά μαθητή',
    sql: 'SELECT Μ.ΟΝΟΜΑΤΕΠΩΝΥΜΟ, Μ.ΤΑΞΗ,\n       ROUND(AVG(Β.ΒΑΘΜΟΣ), 2) AS ΜΕΣΟΣ_ΟΡΟΣ\nFROM ΜΑΘΗΤΕΣ Μ\nJOIN ΒΑΘΜΟΙ Β ON Β.ΜΑΘΗΤΗΣ_ID = Μ.ID\nGROUP BY Μ.ID\nORDER BY ΜΕΣΟΣ_ΟΡΟΣ DESC;' },
  { label: 'UPDATE — Διόρθωση βαθμού',
    sql: "UPDATE ΒΑΘΜΟΙ SET ΒΑΘΜΟΣ = 13\nWHERE ΜΑΘΗΤΗΣ_ID = 7 AND ΜΑΘΗΜΑ_ID = 1 AND ΤΕΤΡΑΜΗΝΟ = 'Α';\nSELECT * FROM ΒΑΘΜΟΙ WHERE ΜΑΘΗΤΗΣ_ID = 7;" },
];

// --- Κατάσταση -------------------------------------------------------------
let db = null;
const $ = (id) => document.getElementById(id);
const editor = $('editor'), resultsEl = $('results'), msgEl = $('message');

function showMessage(text, kind) {
  const styles = {
    ok:   'bg-emerald-50 text-emerald-800 ring-emerald-200',
    err:  'bg-red-50 text-red-800 ring-red-200',
    info: 'bg-blue-50 text-blue-800 ring-blue-200',
  };
  msgEl.className = 'rounded-xl px-4 py-3 text-sm font-medium ring-1 ' + styles[kind];
  msgEl.textContent = text;
}

// --- Δημιουργία / επαναφορά βάσης ------------------------------------------
function createSeedDb(SQL) {
  const d = new SQL.Database();
  d.run(SEED_SQL);
  return d;
}

function renderSchema() {
  const tables = db.exec(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name");
  const box = $('schema');
  box.innerHTML = '';
  if (!tables.length) { box.textContent = 'Η βάση είναι κενή.'; return; }
  for (const t of tables[0].values) {
    const name = t[0];
    const info = db.exec(`PRAGMA table_info("${name}")`);
    const cnt = db.exec(`SELECT COUNT(*) FROM "${name}"`)[0].values[0][0];
    const det = document.createElement('details');
    det.className = 'rounded-lg bg-slate-50 ring-1 ring-slate-200';
    const cols = info[0].values
      .map(c => `<li class="flex justify-between gap-2"><span class="mono">${c[1]}</span><span class="text-slate-400 text-xs">${c[2]}${c[5] ? ' · PK' : ''}</span></li>`)
      .join('');
    det.innerHTML =
      `<summary class="cursor-pointer px-3 py-2 font-semibold text-slate-800">
         <span class="mono">${name}</span>
         <span class="ml-1 text-xs font-normal text-slate-500">(${cnt} γραμμές)</span>
       </summary>
       <ul class="px-3 pb-2 space-y-1 text-xs text-slate-600">${cols}</ul>`;
    box.appendChild(det);
  }
}

function renderExamples() {
  const box = $('examples');
  for (const ex of EXAMPLES) {
    const b = document.createElement('button');
    b.className = 'w-full text-left px-3 py-2 rounded-lg bg-slate-50 hover:bg-blue-50 ring-1 ring-slate-200 hover:ring-blue-300 text-sm font-medium text-slate-700 hover:text-blue-800 transition';
    b.textContent = ex.label;
    b.addEventListener('click', () => { editor.value = ex.sql; runQuery(); });
    box.appendChild(b);
  }
}

// --- Εκτέλεση ερωτήματος ----------------------------------------------------
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function resultTable(res, idx) {
  const head = res.columns.map(c =>
    `<th class="px-3 py-2 text-left font-bold text-slate-700 whitespace-nowrap border-b border-slate-200">${escapeHtml(c)}</th>`).join('');
  const rows = res.values.map((r, i) =>
    `<tr class="${i % 2 ? 'bg-slate-50' : 'bg-white'}">` +
    r.map(v => `<td class="px-3 py-1.5 whitespace-nowrap border-b border-slate-100 mono text-[13px]">${v === null ? '<span class="text-slate-400 italic">NULL</span>' : escapeHtml(v)}</td>`).join('') +
    '</tr>').join('');
  return `
    <div class="rounded-xl bg-white ring-1 ring-slate-200 overflow-hidden">
      <div class="px-4 py-2 border-b border-slate-200 text-xs font-semibold text-slate-500 flex justify-between">
        <span>Αποτέλεσμα #${idx}</span><span>${res.values.length} γραμμές</span>
      </div>
      <div class="overflow-x-auto max-h-[420px] overflow-y-auto">
        <table class="min-w-full text-sm"><thead class="bg-slate-100 sticky top-0"><tr>${head}</tr></thead><tbody>${rows}</tbody></table>
      </div>
    </div>`;
}

function runQuery() {
  if (!db) return;
  const sql = editor.value.trim();
  resultsEl.innerHTML = '';
  if (!sql) { showMessage('Γράψε πρώτα ένα ερώτημα SQL ή διάλεξε ένα έτοιμο παράδειγμα.', 'info'); return; }
  const t0 = performance.now();
  try {
    const results = db.exec(sql);
    const ms = (performance.now() - t0).toFixed(1);
    if (results.length) {
      resultsEl.innerHTML = results.map((r, i) => resultTable(r, i + 1)).join('');
      showMessage(`✓ Επιτυχής εκτέλεση σε ${ms} ms — ${results.length} σύνολα αποτελεσμάτων.`, 'ok');
    } else {
      const changes = db.getRowsModified();
      showMessage(`✓ Το ερώτημα εκτελέστηκε σε ${ms} ms${changes ? ` — επηρεάστηκαν ${changes} γραμμές` : ''} (χωρίς πίνακα αποτελεσμάτων).`, 'ok');
    }
    renderSchema();
  } catch (e) {
    showMessage('✗ Σφάλμα SQL: ' + e.message, 'err');
  }
}

// --- Αρχικοποίηση ------------------------------------------------------------
$('runBtn').addEventListener('click', runQuery);
$('clearBtn').addEventListener('click', () => {
  editor.value = ''; resultsEl.innerHTML = ''; msgEl.className = 'hidden'; editor.focus();
});
$('resetBtn').addEventListener('click', () => {
  if (!window.__SQL) return;
  if (db) db.close();
  db = createSeedDb(window.__SQL);
  resultsEl.innerHTML = '';
  renderSchema();
  showMessage('↺ Η σχολική βάση επανήλθε στην αρχική της κατάσταση.', 'info');
});
editor.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runQuery(); }
});

initSqlJs({ locateFile: f => 'vendor/' + f }).then(SQL => {
  window.__SQL = SQL;
  db = createSeedDb(SQL);
  renderSchema();
  renderExamples();
  editor.value = EXAMPLES[0].sql;
  $('dbState').textContent = '✓ Βάση έτοιμη (SQLite WASM)';
  $('dbState').className = 'text-xs px-3 py-1.5 rounded-full bg-emerald-400/20 ring-1 ring-emerald-300/50 text-emerald-50';
  showMessage('Καλώς ήρθες! Η σχολική βάση φορτώθηκε: ΜΑΘΗΤΕΣ (10), ΜΑΘΗΜΑΤΑ (5), ΒΑΘΜΟΙ (44). Πάτα «Εκτέλεση» ή διάλεξε ένα παράδειγμα.', 'info');
}).catch(e => {
  $('dbState').textContent = '✗ Αποτυχία φόρτωσης';
  showMessage('Αποτυχία φόρτωσης της SQLite WASM: ' + e.message, 'err');
});

