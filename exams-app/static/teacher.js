/*
 * Παράδοση Εργασιών & Ψηφιακά Διαγωνίσματα — περιβάλλον καθηγητή.
 * Ο πραγματικός έλεγχος πρόσβασης γίνεται στον server (HMAC cookie)·
 * εδώ μόνο η διαχείριση του UI.
 */
'use strict';

// Το API ζει πάντα στη ρίζα της εφαρμογής (/exams/api/), ΟΧΙ κάτω από το
// /exams/teacher/ — αφαιρούμε τυχόν κατάληξη teacher/ από το base του template.
const API = window.EXAMS_BASE.replace(/teacher\/$/, '') + 'api/';
const $ = (id) => document.getElementById(id);
let questionsDraft = [];   // ερωτήσεις υπό δημιουργία
let openActivityId = null; // δραστηριότητα με ανοιχτό πίνακα υποβολών

function esc(text) {
  const div = document.createElement('div');
  div.textContent = String(text ?? '');
  return div.innerHTML;
}

function setError(id, msg) {
  const el = $(id);
  el.textContent = msg || '';
  el.hidden = !msg;
}

async function api(path, options = {}) {
  const res = await fetch(API + path, options);
  if (res.status === 401) { lockUI(); throw new Error('Η συνεδρία έληξε — ξαναβάλε τον κωδικό καθηγητή.'); }
  let data = {};
  try { data = await res.json(); } catch (e) { /* κενό σώμα */ }
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Σφάλμα επικοινωνίας με τον διακομιστή.';
    throw new Error(detail);
  }
  return data;
}

function jsonOpts(method, body) {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

// ---------------------------------------------------------------------------
// Σύνδεση / αποσύνδεση
// ---------------------------------------------------------------------------
function unlockUI() {
  $('login-gate').hidden = true;
  $('teacher-app').hidden = false;
  loadActivities();
}

function lockUI() {
  $('teacher-app').hidden = true;
  $('login-gate').hidden = false;
  $('submissions-panel').hidden = true;
  openActivityId = null;
}

async function login(ev) {
  ev.preventDefault();
  setError('login-error', '');
  try {
    await api('teacher/login', jsonOpts('POST', { password: $('login-pass').value }));
    $('login-pass').value = '';
    unlockUI();
  } catch (err) {
    setError('login-error', err.message);
  }
}

async function logout() {
  try { await api('teacher/logout', { method: 'POST' }); } catch (e) { /* αγνόησε */ }
  lockUI();
}

// ---------------------------------------------------------------------------
// Κατασκευαστής ερωτήσεων
// ---------------------------------------------------------------------------
function renderDraft() {
  $('q-list').innerHTML = questionsDraft.map((q, i) => {
    const isMc = q.type === 'mc';
    const badge = isMc ? 'Πολλαπλής Επιλογής' : 'Ανάπτυξης / Κώδικα';
    const color = isMc ? 'indigo' : 'violet';
    let mc = '';
    if (isMc) {
      mc = `<div class="mt-2 space-y-1.5">` + q.options.map((opt, j) => `
        <div class="flex items-center gap-2">
          <input type="radio" name="correct-${i}" ${q.correct === j ? 'checked' : ''}
                 onchange="questionsDraft[${i}].correct=${j}" class="accent-emerald-600" title="Σωστή απάντηση">
          <input type="text" value="${esc(opt)}" maxlength="500" placeholder="Επιλογή ${j + 1}"
                 oninput="questionsDraft[${i}].options[${j}]=this.value"
                 class="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm">
          <button type="button" onclick="removeOption(${i},${j})" class="text-red-500 hover:text-red-700 text-sm px-1" title="Διαγραφή επιλογής">✕</button>
        </div>`).join('') + `
        <button type="button" onclick="addOption(${i})" class="text-xs font-semibold text-blue-700 hover:underline">+ Προσθήκη επιλογής</button>
        <p class="text-[11px] text-slate-500">Το radio αριστερά ορίζει τη σωστή απάντηση (αυτόματη βαθμολόγηση).</p>
      </div>`;
    }
    return `
      <div class="rounded-xl ring-1 ring-slate-200 bg-slate-50 p-4">
        <div class="flex items-center justify-between gap-2 flex-wrap">
          <span class="text-xs font-bold px-2.5 py-1 rounded-full bg-${color}-100 text-${color}-700">Ε${i + 1} · ${badge}</span>
          <div class="flex items-center gap-2 text-sm">
            <label class="font-semibold">Μονάδες:</label>
            <input type="number" min="0" max="100" step="0.5" value="${q.points}"
                   onchange="questionsDraft[${i}].points=Number(this.value)"
                   class="w-20 rounded-lg border border-slate-300 px-2 py-1">
            <button type="button" onclick="removeQuestion(${i})" class="text-red-500 hover:text-red-700 font-bold px-1" title="Διαγραφή ερώτησης">🗑</button>
          </div>
        </div>
        <textarea rows="2" maxlength="4000" placeholder="Εκφώνηση ερώτησης…"
                  oninput="questionsDraft[${i}].text=this.value"
                  class="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">${esc(q.text)}</textarea>
        ${mc}
      </div>`;
  }).join('');
}

function addQuestion(type) {
  questionsDraft.push(type === 'mc'
    ? { type, text: '', options: ['', ''], correct: 0, points: 1 }
    : { type, text: '', options: [], correct: null, points: 5 });
  renderDraft();
}

function removeQuestion(i) { questionsDraft.splice(i, 1); renderDraft(); }
function addOption(i) {
  if (questionsDraft[i].options.length >= 8) return;
  questionsDraft[i].options.push('');
  renderDraft();
}
function removeOption(i, j) {
  const q = questionsDraft[i];
  if (q.options.length <= 2) return;
  q.options.splice(j, 1);
  if (q.correct >= q.options.length) q.correct = 0;
  renderDraft();
}

function onKindChange() {
  const isTest = $('f-kind').value === 'test';
  $('duration-wrap').hidden = !isTest;
  $('questions-builder').hidden = !isTest;
}

async function createActivity() {
  setError('create-error', '');
  const kind = $('f-kind').value;
  const payload = {
    title: $('f-title').value.trim(),
    class_slug: $('f-class').value,
    kind,
    duration: kind === 'test' ? Number($('f-duration').value) : 0,
    active: $('f-active').checked,
    questions: kind === 'test' ? questionsDraft : [],
  };
  if (!payload.title) { setError('create-error', 'Συμπλήρωσε τίτλο.'); return; }
  $('btn-create').disabled = true;
  try {
    await api('teacher/activities', jsonOpts('POST', payload));
    $('f-title').value = '';
    questionsDraft = [];
    renderDraft();
    $('create-box').open = false;
    await loadActivities();
  } catch (err) {
    setError('create-error', err.message);
  } finally {
    $('btn-create').disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Λίστα δραστηριοτήτων & διακόπτης Ενεργό/Κλειστό
// ---------------------------------------------------------------------------
async function loadActivities() {
  const box = $('activities-list');
  try {
    const data = await api('teacher/activities');
    if (!data.activities.length) {
      box.innerHTML = '<div class="rounded-2xl border-2 border-dashed border-slate-300 bg-white/60 p-8 text-center text-sm text-slate-500">Δεν υπάρχουν δραστηριότητες ακόμη. Δημιούργησε την πρώτη παραπάνω.</div>';
      return;
    }
    box.innerHTML = data.activities.map((a) => {
      const kindLabel = a.kind === 'test'
        ? `📝 Διαγώνισμα · ${a.duration}΄ · ${a.questions.length} ερωτήσεις`
        : '📎 Παράδοση Αρχείου';
      const stateBadge = a.active
        ? '<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300">ΕΝΕΡΓΟ</span>'
        : '<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-slate-200 text-slate-600 ring-1 ring-slate-300">ΚΛΕΙΣΤΟ</span>';
      return `
      <div class="rounded-2xl bg-white p-4 sm:p-5 ring-1 ring-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2 flex-wrap">
            <h3 class="font-bold text-slate-900 truncate">${esc(a.title)}</h3>
            ${stateBadge}
          </div>
          <p class="text-xs text-slate-500 mt-1">${esc(a.class_label)} · ${kindLabel} · ${a.submission_count} υποβολές</p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <label class="inline-flex items-center gap-2 cursor-pointer select-none text-sm font-semibold" title="Άνοιγμα μόνο την ώρα του μαθήματος">
            <input type="checkbox" ${a.active ? 'checked' : ''} onchange="toggleActive(${a.id}, this.checked)" class="w-5 h-5 accent-emerald-600">
            ${a.active ? 'Ενεργό' : 'Κλειστό'}
          </label>
          <button onclick="openSubmissions(${a.id})" class="px-3 py-1.5 rounded-lg bg-blue-50 text-blue-700 ring-1 ring-blue-200 text-sm font-semibold hover:bg-blue-100 transition">📋 Υποβολές (${a.submission_count})</button>
          <button onclick="deleteActivity(${a.id}, '${esc(a.title).replace(/'/g, '&#39;')}')" class="px-2.5 py-1.5 rounded-lg text-red-500 hover:bg-red-50 text-sm" title="Διαγραφή δραστηριότητας & υποβολών">🗑</button>
        </div>
      </div>`;
    }).join('');
  } catch (err) {
    box.innerHTML = `<div class="rounded-xl bg-red-50 ring-1 ring-red-200 p-4 text-sm text-red-700">${esc(err.message)}</div>`;
  }
}

async function toggleActive(id, active) {
  try {
    await api(`teacher/activities/${id}`, jsonOpts('PATCH', { active }));
    await loadActivities();
  } catch (err) {
    alert(err.message);
    await loadActivities();
  }
}

async function deleteActivity(id, title) {
  if (!confirm(`Διαγραφή «${title}» μαζί με ΟΛΕΣ τις υποβολές και τα αρχεία της;`)) return;
  try {
    await api(`teacher/activities/${id}`, { method: 'DELETE' });
    if (openActivityId === id) { $('submissions-panel').hidden = true; openActivityId = null; }
    await loadActivities();
  } catch (err) {
    alert(err.message);
  }
}

// ---------------------------------------------------------------------------
// Πίνακας υποβολών & βαθμολόγηση ανάπτυξης
// ---------------------------------------------------------------------------
function fmtNum(v) {
  if (v === null || v === undefined || v === '') return '—';
  return String(Number(v)).replace('.', ',');
}

function fmtWhen(ts) {
  return new Date(ts * 1000).toLocaleString('el-GR', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

async function openSubmissions(id) {
  openActivityId = id;
  setError('subs-error', '');
  const panel = $('submissions-panel');
  panel.hidden = false;
  $('subs-body').innerHTML = '<p class="text-sm text-slate-500">Φόρτωση…</p>';
  try {
    const data = await api(`teacher/activities/${id}/submissions`);
    const a = data.activity;
    $('subs-title').textContent = `📋 Υποβολές — ${a.title}`;
    $('subs-meta').textContent = `${a.class_label} · ${a.kind === 'test' ? `Διαγώνισμα ${a.duration}΄` : 'Παράδοση Αρχείου'} · ${data.submissions.length} υποβολές`;
    $('btn-zip').href = API + `teacher/activities/${id}/zip`;
    $('btn-csv').href = API + `teacher/activities/${id}/csv`;
    $('btn-zip').style.display = a.kind === 'assignment' ? '' : 'none';
    renderSubmissions(a, data.submissions);
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (err) {
    $('subs-body').innerHTML = '';
    setError('subs-error', err.message);
  }
}

function renderSubmissions(a, subs) {
  if (!subs.length) {
    $('subs-body').innerHTML = '<p class="text-sm text-slate-500">Δεν υπάρχουν υποβολές ακόμη.</p>';
    return;
  }
  if (a.kind === 'assignment') {
    $('subs-body').innerHTML = `
      <table class="w-full text-sm border-collapse">
        <thead><tr class="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200">
          <th class="py-2 pr-3">Τμήμα</th><th class="py-2 pr-3">Ονοματεπώνυμο</th>
          <th class="py-2 pr-3">Κωδικός</th><th class="py-2 pr-3">Αρχείο</th>
          <th class="py-2 pr-3">Σχόλιο</th><th class="py-2">Υποβολή</th>
        </tr></thead>
        <tbody>${subs.map((s) => `
          <tr class="border-b border-slate-100 hover:bg-slate-50">
            <td class="py-2.5 pr-3 font-bold">${esc(s.section)}</td>
            <td class="py-2.5 pr-3">${esc(s.fullname)}</td>
            <td class="py-2.5 pr-3 font-mono text-xs">${esc(s.code)}</td>
            <td class="py-2.5 pr-3"><a class="text-blue-700 hover:underline break-all" href="${API}teacher/submissions/${s.id}/file">⬇ ${esc(s.orig_name)}</a></td>
            <td class="py-2.5 pr-3 text-xs text-slate-600 max-w-[16rem]">${esc(s.comment) || '—'}</td>
            <td class="py-2.5 text-xs whitespace-nowrap">${fmtWhen(s.submitted_at)}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
    return;
  }

  // Διαγώνισμα: γραμμές με αναδιπλούμενη λεπτομέρεια & πεδία βαθμολόγησης.
  $('subs-body').innerHTML = `
    <table class="w-full text-sm border-collapse">
      <thead><tr class="text-left text-xs uppercase tracking-wide text-slate-500 border-b border-slate-200">
        <th class="py-2 pr-3">Τμήμα</th><th class="py-2 pr-3">Ονοματεπώνυμο</th>
        <th class="py-2 pr-3">Κωδικός</th><th class="py-2 pr-3">MC (αυτόματο)</th>
        <th class="py-2 pr-3">Σύνολο</th><th class="py-2 pr-3">Υποβολή</th><th class="py-2"></th>
      </tr></thead>
      <tbody>${subs.map((s) => `
        <tr class="border-b border-slate-100 hover:bg-slate-50">
          <td class="py-2.5 pr-3 font-bold">${esc(s.section)}</td>
          <td class="py-2.5 pr-3">${esc(s.fullname)}</td>
          <td class="py-2.5 pr-3 font-mono text-xs">${esc(s.code)}</td>
          <td class="py-2.5 pr-3 font-semibold text-indigo-700">${fmtNum(s.mc_score)} / ${fmtNum(s.mc_max)}</td>
          <td class="py-2.5 pr-3 font-bold text-emerald-700">${fmtNum(s.total_score)} / ${fmtNum(s.max_score)}</td>
          <td class="py-2.5 pr-3 text-xs whitespace-nowrap">${fmtWhen(s.submitted_at)}${s.auto_submit ? ' <span class="text-amber-600 font-semibold" title="Υποβλήθηκε αυτόματα στη λήξη του χρόνου">⏱ auto</span>' : ''}</td>
          <td class="py-2.5"><button onclick="toggleDetail(${s.id})" class="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold">Λεπτομέρειες ▾</button></td>
        </tr>
        <tr id="detail-${s.id}" hidden><td colspan="7" class="pb-4">${renderDetail(a, s)}</td></tr>`).join('')}
      </tbody>
    </table>`;
}

function renderDetail(a, s) {
  const rows = a.questions.map((q, i) => {
    const qid = String(i);
    const answer = s.answers[qid];
    if (q.type === 'mc') {
      const chosenIdx = answer === undefined || answer === null || answer === '' ? null : Number(answer);
      const opts = q.options.map((opt, j) => {
        let cls = 'text-slate-600';
        let mark = '';
        if (j === q.correct) { cls = 'text-emerald-700 font-semibold'; mark = ' ✓'; }
        if (j === chosenIdx && j !== q.correct) { cls = 'text-red-600 font-semibold'; mark = ' ✗ (επιλογή μαθητή)'; }
        else if (j === chosenIdx) { mark = ' ← επιλογή μαθητή'; }
        return `<div class="${cls}">${esc(opt)}${mark}</div>`;
      }).join('');
      const got = chosenIdx === q.correct ? q.points : 0;
      return `<div class="rounded-lg bg-slate-50 ring-1 ring-slate-200 p-3">
        <div class="flex justify-between gap-2 text-xs font-bold"><span>Ε${i + 1} · Πολλαπλής</span><span class="text-indigo-700">${fmtNum(got)} / ${fmtNum(q.points)} μον.</span></div>
        <p class="mt-1 text-sm whitespace-pre-wrap">${esc(q.text)}</p>
        <div class="mt-1.5 text-xs space-y-0.5">${opts}</div>
        ${chosenIdx === null ? '<p class="mt-1 text-xs text-amber-600 font-semibold">Ο μαθητής δεν απάντησε.</p>' : ''}
      </div>`;
    }
    const saved = s.essay_scores[qid];
    return `<div class="rounded-lg bg-violet-50/60 ring-1 ring-violet-200 p-3">
      <div class="flex justify-between gap-2 text-xs font-bold"><span>Ε${i + 1} · Ανάπτυξης / Κώδικα</span><span class="text-violet-700">έως ${fmtNum(q.points)} μον.</span></div>
      <p class="mt-1 text-sm whitespace-pre-wrap">${esc(q.text)}</p>
      <pre class="mt-2 rounded-lg bg-white ring-1 ring-slate-200 p-3 text-xs whitespace-pre-wrap font-mono max-h-64 overflow-auto">${esc(answer || '(κενή απάντηση)')}</pre>
      <div class="mt-2 flex items-center gap-2 text-sm">
        <label class="font-semibold" for="grade-${s.id}-${qid}">Βαθμός:</label>
        <input id="grade-${s.id}-${qid}" type="number" min="0" max="${q.points}" step="0.5"
               value="${saved !== undefined && saved !== null ? saved : ''}" placeholder="—"
               class="w-24 rounded-lg border border-slate-300 px-2 py-1.5">
        <span class="text-xs text-slate-500">/ ${fmtNum(q.points)}</span>
      </div>
    </div>`;
  }).join('');
  const hasEssay = a.questions.some((q) => q.type !== 'mc');
  return `<div class="space-y-2 pt-2">
    ${rows}
    ${hasEssay ? `<div class="flex items-center gap-3">
      <button onclick="saveGrades(${s.id})" class="px-4 py-2 rounded-lg bg-violet-600 text-white text-sm font-bold hover:bg-violet-700 transition">💾 Αποθήκευση Βαθμολογίας Ανάπτυξης</button>
      <span id="grade-msg-${s.id}" class="text-xs font-semibold text-emerald-700"></span>
    </div>` : ''}
  </div>`;
}

function toggleDetail(id) {
  const row = $(`detail-${id}`);
  row.hidden = !row.hidden;
}

async function saveGrades(subId) {
  const scores = {};
  document.querySelectorAll(`[id^="grade-${subId}-"]`).forEach((inp) => {
    const qid = inp.id.split('-').pop();
    if (inp.value !== '') scores[qid] = Number(inp.value);
  });
  const msg = $(`grade-msg-${subId}`);
  try {
    const res = await api(`teacher/submissions/${subId}/grade`, jsonOpts('POST', { essay_scores: scores }));
    msg.textContent = `✓ Αποθηκεύτηκε — Σύνολο: ${fmtNum(res.total_score)} / ${fmtNum(res.max_score)}`;
    setTimeout(() => { if (openActivityId) openSubmissions(openActivityId); }, 1200);
  } catch (err) {
    msg.textContent = '';
    setError('subs-error', err.message);
  }
}

// ---------------------------------------------------------------------------
// Αρχικοποίηση
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  $('login-form').addEventListener('submit', login);
  $('btn-logout').addEventListener('click', logout);
  $('btn-refresh').addEventListener('click', loadActivities);
  $('f-kind').addEventListener('change', onKindChange);
  $('btn-add-mc').addEventListener('click', () => addQuestion('mc'));
  $('btn-add-essay').addEventListener('click', () => addQuestion('essay'));
  $('btn-create').addEventListener('click', createActivity);
  $('btn-close-subs').addEventListener('click', () => {
    $('submissions-panel').hidden = true;
    openActivityId = null;
  });
  if (window.EXAMS_LOGGED_IN) loadActivities();
});