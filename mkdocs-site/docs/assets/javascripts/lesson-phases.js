/*
 * lesson-phases.js — Διδακτικές φάσεις ημερήσιου μαθήματος
 *
 * 1. Προσθέτει διακριτικά (badge) φάσης & διάρκειας — ΜΟΝΟ για τον καθηγητή.
 * 2. Φορτώνει τις σημειώσεις καθηγητή από το index.teacher.html (ο Nginx τις
 *    προστατεύει με auth_request· οι μαθητές παίρνουν 401 και δεν βλέπουν τίποτα).
 * 3. Κουμπί «🖥️ Παρουσίαση»: fullscreen προβολή των φάσεων ως διαφάνειες
 *    με πλοήγηση βελάκια (για προτζέκτορα τάξης).
 */
(function () {
  'use strict';

  var PHASE_LABELS = {
    aformisi: 'Αφόρμηση',
    syzitisi: 'Συζήτηση',
    parousiasi: 'Παρουσίαση',
    drastiriotita: 'Δραστηριότητα',
    aksiologisi: 'Αξιολόγηση',
    kleisimo: 'Κλείσιμο',
    custom: 'Φάση'
  };

  function phases() {
    return Array.prototype.slice.call(document.querySelectorAll('.lesson-phase[data-phase]'));
  }

  /** Είναι ο χρήστης καθηγητής; Ρωτάμε το προστατευμένο αρχείο σημειώσεων. */
  function loadTeacherNotes() {
    var holder = document.querySelector('.teacher-notes[hidden]');
    if (!holder) return Promise.resolve(false);
    var url = window.location.pathname.replace(/index\.html$/, '') + 'index.teacher.html';
    return fetch(url, { credentials: 'same-origin' }).then(function (r) {
      if (!r.ok) return false;
      return r.text().then(function (html) {
        holder.innerHTML = html;
        holder.hidden = false;
        document.body.classList.add('is-teacher');
        return true;
      });
    }).catch(function () { return false; });
  }

  function decoratePhases(isTeacher) {
    var list = phases();
    if (!list.length) return;
    document.body.classList.add('has-lesson-phases');
    list.forEach(function (div, i) {
      div.setAttribute('data-phase-index', String(i));
      if (!isTeacher) return;
      if (div.querySelector('.phase-badge')) return;
      var badge = document.createElement('div');
      badge.className = 'phase-badge';
      var type = div.getAttribute('data-phase');
      var dur = div.getAttribute('data-duration');
      badge.textContent = 'Φ' + (i + 1) + ' · ' + (PHASE_LABELS[type] || type) + (dur ? ' · ⏱ ' + dur + '΄' : '');
      div.insertBefore(badge, div.firstChild);
    });
    // Συνολικός χρόνος στο πάνω μέρος (μόνο καθηγητής)
    if (isTeacher && !document.querySelector('.lesson-plan-bar')) {
      var total = list.reduce(function (s, d) { return s + (parseInt(d.getAttribute('data-duration'), 10) || 0); }, 0);
      var bar = document.createElement('div');
      bar.className = 'lesson-plan-bar';
      bar.innerHTML = '<span>🧑‍🏫 Σχέδιο μαθήματος: <strong>' + list.length + ' φάσεις</strong>' +
        (total ? ' · συνολικά <strong>' + total + '΄</strong>' : '') + '</span>' +
        '<a class="md-button md-button--primary" href="/lesson-wizard/" target="_blank" rel="noopener">✏️ Επεξεργασία στο Wizard</a>';
      var content = document.querySelector('.md-content__inner');
      var h1 = content && content.querySelector('h1');
      if (content) content.insertBefore(bar, h1 ? h1.nextSibling : content.firstChild);
    }
  }

  // -------------------------------------------------------------------
  // Fullscreen παρουσίαση (διαφάνειες = φάσεις)
  // -------------------------------------------------------------------
  var overlay = null, slideIdx = 0;

  function buildOverlay() {
    overlay = document.createElement('div');
    overlay.className = 'present-overlay';
    overlay.innerHTML =
      '<div class="present-top"><span class="present-title"></span>' +
      '<span class="present-count"></span>' +
      '<button type="button" class="present-close" title="Έξοδος (Esc)">✕</button></div>' +
      '<div class="present-body"></div>' +
      '<div class="present-nav">' +
      '<button type="button" class="present-prev">← Πίσω</button>' +
      '<div class="present-dots"></div>' +
      '<button type="button" class="present-next">Επόμενη →</button></div>';
    document.body.appendChild(overlay);
    overlay.querySelector('.present-close').addEventListener('click', closePresent);
    overlay.querySelector('.present-prev').addEventListener('click', function () { showSlide(slideIdx - 1); });
    overlay.querySelector('.present-next').addEventListener('click', function () { showSlide(slideIdx + 1); });
    document.addEventListener('keydown', function (e) {
      if (!overlay || !overlay.classList.contains('is-open')) return;
      if (e.key === 'Escape') closePresent();
      else if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); showSlide(slideIdx + 1); }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); showSlide(slideIdx - 1); }
    });
  }

  function showSlide(i) {
    var list = phases();
    if (!list.length) return;
    slideIdx = Math.max(0, Math.min(list.length - 1, i));
    var src = list[slideIdx];
    var body = overlay.querySelector('.present-body');
    body.innerHTML = '';
    var clone = src.cloneNode(true);
    // Οι σημειώσεις καθηγητή ΔΕΝ μπαίνουν στην προβολή τάξης
    clone.querySelectorAll('.teacher-notes, .phase-badge').forEach(function (n) { n.remove(); });
    body.appendChild(clone);
    overlay.querySelector('.present-title').textContent = src.getAttribute('data-title') || '';
    overlay.querySelector('.present-count').textContent = (slideIdx + 1) + ' / ' + list.length;
    overlay.querySelector('.present-prev').disabled = slideIdx === 0;
    overlay.querySelector('.present-next').disabled = slideIdx === list.length - 1;
    var dots = overlay.querySelector('.present-dots');
    dots.innerHTML = '';
    list.forEach(function (_, k) {
      var d = document.createElement('span');
      d.className = 'present-dot' + (k === slideIdx ? ' is-active' : '');
      d.addEventListener('click', function () { showSlide(k); });
      dots.appendChild(d);
    });
    document.dispatchEvent(new CustomEvent('lesson-present-slide'));
    body.scrollTop = 0;
  }
  function openPresent() {
    if (!overlay) buildOverlay();
    overlay.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    showSlide(0);
    var el = document.documentElement;
    if (el.requestFullscreen) el.requestFullscreen().catch(function () {});
  }

  function closePresent() {
    if (!overlay) return;
    overlay.classList.remove('is-open');
    document.body.style.overflow = '';
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(function () {});
  }

  function addPresentButton() {
    if (!phases().length || document.querySelector('.present-launch')) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'present-launch md-button';
    btn.textContent = '🖥️ Παρουσίαση';
    btn.title = 'Προβολή του μαθήματος σε πλήρη οθόνη, φάση-φάση';
    btn.addEventListener('click', openPresent);
    var content = document.querySelector('.md-content__inner');
    var h1 = content && content.querySelector('h1');
    if (content) content.insertBefore(btn, h1 ? h1.nextSibling : content.firstChild);
  }

  function apply() {
    if (!phases().length) return;
    addPresentButton();
    loadTeacherNotes().then(decoratePhases);
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