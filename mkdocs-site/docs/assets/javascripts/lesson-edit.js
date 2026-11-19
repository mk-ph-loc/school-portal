/*
 * lesson-edit.js — ✏️ Γρήγορη επεξεργασία σελίδων μαθημάτων (μόνο καθηγητής).
 *
 * Self-contained vanilla JS + injected CSS (μοτίβο portal-nav.js). Φορτώνεται
 * σε κάθε σελίδα /docs/ αλλά εμφανίζεται ΜΟΝΟ αν ο χρήστης είναι καθηγητής:
 * η αναγνώριση γίνεται με probe στο προστατευμένο /lesson-wizard/api/check
 * (200 με έγκυρο HMAC cookie, 401 αλλιώς — κανένα νέο σύστημα αυθεντικοποίησης).
 * Δουλεύει και μέσα στο iframe της Ζωντανής Τάξης (/classroom/).
 *
 * Επιλογές από το FAB «✏️»:
 *   ⚡ Γρήγορη επεξεργασία  → raw markdown modal (wizard api/fs/read|save,
 *      αυτόματο .bak + auto-rebuild του site μέσω school-mkdocs.path).
 *   🧙 Visual editor φάσεων → /lesson-wizard/#edit=<cls>/<subj>/<lesson>.
 *   📝 Συνεργατικό Markdown → νέα σημείωση HedgeDoc με το περιεχόμενο της
 *      σελίδας (POST /md-pad/new/<alias>)· δημοσίευση μετά από /md-publish/.
 */
(function () {
  'use strict';
  if (window.__lessonEditLoaded) return;
  window.__lessonEditLoaded = true;

  var WIZARD = '/lesson-wizard/';
  var state = { srcPath: null, lessonKey: null, content: null };

  /** docs URL → σχετική διαδρομή μέσα στο docs/ (π.χ. mathimata/.../index.md).
   *  Με use_directory_urls κάθε φάκελος αντιστοιχεί σε <φάκελος>/index.md. */
  function pageSource() {
    var p = location.pathname;
    if (p.indexOf('/docs/') !== 0) return null;
    var rel = p.slice('/docs/'.length).replace(/index\.html$/, '').replace(/\/+$/, '');
    if (!rel) return { path: 'index.md', view: p };
    // Άμεσα .html αρχεία (π.χ. exports) δεν έχουν αντίστοιχη πηγή .md εδώ.
    if (/\.html?$/.test(rel)) return null;
    return { path: rel + '/index.md', view: p };
  }

  function lessonKeyFromPath(path) {
    var m = path.match(/^mathimata\/([\w-]+)\/([\w-]+)\/([\w-]+)\/index\.md$/);
    return m ? m[1] + '/' + m[2] + '/' + m[3] : null;
  }

  function api(url, opts) {
    return fetch(url, Object.assign({ credentials: 'same-origin' }, opts || {})).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.detail || ('Σφάλμα ' + r.status));
        return data;
      });
    });
  }

  var css = '' +
    '#lesson-edit-fab{position:fixed;left:1rem;bottom:1rem;z-index:9998;width:3.2rem;height:3.2rem;' +
    'border-radius:50%;border:none;cursor:pointer;font-size:1.4rem;line-height:1;' +
    'background:linear-gradient(135deg,#b45309,#f59e0b);color:#fff;' +
    'box-shadow:0 4px 16px rgba(120,53,15,.4);transition:transform .15s}' +
    '#lesson-edit-fab:hover{transform:scale(1.08)}' +
    '#lesson-edit-menu{position:fixed;left:1rem;bottom:4.8rem;z-index:9999;width:17.5rem;' +
    'background:#fff;color:#1e293b;border-radius:.9rem;padding:.5rem;display:none;' +
    'box-shadow:0 10px 40px rgba(10,30,90,.35);border:1px solid #e2e8f0;' +
    'font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}' +
    '#lesson-edit-menu.open{display:block}' +
    '#lesson-edit-menu .le-head{font-size:.68rem;font-weight:700;text-transform:uppercase;' +
    'letter-spacing:.05em;color:#64748b;padding:.4rem .6rem .3rem}' +
    '#lesson-edit-menu button,#lesson-edit-menu a{display:flex;align-items:center;gap:.55rem;width:100%;' +
    'padding:.5rem .6rem;border:none;background:none;border-radius:.55rem;text-decoration:none;' +
    'color:#1e293b;font-size:.82rem;font-weight:600;cursor:pointer;text-align:left}' +
    '#lesson-edit-menu button:hover,#lesson-edit-menu a:hover{background:#fef3c7;color:#92400e}' +
    '#lesson-edit-overlay{position:fixed;inset:0;z-index:10000;background:rgba(15,23,42,.6);' +
    'display:none;align-items:center;justify-content:center;padding:1rem}' +
    '#lesson-edit-overlay.open{display:flex}' +
    '#lesson-edit-modal{background:#fff;border-radius:1rem;width:min(96vw,900px);max-height:92vh;' +
    'display:flex;flex-direction:column;padding:1rem;box-shadow:0 20px 60px rgba(0,0,0,.4)}' +
    '#lesson-edit-modal .le-bar{display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem;flex-wrap:wrap}' +
    '#lesson-edit-modal .le-path{font-family:ui-monospace,monospace;font-size:.72rem;color:#475569;' +
    'flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '#lesson-edit-modal textarea{flex:1;min-height:55vh;width:100%;resize:vertical;' +
    'font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.78rem;line-height:1.5;' +
    'border:1px solid #cbd5e1;border-radius:.6rem;padding:.7rem;color:#0f172a;background:#f8fafc}' +
    '#lesson-edit-modal .le-btn{border:none;border-radius:.55rem;padding:.45rem .9rem;font-size:.75rem;' +
    'font-weight:700;cursor:pointer}' +
    '#lesson-edit-modal .le-save{background:#059669;color:#fff}' +
    '#lesson-edit-modal .le-save:hover{background:#047857}' +
    '#lesson-edit-modal .le-save:disabled{opacity:.5}' +
    '#lesson-edit-modal .le-close{background:#e2e8f0;color:#334155}' +
    '#lesson-edit-modal .le-note{font-size:.65rem;color:#94a3b8;margin-top:.4rem}' +
    '#lesson-edit-modal .le-status{font-size:.72rem;font-weight:600;margin-top:.3rem;min-height:1em}' +
    '@media print{#lesson-edit-fab,#lesson-edit-menu,#lesson-edit-overlay{display:none!important}}';

  function openQuickEdit() {
    var overlay = document.getElementById('lesson-edit-overlay');
    var ta = document.getElementById('lesson-edit-textarea');
    var status = document.getElementById('lesson-edit-status');
    status.textContent = 'Φόρτωση…'; status.style.color = '#64748b';
    overlay.classList.add('open');
    api(WIZARD + 'api/fs/read?path=' + encodeURIComponent(state.srcPath)).then(function (d) {
      state.content = d.content;
      ta.value = d.content;
      status.textContent = '';
    }).catch(function (e) {
      status.textContent = '✗ ' + e.message;
      status.style.color = '#dc2626';
    });
  }

  function saveQuickEdit() {
    var ta = document.getElementById('lesson-edit-textarea');
    var btn = document.getElementById('lesson-edit-save');
    var status = document.getElementById('lesson-edit-status');
    btn.disabled = true;
    status.textContent = 'Αποθήκευση…'; status.style.color = '#64748b';
    api(WIZARD + 'api/fs/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: state.srcPath, content: ta.value })
    }).then(function () {
      status.textContent = '✅ Αποθηκεύτηκε (με .bak backup). Το site ξαναχτίζεται — ανανέωση σε ~40 δευτ…';
      status.style.color = '#059669';
      setTimeout(function () { location.reload(); }, 40000);
    }).catch(function (e) {
      status.textContent = '✗ ' + e.message; status.style.color = '#dc2626';
      btn.disabled = false;
    });
  }

  function openHedgeDoc() {
    var slug = (state.lessonKey || state.srcPath || 'selida').replace(/[^\w-]+/g, '-').slice(-60);
    var alias = 'lesson-' + slug + '-' + Math.random().toString(36).slice(2, 7);
    var proceed = function (content) {
      // POST text/markdown → δημιουργία σημείωσης με έτοιμο περιεχόμενο.
      fetch('/md-pad/new/' + alias, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'text/markdown' }, body: content
      }).then(function (r) {
        if (r.status !== 409 && !r.ok && r.status !== 302) throw new Error('Σφάλμα ' + r.status);
        window.open('/md-pad/' + alias, '_blank');   // 409 = υπάρχει ήδη → απλά άνοιγμα
      }).catch(function (e) { alert('HedgeDoc: ' + e.message); });
    };
    if (state.content !== null) { proceed(state.content); return; }
    api(WIZARD + 'api/fs/read?path=' + encodeURIComponent(state.srcPath))
      .then(function (d) { state.content = d.content; proceed(d.content); })
      .catch(function (e) { alert('Δεν διαβάστηκε η πηγή: ' + e.message); });
  }

  function build() {
    if (document.getElementById('lesson-edit-fab')) return;
    var src = pageSource();
    if (!src) return;
    state.srcPath = src.path;
    state.lessonKey = lessonKeyFromPath(src.path);

    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    var fab = document.createElement('button');
    fab.id = 'lesson-edit-fab';
    fab.title = '✏️ Επεξεργασία σελίδας (καθηγητής)';
    fab.setAttribute('aria-label', 'Επεξεργασία σελίδας μαθήματος');
    fab.textContent = '✏️';

    var menu = document.createElement('div');
    menu.id = 'lesson-edit-menu';
    var head = document.createElement('div');
    head.className = 'le-head';
    head.textContent = '✏️ Επεξεργασία — ' + (state.lessonKey ? 'ημερήσιο μάθημα' : 'σελίδα docs');
    menu.appendChild(head);

    var bQuick = document.createElement('button');
    bQuick.innerHTML = '<span>⚡</span><span>Γρήγορη επεξεργασία (markdown)</span>';
    bQuick.addEventListener('click', function () { menu.classList.remove('open'); openQuickEdit(); });
    menu.appendChild(bQuick);

    if (state.lessonKey) {
      var aVisual = document.createElement('a');
      aVisual.href = WIZARD + '#edit=' + state.lessonKey;
      aVisual.target = '_blank';
      aVisual.innerHTML = '<span>🧙</span><span>Visual editor φάσεων (Wizard)</span>';
      menu.appendChild(aVisual);
    }

    var bPad = document.createElement('button');
    bPad.innerHTML = '<span>📝</span><span>Συνεργατικό Markdown (HedgeDoc)</span>';
    bPad.addEventListener('click', function () { menu.classList.remove('open'); openHedgeDoc(); });
    menu.appendChild(bPad);

    // Modal γρήγορης επεξεργασίας
    var overlay = document.createElement('div');
    overlay.id = 'lesson-edit-overlay';
    overlay.innerHTML =
      '<div id="lesson-edit-modal">' +
      '<div class="le-bar"><span class="le-path"></span>' +
      '<button class="le-btn le-save" id="lesson-edit-save">💾 Αποθήκευση</button>' +
      '<button class="le-btn le-close" id="lesson-edit-close">✕ Κλείσιμο</button></div>' +
      '<textarea id="lesson-edit-textarea" spellcheck="false"></textarea>' +
      '<div class="le-status" id="lesson-edit-status"></div>' +
      '<p class="le-note">Κρατιέται αυτόματο .bak πριν την αποθήκευση · το site ξαναχτίζεται αυτόματα (school-mkdocs.path).</p>' +
      '</div>';
    overlay.addEventListener('click', function (ev) { if (ev.target === overlay) overlay.classList.remove('open'); });

    document.body.appendChild(menu);
    document.body.appendChild(fab);
    document.body.appendChild(overlay);
    overlay.querySelector('.le-path').textContent = state.srcPath;
    document.getElementById('lesson-edit-save').addEventListener('click', saveQuickEdit);
    document.getElementById('lesson-edit-close').addEventListener('click', function () { overlay.classList.remove('open'); });

    fab.addEventListener('click', function (ev) { ev.stopPropagation(); menu.classList.toggle('open'); });
    document.addEventListener('click', function (ev) {
      if (!menu.contains(ev.target) && ev.target !== fab) menu.classList.remove('open');
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') { menu.classList.remove('open'); overlay.classList.remove('open'); }
    });
  }

  /** Καθηγητής; Probe στο προστατευμένο endpoint του wizard (HMAC cookie). */
  function checkTeacherThenBuild() {
    if (!pageSource()) return;
    fetch(WIZARD + 'api/check', { credentials: 'same-origin' }).then(function (r) {
      if (r.ok) build();
    }).catch(function () { /* όχι καθηγητής / offline → τίποτα */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkTeacherThenBuild);
  } else {
    checkTeacherThenBuild();
  }
  // Material instant navigation: επανέλεγχος σε κάθε αλλαγή σελίδας.
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(function () {
      ['lesson-edit-fab', 'lesson-edit-menu', 'lesson-edit-overlay'].forEach(function (id) {
        var el = document.getElementById(id); if (el) el.remove();
      });
      state = { srcPath: null, lessonKey: null, content: null };
      checkTeacherThenBuild();
    });
  }
})();