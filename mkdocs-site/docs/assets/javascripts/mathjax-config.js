/*
 * mathjax-config.js — Μαθηματικά LaTeX σε όλες τις σελίδες (MathJax 3, ΤΟΠΙΚΑ).
 *
 * Το pymdownx.arithmatex (generic) τυλίγει τα $…$ / $$…$$ σε
 * <span class="arithmatex">\(…\)</span>. Εδώ φορτώνουμε το τοπικό
 * /docs/assets/vendor/mathjax/tex-svg-full.js ΜΟΝΟ όταν η σελίδα έχει
 * μαθηματικά (lazy — μηδενική επιβάρυνση στις υπόλοιπες σελίδες).
 */
(function () {
  'use strict';

  var VENDOR = '/docs/assets/vendor/mathjax/tex-svg-full.js';
  var loading = false;

  function hasMath() {
    return !!document.querySelector('.arithmatex');
  }

  function load() {
    if (!hasMath()) return;
    if (window.MathJax && window.MathJax.typesetPromise) {
      // Ήδη φορτωμένο (instant navigation) → απλό re-typeset.
      window.MathJax.typesetPromise().catch(function () {});
      return;
    }
    if (loading) return;
    loading = true;
    window.MathJax = {
      tex: {
        inlineMath: [['\\(', '\\)']],
        displayMath: [['\\[', '\\]']],
        processEscapes: true,
        processEnvironments: true,
        tags: 'ams'
      },
      options: {
        ignoreHtmlClass: '.*|',
        processHtmlClass: 'arithmatex'
      },
      svg: { fontCache: 'global' },
      startup: {
        typeset: true,
        ready: function () {
          window.MathJax.startup.defaultReady();
        }
      }
    };
    var s = document.createElement('script');
    s.src = VENDOR;
    s.async = true;
    s.onerror = function () { loading = false; };
    document.head.appendChild(s);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(load);
  }
})();