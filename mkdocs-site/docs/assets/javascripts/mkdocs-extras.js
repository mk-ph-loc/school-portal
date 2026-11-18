/*
 * mkdocs-extras.js — Επιπλέον δυνατότητες MkDocs σελίδων:
 *
 * 1. 🎞 Reveal.js slides: κάθε <div class="slides-source" hidden> με markdown
 *    διαχωρισμένο σε --- γίνεται παρουσίαση fullscreen (τοπικό vendor).
 *    Σύνταξη στο md:  <div class="slides-source" data-title="…" markdown="1">…</div>
 *    (εναλλακτικά το υλικό μπορεί να είναι ήδη HTML <section> μέσα σε
 *     <template class="slides-html">).
 * 2. 🏷 Chips tags/αγαπημένου από το front-matter του μαθήματος.
 */
(function () {
  'use strict';

  var VENDOR = '/docs/assets/vendor/reveal/';
  var revealLoading = null;

  // ---------------- 1. Slides ----------------
  function loadReveal() {
    if (revealLoading) return revealLoading;
    revealLoading = new Promise(function (resolve, reject) {
      var css1 = document.createElement('link');
      css1.rel = 'stylesheet';
      css1.href = VENDOR + 'reveal.css';
      document.head.appendChild(css1);
      var s = document.createElement('script');
      s.src = VENDOR + 'reveal.js';
      s.onload = function () { resolve(window.Reveal); };
      s.onerror = reject;
      document.head.appendChild(s);
    });
    return revealLoading;
  }

  /** Μετατρέπει απλό markdown σε HTML για τις διαφάνειες (χωρίς εξαρτήσεις). */
  function miniMarkdown(md) {
    var esc = function (t) {
      return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    };
    return md.split('\n').map(function (line) {
      if (/^###\s/.test(line)) return '<h3>' + esc(line.slice(4)) + '</h3>';
      if (/^##\s/.test(line)) return '<h2>' + esc(line.slice(3)) + '</h2>';
      if (/^#\s/.test(line)) return '<h1>' + esc(line.slice(2)) + '</h1>';
      if (/^[-*]\s/.test(line)) return '<li>' + inline(esc(line.slice(2))) + '</li>';
      if (!line.trim()) return '';
      return '<p>' + inline(esc(line)) + '</p>';
    }).join('\n').replace(/(<li>[\s\S]*?<\/li>\n?)+/g, function (m) { return '<ul>' + m + '</ul>'; });
    function inline(t) {
      return t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
              .replace(/\*([^*]+)\*/g, '<em>$1</em>')
              .replace(/`([^`]+)`/g, '<code>$1</code>');
    }
  }

  function openSlides(sourceEl) {
    loadReveal().then(function (Reveal) {
      var overlay = document.createElement('div');
      overlay.className = 'slides-overlay';
      var close = document.createElement('button');
      close.className = 'slides-close';
      close.textContent = '✕ Κλείσιμο (Esc)';
      overlay.appendChild(close);

      var deck = document.createElement('div');
      deck.className = 'reveal';
      var slides = document.createElement('div');
      slides.className = 'slides';

      var tpl = sourceEl.querySelector('template.slides-html');
      if (tpl) {
        slides.innerHTML = tpl.innerHTML;         // έτοιμα <section>
      } else {
        // Το md_in_html έχει ήδη μετατρέψει το markdown σε HTML· τα <hr>
        // (από το ---) είναι οι διαχωριστές διαφανειών. Fallback: raw text.
        var hasHtml = sourceEl.querySelector('h1,h2,h3,p,ul,ol,pre');
        var parts = [];
        if (hasHtml) {
          var cur = [];
          Array.prototype.slice.call(sourceEl.childNodes).forEach(function (node) {
            if (node.nodeType === 1 && node.tagName === 'HR') {
              parts.push(cur); cur = [];
            } else {
              cur.push(node);
            }
          });
          parts.push(cur);
          parts.forEach(function (nodes) {
            var sec = document.createElement('section');
            nodes.forEach(function (n) { sec.appendChild(n.cloneNode(true)); });
            if (sec.textContent.trim()) slides.appendChild(sec);
          });
        } else {
          var raw = sourceEl.getAttribute('data-md') || sourceEl.textContent;
          raw.split(/\n\s*---\s*\n/).forEach(function (chunk) {
            if (!chunk.trim()) return;
            var sec = document.createElement('section');
            sec.innerHTML = miniMarkdown(chunk.trim());
            slides.appendChild(sec);
          });
        }
      }
      deck.appendChild(slides);
      overlay.appendChild(deck);
      document.body.appendChild(overlay);

      var themeLink = document.createElement('link');
      themeLink.rel = 'stylesheet';
      themeLink.href = VENDOR + 'theme/black.css';
      document.head.appendChild(themeLink);

      var instance = new Reveal(deck, {
        embedded: false, hash: false, controls: true, progress: true,
        center: true, transition: 'slide'
      });
      instance.initialize().then(function () { instance.layout(); });

      function destroy() {
        try { instance.destroy(); } catch (e) {}
        overlay.remove();
        themeLink.remove();
        document.removeEventListener('keydown', onKey);
      }
      function onKey(ev) { if (ev.key === 'Escape') destroy(); }
      close.addEventListener('click', destroy);
      document.addEventListener('keydown', onKey);
    }).catch(function () {
      alert('Δεν φορτώθηκε το Reveal.js — έλεγξε τα τοπικά assets (install.sh).');
    });
  }

  function buildSlideButtons() {
    document.querySelectorAll('.slides-source').forEach(function (src) {
      if (src.getAttribute('data-ready')) return;
      src.setAttribute('data-ready', '1');
      src.hidden = true;
      var btn = document.createElement('button');
      btn.className = 'slides-launch';
      btn.textContent = '🎞 ' + (src.getAttribute('data-title') || 'Παρουσίαση διαφανειών');
      btn.addEventListener('click', function () { openSlides(src); });
      src.parentNode.insertBefore(btn, src);
    });
  }

  // ---------------- 2. Lesson chips (tags/favorite από front-matter) ----------------
  function buildChips() {
    var h1 = document.querySelector('.md-content__inner h1');
    if (!h1 || document.querySelector('.lesson-chips')) return;
    var meta = window.__lessonMeta;
    if (!meta) return;
    var box = document.createElement('div');
    box.className = 'lesson-chips';
    if (meta.favorite) {
      var fav = document.createElement('span');
      fav.className = 'lesson-chip lesson-chip--fav';
      fav.textContent = '⭐ Αγαπημένο';
      box.appendChild(fav);
    }
    (meta.tags || []).forEach(function (t) {
      var chip = document.createElement('span');
      chip.className = 'lesson-chip';
      chip.textContent = '#' + t;
      box.appendChild(chip);
    });
    if (box.children.length) h1.parentNode.insertBefore(box, h1.nextSibling);
  }

  function apply() { buildSlideButtons(); buildChips(); }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(apply);
  }
})();