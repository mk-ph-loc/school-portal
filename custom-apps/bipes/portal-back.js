/* portal-back.js — Ψηφιακή Πύλη Σχολείου: κουμπί επιστροφής «← Portal» για το BIPES.
 * Self-contained (χωρίς εξαρτήσεις), ίδιο μοτίβο με τα υπόλοιπα custom apps ΑΛΛΑ
 * τοποθετείται ΠΑΝΩ-ΔΕΞΙΑ μέσα στο top-menu (δίπλα στα εικονίδια account/forum),
 * ΟΧΙ bottom-left: εκεί εμφανίζονται οι ειδοποιήσεις (notify) & το zoom του Blockly.
 * z-index κάτω από τα modals του BIPES (z-index 1000000) ώστε να μην παρεμβάλλεται. */
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
      'position:fixed', 'right:8px', 'top:6px', 'z-index:99000',
      'display:inline-block', 'padding:6px 12px', 'border-radius:9999px',
      'background:#1e293b', 'color:#fff', 'font:600 12px/1.2 system-ui,sans-serif',
      'text-decoration:none', 'box-shadow:0 2px 8px rgba(0,0,0,.35)',
      'opacity:.75', 'transition:opacity .15s ease'
    ].join(';'));
    a.addEventListener('mouseenter', function () { a.style.opacity = '1'; });
    a.addEventListener('mouseleave', function () { a.style.opacity = '.75'; });
    document.body.appendChild(a);
    /* Μετατόπιση των δεξιών κουμπιών του top-menu αριστερά ώστε το pill να
     * κάθεται ΔΙΠΛΑ τους χωρίς να καλύπτει τα εικονίδια account/forum. */
    var style = document.createElement('style');
    style.textContent = '.top-menu{padding-right:92px !important;box-sizing:border-box;}';
    document.head.appendChild(style);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();