/*
 * portal-nav.js — 🧭 Πλωτό μενού πλοήγησης Ψηφιακής Πύλης (παντού).
 *
 * Self-contained vanilla JS + injected CSS (χωρίς εξαρτήσεις), ώστε να
 * φορτώνεται σε κάθε σελίδα της πύλης: dashboard, MkDocs (/docs/), και τα
 * FastAPI apps (lesson-wizard, exams, live-quiz, web-lab, h5p, app-builder…).
 *
 * Χρήση: <script src="/assets/portal-nav.js" defer></script>
 * Δεν εμφανίζεται μέσα σε iframes (ώστε να μην μπαίνει σε embeds μαθημάτων).
 */
(function () {
  'use strict';
  if (window.__portalNavLoaded) return;
  window.__portalNavLoaded = true;
  try { if (window.self !== window.top) return; } catch (e) { return; }

  var LINKS = [
    { href: '/', icon: '🏠', label: 'Αρχική Πύλη' },
    { href: '/classroom/', icon: '🏫', label: 'Ζωντανή Τάξη (κεντρικό παράθυρο)' },
    { href: '/docs/', icon: '📚', label: 'Εκπαιδευτικό Υλικό' },
    { href: '/docs/vivliothiki/', icon: '📖', label: 'Βιβλιοθήκη Βιβλίων' },
    { href: '/exams/', icon: '📤', label: 'Παράδοση Εργασιών' },
    { href: '/live-quiz/', icon: '🎮', label: 'Live Quiz Τάξης' },
    { href: '/board/', icon: '🖍️', label: 'Ψηφιακός Πίνακας' },
    { href: '/web-lab/', icon: '🌐', label: 'Εργαστήριο Web' },
    { href: '/md-pad/', icon: '📝', label: 'Συνεργατικό Markdown' },
    { href: '/lesson-wizard/', icon: '🧙', label: 'Lesson Wizard', teacher: true },
    { href: '/lesson-wizard/#schedule', icon: '🗓️', label: 'Ωράριο & Ενεργό Μάθημα', teacher: true },
    { href: '/h5p-studio/', icon: '🧩', label: 'H5P Studio', teacher: true },
    { href: '/share/', icon: '📂', label: 'Κοινόχρηστα Αρχεία', teacher: true }
  ];

  function isTeacher() {
    // Το cookie του wizard είναι HttpOnly· χρησιμοποιούμε το sessionStorage
    // του dashboard ή την κλάση is-teacher που βάζει το lesson-phases.js.
    try {
      if (sessionStorage.getItem('schoolPortal.teacher') === '1') return true;
    } catch (e) {}
    return document.body && document.body.classList.contains('is-teacher');
  }

  var css = '' +
    '#portal-nav-fab{position:fixed;right:1rem;bottom:1rem;z-index:9998;width:3.2rem;height:3.2rem;' +
    'border-radius:50%;border:none;cursor:pointer;font-size:1.5rem;line-height:1;' +
    'background:linear-gradient(135deg,#1a237e,#0277bd);color:#fff;' +
    'box-shadow:0 4px 16px rgba(10,30,90,.4);transition:transform .15s}' +
    '#portal-nav-fab:hover{transform:scale(1.08)}' +
    '#portal-nav-menu{position:fixed;right:1rem;bottom:4.8rem;z-index:9999;width:17rem;max-height:70vh;' +
    'overflow:auto;background:#fff;color:#1e293b;border-radius:.9rem;padding:.5rem;' +
    'box-shadow:0 10px 40px rgba(10,30,90,.35);border:1px solid #e2e8f0;' +
    'font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;display:none}' +
    '#portal-nav-menu.open{display:block}' +
    '#portal-nav-menu .pn-head{font-size:.68rem;font-weight:700;text-transform:uppercase;' +
    'letter-spacing:.05em;color:#64748b;padding:.4rem .6rem .3rem}' +
    '#portal-nav-menu a{display:flex;align-items:center;gap:.55rem;padding:.5rem .6rem;' +
    'border-radius:.55rem;text-decoration:none;color:#1e293b;font-size:.82rem;font-weight:600}' +
    '#portal-nav-menu a:hover{background:#eef2ff;color:#3730a3}' +
    '#portal-nav-menu a.pn-current{background:#e0e7ff;color:#3730a3}' +
    '#portal-nav-menu .pn-sep{border-top:1px solid #e2e8f0;margin:.35rem .3rem}' +
    '#portal-nav-menu .pn-teacher{font-size:.6rem;color:#b45309;background:#fef3c7;' +
    'border-radius:.6rem;padding:.05rem .4rem;margin-left:auto}' +
    '@media print{#portal-nav-fab,#portal-nav-menu{display:none!important}}';
  function build() {
    if (!document.body || document.getElementById('portal-nav-fab')) return;
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    var fab = document.createElement('button');
    fab.id = 'portal-nav-fab';
    fab.title = '🧭 Πλοήγηση στην Πύλη';
    fab.setAttribute('aria-label', 'Μενού πλοήγησης πύλης');
    fab.textContent = '🧭';

    var menu = document.createElement('nav');
    menu.id = 'portal-nav-menu';
    menu.setAttribute('aria-label', 'Πλοήγηση πύλης');
    var head = document.createElement('div');
    head.className = 'pn-head';
    head.textContent = '🏫 Ψηφιακή Πύλη Σχολείου';
    menu.appendChild(head);

    var teacher = isTeacher();
    var here = location.pathname;
    var sepDone = false;
    LINKS.forEach(function (l) {
      if (l.teacher && !teacher) return;
      if (l.teacher && !sepDone) {
        var sep = document.createElement('div');
        sep.className = 'pn-sep';
        menu.appendChild(sep);
        sepDone = true;
      }
      var a = document.createElement('a');
      a.href = l.href;
      var base = l.href.split('#')[0];
      if (here === base || (base !== '/' && here.indexOf(base) === 0)) a.className = 'pn-current';
      var ic = document.createElement('span');
      ic.textContent = l.icon;
      var lb = document.createElement('span');
      lb.textContent = l.label;
      a.appendChild(ic);
      a.appendChild(lb);
      if (l.teacher) {
        var tg = document.createElement('span');
        tg.className = 'pn-teacher';
        tg.textContent = '🔐';
        a.appendChild(tg);
      }
      menu.appendChild(a);
    });

    fab.addEventListener('click', function (ev) {
      ev.stopPropagation();
      menu.classList.toggle('open');
    });
    document.addEventListener('click', function (ev) {
      if (!menu.contains(ev.target) && ev.target !== fab) menu.classList.remove('open');
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') menu.classList.remove('open');
    });

    document.body.appendChild(menu);
    document.body.appendChild(fab);

    // Deep-link: /lesson-wizard/#schedule → άνοιγμα της καρτέλας Ωράριο
    if (location.hash === '#schedule' && here.indexOf('/lesson-wizard/') === 0) {
      setTimeout(function () {
        var btns = document.querySelectorAll('nav button');
        for (var i = 0; i < btns.length; i++) {
          if ((btns[i].textContent || '').indexOf('Ωράριο') !== -1) { btns[i].click(); break; }
        }
      }, 800);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
  // Σε Material instant navigation το body παραμένει — απλώς επιβεβαιώνουμε.
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(function () { build(); });
  }
})();