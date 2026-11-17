/* H5P Studio — Visual Editor με split-screen ζωντανή προεπισκόπηση */
function editor() {
  return {
    aid: window.ACTIVITY_ID,
    isNew: window.ACTIVITY_ID === 'new',
    meta: { title: '', class_slug: '', subject: '', chapter: '', goal: '', difficulty: '' },
    data: { type: window.ACTIVITY_TYPE || 'multichoice' },
    dirty: false, busy: false, busyMsg: '', toast: '',
    autoPreview: true, previewReady: false, previewTimer: null,
    selectedPin: -1,
    existingVideos: [], pickedVideo: '',
    uploadTarget: null,   // {kind, index} για το async image upload

    typeLabels: {
      multichoice: 'Πολλαπλής Επιλογής', questionset: 'Σετ Ερωτήσεων',
      blanks: 'Συμπλήρωση Κενών', dragtext: 'Σύρε τις Λέξεις',
      hotspots: 'Εικόνα με Hotspots', dialogcards: 'Κάρτες Μνήμης',
      video: 'Διαδραστικό Βίντεο'
    },
    typeLabel() { return this.typeLabels[this.data.type] || this.data.type; },

    async init() {
      // Προστασία από διπλή αρχικοποίηση (Alpine x-init + αυτόματο init)
      if (window.__h5pEditorInitDone) return;
      window.__h5pEditorInitDone = true;
      if (this.isNew) {
        const raw = sessionStorage.getItem('h5pNewDraft');
        if (!raw) { location.href = '/h5p-studio/'; return; }
        sessionStorage.removeItem('h5pNewDraft');
        const d = JSON.parse(raw);
        this.meta.title = d.title || 'Νέα Δραστηριότητα';
        if (d.meta) Object.assign(this.meta, {
          class_slug: d.meta.class_slug || '', subject: d.meta.subject || '',
          chapter: d.meta.chapter || '', goal: d.meta.goal || '',
          difficulty: d.meta.difficulty || '' });
        this.data = Object.assign({ type: d.type }, d.data || {});
        this.data.type = d.type;
        this.dirty = true;
      } else {
        try {
          const d = await this.api('api/activities/' + this.aid);
          this.meta = { title: d.meta.title, class_slug: d.meta.class_slug,
                        subject: d.meta.subject, chapter: d.meta.chapter,
                        goal: d.meta.goal, difficulty: d.meta.difficulty };
          this.data = d.data;
          this.refreshPreview();
        } catch (e) { this.notify('⚠️ ' + e.message); }
      }
      if (this.data.type === 'video') this.loadVideos();
      // Αυτόματη ανανέωση προεπισκόπησης (debounce 2.5s μετά από αλλαγές)
      this.$watch('data', () => {
        this.dirty = true;
        if (this.autoPreview) {
          clearTimeout(this.previewTimer);
          this.previewTimer = setTimeout(() => this.refreshPreview(), 2500);
        }
      });
      window.addEventListener('beforeunload', (e) => {
        if (this.dirty) { e.preventDefault(); e.returnValue = ''; }
      });
    },

    notify(msg) { this.toast = msg; setTimeout(() => { this.toast = ''; }, 3500); },

    async api(url, opts = {}) {
      const r = await fetch('/h5p-studio/' + url,
        Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
      if (!r.ok) {
        let detail = 'Σφάλμα ' + r.status;
        try { detail = (await r.json()).detail || detail; } catch (e) {}
        throw new Error(detail);
      }
      return r.json();
    },

    questions() {
      // Ενιαία διεπαφή για MultiChoice (μία ερώτηση στο data) & QuestionSet (λίστα)
      if (this.data.type === 'multichoice') return [this.data];
      return this.data.questions || [];
    },

    moveItem(arr, i, dir) {
      const j = i + dir;
      if (j < 0 || j >= arr.length) return;
      const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
      this.dirty = true;
    },

    mediaUrl(path) {
      const base = this.isNew ? 'preview-tmp' : this.aid;
      return '/h5p-studio/library/' + base + '/content/' + path;
    },

    /* --- Αποθήκευση --- */
    async save() {
      if (!this.meta.title.trim()) { this.notify('⚠️ Δώσε τίτλο στη δραστηριότητα.'); return; }
      this.busy = true; this.busyMsg = 'Αποθήκευση…';
      try {
        const payload = Object.assign({}, this.meta, { data: this.cleanData() });
        let d;
        if (this.isNew) {
          // Αν έχουν ανέβει media στο preview-tmp, μεταφέρονται παρακάτω μέσω copy
          d = await this.api('api/activities', { method: 'POST',
            body: JSON.stringify(Object.assign({ type: this.data.type }, payload)) });
          await this.copyPreviewMedia(d.id);
          this.dirty = false;
          this.notify('✅ Αποθηκεύτηκε!');
          location.href = '/h5p-studio/edit/' + d.id;
        } else {
          d = await this.api('api/activities/' + this.aid, { method: 'PUT', body: JSON.stringify(payload) });
          this.dirty = false;
          this.notify('✅ Αποθηκεύτηκε!');
          this.refreshPreview();
        }
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; }
    },

    cleanData() {
      // Αντικαθιστά τα paths των media ώστε να δείχνουν στο σωστό φάκελο
      return JSON.parse(JSON.stringify(this.data));
    },

    async copyPreviewMedia(newId) {
      // Τα media ενός νέου activity ανέβηκαν στο preview-tmp/content/ —
      // το backend τα αντιγράφει αυτόματα κατά τη δημιουργία (βλ. /api/activities).
      // Εδώ απλώς ενημερώνουμε τα paths αν χρειαστεί (no-op: ίδια σχετικά paths).
    },

    /* --- Ζωντανή προεπισκόπηση --- */
    async refreshPreview(force) {
      if (this.busy && !force) return;
      try {
        await this.api('api/preview', { method: 'POST',
          body: JSON.stringify({ title: this.meta.title || 'Προεπισκόπηση', data: this.cleanData() }) });
        this.previewReady = true;
        this.$refs.previewFrame.src = '/h5p-studio/play/preview-tmp/?t=' + Date.now();
      } catch (e) {
        // Δεν μπλοκάρουμε τον editor όσο λείπουν υποχρεωτικά πεδία/media
        if (force) this.notify('ℹ️ ' + e.message);
      }
    },

    /* --- Ανέβασμα εικόνων (question / card / hotspot background) --- */
    uploadImage(kind, index) {
      this.uploadTarget = { kind, index };
      this.$refs.imgInput.click();
    },

    async onImagePicked(ev) {
      const f = ev.target.files[0];
      ev.target.value = '';
      if (!f || !this.uploadTarget) return;
      const target = this.isNew ? 'preview-tmp' : this.aid;
      this.busy = true; this.busyMsg = 'Ανέβασμα εικόνας…';
      try {
        const fd = new FormData();
        fd.append('file', f);
        const r = await fetch('/h5p-studio/api/upload/' + target, { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || 'Σφάλμα ανεβάσματος');
        const d = await r.json();
        const img = { path: d.path, mime: d.mime, width: d.width || 0, height: d.height || 0 };
        const t = this.uploadTarget;
        if (t.kind === 'question') this.questions()[t.index].image = img;
        else if (t.kind === 'card') this.data.cards[t.index].image = img;
        else if (t.kind === 'hotspot-bg') this.data.image = img;
        this.dirty = true;
        this.notify('✅ Η εικόνα ανέβηκε.');
        if (this.autoPreview) this.refreshPreview();
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; this.uploadTarget = null; }
    },

    /* --- Hotspots: τοποθέτηση πινέζας με κλικ στην εικόνα --- */
    placePin(ev) {
      const rect = ev.currentTarget.getBoundingClientRect();
      const x = Math.round(((ev.clientX - rect.left) / rect.width) * 1000) / 10;
      const y = Math.round(((ev.clientY - rect.top) / rect.height) * 1000) / 10;
      this.data.hotspots.push({ x, y, header: '', content: '' });
      this.selectedPin = this.data.hotspots.length - 1;
      this.dirty = true;
      this.notify('📍 Πινέζα στο X:' + x + '% Y:' + y + '% — γράψε τίτλο & επεξήγηση παρακάτω.');
    },

    pinGlyph() {
      return { plus: '+', minus: '−', times: '✕', check: '✓', question: '?',
               info: 'i', exclamation: '!' }[this.data.icon] || '+';
    },

    /* --- Blanks: μαρκάρισμα λέξης → *κενό:υπόδειξη* --- */
    makeBlank(qi) {
      const ta = document.getElementById('blank' + qi);
      if (!ta) return;
      const s = ta.selectionStart, e = ta.selectionEnd;
      const text = this.data.questions[qi] || '';
      let sel = text.slice(s, e).trim();
      if (!sel) { this.notify('⚠️ Μαρκάρε πρώτα μια λέξη μέσα στο κείμενο.'); return; }
      if (sel.startsWith('*')) sel = sel.replace(/^\*+|\*+$/g, '');
      const hint = (document.getElementById('hint' + qi) || {}).value || '';
      const blank = '*' + sel + (hint ? ':' + hint : '') + '*';
      this.data.questions[qi] = text.slice(0, s) + blank + text.slice(e);
      this.dirty = true;
      this.notify('⭐ Το «' + sel + '» έγινε κενό!');
    },

    /* --- DragText: μαρκάρισμα λέξης → *λέξη:υπόδειξη* --- */
    makeDragWord() {
      const ta = document.getElementById('dragField');
      if (!ta) return;
      const s = ta.selectionStart, e = ta.selectionEnd;
      const text = this.data.textField || '';
      let sel = text.slice(s, e).trim();
      if (!sel) { this.notify('⚠️ Μαρκάρε πρώτα μια λέξη μέσα στο κείμενο.'); return; }
      if (sel.startsWith('*')) sel = sel.replace(/^\*+|\*+$/g, '');
      const hint = (document.getElementById('dragHint') || {}).value || '';
      const word = '*' + sel + (hint ? ':' + hint : '') + '*';
      this.data.textField = text.slice(0, s) + word + text.slice(e);
      this.dirty = true;
      this.notify('⭐ Το «' + sel + '» έγινε draggable λέξη!');
    },

    addDistractor() {
      const w = prompt('Λέξη-παγίδα (λανθασμένη επιλογή που θα εμφανίζεται):');
      if (!w || !w.trim()) return;
      this.data.distractors = ((this.data.distractors || '') + ' *' + w.trim() + '*').trim();
      this.dirty = true;
    },

    /* --- Interactive Video --- */
    fmtTime(sec) {
      sec = Math.max(0, Math.round(Number(sec) || 0));
      const m = Math.floor(sec / 60), s = sec % 60;
      return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    },
    parseTime(str) {
      const parts = String(str).trim().split(':').map(Number);
      if (parts.length === 2 && parts.every(n => !isNaN(n))) return parts[0] * 60 + parts[1];
      const n = Number(str);
      return isNaN(n) ? 0 : n;
    },

    async loadVideos() {
      try {
        const d = await this.api('api/videos');
        this.existingVideos = d.videos;
      } catch (e) { /* ignore */ }
    },

    async pickExistingVideo() {
      if (!this.pickedVideo) return;
      const target = this.isNew ? 'preview-tmp' : this.aid;
      this.busy = true; this.busyMsg = 'Αντιγραφή βίντεο…';
      try {
        const d = await this.api('api/pick-video/' + target, { method: 'POST',
          body: JSON.stringify({ docs_path: this.pickedVideo }) });
        this.data.video = { path: d.path, mime: d.mime };
        this.dirty = true;
        this.notify('✅ Το βίντεο προστέθηκε στη δραστηριότητα.');
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; }
    },

    async onVideoPicked(ev) {
      const f = ev.target.files[0];
      ev.target.value = '';
      if (!f) return;
      const target = this.isNew ? 'preview-tmp' : this.aid;
      this.busy = true; this.busyMsg = 'Ανέβασμα βίντεο (μπορεί να πάρει λίγο)…';
      try {
        const fd = new FormData();
        fd.append('file', f);
        const r = await fetch('/h5p-studio/api/upload/' + target, { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || 'Σφάλμα ανεβάσματος');
        const d = await r.json();
        this.data.video = { path: d.path, mime: d.mime };
        this.dirty = true;
        this.notify('✅ Το βίντεο ανέβηκε.');
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; }
    },
  };
}

