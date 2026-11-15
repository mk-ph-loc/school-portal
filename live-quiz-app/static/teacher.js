/*
 * Ζωντανό Παιχνίδι Τάξης (Live Quiz) — λογική καθηγητή/προτζέκτορα.
 * Vanilla JS + WebSocket· όλες οι ενέργειες ελέγχου περνούν από το API
 * (HMAC cookie), ενώ η ζωντανή κατάσταση έρχεται μέσω του ίδιου WS που
 * χρησιμοποιούν και οι μαθητές.
 */
'use strict';

const BASE = window.LIVEQUIZ_BASE;                 // π.χ. /live-quiz/teacher/
const ROOT = BASE.replace(/teacher\/$/, '');       // π.χ. /live-quiz/
const API = ROOT + 'api/teacher/';
const $ = (id) => document.getElementById(id);
const SHAPES = ['▲', '◆', '●', '■'];
const MEDALS = ['🥇', '🥈', '🥉', '4.', '5.'];

let ws = null;
let currentPin = null;
let clockOffset = 0;
let timerHandle = null;
let reconnectDelay = 1000;
let closedByUs = false;
let lastBoardIsLast = false;

function esc(text) {
  const div = document.createElement('div');
  div.textContent = String(text ?? '');
  return div.innerHTML;
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

function post(path, body) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
}

function setError(id, msg) {
  const el = $(id);
  el.textContent = msg || '';
  el.hidden = !msg;
}

function showView(view) {
  ['view-login', 'view-manage', 'view-stage'].forEach((v) => { $(v).hidden = v !== view; });
  window.scrollTo({ top: 0 });
}

function showStage(stage) {
  ['stage-lobby', 'stage-question', 'stage-reveal', 'stage-board', 'stage-final']
    .forEach((s) => { $(s).hidden = s !== stage; });
  showView('view-stage');
}

// ---------------------------------------------------------------------------
// Login / Logout
// ---------------------------------------------------------------------------
$('login-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  setError('login-error', '');
  try {
    await post('login', { password: $('inp-pass').value });
    $('inp-pass').value = '';
    showView('view-manage');
    await loadQuizzes();
  } catch (err) {
    setError('login-error', err.message);
  }
});

$('btn-logout').addEventListener('click', async () => {
  await post('logout');
  location.reload();
});

// ---------------------------------------------------------------------------
// Λίστα κουίζ
// ---------------------------------------------------------------------------
async function loadQuizzes() {
  setError('manage-error', '');
  const data = await api('quizzes');
  const list = $('quiz-list');
  $('quiz-empty').hidden = data.quizzes.length > 0;
  list.innerHTML = data.quizzes.map((q) => {
    const live = q.live
      ? '<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200">● LIVE ' + esc(q.live.pin) + '</span>'
      : '<span class="text-[11px] font-bold px-2.5 py-1 rounded-full bg-slate-100 text-slate-600">' + q.questions.length + ' ερωτήσεις</span>';
    const action = q.live
      ? '<button data-resume="' + esc(q.live.pin) + '" class="flex-1 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold hover:bg-emerald-700 transition">▶ Συνέχεια</button>'
      : '<button data-start="' + q.id + '" class="flex-1 px-3 py-2 rounded-lg bg-fuchsia-700 text-white text-sm font-semibold hover:bg-fuchsia-800 transition">▶ Έναρξη Live</button>';
    return '<div class="rounded-2xl bg-white p-5 ring-1 ring-slate-200 shadow-sm">' +
      '<div class="flex items-start justify-between gap-2"><h3 class="font-bold text-slate-900 leading-snug">' + esc(q.title) + '</h3>' + live + '</div>' +
      '<p class="mt-1 text-xs text-slate-500">' + q.questions.length + ' ερωτήσεις πολλαπλής επιλογής</p>' +
      '<div class="mt-4 flex gap-2">' + action +
      '<button data-del="' + q.id + '" class="px-3 py-2 rounded-lg bg-white ring-1 ring-slate-300 text-red-600 text-sm font-semibold hover:bg-red-50 transition" title="Διαγραφή">🗑</button>' +
      '</div></div>';
  }).join('');

  list.querySelectorAll('[data-start]').forEach((b) => b.addEventListener('click', () => startSession(Number(b.dataset.start))));
  list.querySelectorAll('[data-resume]').forEach((b) => b.addEventListener('click', () => openStage(b.dataset.resume)));
  list.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Διαγραφή αυτού του κουίζ;')) return;
    try { await api('quizzes/' + b.dataset.del, { method: 'DELETE' }); await loadQuizzes(); }
    catch (err) { setError('manage-error', err.message); }
  }));
}

// ---------------------------------------------------------------------------
// Επεξεργαστής νέου κουίζ
// ---------------------------------------------------------------------------
function questionEditorRow(q) {
  q = q || { text: '', options: ['', '', '', ''], correct: 0, time: 20 };
  const row = document.createElement('div');
  row.className = 'q-row rounded-xl bg-slate-50 ring-1 ring-slate-200 p-4';
  const groupName = 'correct-' + Math.random().toString(36).slice(2);
  row.innerHTML =
    '<div class="flex items-center justify-between gap-2">' +
      '<span class="q-num text-sm font-bold text-slate-500"></span>' +
      '<button type="button" class="q-del text-red-600 text-sm font-semibold hover:underline">Αφαίρεση</button>' +
    '</div>' +
    '<input type="text" maxlength="500" placeholder="Κείμενο ερώτησης" class="q-text mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-fuchsia-500">' +
    '<div class="mt-3 grid sm:grid-cols-2 gap-2">' +
      [0, 1, 2, 3].map((i) =>
        '<label class="flex items-center gap-2 rounded-lg ans-' + i + ' p-2 text-white">' +
          '<input type="radio" name="' + groupName + '" class="q-correct accent-white" value="' + i + '" title="Σωστή απάντηση">' +
          '<span aria-hidden="true">' + SHAPES[i] + '</span>' +
          '<input type="text" maxlength="200" placeholder="Απάντηση ' + (i + 1) + '" class="q-opt flex-1 min-w-0 rounded bg-white/90 text-slate-900 px-2 py-1.5 text-sm focus:outline-none">' +
        '</label>').join('') +
    '</div>' +
    '<div class="mt-3 flex items-center gap-2 text-sm">' +
      '<label class="font-semibold text-slate-600">⏱ Χρόνος:</label>' +
      '<input type="number" min="5" max="120" step="5" class="q-time w-20 rounded-lg border border-slate-300 px-2 py-1.5">' +
      '<span class="text-slate-500">δευτερόλεπτα · επίλεξε το radio της σωστής απάντησης</span>' +
    '</div>';
  row.querySelector('.q-text').value = q.text;
  row.querySelectorAll('.q-opt').forEach((inp, i) => { inp.value = q.options[i]; });
  row.querySelectorAll('.q-correct')[q.correct].checked = true;
  row.querySelector('.q-time').value = q.time;
  row.querySelector('.q-del').addEventListener('click', () => { row.remove(); renumber(); });
  return row;
}

function renumber() {
  document.querySelectorAll('#q-editor-list .q-num').forEach((el, i) => {
    el.textContent = 'Ερώτηση ' + (i + 1);
  });
}

$('btn-new').addEventListener('click', () => {
  $('samples-panel').hidden = true;
  $('inp-title').value = '';
  $('q-editor-list').innerHTML = '';
  $('q-editor-list').appendChild(questionEditorRow());
  renumber();
  setError('editor-error', '');
  $('editor-panel').hidden = false;
  $('editor-panel').scrollIntoView({ behavior: 'smooth' });
});

$('btn-add-q').addEventListener('click', () => {
  $('q-editor-list').appendChild(questionEditorRow());
  renumber();
});

$('btn-cancel-edit').addEventListener('click', () => { $('editor-panel').hidden = true; });

$('btn-save-quiz').addEventListener('click', async () => {
  setError('editor-error', '');
  const title = $('inp-title').value.trim();
  if (!title) { setError('editor-error', 'Δώσε έναν τίτλο στο κουίζ.'); return; }
  const questions = [];
  for (const row of document.querySelectorAll('#q-editor-list .q-row')) {
    const opts = Array.from(row.querySelectorAll('.q-opt')).map((i) => i.value.trim());
    const checked = row.querySelector('.q-correct:checked');
    questions.push({
      text: row.querySelector('.q-text').value.trim(),
      options: opts,
      correct: checked ? Number(checked.value) : -1,
      time: Number(row.querySelector('.q-time').value) || 20,
    });
  }
  try {
    await post('quizzes', { title, questions });
    $('editor-panel').hidden = true;
    await loadQuizzes();
  } catch (err) {
    setError('editor-error', err.message);
  }
});

// ---------------------------------------------------------------------------
// Εισαγωγή JSON/CSV & έτοιμα παραδείγματα
// ---------------------------------------------------------------------------
$('btn-import').addEventListener('click', () => $('imp-file').click());

$('imp-file').addEventListener('change', async () => {
  const file = $('imp-file').files[0];
  $('imp-file').value = '';
  if (!file) return;
  setError('manage-error', '');
  try {
    const content = await file.text();
    const data = await post('import', { filename: file.name, content });
    alert('Εισήχθησαν ' + data.count + ' ερωτήσεις στο κουίζ «' + data.title + '».');
    await loadQuizzes();
  } catch (err) {
    setError('manage-error', err.message);
  }
});

$('btn-samples').addEventListener('click', async () => {
  setError('manage-error', '');
  try {
    const data = await api('samples');
    $('samples-list').innerHTML = data.samples.map((s, i) =>
      '<div class="rounded-xl bg-slate-50 ring-1 ring-slate-200 p-4">' +
      '<h4 class="font-bold text-slate-900 text-sm leading-snug">' + esc(s.title) + '</h4>' +
      '<p class="mt-1 text-xs text-slate-500">' + s.questions.length + ' ερωτήσεις</p>' +
      '<button data-sample="' + i + '" class="mt-3 w-full px-3 py-2 rounded-lg bg-fuchsia-700 text-white text-sm font-semibold hover:bg-fuchsia-800 transition">＋ Προσθήκη στα Κουίζ μου</button></div>'
    ).join('');
    $('samples-list').querySelectorAll('[data-sample]').forEach((b) =>
      b.addEventListener('click', async () => {
        try {
          await post('samples/' + b.dataset.sample);
          $('samples-panel').hidden = true;
          await loadQuizzes();
        } catch (err) { setError('manage-error', err.message); }
      }));
    $('samples-panel').hidden = false;
    $('samples-panel').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    setError('manage-error', err.message);
  }
});

// ---------------------------------------------------------------------------
// Ζωντανό παιχνίδι — WebSocket προτζέκτορα (ταυτοποίηση με το HMAC cookie)
// ---------------------------------------------------------------------------
async function startSession(quizId) {
  setError('manage-error', '');
  try {
    const data = await post('start', { quiz_id: quizId });
    openStage(data.pin);
  } catch (err) {
    setError('manage-error', err.message);
  }
}

function openStage(pin) {
  currentPin = pin;
  $('stage-pin').textContent = pin;
  $('stage-url').textContent = location.host + ROOT;
  showStage('stage-lobby');
  connectWS();
}

function connectWS() {
  closedByUs = false;
  if (ws) { try { ws.close(); } catch (e) { /* ignore */ } }
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  ws = new WebSocket(proto + location.host + ROOT + 'ws/' + currentPin);
  ws.onopen = () => { reconnectDelay = 1000; };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    handleMessage(msg);
  };
  ws.onclose = () => {
    if (closedByUs || !currentPin) return;
    setTimeout(connectWS, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 15000);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) { /* ignore */ } };
}

setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
}, 30000);

function handleMessage(msg) {
  switch (msg.type) {
    case 'lobby': renderLobby(msg); break;
    case 'question': renderQuestion(msg); break;
    case 'progress':
      $('st-answered').textContent = msg.answered;
      $('st-players').textContent = msg.players;
      break;
    case 'reveal': renderReveal(msg); break;
    case 'leaderboard': renderBoard(msg); break;
    case 'finished': renderFinal(msg); break;
  }
}

function renderLobby(msg) {
  stopTimer();
  $('stage-title').textContent = msg.title;
  $('stage-count').textContent = msg.players.length;
  $('btn-start-game').disabled = msg.players.length === 0;
  $('stage-names').innerHTML = msg.players.map((n) =>
    '<span class="pop-in px-4 py-2 rounded-full bg-white ring-1 ring-slate-300 font-bold text-slate-800 shadow-sm">' + esc(n) + '</span>'
  ).join('');
  showStage('stage-lobby');
}

function renderQuestion(msg) {
  clockOffset = (msg.server_now * 1000) - Date.now();
  $('st-progress').textContent = 'Ερώτηση ' + (msg.q_index + 1) + '/' + msg.total;
  $('st-text').textContent = msg.text;
  document.querySelectorAll('#st-options .st-opt').forEach((el, i) => { el.textContent = msg.options[i]; });
  showStage('stage-question');
  runTimer(msg.deadline);
}

function runTimer(deadlineEpoch) {
  stopTimer();
  const tick = () => {
    const secs = Math.max(0, Math.ceil((deadlineEpoch * 1000 - (Date.now() + clockOffset)) / 1000));
    const el = $('st-timer');
    el.textContent = secs;
    el.classList.toggle('timer-low', secs <= 5);
    el.classList.toggle('text-red-600', secs <= 5);
    if (secs <= 0) stopTimer();
  };
  tick();
  timerHandle = setInterval(tick, 250);
}

function stopTimer() {
  if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
}

function renderReveal(msg) {
  stopTimer();
  $('rv-progress').textContent = 'Ερώτηση ' + (msg.q_index + 1) + '/' + msg.total + ' — Αποτελέσματα';
  $('rv-text').textContent = msg.text;
  $('rv-answered').textContent = msg.answered;
  $('rv-players').textContent = msg.players;
  const maxCount = Math.max(1, ...msg.counts);
  $('rv-chart').innerHTML = msg.counts.map((n, i) => {
    const h = Math.round((n / maxCount) * 100);
    const isCorrect = i === msg.correct;
    return '<div class="flex flex-col items-center justify-end h-full w-20 sm:w-28">' +
      '<span class="mb-1 text-xl font-extrabold tabular-nums">' + n + '</span>' +
      '<div class="bar-fill ans-' + i + ' w-full rounded-t-lg" style="height:' + Math.max(h, 3) + '%"></div>' +
      '<div class="mt-2 text-2xl ' + (isCorrect ? '' : 'opacity-40') + '">' + SHAPES[i] + '</div>' +
      (isCorrect ? '<div class="text-emerald-600 font-extrabold text-sm">✓ Σωστό</div>' : '<div class="text-transparent text-sm">·</div>') +
      '</div>';
  }).join('');
  showStage('stage-reveal');
}

function boardRows(top5) {
  return top5.map((e, i) =>
    '<div class="pop-in flex items-center justify-between rounded-xl bg-white ring-1 ring-slate-200 shadow-sm px-5 py-3.5">' +
    '<span class="text-lg font-bold text-slate-900">' + MEDALS[i] + ' ' + esc(e.name) + '</span>' +
    '<span class="text-xl font-extrabold text-fuchsia-700 tabular-nums">' + e.score + '</span></div>'
  ).join('') || '<p class="text-slate-500">Δεν υπάρχουν παίκτες.</p>';
}

function renderBoard(msg) {
  stopTimer();
  lastBoardIsLast = msg.is_last;
  $('lb-progress').textContent = 'Μετά την ερώτηση ' + (msg.q_index + 1) + '/' + msg.total;
  $('lb-list').innerHTML = boardRows(msg.top5);
  $('btn-next-2').textContent = msg.is_last ? '🏁 Τελικά Αποτελέσματα' : '▶ Επόμενη Ερώτηση';
  showStage('stage-board');
}

function renderFinal(msg) {
  stopTimer();
  $('fn-podium').innerHTML = boardRows(msg.top5);
  showStage('stage-final');
}

// ---------------------------------------------------------------------------
// Κουμπιά ελέγχου ροής παιχνιδιού
// ---------------------------------------------------------------------------
async function nextStep() {
  try { await post(currentPin + '/next'); }
  catch (err) { alert(err.message); }
}

$('btn-start-game').addEventListener('click', nextStep);   // lobby → ερώτηση 1
$('btn-skip').addEventListener('click', nextStep);         // question → reveal
$('btn-next-1').addEventListener('click', nextStep);       // reveal → leaderboard
$('btn-next-2').addEventListener('click', nextStep);       // leaderboard → επόμενη/τέλος

$('btn-end').addEventListener('click', async () => {
  if (!confirm('Τερματισμός του παιχνιδιού τώρα;')) return;
  try { await post(currentPin + '/end'); } catch (err) { alert(err.message); }
});

$('btn-cancel-lobby').addEventListener('click', async () => {
  if (!confirm('Ακύρωση του δωματίου; Οι μαθητές θα αποσυνδεθούν.')) return;
  try { await post(currentPin + '/end'); } catch (err) { /* ignore */ }
  backToManage();
});

$('btn-back').addEventListener('click', backToManage);

function backToManage() {
  closedByUs = true;
  currentPin = null;
  stopTimer();
  try { ws && ws.close(); } catch (e) { /* ignore */ }
  showView('view-manage');
  loadQuizzes().catch(() => { /* μη έγκυρο cookie → login */ });
}

// ---------------------------------------------------------------------------
// Εξαγωγή αποτελεσμάτων CSV (όλα τοπικά στον browser)
// ---------------------------------------------------------------------------
$('btn-csv').addEventListener('click', async () => {
  if (!currentPin) return;
  try {
    const data = await api(currentPin + '/results');
    const rows = [['Κατάταξη', 'Όνομα', 'Σύνολο Πόντων', 'Σωστές Απαντήσεις', 'Απαντήσεις']];
    for (const e of data.board) {
      const ans = data.answers[e.id] || [];
      rows.push([e.rank, e.name, e.score, ans.filter((a) => a.correct).length, ans.length]);
    }
    const csv = '\ufeff' + rows.map((r) => r.map((c) => '"' + String(c).replace(/"/g, '""') + '"').join(';')).join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'live-quiz-' + data.pin + '.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) {
    alert(err.message);
  }
});

// ---------------------------------------------------------------------------
// Αρχικοποίηση
// ---------------------------------------------------------------------------
if (window.LIVEQUIZ_LOGGED_IN) {
  showView('view-manage');
  loadQuizzes().catch((err) => setError('manage-error', err.message));
} else {
  showView('view-login');
}
