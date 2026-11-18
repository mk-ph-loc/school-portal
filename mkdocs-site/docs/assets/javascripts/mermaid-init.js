/*
 * mermaid-init.js — Διαγράμματα Mermaid (flowcharts, sequence, class, ER…).
 *
 * ΣΗΜΑΝΤΙΚΟ: Το Material for MkDocs έχει ΕΝΣΩΜΑΤΩΜΕΝΟ mermaid handler που
 * φορτώνει τη βιβλιοθήκη από το unpkg.com (CDN!) και αντικαθιστά τα
 * <pre class="mermaid"> με <div class="mermaid"> + closed shadow root.
 * Σε offline LAN αυτό αποτυγχάνει σιωπηλά.
 *
 * Εδώ «κερδίζουμε τον αγώνα δρόμου»: μόλις εμφανιστεί pre.mermaid, το
 * μετονομάζουμε ΑΜΕΣΑ σε pre.mmd-local (ώστε να μην το πιάσει το Material),
 * φορτώνουμε τη βιβλιοθήκη ΤΟΠΙΚΑ από /docs/assets/vendor/mermaid/ και
 * κάνουμε render με theme συγχρονισμένο στο light/dark. Έτσι δουλεύει
 * 100% offline και χωρίς εξαρτήσεις από CDN.
 */
(function () {
  'use strict';

  var VENDOR = '/docs/assets/vendor/mermaid/mermaid.min.js';
  var loading = false;
  var seq = 0;

  /** Μετονομασία πριν προλάβει ο handler του Material (MutationObserver). */
  function claim(root) {
    (root.querySelectorAll ? root : document).querySelectorAll('pre.mermaid').forEach(function (pre) {
      pre.className = 'mmd-local';
      var code = pre.querySelector('code');
      if (code) pre.textContent = code.textContent;
      pre.setAttribute('data-src', pre.textContent);
    });
  }

  function blocks() {
    return Array.prototype.slice.call(document.querySelectorAll('pre.mmd-local:not([data-processed])'));
  }

  function isDark() {
    return document.body.getAttribute('data-md-color-scheme') === 'slate';
  }

  function renderAll() {
    var list = blocks();
    if (!list.length) return;
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: isDark() ? 'dark' : 'default',
      fontFamily: 'inherit'
    });
    list.forEach(function (pre) {
      var src = pre.getAttribute('data-src') || pre.textContent;
      var id = 'mmd-' + (++seq);
      window.mermaid.render(id, src).then(function (out) {
        pre.innerHTML = out.svg;
        pre.setAttribute('data-processed', 'true');
      }).catch(function (err) {
        pre.innerHTML = '';
        var box = document.createElement('div');
        box.className = 'admonition warning';
        var t = document.createElement('p');
        t.className = 'admonition-title';
        t.textContent = 'Σφάλμα διαγράμματος Mermaid';
        var msg = document.createElement('pre');
        msg.textContent = String(err && err.message || err) + '\n\n' + src;
        box.appendChild(t);
        box.appendChild(msg);
        pre.appendChild(box);
        pre.setAttribute('data-processed', 'error');
      });
    });
  }

  function apply() {
    claim(document);
    if (!blocks().length) return;
    if (window.mermaid && window.mermaid.render) { renderAll(); return; }
    if (loading) return;
    loading = true;
    var s = document.createElement('script');
    s.src = VENDOR;
    s.onload = renderAll;
    s.onerror = function () { loading = false; };
    document.head.appendChild(s);
  }

  // 1. Παρακολούθηση DOM: «αρπάζουμε» τα pre.mermaid τη στιγμή που μπαίνουν
  //    (πριν ο observer του Material τα κάνει div+shadow με CDN mermaid).
  var domObs = new MutationObserver(function (muts) {
    var found = false;
    muts.forEach(function (m) {
      m.addedNodes && m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if ((n.matches && n.matches('pre.mermaid')) ||
            (n.querySelector && n.querySelector('pre.mermaid'))) found = true;
      });
    });
    if (found) apply();
  });

  // 2. Αλλαγή light/dark → επανα-render των διαγραμμάτων.
  var themeObs = new MutationObserver(function (muts) {
    muts.forEach(function (m) {
      if (m.attributeName === 'data-md-color-scheme' && window.mermaid) {
        document.querySelectorAll('pre.mmd-local[data-processed]').forEach(function (pre) {
          pre.removeAttribute('data-processed');
          pre.textContent = pre.getAttribute('data-src') || pre.textContent;
        });
        renderAll();
      }
    });
  });

  function start() {
    domObs.observe(document.documentElement, { childList: true, subtree: true });
    if (document.body) {
      themeObs.observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
    } else {
      document.addEventListener('DOMContentLoaded', function () {
        themeObs.observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
      });
    }
    apply();
  }

  // Τρέχουμε όσο το δυνατόν νωρίτερα (το script φορτώνεται στο <head> defer,
  // πριν εκτελεστεί το bundle του Material).
  start();
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(apply);
  }
})();