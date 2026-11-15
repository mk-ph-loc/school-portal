/*
 * Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα — λογική περιβάλλοντος μαθητή.
 * Vanilla JS (χωρίς εξαρτήσεις)· το χρονόμετρο βασίζεται στο deadline του server.
 */
'use strict';

const API = window.EXAMS_BASE + 'api/'; // π.χ. /exams/api/ (ορίζεται από το template)
const $ = (id) => document.getElementById(id);
const STEPS = ['step-select', 'step-test', 'step-confirm-file', 'step-done'];
const RESUME_KEY = 'schoolExams.inProgress';
const ALLOWED_EXT = ['.py', '.docx', '.pdf', '.zip', '.txt', '.sb3', '.glo'];

let activities = [];
let current = null;      // επιλεγμένη δραστηριότητα
let testSession = null;  // {submission_id, code, deadline, questions}
let timerHandle = null;
let submitting = false;

function show(step) {
  STEPS.forEach((s) => { $(s).hidden = s !== step; });
  window.scrollTo({ top: 0 });
}

function setError(id, msg) {
  const el = $(id);
  el.textContent = msg || '';
  el.hidden = !msg;
}

async function api(path, options = {}) {
  const res = await fetch(API + path, options);
  let data = {};
  try { data = await res.json(); } catch (e) { /* κενό σώμα */ }
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Σφάλμα επικοινωνίας με τον διακομιστή.';
    throw new Error(detail);
  }
  return data;
}

function esc(text) {
  const div = document.createElement('div');
  div.textContent = String(text ?? '');
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Βήμα 1: τάξη → ενεργές δραστηριότητες
// ---------------------------------------------------------------------------
async function loadActivities() {
  const slug = $('sel-class').value;
  const sel = $('sel-activity');
  current = null;
  $('file-fields').hidden = true;
  $('activity-info').textContent = '';
  $('btn-continue').disabled = true;
  if (!slug) {
    sel.innerHTML = '<option value="">— Πρώτα επίλεξε τάξη —</option>';
    sel.disabled = true;
    return;
  }
  sel.disabled = true;
  sel.innerHTML = '<option value="">Φόρτωση…</option>';
  try {
    const data = await api('activities?class_slug=' + encodeURIComponent(slug));
    activities = data.activities;
    if (!activities.length) {
      sel.innerHTML = '<option value="">Δεν υπάρχει ενεργή δραστηριότητα για την τάξη σου</option>';
      return;
    }
    sel.innerHTML = '<option value="">— Επίλεξε δραστηριότητα —</option>' +
      activities.map((a) => {
        const kind = a.kind === 'test' ? `📝 Διαγώνισμα (${a.duration}΄)` : '📎 Παράδοση Αρχείου';
        return `<option value="${a.id}">${esc(a.title)} — ${kind}</option>`;
      }).join('');
    sel.disabled = false;
  } catch (err) {
    sel.innerHTML = '<option value="">Σφάλμα φόρτωσης — δοκίμασε ξανά</option>';
    setError('select-error', err.message);
  }
}

function onActivityChange() {
  const id = Number($('sel-activity').value);
  current = activities.find((a) => a.id === id) || null;
  setError('select-error', '');
  if (!current) {
    $('file-fields').hidden = true;
    $('activity-info').textContent = '';
    $('btn-continue').disabled = true;
    return;
  }
  if (current.kind === 'assignment') {
    $('file-fields').hidden = false;
    $('activity-info').textContent = '📎 Παράδοση αρχείου εργασίας (.py, .docx, .pdf, .zip, .txt, .sb3, .glo).';
    $('btn-continue').textContent = 'Συνέχεια →';
  } else {
    $('file-fields').hidden = true;
    $('activity-info').textContent =
      `📝 Ηλεκτρονικό διαγώνισμα · ${current.question_count} ερωτήσεις · ⏱️ ${current.duration} λεπτά. ` +
      'Το χρονόμετρο ξεκινά μόλις πατήσεις «Έναρξη Διαγωνίσματος».';
    $('btn-continue').textContent = '⏱️ Έναρξη Διαγωνίσματος →';
  }
  $('btn-continue').disabled = false;
}

function validateStudent() {
  const name = $('inp-name').value.trim();
  const section = $('inp-section').value.trim();
  if (name.length < 3) return 'Συμπλήρωσε το ονοματεπώνυμό σου (τουλάχιστον 3 χαρακτήρες).';
  if (!section) return 'Συμπλήρωσε το τμήμα σου (π.χ. Α2, Γ1).';
  return '';
}

async function onContinue() {
  setError('select-error', '');
  if (!current) return;
  const problem = validateStudent();
  if (problem) { setError('select-error', problem); return; }
  const fullname = $('inp-name').value.trim();
  const section = $('inp-section').value.trim();

  if (current.kind === 'assignment') {
    const file = $('inp-file').files[0];
    if (!file) { setError('select-error', 'Επίλεξε το αρχείο της εργασίας σου.'); return; }
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      setError('select-error', 'Μη επιτρεπτός τύπος αρχείου. Επιτρέπονται: ' + ALLOWED_EXT.join(', '));
      return;
    }
    if (file.size > 50 * 1024 * 1024) { setError('select-error', 'Το αρχείο υπερβαίνει τα 50 MB.'); return; }
    $('cf-activity').textContent = current.title;
    $('cf-student').textContent = `${fullname} · Τμήμα ${section.toUpperCase()}`;
    $('cf-file').textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    show('step-confirm-file');
    return;
  }

  // Διαγώνισμα: η έναρξη δεσμεύει τον χρόνο στον server.
  $('btn-continue').disabled = true;
  try {
    const data = await api(`activities/${current.id}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fullname, section }),
    });
    startTest(data, fullname, section);
  } catch (err) {
    setError('select-error', err.message);
  } finally {
    $('btn-continue').disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Βήμα 2α: διαγώνισμα — ερωτήσεις, χρονόμετρο, αυτόματη υποβολή
// ---------------------------------------------------------------------------
function renderQuestions(questions) {
  $('questions').innerHTML = questions.map((q, i) => {
    const badge = q.type === 'mc' ? 'Πολλαπλής Επιλογής' : 'Ανάπτυξης / Κώδικα';
    let body;
    if (q.type === 'mc') {
      body = q.options.map((opt, j) => `
        <label class="flex items-start gap-2.5 rounded-lg border border-slate-200 px-3 py-2.5 hover:bg-slate-50 cursor-pointer">
          <input type="radio" name="q${i}" value="${j}" class="mt-1 accent-blue-700" onchange="saveDraft()">
          <span class="text-sm">${esc(opt)}</span>
        </label>`).join('');
    } else {
      body = `<textarea name="q${i}" rows="6" maxlength="20000" oninput="saveDraft()"
        placeholder="Γράψε την απάντησή σου ή τον κώδικά σου εδώ…"
        class="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"></textarea>`;
    }
    return `
      <div class="rounded-2xl bg-white p-5 ring-1 ring-slate-200 shadow-sm">
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <h3 class="font-bold text-slate-900">Ερώτηση ${i + 1}</h3>
          <span class="text-[11px] font-semibold px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200">${badge} · ${q.points} μον.</span>
        </div>
        <p class="mt-2 text-sm whitespace-pre-wrap">${esc(q.text)}</p>
        <div class="mt-3 space-y-2">${body}</div>
      </div>`;
  }).join('');
}

function collectAnswers() {
  const answers = {};
  testSession.questions.forEach((q, i) => {
    if (q.type === 'mc') {
      const checked = document.querySelector(`input[name="q${i}"]:checked`);
      if (checked) answers[String(i)] = Number(checked.value);
    } else {
      const ta = document.querySelector(`textarea[name="q${i}"]`);
      if (ta && ta.value.trim()) answers[String(i)] = ta.value;
    }
  });
  return answers;
}

function saveDraft() {
  // Προσωρινή αποθήκευση ώστε ένα refresh να μην χάνει τις απαντήσεις.
  if (!testSession) return;
  try {
    localStorage.setItem(RESUME_KEY, JSON.stringify({
      session: testSession, answers: collectAnswers(),
    }));
  } catch (e) { /* storage απενεργοποιημένο */ }
}

function clearDraft() {
  try { localStorage.removeItem(RESUME_KEY); } catch (e) { /* αγνόησε */ }
}

function startTest(data, fullname, section, restoredAnswers) {
  testSession = {
    submission_id: data.submission_id,
    code: data.code,
    deadline: data.deadline,
    questions: data.questions,
    title: data.title,
    fullname, section,
    // Διόρθωση ρολογιού client με βάση την ώρα του server.
    offset: data.server_now - Date.now() / 1000,
  };
  $('test-title').textContent = data.title;
  $('test-student').textContent = `${fullname} · Τμήμα ${section.toUpperCase()} · Κωδικός: ${data.code}`;
  renderQuestions(data.questions);
  if (restoredAnswers) {
    Object.entries(restoredAnswers).forEach(([qid, val]) => {
      const q = data.questions[Number(qid)];
      if (!q) return;
      if (q.type === 'mc') {
        const radio = document.querySelector(`input[name="q${qid}"][value="${val}"]`);
        if (radio) radio.checked = true;
      } else {
        const ta = document.querySelector(`textarea[name="q${qid}"]`);
        if (ta) ta.value = val;
      }
    });
  }
  show('step-test');
  saveDraft();
  tick();
  timerHandle = setInterval(tick, 1000);
}

function tick() {
  if (!testSession) return;
  const now = Date.now() / 1000 + testSession.offset;
  const left = Math.max(0, Math.round(testSession.deadline - now));
  const mm = String(Math.floor(left / 60)).padStart(2, '0');
  const ss = String(left % 60).padStart(2, '0');
  const el = $('timer');
  el.textContent = `${mm}:${ss}`;
  el.classList.toggle('text-emerald-400', left > 120);
  el.classList.toggle('text-amber-400', left <= 120 && left > 30);
  el.classList.toggle('text-red-500', left <= 30);
  el.classList.toggle('timer-low', left <= 30 && left > 0);
  if (left <= 0) submitTest(true);
}

async function submitTest(auto) {
  if (!testSession || submitting) return;
  if (!auto && !confirm('Οριστική υποβολή διαγωνίσματος; Δεν μπορείς να το αλλάξεις μετά.')) return;
  submitting = true;
  clearInterval(timerHandle);
  $('btn-submit-test').disabled = true;
  setError('test-error', '');
  try {
    const data = await api(`submissions/${testSession.submission_id}/submit-test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: collectAnswers(), auto: !!auto }),
    });
    clearDraft();
    finish(data.code, auto || data.auto
      ? 'Ο χρόνος έληξε — το διαγώνισμα υποβλήθηκε αυτόματα με τις απαντήσεις που είχες συμπληρώσει.'
      : 'Το διαγώνισμά σου παραδόθηκε στον καθηγητή.');
  } catch (err) {
    setError('test-error', err.message + ' — Οι απαντήσεις σου διατηρούνται, δοκίμασε ξανά.');
    $('btn-submit-test').disabled = false;
    if (!auto) timerHandle = setInterval(tick, 1000);
    else setTimeout(() => submitTest(true), 5000); // επανάληψη αυτόματης υποβολής
  } finally {
    submitting = false;
  }
}

// ---------------------------------------------------------------------------
// Βήμα 2β & 3: παράδοση αρχείου και κωδικός επιβεβαίωσης
// ---------------------------------------------------------------------------
async function submitFile() {
  const file = $('inp-file').files[0];
  if (!file || !current) { show('step-select'); return; }
  setError('file-error', '');
  $('btn-submit-file').disabled = true;
  const fd = new FormData();
  fd.append('fullname', $('inp-name').value.trim());
  fd.append('section', $('inp-section').value.trim());
  fd.append('comment', $('inp-comment').value.trim());
  fd.append('file', file);
  try {
    const data = await api(`activities/${current.id}/submit-file`, { method: 'POST', body: fd });
    finish(data.code, `Η εργασία «${current.title}» παραδόθηκε μαζί με το αρχείο ${data.filename}.`);
  } catch (err) {
    setError('file-error', err.message);
  } finally {
    $('btn-submit-file').disabled = false;
  }
}

function finish(code, note) {
  clearInterval(timerHandle);
  testSession = null;
  $('done-code').textContent = code;
  $('done-note').textContent = note;
  show('step-done');
}

function resetAll() {
  current = null;
  testSession = null;
  activities = [];
  clearInterval(timerHandle);
  clearDraft();
  $('sel-class').value = '';
  $('inp-file').value = '';
  $('inp-comment').value = '';
  loadActivities();
  show('step-select');
}

// ---------------------------------------------------------------------------
// Αρχικοποίηση & ανάκτηση ημιτελούς διαγωνίσματος μετά από refresh
// ---------------------------------------------------------------------------
function tryResume() {
  let draft = null;
  try { draft = JSON.parse(localStorage.getItem(RESUME_KEY) || 'null'); } catch (e) { /* αγνόησε */ }
  if (!draft || !draft.session) return false;
  const s = draft.session;
  const now = Date.now() / 1000 + (s.offset || 0);
  if (now > s.deadline + 60) { clearDraft(); return false; } // πολύ εκπρόθεσμο
  startTest(
    { ...s, server_now: now - (s.offset || 0) },
    s.fullname, s.section, draft.answers || {}
  );
  if (now >= s.deadline) submitTest(true); // ο χρόνος έληξε όσο η σελίδα ήταν κλειστή
  return true;
}

document.addEventListener('DOMContentLoaded', () => {
  $('sel-class').addEventListener('change', loadActivities);
  $('sel-activity').addEventListener('change', onActivityChange);
  $('btn-continue').addEventListener('click', onContinue);
  $('btn-back').addEventListener('click', () => show('step-select'));
  $('btn-submit-file').addEventListener('click', submitFile);
  $('btn-submit-test').addEventListener('click', () => submitTest(false));
  $('btn-new').addEventListener('click', resetAll);
  window.addEventListener('beforeunload', (e) => {
    if (testSession) { e.preventDefault(); e.returnValue = ''; }
  });
  if (!tryResume()) show('step-select');
});