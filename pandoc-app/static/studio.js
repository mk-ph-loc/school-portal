/* Visual Pandoc Studio — λογική διεπαφής */
(function () {
  'use strict';

  // Το app τρέχει πίσω από τον Nginx στο /pandoc/
  var BASE = window.location.pathname.replace(/\/$/, '') || '/pandoc';
  var $ = function (id) { return document.getElementById(id); };

  /* ---------- Βοηθητικά ---------- */
  function toast(msg, kind) {
    var t = $('toast');
    t.textContent = msg;
    t.className = 'toast show ' + (kind || '');
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.className = 'toast ' + (kind || ''); }, 4200);
  }

  function api(path, opts) {
    return fetch(BASE + path, opts).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return { detail: res.statusText }; })
          .then(function (j) { throw new Error(j.detail || ('Σφάλμα ' + res.status)); });
      }
      return res;
    });
  }

  function postJSON(path, body) {
    return api(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); });
  }

  /* ---------- Καρτέλες ---------- */
  document.querySelectorAll('.tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.tab').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      $('panel-' + btn.getAttribute('data-tab')).classList.add('active');
      if (btn.getAttribute('data-tab') === 'templates') loadTemplates();
      if (btn.getAttribute('data-tab') === 'publish') loadLessons();
    });
  });

  /* ---------- Συλλογή τιμών flags ---------- */
  function collectFlags() {
    var values = {};
    document.querySelectorAll('[data-flag]').forEach(function (el) {
      var id = el.getAttribute('data-flag');
      var type = el.getAttribute('data-type');
      if (type === 'bool') values[id] = el.checked;
      else if (type === 'int') values[id] = parseInt(el.value, 10) || 0;
      else values[id] = el.value;
    });
    return values;
  }

  function updateCommand() {
    postJSON('/api/command', { format: $('format').value, flags: collectFlags() })
      .then(function (j) {
        $('commandLine').textContent = j.command;
        var c2 = $('commandLine2');
        if (c2) c2.textContent = j.command;
      })
      .catch(function () { /* σιωπηλή αποτυχία */ });
  }

  /* ---------- Προεπισκόπηση ---------- */
  var previewTimer = null;
  function refreshPreview() {
    var md = $('markdown').value;
    $('previewStatus').textContent = '⏳';
    postJSON('/api/preview', { markdown: md })
      .then(function (j) {
        $('preview').innerHTML = j.html;
        $('previewStatus').textContent = '✓ ενημερώθηκε';
      })
      .catch(function (e) {
        $('previewStatus').textContent = '⚠ ' + e.message;
      });
  }

  function schedulePreview() {
    if (!$('autoPreview').checked) return;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(refreshPreview, 600);
  }

  $('markdown').addEventListener('input', schedulePreview);
  $('previewBtn').addEventListener('click', refreshPreview);

  /* ---------- Snippets ---------- */
  var SNIPPETS = {
    heading: '\n## Νέα Ενότητα\n\nΚείμενο ενότητας.\n',
    table: '\n| Στήλη 1 | Στήλη 2 |\n| --- | --- |\n| Τιμή Α | Τιμή Β |\n',
    python: '\n```python\nprint("Γεια σου κόσμε!")\n```\n',
    glossa: '\n```glossa\nΑΛΓΟΡΙΘΜΟΣ Παράδειγμα\nΑΡΧΗ\n  ΓΡΑΨΕ \'Γεια\'\nΤΕΛΟΣ_ΠΡΟΓΡΑΜΜΑΤΟΣ\n```\n',
    quiz: '\n<div class="quiz" data-quiz=\'[{"q":"Ερώτηση;","options":["Α","Β"],"answer":0,"explain":"Επεξήγηση."}]\' markdown></div>\n'
  };
  document.querySelectorAll('.chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var ta = $('markdown');
      var text = SNIPPETS[chip.getAttribute('data-snippet')] || '';
      var start = ta.selectionStart;
      ta.value = ta.value.slice(0, start) + text + ta.value.slice(ta.selectionEnd);
      ta.focus();
      ta.selectionStart = ta.selectionEnd = start + text.length;
      schedulePreview();
    });
  });

  $('copyCmd').addEventListener('click', function () {
    var text = $('commandLine').textContent;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(function () { toast('📋 Η εντολή αντιγράφηκε', 'ok'); });
    } else {
      toast('Η αντιγραφή δεν υποστηρίζεται σε αυτόν τον περιηγητή', 'warn');
    }
  });
  /* ---------- Μετατροπή & λήψη ---------- */
  $('convertBtn').addEventListener('click', function () {
    var btn = this;
    btn.disabled = true;
    btn.textContent = '⏳ Μετατροπή…';
    var payload = {
      markdown: $('markdown').value,
      format: $('format').value,
      filename: $('filename').value || 'eggrafo',
      flags: collectFlags()
    };
    api('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      var cd = res.headers.get('Content-Disposition') || '';
      var m = cd.match(/filename="([^"]+)"/);
      var name = m ? m[1] : ('eggrafo.' + payload.format);
      return res.blob().then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = name;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
        toast('✅ Το αρχείο ' + name + ' δημιουργήθηκε', 'ok');
      });
    }).catch(function (e) {
      toast('❌ ' + e.message, 'err');
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = '⬇ Μετατροπή & Λήψη';
    });
  });

  /* ---------- Πρότυπα .docx ---------- */
  function fmtSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function loadTemplates() {
    api('/api/templates').then(function (r) { return r.json(); }).then(function (j) {
      var body = $('tplBody');
      body.innerHTML = '';
      if (!j.templates.length) {
        body.innerHTML = '<tr><td colspan="3" class="muted">Δεν υπάρχουν πρότυπα. Πάτησε «Δημιουργία προεπιλεγμένου».</td></tr>';
        return;
      }
      j.templates.forEach(function (t) {
        var tr = document.createElement('tr');
        var tdName = document.createElement('td');
        tdName.textContent = t.name;
        var tdSize = document.createElement('td');
        tdSize.textContent = fmtSize(t.size);
        var tdAct = document.createElement('td');
        var del = document.createElement('button');
        del.className = 'btn btn--sm btn--danger';
        del.textContent = '🗑 Διαγραφή';
        del.addEventListener('click', function () {
          if (!confirm('Διαγραφή του προτύπου ' + t.name + ';')) return;
          api('/api/templates/' + encodeURIComponent(t.name), { method: 'DELETE' })
            .then(function () { toast('🗑 Διαγράφηκε', 'ok'); loadTemplates(); refreshTemplateSelect(); })
            .catch(function (e) { toast('❌ ' + e.message, 'err'); });
        });
        tdAct.appendChild(del);
        tr.appendChild(tdName); tr.appendChild(tdSize); tr.appendChild(tdAct);
        body.appendChild(tr);
      });
    }).catch(function (e) { toast('❌ ' + e.message, 'err'); });
  }

  function refreshTemplateSelect() {
    api('/api/templates').then(function (r) { return r.json(); }).then(function (j) {
      var sel = $('flag-reference_doc');
      if (!sel) return;
      var current = sel.value;
      sel.innerHTML = '<option value="">— Κανένα (προεπιλογή pandoc) —</option>';
      j.templates.forEach(function (t) {
        var o = document.createElement('option');
        o.value = t.name; o.textContent = t.name;
        if (t.name === current) o.selected = true;
        sel.appendChild(o);
      });
    }).catch(function () { /* αγνόησε */ });
  }

  $('tplUpload').addEventListener('change', function () {
    var file = this.files[0];
    if (!file) return;
    var fd = new FormData();
    fd.append('file', file);
    toast('⏳ Ανέβασμα…');
    api('/api/templates/upload', { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function () { toast('✅ Το πρότυπο ανέβηκε', 'ok'); loadTemplates(); refreshTemplateSelect(); })
      .catch(function (e) { toast('❌ ' + e.message, 'err'); })
      .finally(function () { $('tplUpload').value = ''; });
  });

  $('genTplBtn').addEventListener('click', function () {
    postJSON('/api/templates/generate', {})
      .then(function () { toast('✨ Το πρότυπο δημιουργήθηκε', 'ok'); loadTemplates(); refreshTemplateSelect(); })
      .catch(function (e) { toast('❌ ' + e.message, 'err'); });
  });
  $('refreshTplBtn').addEventListener('click', loadTemplates);
  /* ---------- Δημοσίευση στο MkDocs ---------- */
  function loadLessons() {
    var slug = $('pubClass').value;
    api('/api/lessons/' + slug).then(function (r) { return r.json(); }).then(function (j) {
      var ul = $('lessonsList');
      ul.innerHTML = '';
      if (!j.lessons.length) {
        ul.innerHTML = '<li class="muted">Δεν υπάρχουν μαθήματα σε αυτή την τάξη.</li>';
        return;
      }
      j.lessons.forEach(function (l) {
        var li = document.createElement('li');
        var span = document.createElement('span');
        span.textContent = l.title;
        var small = document.createElement('small');
        small.className = 'muted';
        small.textContent = l.filename;
        li.appendChild(span); li.appendChild(small);
        li.addEventListener('click', function () {
          api('/api/lesson/' + slug + '/' + encodeURIComponent(l.filename))
            .then(function (r) { return r.json(); })
            .then(function (d) {
              $('markdown').value = d.markdown;
              $('pubTitle').value = l.title;
              $('pubOverwrite').checked = true;
              document.querySelector('.tab[data-tab="editor"]').click();
              refreshPreview();
              toast('📂 Φορτώθηκε: ' + l.title, 'ok');
            })
            .catch(function (e) { toast('❌ ' + e.message, 'err'); });
        });
        ul.appendChild(li);
      });
    }).catch(function (e) { toast('❌ ' + e.message, 'err'); });
  }

  $('pubClass').addEventListener('change', loadLessons);
  $('refreshLessons').addEventListener('click', loadLessons);

  $('publishBtn').addEventListener('click', function () {
    var btn = this;
    var res = $('pubResult');
    btn.disabled = true;
    btn.textContent = '⏳ Αποστολή…';
    res.className = 'result';
    postJSON('/api/publish', {
      markdown: $('markdown').value,
      title: $('pubTitle').value,
      class_slug: $('pubClass').value,
      overwrite: $('pubOverwrite').checked,
      rebuild: $('pubRebuild').checked
    }).then(function (j) {
      res.className = 'result show ok';
      res.innerHTML = '';
      var p = document.createElement('div');
      p.textContent = '✅ Δημοσιεύτηκε: ' + j.file;
      var link = document.createElement('a');
      link.href = j.url; link.target = '_blank';
      link.textContent = '🔗 Άνοιγμα μαθήματος';
      var info = document.createElement('div');
      info.textContent = (j.nav_updated ? 'Το μενού ενημερώθηκε. ' : 'Υπήρχε ήδη στο μενού. ') +
        (j.rebuild && j.rebuild.ok ? 'Το site ανακατασκευάστηκε.' : '');
      res.appendChild(p); res.appendChild(link); res.appendChild(info);
      toast('🚀 Το μάθημα δημοσιεύτηκε!', 'ok');
      loadLessons();
    }).catch(function (e) {
      res.className = 'result show err';
      res.textContent = '❌ ' + e.message;
      toast('❌ ' + e.message, 'err');
    }).finally(function () {
      btn.disabled = false;
      btn.textContent = '🚀 Αποστολή & Δημοσίευση';
    });
  });

  $('rebuildBtn').addEventListener('click', function () {
    var btn = this;
    btn.disabled = true;
    btn.textContent = '⏳ Ανακατασκευή…';
    postJSON('/api/rebuild', {}).then(function (j) {
      var res = $('pubResult');
      res.className = 'result show ' + (j.ok ? 'ok' : 'err');
      res.textContent = (j.ok ? '✅ Ολοκληρώθηκε η ανακατασκευή.' : '❌ Αποτυχία ανακατασκευής.') +
        '\n' + (j.output || '').slice(-500);
      toast(j.ok ? '✅ Το υλικό ενημερώθηκε' : '❌ Αποτυχία', j.ok ? 'ok' : 'err');
    }).catch(function (e) { toast('❌ ' + e.message, 'err'); })
      .finally(function () {
        btn.disabled = false;
        btn.textContent = '🔄 Ανακατασκευή υλικού μόνο';
      });
  });

  /* ---------- Αρχικοποίηση ---------- */
  document.querySelectorAll('[data-flag]').forEach(function (el) {
    el.addEventListener('change', updateCommand);
    el.addEventListener('input', updateCommand);
  });
  $('format').addEventListener('change', updateCommand);

  $('markdown').value = [
    '# Τίτλος Μαθήματος',
    '',
    'Σύντομη εισαγωγή στο μάθημα.',
    '',
    '## Θεωρία',
    '',
    'Γράψε εδώ τη θεωρία με **έντονα** και *πλάγια* στοιχεία.',
    '',
    '## Παράδειγμα σε Python',
    '',
    '```python',
    'for i in range(1, 6):',
    '    print("Γραμμή", i)',
    '```',
    '',
    '## Ασκήσεις',
    '',
    '1. Πρώτη άσκηση.',
    '2. Δεύτερη άσκηση.',
    ''
  ].join('\n');

  updateCommand();
  refreshPreview();
})();