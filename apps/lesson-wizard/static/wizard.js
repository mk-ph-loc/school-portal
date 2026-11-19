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
    // --- Φίλτρα / tags / αγαπημένα ---
    filters: { cls: '', subject: '', tag: '', q: '', fav: false },
    tagModal: null, tagInput: '',
    quickModal: null, quickForm: { tmima: '', minutes: 45 },
    // --- Πλέγμα ωραρίου ---
    days: ['Δευτέρα', 'Τρίτη', 'Τετάρτη', 'Πέμπτη', 'Παρασκευή'],
    gridTmima: '', cellMenu: null, cellEditing: false,
    cellForm: { title: '', url: '' }, _cellDrag: null,
    virtual: { on: false, day: 'Δευτέρα', time: '10:30' },
    showVirtual: false, nowTick: Date.now(),
    showTmimaForm: false, tmimaForm: { name: '', class_slug: 'gymnasio-g' },
    showPeriodsForm: false, periodsForm: [],
    // --- Μετάδοση ---
    broadcast: null, bcForm: { tmima: '', minutes: 45, lessonUrl: '', message: '' },
    // --- File browser ---
    fs: { path: '', dirs: [], files: [], view_url: '/docs/', lesson_key: null },
    fsEditor: null, fsSaving: false,
    // --- Βιβλία ---
    books: [], bookForm: { title: '', slug: '', class_slug: '' },
    bookLink: null, bookLinkForm: { lesson_key: '', page: 1 },

    async init() {
      try {
        const v = JSON.parse(localStorage.getItem('wizard-virtual') || 'null');
        if (v && v.day && v.time) this.virtual = v;
        this.gridTmima = localStorage.getItem('wizard-grid-tmima') || '';
      } catch (e) {}
      this.$watch('virtual', v => { try { localStorage.setItem('wizard-virtual', JSON.stringify(v)); } catch (e) {} });
      this.$watch('gridTmima', v => { try { localStorage.setItem('wizard-grid-tmima', v); } catch (e) {} });
      setInterval(() => { this.nowTick = Date.now(); }, 20000);   // ρολόι συστήματος → χρωματισμός «τώρα»
      if (this.authed) {
        await this.refresh();
        await this.handleDeepLink();
      }
    },

    /** Deep-links: #schedule → καρτέλα Ωράριο· #edit=<cls>/<subj>/<lesson> →
     *  άμεσο άνοιγμα του visual editor (π.χ. από το ✏️ στις σελίδες /docs/). */
    async handleDeepLink() {
      const h = location.hash || '';
      if (h === '#schedule') { this.tab = 'schedule'; return; }
      const m = h.match(/^#edit=([\w-]+\/[\w-]+\/[\w-]+)$/);
      if (m) {
        this.tab = 'lessons';
        await this.openLessonByKey(m[1]);
        if (!this.editing) this.error = 'Το μάθημα δεν βρέθηκε: ' + m[1];
      }
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
        if (!this.gridTmima || !(this.schedule.tmimata || []).some(t => t.name === this.gridTmima)) {
          this.gridTmima = (this.schedule.tmimata[0] || {}).name || '';
        }
        const pub = await this.api('api/schedule/public');
        this.broadcast = pub.broadcast || null;
        const b = await this.api('api/books');
        this.books = b.books;
        await this.fsOpen(this.fs.path);
      } catch (e) { this.error = e.message; }
    },

    // ---------------- Φίλτρα / tags / αγαπημένα ----------------
    allSubjects() { return [...new Set(this.lessons.map(l => l.subject))].sort(); },
    allTags() { return [...new Set(this.lessons.flatMap(l => l.tags || []))].sort(); },
    classLabel(slug) { const c = this.lessons.find(l => l.class_slug === slug); return c ? c.class_label : slug; },

    filteredLessons() {
      const f = this.filters, q = f.q.trim().toLowerCase();
      return this.lessons.filter(l =>
        (!f.cls || l.class_slug === f.cls) &&
        (!f.subject || l.subject === f.subject) &&
        (!f.tag || (l.tags || []).includes(f.tag)) &&
        (!f.fav || l.favorite) &&
        (!q || l.title.toLowerCase().includes(q) || l.lesson.includes(q) ||
         (l.tags || []).some(t => t.toLowerCase().includes(q)))
      ).sort((a, b) => (b.favorite - a.favorite) || a.title.localeCompare(b.title, 'el'));
    },

    async toggleFav(l) {
      try {
        const d = await this.api('api/meta/' + this.lessonKey(l), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ favorite: !l.favorite }),
        });
        l.favorite = d.favorite;
      } catch (e) { this.error = e.message; }
    },

    editTags(l) { this.tagModal = l; this.tagInput = (l.tags || []).join(', '); },
    addTagSuggestion(t) {
      const cur = this.tagInput.split(',').map(x => x.trim()).filter(Boolean);
      if (!cur.includes(t)) cur.push(t);
      this.tagInput = cur.join(', ');
    },
    async saveTags() {
      const l = this.tagModal; if (!l) return;
      const tags = this.tagInput.split(',').map(x => x.trim()).filter(Boolean);
      try {
        const d = await this.api('api/meta/' + this.lessonKey(l), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tags }),
        });
        l.tags = d.tags; this.tagModal = null;
        this.notice = '🏷 Tags αποθηκεύτηκαν — θα εμφανίζονται και στη σελίδα του μαθήματος.';
      } catch (e) { this.error = e.message; }
    },

    quickActive(l) {
      this.quickModal = { mode: 'active', lesson: l };
      this.quickForm = { tmima: this.gridTmima || (this.schedule.tmimata[0] || {}).name || '', minutes: 45 };
    },
    quickBroadcast(l) {
      this.quickModal = { mode: 'broadcast', lesson: l };
      this.quickForm = { tmima: '', minutes: 45 };
    },
    async runQuick() {
      const m = this.quickModal; if (!m) return;
      const l = m.lesson;
      try {
        if (m.mode === 'active') {
          if (!this.quickForm.tmima) throw new Error('Διάλεξε τμήμα.');
          await this.api('api/active', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmima: this.quickForm.tmima, minutes: this.quickForm.minutes, title: l.title, url: l.url }),
          });
          this.notice = '▶ Ενεργό μάθημα για ' + this.quickForm.tmima + ': ' + l.title;
        } else {
          const d = await this.api('api/broadcast', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tmima: this.quickForm.tmima, minutes: this.quickForm.minutes, title: l.title, url: l.url }),
          });
          this.broadcast = d.broadcast;
          this.notice = '📡 Μετάδοση: ' + l.title + ' → ' + (this.quickForm.tmima || 'όλα τα τμήματα');
        }
        this.quickModal = null;
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

    // ---------------- Μετάδοση (broadcast) ----------------
    async setBroadcast(clear) {
      this.error = ''; this.notice = '';
      try {
        const l = this.lessons.find(x => x.url === this.bcForm.lessonUrl);
        const payload = clear ? { clear: true }
          : { tmima: this.bcForm.tmima, minutes: this.bcForm.minutes,
              title: l ? l.title : '', url: this.bcForm.lessonUrl, message: this.bcForm.message };
        if (!clear && !l) throw new Error('Διάλεξε μάθημα για μετάδοση.');
        const d = await this.api('api/broadcast', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
        });
        this.broadcast = d.broadcast;
        this.notice = clear ? '⏹ Η μετάδοση σταμάτησε.' : '📡 Μετάδοση σε εξέλιξη: ' + l.title;
      } catch (e) { this.error = e.message; }
    },

    // ---------------- Πλέγμα ωραρίου ----------------
    nowInfo() {
      // Επιστρέφει {day, period, hhmm} βάσει πραγματικής ή εικονικής ώρας.
      void this.nowTick;                       // reactive ρολόι (20″)
      let day, hhmm;
      if (this.virtual.on) {
        day = this.virtual.day; hhmm = this.virtual.time;
      } else {
        const n = new Date();
        day = ['Κυριακή', ...this.days, 'Σάββατο'][n.getDay()];
        hhmm = ('0' + n.getHours()).slice(-2) + ':' + ('0' + n.getMinutes()).slice(-2);
      }
      let period = null;
      (this.schedule.periods || []).forEach((p, i) => {
        if (hhmm >= p.start && hhmm < p.end) period = i + 1;
      });
      return { day, period, hhmm };
    },
    clockLabel() {
      const n = this.nowInfo();
      const base = n.day + ' ' + n.hhmm + (n.period ? ' · ' + n.period + 'η ώρα' : ' · εκτός ωραρίου');
      return (this.virtual.on ? 'ΕΙΚΟΝΙΚΗ: ' : '') + base;
    },
    cellEntry(day, period) {
      return (((this.schedule.timetable || {})[this.gridTmima] || {})[day] || {})[String(period)] || null;
    },
    cellClass(day, period) {
      const n = this.nowInfo();
      const cls = [];
      if (this.cellEntry(day, period)) cls.push('filled');
      if (n.period === period) cls.push('now-col');
      if (n.day === day && n.period === period) cls.push('now');
      return cls.join(' ');
    },
    openCell(day, period) {
      this.cellMenu = { day, period, entry: this.cellEntry(day, period) };
      this.cellEditing = false;
      this.cellForm = { title: this.cellMenu.entry?.title || '', url: this.cellMenu.entry?.url || '' };
    },
    cellEdit() { this.cellEditing = true; },
    pickLessonForCell(url) {
      const l = this.lessons.find(x => x.url === url);
      if (l) { this.cellForm.title = l.title; this.cellForm.url = l.url; }
    },
    async saveCell() {
      if (!this.cellMenu) return;
      try {
        const d = await this.api('api/schedule/cell', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tmima: this.gridTmima, day: this.cellMenu.day, period: String(this.cellMenu.period),
                                 title: this.cellForm.title, url: this.cellForm.url }),
        });
        this.schedule = d.schedule;
        this.cellMenu = null;
        this.notice = '✅ Το κελί αποθηκεύτηκε — οι μαθητές το βλέπουν άμεσα.';
      } catch (e) { this.error = e.message; }
    },
    async cellClear() {
      if (!this.cellMenu || !confirm('Καθαρισμός κελιού;')) return;
      try {
        const d = await this.api('api/schedule/cell', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tmima: this.gridTmima, day: this.cellMenu.day, period: String(this.cellMenu.period), clear: true }),
        });
        this.schedule = d.schedule; this.cellMenu = null;
      } catch (e) { this.error = e.message; }
    },
    async cellActivate() {
      const m = this.cellMenu; if (!m || !m.entry) return;
      try {
        await this.api('api/active', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tmima: this.gridTmima, minutes: 45, title: m.entry.title, url: m.entry.url }),
        });
        this.notice = '▶ Ενεργό μάθημα για ' + this.gridTmima + ': ' + m.entry.title + ' (45΄)';
        this.cellMenu = null;
      } catch (e) { this.error = e.message; }
    },
    async cellBroadcast() {
      const m = this.cellMenu; if (!m || !m.entry) return;
      try {
        const d = await this.api('api/broadcast', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tmima: this.gridTmima, minutes: 45, title: m.entry.title, url: m.entry.url }),
        });
        this.broadcast = d.broadcast;
        this.notice = '📡 Μετάδοση: ' + m.entry.title + ' → ' + this.gridTmima;
        this.cellMenu = null;
      } catch (e) { this.error = e.message; }
    },
    cellDragStart(day, period, ev) {
      this._cellDrag = { tmima: this.gridTmima, day, period: String(period) };
      ev.dataTransfer.effectAllowed = 'copyMove';
      ev.dataTransfer.setData('text/plain', JSON.stringify(this._cellDrag));
    },
    async cellDrop(day, period, ev) {
      ev.currentTarget.classList.remove('drag-over');
      let src = this._cellDrag;
      try { src = JSON.parse(ev.dataTransfer.getData('text/plain')) || src; } catch (e) {}
      this._cellDrag = null;
      if (!src || (src.day === day && String(src.period) === String(period) && src.tmima === this.gridTmima)) return;
      try {
        const d = await this.api('api/schedule/move', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from: src, to: { tmima: this.gridTmima, day, period: String(period) },
                                 copy: ev.ctrlKey || ev.metaKey }),
        });
        this.schedule = d.schedule;
        this.notice = (ev.ctrlKey || ev.metaKey) ? '📋 Το κελί αντιγράφηκε.' : '↔ Το κελί μετακινήθηκε.';
      } catch (e) { this.error = e.message; }
    },
    async addTmima() {
      try {
        const d = await this.api('api/schedule/tmima', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.tmimaForm),
        });
        this.schedule = d.schedule; this.gridTmima = this.tmimaForm.name.trim();
        this.tmimaForm.name = ''; this.showTmimaForm = false;
      } catch (e) { this.error = e.message; }
    },
    async removeTmima() {
      if (!this.gridTmima || !confirm('Διαγραφή τμήματος «' + this.gridTmima + '» και όλων των κελιών του;')) return;
      try {
        const d = await this.api('api/schedule/tmima', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: this.gridTmima, remove: true }),
        });
        this.schedule = d.schedule;
        this.gridTmima = (d.schedule.tmimata[0] || {}).name || '';
      } catch (e) { this.error = e.message; }
    },
    openPeriodsForm() {
      this.periodsForm = (this.schedule.periods || []).map(p => ({ ...p }));
      if (!this.periodsForm.length) this.periodsForm = [{ start: '08:15', end: '09:00' }];
      this.showPeriodsForm = !this.showPeriodsForm;
    },
    async savePeriods() {
      try {
        const d = await this.api('api/schedule/periods', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ periods: this.periodsForm }),
        });
        this.schedule = d.schedule; this.showPeriodsForm = false;
        this.notice = '✅ Οι διδακτικές ώρες ενημερώθηκαν.';
      } catch (e) { this.error = e.message; }
    },
    // ---------------- Γενικός file browser ----------------
    joinPath(a, b) { return a ? a + '/' + b : b; },
    fsCrumbs() {
      if (!this.fs.path) return [];
      const parts = this.fs.path.split('/');
      return parts.map((p, i) => ({ name: p, path: parts.slice(0, i + 1).join('/') }));
    },
    isLessonDir(path) {
      return this.lessons.some(l => 'mathimata/' + this.lessonKey(l) === path);
    },
    async fsOpen(path) {
      try {
        this.fs = await this.api('api/fs/list?path=' + encodeURIComponent(path || ''));
      } catch (e) { this.error = e.message; }
    },
    async openLessonByKey(key) {
      const l = this.lessons.find(x => this.lessonKey(x) === key);
      if (l) { this.tab = 'lessons'; await this.openLesson(l); }
    },
    async fsEdit(f) {
      try {
        const path = this.joinPath(this.fs.path, f.name);
        // index.md ημερήσιου μαθήματος → visual editor φάσεων αντί για raw text
        if (f.name === 'index.md' && this.isLessonDir(this.fs.path)) {
          return this.openLessonByKey(this.fs.path.replace(/^mathimata\//, ''));
        }
        const d = await this.api('api/fs/read?path=' + encodeURIComponent(path));
        this.fsEditor = { path: d.path, content: d.content, view_url: d.view_url };
      } catch (e) { this.error = e.message; }
    },
    async fsSave() {
      if (!this.fsEditor) return;
      this.fsSaving = true;
      try {
        await this.api('api/fs/save', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: this.fsEditor.path, content: this.fsEditor.content }),
        });
        this.notice = '✅ Αποθηκεύτηκε: ' + this.fsEditor.path + ' (auto-rebuild σε ~1 λεπτό).';
        this.fsEditor = null;
        await this.fsOpen(this.fs.path);
      } catch (e) { this.error = e.message; }
      this.fsSaving = false;
    },
    async fsUpload(ev) {
      const f = ev.target.files[0];
      if (!f) return;
      try {
        const fd = new FormData();
        fd.append('file', f);
        const d = await this.api('api/fs/upload?path=' + encodeURIComponent(this.fs.path), { method: 'POST', body: fd });
        this.notice = '✅ Ανέβηκε: ' + d.name + ' στον φάκελο ' + (this.fs.path || 'docs') + '.';
        await this.fsOpen(this.fs.path);
      } catch (e) { this.error = e.message; }
      ev.target.value = '';
    },
    async fsMkdir() {
      const name = prompt('Όνομα νέου φακέλου (λατινικά/greeklish, χωρίς κενά):');
      if (!name) return;
      try {
        await this.api('api/fs/mkdir', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: this.fs.path, name }),
        });
        await this.fsOpen(this.fs.path);
      } catch (e) { this.error = e.message; }
    },
    async fsDelete(f) {
      if (!confirm('Διαγραφή του «' + f.name + '»; (κρατιέται backup)')) return;
      try {
        await this.api('api/fs/delete?path=' + encodeURIComponent(this.joinPath(this.fs.path, f.name)), { method: 'DELETE' });
        await this.fsOpen(this.fs.path);
      } catch (e) { this.error = e.message; }
    },

    // ---------------- Βιβλιοθήκη βιβλίων ----------------
    async uploadBook(ev) {
      const f = ev.target.files[0];
      if (!f) return;
      this.error = ''; this.notice = '⏳ Ανέβασμα βιβλίου…';
      try {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('title', this.bookForm.title);
        fd.append('slug', this.bookForm.slug);
        fd.append('class_slug', this.bookForm.class_slug);
        const d = await this.api('api/books/upload', { method: 'POST', body: fd });
        this.notice = '✅ Το βιβλίο «' + d.book.title + '» μπήκε στη βιβλιοθήκη (' + (d.book.pages || '?') + ' σελίδες).';
        this.bookForm = { title: '', slug: '', class_slug: '' };
        const b = await this.api('api/books');
        this.books = b.books;
      } catch (e) { this.error = e.message; this.notice = ''; }
      ev.target.value = '';
    },
    async deleteBook(b) {
      if (!confirm('Διαγραφή του βιβλίου «' + b.title + '» από τη βιβλιοθήκη; (κρατιέται backup)')) return;
      try {
        await this.api('api/books/' + b.slug, { method: 'DELETE' });
        this.books = this.books.filter(x => x.slug !== b.slug);
      } catch (e) { this.error = e.message; }
    },
    openBookLink(b) {
      this.bookLink = b;
      this.bookLinkForm = { lesson_key: this.editing || '', page: 1 };
    },
    bookLinkMd() {
      const b = this.bookLink;
      return '[📖 ' + b.title + ', σελ. ' + this.bookLinkForm.page + '](' + b.file + '#page=' + this.bookLinkForm.page + '){target=_blank}';
    },
    async insertBookLink() {
      if (!this.bookLinkForm.lesson_key) { this.error = 'Διάλεξε μάθημα.'; return; }
      try {
        const d = await this.api('api/books/link', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slug: this.bookLink.slug, page: this.bookLinkForm.page,
                                 lesson_key: this.bookLinkForm.lesson_key }),
        });
        this.notice = d.already ? 'ℹ️ Το link υπάρχει ήδη στο μάθημα.' : '✅ Το link προστέθηκε στην κεφαλίδα του μαθήματος.';
        this.bookLink = null;
      } catch (e) { this.error = e.message; }
    },
    async copyBookLink() {
      try {
        await navigator.clipboard.writeText(this.bookLinkMd());
        this.notice = '📋 Αντιγράφηκε: ' + this.bookLinkMd();
      } catch (e) { prompt('Αντιγραφή χειροκίνητα:', this.bookLinkMd()); }
    },
  };
}