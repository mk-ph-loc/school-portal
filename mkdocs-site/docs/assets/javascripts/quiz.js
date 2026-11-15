/*
 * quiz.js — Διαδραστικό κουίζ αυτοαξιολόγησης
 *
 * Δήλωση κουίζ σε Markdown με md_in_html:
 * <div class="quiz" data-quiz='[{"q":"Ερώτηση;","options":["Α","Β"],"answer":1,"explain":"..."}]'></div>
 */
(function () {
  'use strict';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function buildQuiz(host) {
    if (host.getAttribute('data-quiz-ready') === '1') return;
    var data;
    try {
      data = JSON.parse(host.getAttribute('data-quiz') || '[]');
    } catch (e) {
      host.appendChild(el('p', 'quiz-error', '⚠️ Μη έγκυρα δεδομένα κουίζ.'));
      return;
    }
    if (!Array.isArray(data) || data.length === 0) return;
    host.setAttribute('data-quiz-ready', '1');
    host.classList.add('quiz-box');

    var state = { i: 0, score: 0, answered: false };

    var head = el('div', 'quiz-head');
    var progress = el('span', 'quiz-progress');
    var scoreEl = el('span', 'quiz-score');
    head.appendChild(progress);
    head.appendChild(scoreEl);

    var qText = el('h4', 'quiz-question');
    var opts = el('div', 'quiz-options');
    var feedback = el('div', 'quiz-feedback');
    var actions = el('div', 'quiz-actions');
    var nextBtn = el('button', 'quiz-btn', 'Επόμενη →');
    nextBtn.type = 'button';
    nextBtn.disabled = true;
    actions.appendChild(nextBtn);

    host.appendChild(head);
    host.appendChild(qText);
    host.appendChild(opts);
    host.appendChild(feedback);
    host.appendChild(actions);

    function render() {
      var item = data[state.i];
      state.answered = false;
      progress.textContent = 'Ερώτηση ' + (state.i + 1) + ' / ' + data.length;
      scoreEl.textContent = 'Σκορ: ' + state.score;
      qText.textContent = item.q;
      opts.innerHTML = '';
      feedback.textContent = '';
      feedback.className = 'quiz-feedback';
      nextBtn.disabled = true;
      nextBtn.textContent = (state.i === data.length - 1) ? 'Ολοκλήρωση ✓' : 'Επόμενη →';

      item.options.forEach(function (opt, idx) {
        var b = el('button', 'quiz-option', opt);
        b.type = 'button';
        b.addEventListener('click', function () {
          if (state.answered) return;
          state.answered = true;
          var correct = idx === item.answer;
          if (correct) {
            state.score++;
            b.classList.add('is-correct');
            feedback.textContent = '✅ Σωστά! ' + (item.explain || '');
            feedback.className = 'quiz-feedback is-ok';
          } else {
            b.classList.add('is-wrong');
            var right = opts.children[item.answer];
            if (right) right.classList.add('is-correct');
            feedback.textContent = '❌ Λάθος. ' + (item.explain || '');
            feedback.className = 'quiz-feedback is-err';
          }
          Array.prototype.forEach.call(opts.children, function (c) { c.disabled = true; });
          scoreEl.textContent = 'Σκορ: ' + state.score;
          nextBtn.disabled = false;
        });
        opts.appendChild(b);
      });
    }

    function finish() {
      var pct = Math.round((state.score / data.length) * 100);
      var msg = pct >= 80 ? '🏆 Εξαιρετικά!' : pct >= 50 ? '👍 Καλή προσπάθεια!' : '📖 Χρειάζεται επανάληψη.';
      host.innerHTML = '';
      var res = el('div', 'quiz-result');
      res.appendChild(el('div', 'quiz-result__emoji', pct >= 80 ? '🏆' : pct >= 50 ? '👍' : '📖'));
      res.appendChild(el('h4', 'quiz-result__title', 'Αποτέλεσμα: ' + state.score + ' / ' + data.length + ' (' + pct + '%)'));
      res.appendChild(el('p', 'quiz-result__msg', msg));
      var again = el('button', 'quiz-btn', '↻ Ξανά από την αρχή');
      again.type = 'button';
      again.addEventListener('click', function () {
        host.removeAttribute('data-quiz-ready');
        host.innerHTML = '';
        buildQuiz(host);
      });
      res.appendChild(again);
      host.appendChild(res);
    }

    nextBtn.addEventListener('click', function () {
      if (state.i === data.length - 1) { finish(); }
      else { state.i++; render(); }
    });

    render();
  }

  function apply() {
    document.querySelectorAll('.quiz[data-quiz]').forEach(buildQuiz);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(apply);
  }
})();