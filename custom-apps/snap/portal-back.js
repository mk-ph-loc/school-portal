/* portal-back.js — Ψηφιακή Πύλη Σχολείου: κουμπί επιστροφής «← Portal» για το Snap!.
 * Self-contained (χωρίς εξαρτήσεις), ίδιο μοτίβο με τα υπόλοιπα custom apps ΑΛΛΑ
 * τοποθετείται ΚΑΤΩ-ΔΕΞΙΑ: κάτω-αριστερά βρίσκεται το stage του Snap! που δεν
 * πρέπει να καλυφθεί. Το Snap! ζωγραφίζει τα πάντα σε canvas#world — το pill
 * είναι DOM στοιχείο πάνω από το canvas (z-index max), ημιδιαφανές → hover. */
(function () {
  'use strict';
  function inject() {
    if (!document.body || document.getElementById('portal-back-pill')) return;
    var a = document.createElement('a');
    a.id = 'portal-back-pill';
    a.href = '/';
    a.textContent = '\u2190 Portal';
    a.title = 'Επιστροφή στην Ψηφιακή Πύλη';
    a.setAttribute('style', [
      'position:fixed', 'right:12px', 'bottom:12px', 'z-index:2147483647',
      'display:inline-block', 'padding:7px 14px', 'border-radius:9999px',
      'background:#1e293b', 'color:#fff', 'font:600 13px/1.2 system-ui,sans-serif',
      'text-decoration:none', 'box-shadow:0 2px 8px rgba(0,0,0,.35)',
      'opacity:.55', 'transition:opacity .15s ease'
    ].join(';'));
    a.addEventListener('mouseenter', function () { a.style.opacity = '1'; });
    a.addEventListener('mouseleave', function () { a.style.opacity = '.55'; });
    document.body.appendChild(a);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
