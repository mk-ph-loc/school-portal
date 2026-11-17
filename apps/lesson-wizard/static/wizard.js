/* wizard.js — Alpine component για το Lesson Wizard (βλ. templates/index.html) */
function wizard(authed) {
  return {
    authed: authed,
    code: '', error: '', notice: '',
    tab: 'lessons',
    lessons: [], phaseTypes: {},
    editing: null, current: null,
    doc: { front_matter: '', header: '', phases: [], teacher_notes: '' },
    files: [], saving: false, uploading: false,
    showNew: false,
    newForm: { class_slug: 'gymnasio-g', subject: 'pliroforiki', lesson: '', title: '', book_url: '' },
    schedule: {},
    activeForm: { tmima: '', minutes: 45, lessonUrl: '' },
    _dragIdx: -1, _idSeq: 0,

    async init() {
      if (this.authed) await this.refresh();
    },

    async api(url, opts) {
      this.error = ''; 
      const r = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts || {}));
      if (r.status === 401) { this.authed = false; throw new Error('Απαιτείται ξανά είσοδος.'); }
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || ('Σφάλμα ' + r.status));
      return data;
    },

    async login() {
      try {
        await this.api('api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: this.code }) });
        this.authed = true; this.code = '';
        await this.refresh();
      } catch (e) { this.error = e.message; }
    },

    async logout() {
      await fetch('api/logout', { method: 'POST', credentials: 'same-origin' });
      this.authed = false; this.editing = null;
    },

    async refresh() {
      try {
        const d = await this.api('api/lessons');
        this.lessons = d.lessons; this.phaseTypes = d.phase_types;
        this.schedule = await this.api('api/schedule');
      } catch (e) { this.error = e.message; }
    },

    // ---------------- Editor ----------------
    lessonKey(l) { return l.class_slug + '/' + l.subject + '/' + l.lesson; },
    lessonUrl() { return this.current ? this.current.url : '/docs/'; },

    async openLesson(l) {
      try {
        const d = await this.api('api/lesson/' + this.lessonKey(l));
        this.current = l;
        this.editing = this.lessonKey(l);
        this.doc = {
          front_matter: d.front_matter, header: d.header,
          teacher_notes: d.teacher_notes,
          phases: d.phases.map(p => Object.assign({ _open: false, _id: ++this._idSeq }, p)),
        };
        this.files = d.files;
        this.notice = '';
        window.scrollTo(0, 0);
      } catch (e) { this.error = e.message; }
    },

    closeLesson() { this.editing = null; this.current = null; this.refresh(); },

    totalDuration() { return this.doc.phases.reduce((s, p) => s + (parseInt(p.duration, 10) || 0), 0); },

    phaseIcon(t) { return (this.phaseTypes[t] || {}).icon || '🧩'; },
    phaseColor(t) {
      return { aformisi: '#ff9800', syzitisi: '#26a69a', parousiasi: '#3f51b5',
               drastiriotita: '#8e24aa', aksiologisi: '#43a047', kleisimo: '#78909c' }[t] || '#94a3b8';
    },

    addPhase(type) {
      const meta = this.phaseTypes[type] || {};
      this.doc.phases.push({
        _id: ++this._idSeq, _open: true, type: type,
        title: meta.label || 'Φάση', duration: meta.duration || 5,
        body: '## ' + (meta.icon || '') + ' ' + (meta.label || 'Φάση') + '\n\nΓράψε εδώ το περιεχόμενο…',
      });
    },

    removePhase(i) {
      if (confirm('Διαγραφή της φάσης «' + this.doc.phases[i].title + '»;')) this.doc.phases.splice(i, 1);
    },

    movePhase(i, dir) {
      const j = i + dir;
      if (j < 0 || j >= this.doc.phases.length) return;
      const arr = this.doc.phases;
      [arr[i], arr[j]] = [arr[j], arr[i]];
    },

    dragStart(i, ev) { this._dragIdx = i; ev.currentTarget.classList.add('dragging'); ev.dataTransfer.effectAllowed = 'move'; },
    dragEnd(ev) { ev.currentTarget.classList.remove('dragging'); this._dragIdx = -1; },
    dropOn(i, ev) {
      ev.currentTarget.classList.remove('drag-over');
      if (this._dragIdx < 0 || this._dragIdx === i) return;
      const arr = this.doc.phases;
      const [moved] = arr.splice(this._dragIdx, 1);
      arr.splice(i, 0, moved);
      this._dragIdx = -1;
    },

    insertSnippet(ph, kind) {
      const snippets = {
        image: '\n![Λεζάντα εικόνας](ΟΝΟΜΑ-ΕΙΚΟΝΑΣ.png)\n',
        pdf: '\n<object data="ΟΝΟΜΑ.pdf" type="application/pdf" width="100%" height="480px">\n<p>📄 <a href="ΟΝΟΜΑ.pdf" target="_blank">Άνοιγμα PDF</a></p>\n</object>\n',
        iframe: '\n<iframe src="ΟΝΟΜΑ.html" width="100%" height="600" style="border:1px solid #c5cae9;border-radius:8px;" loading="lazy" title="Διαδραστικό"></iframe>\n',
        quiz: '\n<div class="quiz" data-quiz=\'[\n {"q":"Ερώτηση;","options":["Α","Β","Γ"],"answer":0,"explain":"Επεξήγηση."}\n]\'></div>\n',
        python: '\n```python\n# Γράψε τον κώδικά σου — ο μαθητής πατά ▶ Εκτέλεση\nprint("Γεια!")\n```\n',
        exams: '\n**Παραδοτέο:** [📤 Παράδοση Εργασιών](/exams/){target=_blank} με τίτλο **«ΤΙΤΛΟΣ»**.\n',
      };
      ph.body += snippets[kind] || '';
      ph._open = true;
    },

    async saveLesson() {
      this.saving = true; this.notice = '';
      try {
        const payload = {
          front_matter: this.doc.front_matter,
          header: this.doc.header,
          teacher_notes: this.doc.teacher_notes,
          phases: this.doc.phases.map(p => ({ type: p.type, title: p.title, duration: p.duration, body: p.body })),
        };
        const d = await this.api('api/lesson/' + this.editing, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        this.notice = '✅ Αποθηκεύτηκε (' + d.phases + ' φάσεις, ' + d.duration + '΄). Το site ξαναχτίζεται αυτόματα — έλεγξε την Προβολή σε ~1 λεπτό.';
      } catch (e) { this.error = e.message; }
      this.saving = false;
    },

    async createLesson() {
      try {
        const d = await this.api('api/lesson-new', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.newForm),
        });
        this.showNew = false;
        await this.refresh();
        const l = this.lessons.find(x => x.url === d.url);
        if (l) this.openLesson(l);
      } catch (e) { this.error = e.message; }
    },

    // ---------------- Υλικό ----------------
    fileIcon(name) {
      const ext = name.split('.').pop().toLowerCase();
      return { png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼', webp: '🖼',
               pdf: '📄', html: '🎮', mp4: '🎬', webm: '🎬', mp3: '🎵', pptx: '📽️', odp: '📽️', zip: '🗜' }[ext] || '📎';
    },
    fmtSize(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; },

    async uploadFile(ev) {
      const f = ev.target.files[0];
      if (!f) return;
      this.uploading = true; this.error = '';
      try {
        const fd = new FormData();
        fd.append('file', f);
        const d = await this.api('api/upload/' + this.editing, { method: 'POST', body: fd });
        this.files.push({ name: d.name, size: d.size });
        this.notice = '✅ Ανέβηκε: ' + d.name + ' — μπορείς τώρα να το ενσωματώσεις σε φάση με τα κουμπιά Εισαγωγής.';
      } catch (e) { this.error = e.message; }
      this.uploading = false;
      ev.target.value = '';
    },

    async deleteFile(name) {
      if (!confirm('Διαγραφή του «' + name + '»; (κρατιέται backup)')) return;
      try {
        await this.api('api/file/' + this.editing + '/' + encodeURIComponent(name), { method: 'DELETE' });
        this.files = this.files.filter(f => f.name !== name);
      } catch (e) { this.error = e.message; }
    },

    // ---------------- Ωράριο ----------------
    async uploadSchedule(ev) {
      const f = ev.target.files[0];
      if (!f) return;
      this.error = ''; this.notice = '';
      try {
        const fd = new FormData();
        fd.append('file', f);
        const d = await this.api('api/schedule/upload', { method: 'POST', body: fd });
        this.schedule = await this.api('api/schedule');
        this.notice = '✅ Ωράριο ενημερώθηκε: ' + d.tmimata + ' τμήματα, ' + d.periods + ' ώρες, ' + d.entries + ' καταχωρήσεις.';
      } catch (e) { this.error = e.message; }
      ev.target.value = '';
    },

    async setActive(clear) {
      this.error = ''; this.notice = '';
      try {
        const l = this.lessons.find(x => x.url === this.activeForm.lessonUrl);
        const payload = clear
          ? { tmima: this.activeForm.tmima, clear: true }
          : { tmima: this.activeForm.tmima, minutes: this.activeForm.minutes,
              title: l ? l.title : '', url: this.activeForm.lessonUrl };
        await this.api('api/active', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        this.notice = clear ? '⏹ Το override διακόπηκε για το ' + this.activeForm.tmima
                            : '▶ Ενεργό μάθημα για ' + this.activeForm.tmima + ': ' + (l ? l.title : '') + ' (' + this.activeForm.minutes + '΄)';
      } catch (e) { this.error = e.message; }
    },
  };
}