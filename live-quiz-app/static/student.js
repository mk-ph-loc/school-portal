/*
 * Ζωντανό Παιχνίδι Τάξης (Live Quiz) — λογική οθόνης μαθητή.
 * Vanilla JS + WebSocket· το χρονόμετρο βασίζεται στο deadline του server
 * (με αντιστάθμιση ρολογιού), ώστε όλοι οι μαθητές να συγχρονίζονται.
 */
'use strict';

const BASE = window.LIVEQUIZ_BASE;              // π.χ. /live-quiz/
const API = BASE + 'api/';
const $ = (id) => document.getElementById(id);
const STEPS = ['step-join', 'step-lobby', 'step-question', 'step-result', 'step-final'];
const STORE_KEY = 'schoolLiveQuiz.player';      // {pin, token, name} για επανασύνδεση

let ws = null;
let me = null;               // {pin, token, name, player_id}
let clockOffset = 0;         // server_now - client_now (ms)
let timerHandle = null;
let answeredChoice = null;   // η επιλογή μου στην τρέχουσα ερώτηση
let lastResult = null;       // τελευταίο προσωπικό αποτέλεσμα
let reconnectDelay = 1000;
let closedByUs = false;

function show(step) {
  STEPS.forEach((s) => { $(s).hidden = s !== step; });
  window.scrollTo({ top: 0 });
}

function setError(msg) {
  const el = $('join-error');
  el.textContent = msg || '';
  el.hidden = !msg;
}

function esc(text) {
  const div = document.createElement('div');
  div.textContent = String(text ?? '');
  return div.innerHTML;
}

function ordinal(n) { return n > 0 ? n + 'η' : '—'; }

// ---------------------------------------------------------------------------
// Είσοδος με PIN + όνομα (με αυτόματη επανασύνδεση από sessionStorage)
// ---------------------------------------------------------------------------
async function join(pin, name, token) {
  const res = await fetch(API + 'join', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin, name, token: token || null }),
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* κενό σώμα */ }
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : 'Σφάλμα σύνδεσης με τον διακομιστή.';
    throw new Error(detail);
  }
  return data;
}

function connectWS() {
  closedByUs = false;
  const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
  ws = new WebSocket(proto + location.host + BASE + 'ws/' + me.pin + '?token=' + encodeURIComponent(me.token));
  ws.onopen = () => {
    reconnectDelay = 1000;
    setConnBadge(true);
  };
  ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    handleMessage(msg);
  };
  ws.onclose = () => {
    setConnBadge(false);
    if (closedByUs) return;
    setTimeout(connectWS, reconnectDelay);          // αυτόματη επανασύνδεση
    reconnectDelay = Math.min(reconnectDelay * 2, 15000);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) { /* ήδη έκλεισε */ } };
}

function setConnBadge(ok) {
  const el = $('conn-badge');
  el.textContent = ok ? '● Συνδεδεμένος' : '● Επανασύνδεση…';
  el.className = 'mt-4 inline-block text-xs px-3 py-1.5 rounded-full ring-1 ' + (ok
    ? 'bg-emerald-100 text-emerald-700 ring-emerald-200'
    : 'bg-amber-100 text-amber-700 ring-amber-200');
}

// keepalive ώστε το nginx proxy_read_timeout να μην κόβει τη σύνδεση
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
}, 30000);

// ---------------------------------------------------------------------------
// Χειρισμός μηνυμάτων WebSocket
// ---------------------------------------------------------------------------
function handleMessage(msg) {
  switch (msg.type) {
    case 'lobby':
      stopTimer();
      $('lobby-name').textContent = me.name;
      show('step-lobby');
      break;
    case 'question':
      startQuestion(msg);
      break;
    case 'answer_ack':
      lastResult = msg;
      answeredChoice = msg.choice;
      lockButtons(msg.choice);
      $('wait-note').hidden = false;
      // Άμεση ανατροφοδότηση ορθότητας/πόντων/θέσης χωρίς αναμονή των άλλων
      showResult(msg);
      break;
    case 'result':
      lastResult = msg;
      if ($('step-question').hidden === false || $('step-result').hidden === false) {
        showResult(msg);
      }
      break;
    case 'reveal':
    case 'leaderboard':
      stopTimer();
      if (lastResult && lastResult.q_index === msg.q_index) showResult(lastResult);
      else showResult({ correct: false, points: 0, answered: false,
                        score: lastResult ? lastResult.score : 0,
                        rank: lastResult ? lastResult.rank : 0 });
      break;
    case 'finished':
      stopTimer();
      showFinal(msg);
      break;
    case 'error':
      // π.χ. «Ο χρόνος έληξε» — εμφάνιση στην οθόνη αναμονής/ερώτησης
      $('wait-note').textContent = '⚠ ' + msg.message;
      $('wait-note').hidden = false;
      break;
    case 'progress':
    case 'pong':
      break;
  }
}

// ---------------------------------------------------------------------------
// Ερώτηση & αντίστροφη μέτρηση (συγχρονισμένη με τον server)
// ---------------------------------------------------------------------------
function startQuestion(msg) {
  clockOffset = (msg.server_now * 1000) - Date.now();
  answeredChoice = null;
  lastResult = null;
  $('q-progress').textContent = 'Ερώτηση ' + (msg.q_index + 1) + '/' + msg.total;
  $('q-text').textContent = msg.text;
  $('wait-note').textContent = '✓ Η απάντησή σου καταχωρήθηκε — περίμενε τα αποτελέσματα…';
  $('wait-note').hidden = true;
  const buttons = document.querySelectorAll('#answer-grid .ans-btn');
  buttons.forEach((btn, i) => {
    btn.disabled = false;
    btn.classList.remove('ring-4', 'ring-white');
    btn.querySelector('.ans-label').textContent = msg.options[i];
  });
  show('step-question');
  runTimer(msg.deadline);
}

function runTimer(deadlineEpoch) {
  stopTimer();
  const tick = () => {
    const remainMs = deadlineEpoch * 1000 - (Date.now() + clockOffset);
    const secs = Math.max(0, Math.ceil(remainMs / 1000));
    const el = $('q-timer');
    el.textContent = secs;
    el.classList.toggle('timer-low', secs <= 5);
    el.classList.toggle('text-red-600', secs <= 5);
    if (secs <= 0) {
      stopTimer();
      lockButtons(answeredChoice);
      if (answeredChoice === null) {
        $('wait-note').textContent = '⏰ Ο χρόνος τελείωσε — δεν πρόλαβες να απαντήσεις.';
        $('wait-note').hidden = false;
      }
    }
  };
  tick();
  timerHandle = setInterval(tick, 250);
}

function stopTimer() {
  if (timerHandle) { clearInterval(timerHandle); timerHandle = null; }
}

function lockButtons(chosen) {
  document.querySelectorAll('#answer-grid .ans-btn').forEach((btn) => {
    btn.disabled = true;
    if (chosen !== null && Number(btn.dataset.choice) === chosen) {
      btn.classList.add('ring-4', 'ring-white');
    }
  });
}

document.querySelectorAll('#answer-grid .ans-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    if (answeredChoice !== null || !ws || ws.readyState !== WebSocket.OPEN) return;
    answeredChoice = Number(btn.dataset.choice);   // αισιόδοξο κλείδωμα
    lockButtons(answeredChoice);
    ws.send(JSON.stringify({ type: 'answer', choice: answeredChoice }));
  });
});

// ---------------------------------------------------------------------------
// Προσωπικό αποτέλεσμα & τελική κατάταξη
// ---------------------------------------------------------------------------
function showResult(msg) {
  const card = $('result-card');
  const noAnswer = msg.answered === false && !msg.points;
  if (msg.correct) {
    card.className = 'pop-in rounded-2xl p-8 text-white shadow-lg bg-emerald-600';
    $('result-icon').textContent = '✅';
    $('result-title').textContent = 'Σωστά!';
  } else if (noAnswer) {
    card.className = 'pop-in rounded-2xl p-8 text-white shadow-lg bg-slate-500';
    $('result-icon').textContent = '⏰';
    $('result-title').textContent = 'Δεν απάντησες';
  } else {
    card.className = 'pop-in rounded-2xl p-8 text-white shadow-lg bg-red-600';
    $('result-icon').textContent = '❌';
    $('result-title').textContent = 'Λάθος…';
  }
  $('result-points').textContent = '+' + (msg.points || 0);
  $('result-score').textContent = msg.score ?? 0;
  $('result-rank').textContent = ordinal(msg.rank || 0);
  show('step-result');
}

function showFinal(msg) {
  const mine = (msg.final || []).find((e) => e.name === me.name);
  $('final-rank').textContent = mine ? ordinal(mine.rank) : '—';
  $('final-score').textContent = mine ? mine.score : (lastResult ? lastResult.score : 0);
  const medals = ['🥇', '🥈', '🥉', '4.', '5.'];
  $('final-top').innerHTML = (msg.top5 || []).map((e, i) =>
    '<div class="flex items-center justify-between rounded-lg px-3 py-2 text-sm ' +
    (mine && e.name === me.name ? 'bg-fuchsia-100 ring-1 ring-fuchsia-300 font-bold' : 'bg-slate-50') + '">' +
    '<span>' + medals[i] + ' ' + esc(e.name) + '</span>' +
    '<span class="tabular-nums font-semibold">' + e.score + '</span></div>'
  ).join('');
  sessionStorage.removeItem(STORE_KEY);
  show('step-final');
}

$('btn-again').addEventListener('click', () => {
  closedByUs = true;
  try { ws && ws.close(); } catch (e) { /* ήδη έκλεισε */ }
  me = null; lastResult = null; answeredChoice = null;
  $('inp-pin').value = '';
  $('inp-name').value = '';
  setError('');
  show('step-join');
});

// ---------------------------------------------------------------------------
// Φόρμα εισόδου & αυτόματη επανασύνδεση
// ---------------------------------------------------------------------------
$('join-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  setError('');
  const pin = $('inp-pin').value.trim();
  const name = $('inp-name').value.trim();
  if (!/^\d{4}$/.test(pin)) { setError('Το PIN πρέπει να έχει ακριβώς 4 ψηφία.'); return; }
  if (!name) { setError('Γράψε το όνομά σου.'); return; }
  $('btn-join').disabled = true;
  try {
    const data = await join(pin, name, null);
    me = { pin, token: data.token, name: data.name, player_id: data.player_id };
    sessionStorage.setItem(STORE_KEY, JSON.stringify(me));
    connectWS();
    $('lobby-name').textContent = me.name;
    show('step-lobby');
  } catch (err) {
    setError(err.message);
  } finally {
    $('btn-join').disabled = false;
  }
});

(async function resume() {
  let saved = null;
  try { saved = JSON.parse(sessionStorage.getItem(STORE_KEY)); } catch (e) { /* ignore */ }
  if (!saved || !saved.pin || !saved.token) return;
  try {
    const data = await join(saved.pin, saved.name, saved.token);
    me = { pin: saved.pin, token: data.token, name: data.name, player_id: data.player_id };
    sessionStorage.setItem(STORE_KEY, JSON.stringify(me));
    connectWS();
    $('lobby-name').textContent = me.name;
    show('step-lobby');
  } catch (err) {
    sessionStorage.removeItem(STORE_KEY);   // το παιχνίδι τελείωσε/έληξε → νέα είσοδος
  }
})();
