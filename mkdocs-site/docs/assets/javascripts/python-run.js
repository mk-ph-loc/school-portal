/*
 * python-run.js — Εκτέλεση Python στον browser με Pyodide (τοπικά αρχεία)
 *
 * Σε κάθε μπλοκ ```python προστίθεται κουμπί «▶ Εκτέλεση». Το Pyodide
 * φορτώνεται ΤΟΠΙΚΑ από /docs/assets/pyodide/ και ΜΟΝΟ όταν ο μαθητής
 * πατήσει εκτέλεση (lazy load) — μηδενική επιβάρυνση στον server.
 */
(function () {
  'use strict';

  var PYODIDE_URL = '/docs/assets/pyodide/';
  var pyodidePromise = null;
  var statusBar = null;

  function ensureStatus() {
    if (statusBar) return statusBar;
    statusBar = document.createElement('div');
    statusBar.className = 'py-status';
    statusBar.setAttribute('role', 'status');
    document.body.appendChild(statusBar);
    return statusBar;
  }

  function showStatus(msg, kind) {
    var el = ensureStatus();
    el.textContent = msg;
    el.className = 'py-status py-status--' + (kind || 'info') + ' is-visible';
    if (kind === 'ok' || kind === 'err') {
      setTimeout(function () { el.classList.remove('is-visible'); }, 4000);
    }
  }

  /** Φορτώνει το Pyodide μία φορά (lazy). */
  function loadPyodideOnce() {
    if (pyodidePromise) return pyodidePromise;
    pyodidePromise = new Promise(function (resolve, reject) {
      showStatus('⏳ Φόρτωση Python στον browser… (μία φορά ανά συνεδρία)', 'info');
      var s = document.createElement('script');
      s.src = PYODIDE_URL + 'pyodide.js';
      s.onload = function () {
        if (typeof loadPyodide !== 'function') {
          reject(new Error('Το Pyodide δεν φορτώθηκε σωστά.'));
          return;
        }
        window.loadPyodide({ indexURL: PYODIDE_URL })
          .then(function (py) {
            showStatus('✅ Η Python είναι έτοιμη!', 'ok');
            resolve(py);
          })
          .catch(reject);
      };
      s.onerror = function () {
        reject(new Error('Αδυναμία φόρτωσης αρχείων Pyodide από ' + PYODIDE_URL));
      };
      document.head.appendChild(s);
    }).catch(function (err) {
      pyodidePromise = null; // επιτρέπει νέα προσπάθεια
      throw err;
    });
    return pyodidePromise;
  }

  /** Εκτελεί κώδικα και συλλέγει stdout/stderr. */
  function runCode(code, outputEl, btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Εκτέλεση…';
    outputEl.className = 'py-output is-visible';
    outputEl.textContent = '';

    loadPyodideOnce().then(function (py) {
      var buffer = '';
      py.setStdout({ batched: function (s) { buffer += s + '\n'; } });
      py.setStderr({ batched: function (s) { buffer += s + '\n'; } });

      // Υποστήριξη input(): ρωτά τον μαθητή με prompt
      py.globals.set('__js_input__', function (promptText) {
        var answer = window.prompt(promptText || 'Εισαγωγή τιμής:');
        return answer === null ? '' : answer;
      });
      var prelude =
        "import builtins\n" +
        "def __input__(p=''):\n" +
        "    return __js_input__(str(p))\n" +
        "builtins.input = __input__\n";

      return py.runPythonAsync(prelude).then(function () {
        return py.runPythonAsync(code);
      }).then(function (result) {
        if (result !== undefined && result !== null && String(result) !== 'None') {
          buffer += String(result) + '\n';
        }
        outputEl.textContent = buffer.trim() === '' ? '(χωρίς έξοδο)' : buffer;
        outputEl.classList.add('py-output--ok');
      }).catch(function (err) {
        outputEl.textContent = (buffer ? buffer + '\n' : '') + '❌ Σφάλμα:\n' + (err.message || err);
        outputEl.classList.add('py-output--err');
      });
    }).catch(function (err) {
      outputEl.textContent = '❌ ' + (err.message || err);
      outputEl.classList.add('py-output--err');
      showStatus('❌ Αποτυχία φόρτωσης Python', 'err');
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = '▶ Εκτέλεση';
    });
  }

  function decorate(code) {
    // Idempotency: το marker μπαίνει στο ΙΔΙΟ το <code>, γιατί αυτό δεν
    // μετακινείται ποτέ. Αν το βάζαμε στον γονέα, η δεύτερη κλήση της apply()
    // (DOMContentLoaded + document$.subscribe του Material) θα έβλεπε νέο
    // γονέα (.py-runner) χωρίς marker και θα δημιουργούσε ΔΙΠΛΑ κουμπιά.
    if (code.getAttribute('data-py-ready') === '1') return;

    var pre = code.closest('pre');
    if (!pre) return;
    var container = pre.parentElement;
    if (!container) return;

    // Διπλή προστασία: αν υπάρχει ήδη runner/toolbar για αυτό το pre, έξοδος.
    if (pre.closest('.py-runner')) {
      code.setAttribute('data-py-ready', '1');
      return;
    }

    code.setAttribute('data-py-ready', '1');

    var wrap = document.createElement('div');
    wrap.className = 'py-runner';
    container.insertBefore(wrap, pre);
    wrap.appendChild(pre);

    var bar = document.createElement('div');
    bar.className = 'py-toolbar';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'py-run-btn';
    btn.textContent = '▶ Εκτέλεση';

    var hint = document.createElement('span');
    hint.className = 'py-hint';
    hint.textContent = 'Python στον browser — χωρίς εγκατάσταση';

    bar.appendChild(btn);
    bar.appendChild(hint);
    wrap.insertBefore(bar, pre);

    var out = document.createElement('pre');
    out.className = 'py-output';
    wrap.appendChild(out);

    btn.addEventListener('click', function () {
      out.classList.remove('py-output--ok', 'py-output--err');
      runCode(code.textContent, out, btn);
    });
  }

  /**
   * Εντοπίζει όλα τα μπλοκ Python.
   *
   * ΣΗΜΑΝΤΙΚΟ: Το Pygments/pymdownx βάζει την κλάση γλώσσας στο ΠΕΡΙΒΛΗΜΑ
   * (<div class="language-python highlight"><pre><code>…), ΟΧΙ στο <code>.
   * Γι' αυτό ψάχνουμε πρώτα τα wrappers και μετά τα code elements.
   */
  function findPythonCodes() {
    var found = [];
    var seen = new Set();

    function add(code) {
      if (code && !seen.has(code)) { seen.add(code); found.push(code); }
    }

    // 1. Κλασική μορφή Material/Pygments: div.language-python.highlight > pre > code
    document.querySelectorAll(
      'div.language-python > pre > code, div.language-py > pre > code,' +
      'div.highlight-python > pre > code, div.highlight-py > pre > code,' +
      '.language-python.highlight > pre > code, .language-py.highlight > pre > code'
    ).forEach(add);

    // 2. Μορφή με κλάση απευθείας στο code ή στο pre
    document.querySelectorAll(
      'code.language-python, code.lang-python, code.language-py,' +
      'pre.language-python > code, pre.python > code'
    ).forEach(add);

    // 3. Fallback: οποιοδήποτε highlight wrapper που δηλώνει python στη data-* ή class
    document.querySelectorAll('div[class*="highlight"]').forEach(function (div) {
      if (/(^|\s)(language|highlight)-(python|py)(\s|$)/.test(div.className)) {
        var c = div.querySelector('pre > code');
        add(c);
      }
    });

    return found;
  }

  function apply() {
    findPythonCodes().forEach(decorate);
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