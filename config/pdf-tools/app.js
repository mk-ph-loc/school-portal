/* =========================================================================
 * PDF Studio — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου
 * Συγχώνευση / εξαγωγή σελίδων / υδατογράφημα & αρίθμηση με pdf-lib.
 * 100% τοπική επεξεργασία στον browser — κανένα upload στον server.
 * ========================================================================= */
'use strict';

const { PDFDocument, degrees, rgb } = PDFLib;
const $ = (id) => document.getElementById(id);

// --- Γραμματοσειρά Unicode (DejaVu subset: Ελληνικά + Λατινικά) -------------
let greekFontBytes = null;
async function loadGreekFont() {
  if (!greekFontBytes) {
    const r = await fetch('vendor/fonts/DejaVuSans-el.ttf');
    if (!r.ok) throw new Error('Αδυναμία φόρτωσης γραμματοσειράς ελληνικών.');
    greekFontBytes = await r.arrayBuffer();
  }
  return greekFontBytes;
}

// --- Βοηθητικά ---------------------------------------------------------------
function showMsg(text, kind) {
  const styles = {
    ok:   'bg-emerald-50 text-emerald-800 ring-emerald-200',
    err:  'bg-red-50 text-red-800 ring-red-200',
    info: 'bg-blue-50 text-blue-800 ring-blue-200',
  };
  const el = $('msg');
  el.className = 'mt-4 rounded-xl px-4 py-3 text-sm font-medium ring-1 ' + styles[kind];
  el.textContent = text;
}

function download(bytes, filename) {
  const blob = new Blob([bytes], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

function fmtSize(n) {
  return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
}

async function readPdf(file) {
  const bytes = await file.arrayBuffer();
  const doc = await PDFDocument.load(bytes, { ignoreEncryption: true });
  return { file, bytes, pages: doc.getPageCount() };
}

// Ανάλυση "1-3, 5, 8-10" → [0,1,2,4,7,8,9] (0-based, έγκυρα & χωρίς διπλότυπα)
function parseRange(text, max) {
  const t = text.trim();
  if (!t) return Array.from({ length: max }, (_, i) => i);
  const out = [];
  for (const part of t.split(',')) {
    const m = part.trim().match(/^(\d+)(?:\s*-\s*(\d+))?$/);
    if (!m) throw new Error(`Μη έγκυρη δήλωση σελίδων: «${part.trim()}». Χρησιμοποίησε μορφή όπως 1-3, 5, 8-10.`);
    let a = parseInt(m[1], 10), b = m[2] ? parseInt(m[2], 10) : a;
    if (a < 1 || b < a || b > max)
      throw new Error(`Οι σελίδες πρέπει να είναι μεταξύ 1 και ${max} (δήλωση «${part.trim()}»).`);
    for (let i = a; i <= b; i++) if (!out.includes(i - 1)) out.push(i - 1);
  }
  if (!out.length) throw new Error('Δεν επιλέχθηκε καμία σελίδα.');
  return out;
}

// --- Tabs ---------------------------------------------------------------------
const TAB_ON  = 'tab px-3 py-3 rounded-xl font-bold text-sm ring-1 transition bg-blue-700 text-white ring-blue-700 shadow';
const TAB_OFF = 'tab px-3 py-3 rounded-xl font-bold text-sm ring-1 transition bg-white text-slate-700 ring-slate-200 hover:bg-blue-50';
function selectTab(name) {
  document.querySelectorAll('#tabs .tab').forEach(b => {
    b.className = b.dataset.tab === name ? TAB_ON : TAB_OFF;
  });
  for (const p of ['merge', 'split', 'mark'])
    $('panel-' + p).hidden = p !== name;
  $('msg').className = 'hidden';
}
document.querySelectorAll('#tabs .tab').forEach(b =>
  b.addEventListener('click', () => selectTab(b.dataset.tab)));
selectTab('merge');

// --- Drag & drop σε όλα τα dropzones ------------------------------------------
for (const zone of document.querySelectorAll('.dropzone')) {
  const input = zone.querySelector('input[type=file]');
  ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); zone.classList.add('drag');
  }));
  ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => {
    e.preventDefault(); zone.classList.remove('drag');
  }));
  zone.addEventListener('drop', e => {
    const files = [...e.dataTransfer.files].filter(f => /\.pdf$/i.test(f.name) || f.type === 'application/pdf');
    if (!files.length) { showMsg('Σύρε μόνο αρχεία PDF.', 'err'); return; }
    const dt = new DataTransfer();
    (input.multiple ? files : files.slice(0, 1)).forEach(f => dt.items.add(f));
    input.files = dt.files;
    input.dispatchEvent(new Event('change'));
  });
}

// ============================ 1. ΣΥΓΧΩΝΕΥΣΗ ==================================
let mergeFiles = [];   // {file, bytes, pages}

function renderMergeList() {
  const ul = $('mergeList');
  ul.innerHTML = '';
  mergeFiles.forEach((f, i) => {
    const li = document.createElement('li');
    li.className = 'flex items-center gap-2 rounded-lg bg-slate-50 ring-1 ring-slate-200 px-3 py-2';
    li.innerHTML =
      `<span class="text-lg">📄</span>
       <span class="flex-1 min-w-0">
         <span class="block text-sm font-semibold text-slate-800 truncate"></span>
         <span class="block text-xs text-slate-500">${f.pages} σελίδες · ${fmtSize(f.file.size)}</span>
       </span>
       <button class="up px-2 py-1 rounded bg-white ring-1 ring-slate-300 hover:bg-blue-50 text-sm disabled:opacity-30" title="Πάνω" ${i === 0 ? 'disabled' : ''}>↑</button>
       <button class="down px-2 py-1 rounded bg-white ring-1 ring-slate-300 hover:bg-blue-50 text-sm disabled:opacity-30" title="Κάτω" ${i === mergeFiles.length - 1 ? 'disabled' : ''}>↓</button>
       <button class="del px-2 py-1 rounded bg-white ring-1 ring-red-200 text-red-600 hover:bg-red-50 text-sm" title="Αφαίρεση">✕</button>`;
    li.querySelector('.truncate').textContent = f.file.name;
    li.querySelector('.up').addEventListener('click', () => {
      [mergeFiles[i - 1], mergeFiles[i]] = [mergeFiles[i], mergeFiles[i - 1]]; renderMergeList();
    });
    li.querySelector('.down').addEventListener('click', () => {
      [mergeFiles[i + 1], mergeFiles[i]] = [mergeFiles[i], mergeFiles[i + 1]]; renderMergeList();
    });
    li.querySelector('.del').addEventListener('click', () => {
      mergeFiles.splice(i, 1); renderMergeList();
    });
    ul.appendChild(li);
  });
  $('mergeBtn').disabled = mergeFiles.length < 2;
}

$('mergeInput').addEventListener('change', async (e) => {
  for (const file of e.target.files) {
    try { mergeFiles.push(await readPdf(file)); }
    catch { showMsg(`Το αρχείο «${file.name}» δεν είναι έγκυρο PDF ή είναι κρυπτογραφημένο.`, 'err'); }
  }
  e.target.value = '';
  renderMergeList();
});
$('mergeClear').addEventListener('click', () => { mergeFiles = []; renderMergeList(); $('msg').className = 'hidden'; });

$('mergeBtn').addEventListener('click', async () => {
  try {
    showMsg('⏳ Συγχώνευση σε εξέλιξη…', 'info');
    const out = await PDFDocument.create();
    for (const f of mergeFiles) {
      const src = await PDFDocument.load(f.bytes, { ignoreEncryption: true });
      const copied = await out.copyPages(src, src.getPageIndices());
      copied.forEach(p => out.addPage(p));
    }
    const total = out.getPageCount();
    download(await out.save(), 'συγχωνευμένο.pdf');
    showMsg(`✓ Έτοιμο! Συγχωνεύθηκαν ${mergeFiles.length} αρχεία σε ένα PDF ${total} σελίδων — ξεκίνησε η λήψη.`, 'ok');
  } catch (e) { showMsg('✗ Σφάλμα συγχώνευσης: ' + e.message, 'err'); }
});

// ============================ 2. ΕΞΑΓΩΓΗ ΣΕΛΙΔΩΝ =============================
let splitFile = null;

$('splitInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    splitFile = await readPdf(file);
    $('splitName').textContent = file.name;
    $('splitInfo').textContent = `${splitFile.pages} σελίδες · ${fmtSize(file.size)}`;
    $('splitBtn').disabled = false;
    showMsg(`Φορτώθηκε το «${file.name}» (${splitFile.pages} σελίδες). Δήλωσε ποιες σελίδες θέλεις.`, 'info');
  } catch {
    splitFile = null; $('splitBtn').disabled = true;
    showMsg(`Το αρχείο «${file.name}» δεν είναι έγκυρο PDF.`, 'err');
  }
});

$('splitBtn').addEventListener('click', async () => {
  if (!splitFile) return;
  try {
    const idx = parseRange($('splitRange').value, splitFile.pages);
    showMsg('⏳ Εξαγωγή σελίδων σε εξέλιξη…', 'info');
    const src = await PDFDocument.load(splitFile.bytes, { ignoreEncryption: true });
    const out = await PDFDocument.create();
    const copied = await out.copyPages(src, idx);
    copied.forEach(p => out.addPage(p));
    const base = splitFile.file.name.replace(/\.pdf$/i, '');
    download(await out.save(), `${base}_σελίδες.pdf`);
    showMsg(`✓ Έτοιμο! Εξήχθησαν ${idx.length} σελίδες — ξεκίνησε η λήψη.`, 'ok');
  } catch (e) { showMsg('✗ ' + e.message, 'err'); }
});


// ==================== 3. ΥΔΑΤΟΓΡΑΦΗΜΑ & ΑΡΙΘΜΗΣΗ =============================
let markFile = null;

$('markInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  try {
    markFile = await readPdf(file);
    $('markName').textContent = file.name;
    $('markInfo').textContent = `${markFile.pages} σελίδες · ${fmtSize(file.size)}`;
    $('markBtn').disabled = false;
    showMsg(`Φορτώθηκε το «${file.name}» (${markFile.pages} σελίδες). Ρύθμισε υδατογράφημα/αρίθμηση και πάτα «Εφαρμογή».`, 'info');
  } catch {
    markFile = null; $('markBtn').disabled = true;
    showMsg(`Το αρχείο «${file.name}» δεν είναι έγκυρο PDF.`, 'err');
  }
});

$('wmOpacity').addEventListener('input', () => {
  $('wmOpacityVal').textContent = $('wmOpacity').value + '%';
});

$('markBtn').addEventListener('click', async () => {
  if (!markFile) return;
  const useWm = $('wmEnable').checked, useNum = $('numEnable').checked;
  const wmText = $('wmText').value.trim();
  if (!useWm && !useNum) { showMsg('Ενεργοποίησε τουλάχιστον μία λειτουργία (υδατογράφημα ή αρίθμηση).', 'err'); return; }
  if (useWm && !wmText) { showMsg('Γράψε το κείμενο του υδατογραφήματος.', 'err'); return; }
  try {
    showMsg('⏳ Επεξεργασία σε εξέλιξη…', 'info');
    const doc = await PDFDocument.load(markFile.bytes, { ignoreEncryption: true });
    doc.registerFontkit(fontkit);
    const font = await doc.embedFont(await loadGreekFont(), { subset: true });
    const opacity = parseInt($('wmOpacity').value, 10) / 100;
    const pages = doc.getPages();
    const total = pages.length;

    pages.forEach((page, i) => {
      const { width, height } = page.getSize();
      // Σημείωση: οι συντεταγμένες είναι στον χώρο της (μη περιστραμμένης)
      // σελίδας — ο PDF viewer εφαρμόζει το /Rotate κατά την εμφάνιση.
      if (useWm) {
        // Μέγεθος ώστε το κείμενο να πιάνει ~70% της διαγωνίου
        const diag = Math.sqrt(width * width + height * height);
        let size = (diag * 0.7) / Math.max(1, font.widthOfTextAtSize(wmText, 1));
        size = Math.min(size, height * 0.25);
        const tw = font.widthOfTextAtSize(wmText, size);
        const th = font.heightAtSize(size);
        // Κέντρο κειμένου στο κέντρο της σελίδας, με διαγώνια κλίση 45°
        const angle = 45 * Math.PI / 180;
        const cx = width / 2, cy = height / 2;
        const x = cx - (tw / 2) * Math.cos(angle) + (th / 2) * Math.sin(angle);
        const y = cy - (tw / 2) * Math.sin(angle) - (th / 2) * Math.cos(angle);
        page.drawText(wmText, {
          x, y, size, font,
          color: rgb(0.45, 0.45, 0.5),
          opacity,
          rotate: degrees(45),
        });
      }

      if (useNum) {
        const label = `Σελίδα ${i + 1} από ${total}`;
        const size = Math.max(8, Math.min(12, width * 0.018));
        const tw = font.widthOfTextAtSize(label, size);
        page.drawText(label, {
          x: width - tw - 24,
          y: 18,
          size, font,
          color: rgb(0.25, 0.25, 0.3),
          opacity: 0.85,
        });
      }
    });

    const base = markFile.file.name.replace(/\.pdf$/i, '');
    download(await doc.save(), `${base}_με_σήμανση.pdf`);
    const parts = [];
    if (useWm) parts.push(`υδατογράφημα «${wmText}»`);
    if (useNum) parts.push('αρίθμηση σελίδων');
    showMsg(`✓ Έτοιμο! Προστέθηκαν ${parts.join(' & ')} σε ${total} σελίδες — ξεκίνησε η λήψη.`, 'ok');
  } catch (e) { showMsg('✗ Σφάλμα επεξεργασίας: ' + e.message, 'err'); }
});

