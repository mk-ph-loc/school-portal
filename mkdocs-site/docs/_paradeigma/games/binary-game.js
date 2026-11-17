/* Παιχνίδι Δυαδικού Συστήματος — Ψηφιακή Πύλη Σχολείου & Εργαστηρίου */
(function () {
  'use strict';

  var state = {
    mode: 'b2d',      // b2d | d2b | bits
    score: 0, level: 1, streak: 0, correct: 0, total: 0,
    target: 0, bits: 4, bitState: []
  };

  var $ = function (id) { return document.getElementById(id); };

  function maxForLevel() {
    state.bits = Math.min(8, 4 + Math.floor((state.level - 1) / 2));
    return Math.pow(2, state.bits) - 1;
  }
  function randTarget() { return Math.floor(Math.random() * (maxForLevel() + 1)); }
  function toBinary(n, width) {
    var s = n.toString(2);
    while (s.length < width) s = '0' + s;
    return s;
  }
  function updateStats() {
    $('score').textContent = state.score;
    $('level').textContent = state.level;
    $('streak').textContent = state.streak;
    $('correct').textContent = state.correct + '/' + state.total;
    var pct = state.total ? Math.round((state.correct / state.total) * 100) : 0;
    $('progressBar').style.width = pct + '%';
  }
  function showFeedback(msg, ok) {
    var f = $('feedback');
    f.textContent = msg;
    f.className = 'feedback show ' + (ok ? 'ok' : 'err');
  }
  function hideFeedback() { $('feedback').className = 'feedback'; }

  /* ---------- Λειτουργία: Άναψε τα Bits ---------- */
  function renderBits() {
    var area = $('bitsArea');
    area.innerHTML = '';
    state.bitState = new Array(state.bits).fill(0);
    for (var i = 0; i < state.bits; i++) {
      (function (idx) {
        var weight = Math.pow(2, state.bits - 1 - idx);
        var b = document.createElement('div');
        b.className = 'bit';
        b.innerHTML = '<span class="val">0</span><span class="weight">' + weight + '</span>';
        b.addEventListener('click', function () {
          state.bitState[idx] = state.bitState[idx] ? 0 : 1;
          b.classList.toggle('on', !!state.bitState[idx]);
          b.querySelector('.val').textContent = state.bitState[idx];
          updateSum();
        });
        area.appendChild(b);
      })(i);
    }
    updateSum();
  }
  function currentBitValue() {
    var v = 0;
    for (var i = 0; i < state.bitState.length; i++) v = v * 2 + state.bitState[i];
    return v;
  }
  function updateSum() {
    var parts = [];
    for (var i = 0; i < state.bitState.length; i++) {
      if (state.bitState[i]) parts.push(Math.pow(2, state.bits - 1 - i));
    }
    $('sumLine').textContent = (parts.length ? parts.join(' + ') + ' = ' : '') + currentBitValue();
  }
  /* ---------- Γύρος ---------- */
  function newRound() {
    hideFeedback();
    state.target = randTarget();
    $('answer').value = '';

    var bitsMode = state.mode === 'bits';
    $('bitsArea').style.display = bitsMode ? 'flex' : 'none';
    $('sumLine').style.display = bitsMode ? 'block' : 'none';
    $('answerRow').style.display = bitsMode ? 'none' : 'flex';
    $('bitsCheckBtn').style.display = bitsMode ? 'block' : 'none';

    if (state.mode === 'b2d') {
      $('question').textContent = 'Μετέτρεψε τον δυαδικό αριθμό σε δεκαδικό:';
      $('target').textContent = toBinary(state.target, state.bits) + '₂';
      $('hint').textContent = 'Συμβουλή: πολλαπλασίασε κάθε ψηφίο με τη δύναμη του 2 (…8, 4, 2, 1) και άθροισε.';
      $('answer').focus();
    } else if (state.mode === 'd2b') {
      $('question').textContent = 'Μετέτρεψε τον δεκαδικό αριθμό σε δυαδικό:';
      $('target').textContent = state.target + '₁₀';
      $('hint').textContent = 'Συμβουλή: διαίρεσε συνεχώς με το 2 και κράτα τα υπόλοιπα από κάτω προς τα πάνω. Γράψε μόνο 0 και 1.';
      $('answer').focus();
    } else {
      $('question').textContent = 'Άναψε τα κατάλληλα bits ώστε να φτιάξεις τον αριθμό:';
      $('target').textContent = state.target + '₁₀';
      renderBits();
      $('hint').textContent = 'Πάτησε τα τετράγωνα για να αλλάξεις 0 ↔ 1. Κάθε θέση έχει το βάρος της. Πάτησε «Έλεγχος Bits» ή Enter.';
    }
    updateStats();
  }

  function judge(ok, expectedText) {
    state.total++;
    if (ok) {
      state.correct++;
      state.streak++;
      var bonus = state.streak >= 3 ? 5 : 0;
      var points = 10 * state.level + bonus;
      state.score += points;
      showFeedback('✅ Σωστά! +' + points + ' πόντοι' + (bonus ? ' (μπόνους σερί 🔥)' : ''), true);
      if (state.correct % 5 === 0) {
        state.level++;
        setTimeout(function () {
          showFeedback('🎉 Ανέβηκες στο επίπεδο ' + state.level + '!', true);
        }, 900);
      }
    } else {
      state.streak = 0;
      showFeedback('❌ Λάθος. Η σωστή απάντηση είναι: ' + expectedText, false);
    }
    updateStats();
    setTimeout(newRound, ok ? 1300 : 2600);
  }

  function checkAnswer() {
    var raw = $('answer').value.trim().replace(/\s+/g, '');
    if (raw === '') { showFeedback('⚠️ Γράψε μια απάντηση πρώτα.', false); return; }
    if (state.mode === 'b2d') {
      if (!/^\d+$/.test(raw)) { showFeedback('⚠️ Γράψε έναν δεκαδικό αριθμό (μόνο ψηφία).', false); return; }
      judge(parseInt(raw, 10) === state.target, String(state.target));
    } else {
      if (!/^[01]+$/.test(raw)) { showFeedback('⚠️ Γράψε μόνο 0 και 1.', false); return; }
      judge(parseInt(raw, 2) === state.target, toBinary(state.target, state.bits));
    }
  }

  function checkBits() {
    judge(currentBitValue() === state.target, toBinary(state.target, state.bits));
  }

  /* ---------- Events ---------- */
  document.querySelectorAll('.mode-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.mode-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      state.mode = btn.getAttribute('data-mode');
      newRound();
    });
  });

  // Κουμπί ελέγχου για τη λειτουργία bits
  var bitsCheck = document.createElement('button');
  bitsCheck.className = 'primary';
  bitsCheck.id = 'bitsCheckBtn';
  bitsCheck.textContent = 'Έλεγχος Bits';
  bitsCheck.style.margin = '.8rem auto 0';
  bitsCheck.style.display = 'none';
  bitsCheck.addEventListener('click', checkBits);
  $('answerRow').parentNode.insertBefore(bitsCheck, $('feedback'));

  $('checkBtn').addEventListener('click', checkAnswer);
  $('answer').addEventListener('keydown', function (e) { if (e.key === 'Enter') checkAnswer(); });
  $('skipBtn').addEventListener('click', function () {
    state.total++;
    state.streak = 0;
    var exp = state.mode === 'b2d' ? String(state.target) : toBinary(state.target, state.bits);
    showFeedback('⏭️ Η σωστή απάντηση ήταν: ' + exp, false);
    updateStats();
    setTimeout(newRound, 1800);
  });
  document.addEventListener('keydown', function (e) {
    if (state.mode === 'bits' && e.key === 'Enter') checkBits();
  });

  newRound();
})();