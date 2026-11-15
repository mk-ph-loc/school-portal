/*
 * glossa.js — Χρωματισμός ελληνικής ψευδογλώσσας (ΓΛΩΣΣΑ)
 *
 * Το Pygments/skylighting δεν διαθέτει lexer για την ελληνική ψευδογλώσσα
 * του σχολικού εγχειριδίου, επομένως υλοποιείται εδώ ένας ελαφρύς
 * tokenizer που εφαρμόζεται σε μπλοκ ```glossa.
 */
(function () {
  'use strict';

  // Λέξεις-κλειδιά της σχολικής ψευδογλώσσας
  var KEYWORDS = [
    'ΑΛΓΟΡΙΘΜΟΣ', 'ΑΡΧΗ', 'ΤΕΛΟΣ', 'ΔΕΔΟΜΕΝΑ', 'ΣΤΑΘΕΡΕΣ', 'ΜΕΤΑΒΛΗΤΕΣ',
    'ΑΚΕΡΑΙΕΣ', 'ΠΡΑΓΜΑΤΙΚΕΣ', 'ΧΑΡΑΚΤΗΡΕΣ', 'ΛΟΓΙΚΕΣ', 'ΠΙΝΑΚΑΣ',
    'ΕΑΝ', 'ΑΝ', 'ΤΟΤΕ', 'ΑΛΛΙΩΣ', 'ΑΛΛΙΩΣ_ΑΝ', 'ΤΕΛΟΣ_ΑΝ',
    'ΓΙΑ', 'ΑΠΟ', 'ΜΕΧΡΙ', 'ΜΕ', 'ΒΗΜΑ', 'ΤΕΛΟΣ_ΕΠΑΝΑΛΗΨΗΣ',
    'ΟΣΟ', 'ΕΠΑΝΑΛΑΒΕ', 'ΜΕΧΡΙΣ_ΟΤΟΥ', 'ΕΠΙΛΕΞΕ', 'ΠΕΡΙΠΤΩΣΗ', 'ΤΕΛΟΣ_ΕΠΙΛΟΓΩΝ',
    'ΔΙΑΒΑΣΕ', 'ΓΡΑΨΕ', 'ΕΜΦΑΝΙΣΕ', 'ΕΙΣΟΔΟΣ', 'ΕΞΟΔΟΣ',
    'ΣΥΝΑΡΤΗΣΗ', 'ΔΙΑΔΙΚΑΣΙΑ', 'ΤΕΛΟΣ_ΣΥΝΑΡΤΗΣΗΣ', 'ΤΕΛΟΣ_ΔΙΑΔΙΚΑΣΙΑΣ',
    'ΚΑΛΕΣΕ', 'ΕΠΙΣΤΡΕΦΕΙ', 'ΕΠΙΣΤΡΟΦΗ', 'ΑΚΕΡΑΙΑ', 'ΠΡΑΓΜΑΤΙΚΗ', 'ΛΟΓΙΚΗ',
    'ΑΛΗΘΗΣ', 'ΨΕΥΔΗΣ', 'ΚΑΙ', 'Η', 'ΟΧΙ', 'MOD', 'DIV', 'Α_Μ', 'Α_Τ', 'Τ_Ρ'
  ];

  // Ενσωματωμένες συναρτήσεις
  var BUILTINS = ['Τ_Ρ', 'Α_Μ', 'Α_Τ', 'ΗΜ', 'ΣΥΝ', 'ΕΦ', 'ΛΟΓ', 'Ε', 'ΜΗΚΟΣ'];

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /**
   * Μετατρέπει πηγαίο κώδικα ψευδογλώσσας σε HTML με spans χρωματισμού.
   * Η σάρωση γίνεται με μία regex ώστε τα strings/comments να έχουν προτεραιότητα.
   */
  function highlight(src) {
    var kwSet = {};
    KEYWORDS.forEach(function (k) { kwSet[k] = true; });
    var biSet = {};
    BUILTINS.forEach(function (b) { biSet[b] = true; });

    // Σειρά εναλλακτικών: σχόλια | strings | αριθμοί | λέξεις | τελεστές
    var tokenRe = /(![^\n]*|\/\/[^\n]*)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(\b\d+(?:\.\d+)?\b)|([A-Za-zΑ-Ωα-ωΆ-ώ_][A-Za-zΑ-Ωα-ωΆ-ώ0-9_]*)|(<-|<=|>=|<>|[+\-*/^<>=])|([\s\S])/g;

    var out = '';
    var m;
    while ((m = tokenRe.exec(src)) !== null) {
      if (m[1] !== undefined) {
        out += '<span class="gl-c">' + escapeHtml(m[1]) + '</span>';
      } else if (m[2] !== undefined) {
        out += '<span class="gl-s">' + escapeHtml(m[2]) + '</span>';
      } else if (m[3] !== undefined) {
        out += '<span class="gl-n">' + escapeHtml(m[3]) + '</span>';
      } else if (m[4] !== undefined) {
        var w = m[4];
        var up = w.toUpperCase();
        if (kwSet[up]) {
          out += '<span class="gl-k">' + escapeHtml(w) + '</span>';
        } else if (biSet[up]) {
          out += '<span class="gl-b">' + escapeHtml(w) + '</span>';
        } else {
          out += '<span class="gl-v">' + escapeHtml(w) + '</span>';
        }
      } else if (m[5] !== undefined) {
        out += '<span class="gl-o">' + escapeHtml(m[5]) + '</span>';
      } else {
        out += escapeHtml(m[6]);
      }
    }
    return out;
  }

  function apply() {
    // Μπλοκ που σημάνθηκαν ως glossa (pymdownx pygments_lang_class)
    var blocks = document.querySelectorAll(
      'code.language-glossa, code.lang-glossa, .highlight-glossa code, pre.glossa > code'
    );
    blocks.forEach(function (code) {
      if (code.getAttribute('data-glossa-done') === '1') return;
      var raw = code.textContent;
      code.innerHTML = highlight(raw);
      code.setAttribute('data-glossa-done', '1');
      var pre = code.closest('pre');
      if (pre) pre.classList.add('glossa-highlighted');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
  if (typeof document$ !== 'undefined' && document$.subscribe) {
    document$.subscribe(apply);
  }

  window.GlossaHighlight = { highlight: highlight, apply: apply };
})();