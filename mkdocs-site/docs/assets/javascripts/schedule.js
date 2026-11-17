/*
 * schedule.js — Ωράριο σχολείου & ενεργό μάθημα
 *
 * - Ο μαθητής δηλώνει το τμήμα του (π.χ. Γ1)· αποθηκεύεται στο localStorage.
 * - Το ωράριο έρχεται από το /lesson-wizard/api/schedule/public (JSON που
 *   παράγεται από το Excel του καθηγητή).
 * - Widget «Τώρα στο σχολείο»: δείχνει το μάθημα της τρέχουσας ώρας για το
 *   τμήμα, ή το χειροκίνητο «ενεργό μάθημα» που όρισε ο καθηγητής (override).
 * - Φιλτράρει το πλαϊνό μενού ώστε ο μαθητής να βλέπει μόνο την τάξη του.
 */
(function () {
  'use strict';

  var LS_KEY = 'school-tmima';
  var API = '/lesson-wizard/api/schedule/public';
  var cache = null;

  function getTmima() { try { return localStorage.getItem(LS_KEY) || ''; } catch (e) { return ''; } }
  function setTmima(t) { try { localStorage.setItem(LS_KEY, t); } catch (e) {} }

  function fetchSchedule() {
    if (cache) return cache;
    cache = fetch(API, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
    return cache;
  }

  /** Τρέχουσα διδακτική ώρα βάσει των ζωνών του Excel. */
  function currentPeriod(data) {
    if (!data || !data.periods) return null;
    var now = new Date();
    var hhmm = ('0' + now.getHours()).slice(-2) + ':' + ('0' + now.getMinutes()).slice(-2);
    for (var i = 0; i < data.periods.length; i++) {
      var p = data.periods[i];
      if (hhmm >= p.start && hhmm < p.end) return i + 1;
    }
    return null;
  }

  var DAYS = ['Κυριακή', 'Δευτέρα', 'Τρίτη', 'Τετάρτη', 'Πέμπτη', 'Παρασκευή', 'Σάββατο'];

  function activeLesson(data, tmima) {
    if (!data) return null;
    // 1. Χειροκίνητο override καθηγητή (με TTL)
    var ov = (data.overrides || {})[tmima];
    if (ov && ov.until && Date.now() / 1000 < ov.until) {
      return { title: ov.title, url: ov.url, source: '🧑‍🏫 Ο καθηγητής όρισε ενεργό μάθημα' };
    }
    // 2. Ωράριο
    var day = DAYS[new Date().getDay()];
    var period = currentPeriod(data);
    if (!period) return null;
    var cell = ((data.timetable || {})[tmima] || {})[day];
    var entry = cell && cell[String(period)];
    if (!entry) return null;
    return { title: entry.title, url: entry.url || '', source: '🕐 ' + day + ', ' + period + 'η ώρα' };
  }

  function renderWidget() {
    var host = document.getElementById('tmata-widget');
    if (!host) return;
    fetchSchedule().then(function (data) {
      var tmima = getTmima();
      if (!tmima) { host.hidden = true; return; }
      var act = activeLesson(data, tmima);
      host.hidden = false;
      host.innerHTML = '';
      var head = document.createElement('div');
      head.className = 'tmata-box__head';
      head.textContent = 'Τώρα στο σχολείο — Τμήμα ' + tmima;
      host.appendChild(head);
      var body = document.createElement('div');
      if (act) {
        body.className = 'tmata-box__active';
        if (act.url) {
          var a = document.createElement('a');
          a.href = act.url;
          a.textContent = '▶ ' + act.title;
          body.appendChild(a);
        } else {
          body.textContent = act.title;
        }
        var src = document.createElement('small');
        src.textContent = act.source;
        body.appendChild(src);
      } else {
        body.className = 'tmata-box__idle';
        body.textContent = 'Δεν υπάρχει ενεργό μάθημα αυτή την ώρα. Διάλεξε ελεύθερα από το μενού! 📚';
      }
      host.appendChild(body);
    });
  }
  /** Dropdown «Το τμήμα μου» στο header του Material. */
  function buildPicker(data) {
    if (document.querySelector('.tmima-picker')) return;
    var header = document.querySelector('.md-header__inner');
    if (!header) return;
    var box = document.createElement('div');
    box.className = 'tmima-picker';
    var sel = document.createElement('select');
    sel.title = 'Δήλωσε το τμήμα σου για να βλέπεις τα μαθήματά του';
    var opt0 = document.createElement('option');
    opt0.value = '';
    opt0.textContent = '👥 Το τμήμα μου…';
    sel.appendChild(opt0);
    var tmimata = (data && data.tmimata) || [];
    tmimata.forEach(function (t) {
      var o = document.createElement('option');
      o.value = t.name;
      o.textContent = t.name;
      if (t.name === getTmima()) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () {
      setTmima(sel.value);
      renderWidget();
      filterNavByClass(data);
    });
    box.appendChild(sel);
    var search = header.querySelector('.md-search');
    header.insertBefore(box, search || null);
  }

  /** Κρύβει από το μενού τις τάξεις που δεν αντιστοιχούν στο τμήμα. */
  function filterNavByClass(data) {
    var tmima = getTmima();
    if (!tmima || !data) return;
    var t = (data.tmimata || []).filter(function (x) { return x.name === tmima; })[0];
    if (!t || !t.class_slug) return;
    var nav = document.querySelector('.md-sidebar--primary nav.md-nav--primary');
    if (!nav) return;
    nav.querySelectorAll('li.md-nav__item--nested').forEach(function (li) {
      var links = li.querySelectorAll('a.md-nav__link');
      var slugs = {};
      links.forEach(function (a) {
        var m = (a.getAttribute('href') || '').match(/mathimata\/([a-z-]+)\//);
        if (m) slugs[m[1]] = true;
      });
      var keys = Object.keys(slugs);
      if (keys.length && keys.indexOf(t.class_slug) === -1) li.style.display = 'none';
      else li.style.display = '';
    });
  }

  function apply() {
    fetchSchedule().then(function (data) {
      buildPicker(data);
      renderWidget();
      filterNavByClass(data);
    });
    // Ανανέωση κάθε λεπτό (αλλαγή ώρας / override καθηγητή)
    if (!window.__tmataTimer) {
      window.__tmataTimer = setInterval(function () { cache = null; renderWidget(); }, 60000);
    }
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