/*
 * Μετατροπέας Δυαδικού & Βάρη Bits — standalone εκπαιδευτική εφαρμογή.
 * Δεκαδικό ↔ Δυαδικό ↔ Δεκαεξαδικό (0–255) με 8 διαδραστικά διακοπτάκια.
 * Καθαρή vanilla JS — καμία εξωτερική βιβλιοθήκη, 0 MB RAM στον server.
 */
'use strict';

const WEIGHTS = [128, 64, 32, 16, 8, 4, 2, 1]; // θέσεις bit 7…0 (MSB → LSB)
let bits = [0, 0, 0, 0, 0, 0, 0, 0];

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Δημιουργία των 8 διακοπτών (βάρος, μοχλός, ψηφίο 0/1)
// ---------------------------------------------------------------------------
function buildSwitches() {
  const row = $('bits-row');
  WEIGHTS.forEach((weight, i) => {
    const pos = 7 - i;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'bit-' + pos;
    btn.className = 'bit-switch bit-off flex flex-col items-center gap-2 rounded-xl border-2 p-3 select-none focus:outline-none focus:ring-2 focus:ring-blue-400';
    btn.setAttribute('aria-pressed', 'false');
    btn.setAttribute('aria-label', `Bit θέσης ${pos}, βάρος ${weight}`);
    btn.innerHTML =
      `<span class="text-xs font-bold text-slate-500">θέση ${pos}</span>` +
      `<span class="mono text-sm font-extrabold weight-label">${weight}</span>` +
      `<span class="relative block w-9 h-16 rounded-full bg-slate-200 ring-1 ring-inset ring-slate-300 track">` +
        `<span class="bit-knob absolute left-1 top-1 w-7 h-7 rounded-full shadow"></span>` +
      `</span>` +
      `<span class="mono text-2xl font-extrabold digit">0</span>`;
    btn.addEventListener('click', () => {
      bits[i] = bits[i] ? 0 : 1;
      render();
    });
    row.appendChild(btn);
  });
}

// ---------------------------------------------------------------------------
// Υπολογισμοί & συγχρονισμός ΟΛΩΝ των ενδείξεων
// ---------------------------------------------------------------------------
function value() {
  return bits.reduce((sum, b, i) => sum + b * WEIGHTS[i], 0);
}

function render(skipInputId) {
  const v = value();
  const binStr = bits.join('');
  const hexStr = v.toString(16).toUpperCase().padStart(2, '0');

  // Διακοπτάκια
  bits.forEach((b, i) => {
    const el = $('bit-' + (7 - i));
    el.classList.toggle('bit-on', !!b);
    el.classList.toggle('bit-off', !b);
    el.classList.toggle('border-emerald-400', !!b);
    el.classList.toggle('bg-emerald-50', !!b);
    el.classList.toggle('border-slate-200', !b);
    el.classList.toggle('bg-white', !b);
    el.setAttribute('aria-pressed', b ? 'true' : 'false');
    el.querySelector('.digit').textContent = b;
    el.querySelector('.digit').className = 'mono text-2xl font-extrabold digit ' + (b ? 'text-emerald-600' : 'text-slate-400');
    el.querySelector('.weight-label').className = 'mono text-sm font-extrabold weight-label ' + (b ? 'text-emerald-700' : 'text-slate-400');
    el.querySelector('.track').className = 'relative block w-9 h-16 rounded-full ring-1 ring-inset track ' + (b ? 'bg-emerald-200 ring-emerald-300' : 'bg-slate-200 ring-slate-300');
    el.querySelector('.bit-knob').classList.toggle('bg-emerald-500', !!b);
    el.querySelector('.bit-knob').classList.toggle('bg-slate-400', !b);
  });

  // Ζωντανές τιμές
  $('out-dec').textContent = v;
  $('out-bin').textContent = binStr.slice(0, 4) + ' ' + binStr.slice(4);
  $('out-hex').textContent = '0x' + hexStr;

  // Άθροισμα ενεργών βαρών: π.χ. 32 + 8 + 2 = 42
  const active = bits.map((b, i) => b ? WEIGHTS[i] : null).filter(w => w !== null);
  $('sum-expression').textContent = active.length ? active.join(' + ') + ' = ' + v : '0 (κανένα ενεργό bit)';

  // Γραμμή κατάστασης στον πίνακα βαρών
  $('weights-state').innerHTML =
    '<td class="py-2 px-2 text-left font-sans font-semibold text-slate-600">Τώρα</td>' +
    bits.map(b => `<td class="py-2 px-2 font-extrabold ${b ? 'text-emerald-600' : 'text-slate-300'}">${b}</td>`).join('');

  // Πεδία εισαγωγής (δεν πειράζουμε αυτό που πληκτρολογεί ο χρήστης)
  if (skipInputId !== 'in-dec') $('in-dec').value = String(v);
  if (skipInputId !== 'in-bin') $('in-bin').value = binStr;
  if (skipInputId !== 'in-hex') $('in-hex').value = hexStr;
}

function setValue(v, skipInputId) {
  bits = WEIGHTS.map(w => (v & w) ? 1 : 0);
  hideError();
  render(skipInputId);
}

// ---------------------------------------------------------------------------
// Εισαγωγή από τον χρήστη (με επικύρωση & ελληνικά μηνύματα)
// ---------------------------------------------------------------------------
function showError(msg) {
  const el = $('input-error');
  el.textContent = '⚠️ ' + msg;
  el.classList.remove('hidden');
}
function hideError() {
  $('input-error').classList.add('hidden');
}

function bindInput(id, parse, errMsg) {
  $(id).addEventListener('input', (ev) => {
    const raw = ev.target.value.trim();
    if (raw === '') { hideError(); return; }
    const v = parse(raw);
    if (v === null || v < 0 || v > 255) { showError(errMsg); return; }
    setValue(v, id);
  });
}

// ---------------------------------------------------------------------------
// Αρχικοποίηση
// ---------------------------------------------------------------------------
buildSwitches();

bindInput('in-dec', s => /^\d{1,3}$/.test(s) ? parseInt(s, 10) : null,
  'Το δεκαδικό πρέπει να είναι ακέραιος από 0 έως 255.');
bindInput('in-bin', s => /^[01]{1,8}$/.test(s) ? parseInt(s, 2) : null,
  'Το δυαδικό δέχεται μόνο ψηφία 0 και 1 (έως 8 ψηφία).');
bindInput('in-hex', s => /^(0x)?[0-9a-fA-F]{1,2}$/.test(s) ? parseInt(s.replace(/^0x/i, ''), 16) : null,
  'Το δεκαεξαδικό δέχεται 1–2 ψηφία 0–9 / A–F (π.χ. 2A ή 0x2A), τιμή έως FF.');

$('btn-all-on').addEventListener('click', () => setValue(255));
$('btn-all-off').addEventListener('click', () => setValue(0));
$('btn-invert').addEventListener('click', () => setValue(255 - value()));
$('btn-random').addEventListener('click', () => setValue(Math.floor(Math.random() * 256)));

render();