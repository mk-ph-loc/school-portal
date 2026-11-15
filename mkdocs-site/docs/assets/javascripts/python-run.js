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
    var pre = code.closest('pre');
    if (!pre) return;
    var container = pre.parentElement;
    if (!container || container.getAttribute('data-py-ready') === '1') return;
    // Αγνόησε μπλοκ μέσα σε highlight wrapper που ήδη έχει κουμπί αντιγραφής
    container.setAttribute('data-py-ready', '1');

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

  function apply() {
    document.querySelectorAll('code.language-python, code.lang-python, .highlight-python code')
      .forEach(decorate);
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