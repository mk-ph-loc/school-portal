/* portal-back.js — Ψηφιακή Πύλη Σχολείου: κουμπί επιστροφής «← Portal» για το TurboWarp.
 * Self-contained (χωρίς εξαρτήσεις), ίδιο μοτίβο με τα υπόλοιπα custom apps ΑΛΛΑ
 * τοποθετείται ΠΑΝΩ-ΑΡΙΣΤΕΡΑ μέσα στο menu bar (δίπλα στο logo), ΟΧΙ bottom-left:
 * εκεί βρίσκεται το backpack area & τα stage controls που δεν πρέπει να καλυφθούν.
 * z-index κάτω από τα modals του GUI (z-index 5000+) ώστε να μην παρεμβάλλεται. */
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
      'position:fixed', 'left:8px', 'top:6px', 'z-index:4900',
      'display:inline-block', 'padding:6px 12px', 'border-radius:9999px',
      'background:#1e293b', 'color:#fff', 'font:600 12px/1.2 system-ui,sans-serif',
      'text-decoration:none', 'box-shadow:0 2px 8px rgba(0,0,0,.35)',
      'opacity:.75', 'transition:opacity .15s ease'
    ].join(';'));
    a.addEventListener('mouseenter', function () { a.style.opacity = '1'; });
    a.addEventListener('mouseleave', function () { a.style.opacity = '.75'; });
    document.body.appendChild(a);
    /* Μετατόπιση του menu bar δεξιά ώστε το pill να κάθεται ΔΙΠΛΑ στο logo
     * χωρίς να καλύπτει τα μενού (Αρχείο/Επεξεργασία/Ρυθμίσεις). */
    var style = document.createElement('style');
    style.textContent = '[class*="menu-bar_menu-bar"]{padding-left:92px !important;box-sizing:border-box;}';
    document.head.appendChild(style);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();