/* H5P Studio — κεντρική σελίδα (βιβλιοθήκη, login, import/export, embed) */
function studio() {
  return {
    teacher: window.LOGGED_IN === true,
    activities: [],
    filterClass: '', filterSubject: '',
    showLogin: false, password: '', loginError: '',
    busy: false, busyMsg: '',
    toast: '',
    typeLabels: {
      multichoice: 'Πολλαπλής Επιλογής', questionset: 'Σετ Ερωτήσεων',
      blanks: 'Συμπλήρωση Κενών', dragtext: 'Σύρε τις Λέξεις',
      hotspots: 'Εικόνα με Hotspots', dialogcards: 'Κάρτες Μνήμης',
      video: 'Διαδραστικό Βίντεο', external: 'Εξωτερικό H5P'
    },
    typeIcons: {
      multichoice: '✅', questionset: '📝', blanks: '✏️', dragtext: '🔀',
      hotspots: '📍', dialogcards: '🃏', video: '🎬', external: '📦'
    },
    // Embed modal
    showEmbed: false, embedActivity: null, embedCode: '', embedHeight: 600,
    lessonGroups: [], embedLesson: '', embedDone: false, embedDoneUrl: '',
    // Settings modal
    showSettings: false,
    settings: { configured: false, base_url: '', model: '', models: [], source: '' },
    settingsForm: { api_key: '', base_url: '', model: '' },
    aiConfigured: false,

    init() {
      this.load();
      if (this.teacher) this.loadSettings();
    },

    notify(msg) {
      this.toast = msg;
      setTimeout(() => { this.toast = ''; }, 3200);
    },

    async api(url, opts = {}) {
      const r = await fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts));
      if (!r.ok) {
        let detail = 'Σφάλμα ' + r.status;
        try { detail = (await r.json()).detail || detail; } catch (e) {}
        throw new Error(detail);
      }
      return r.json();
    },

    async load() {
      const qs = new URLSearchParams();
      if (this.filterClass) qs.set('class_slug', this.filterClass);
      if (this.filterSubject) qs.set('subject', this.filterSubject);
      const d = await this.api('api/activities?' + qs.toString());
      this.activities = d.activities;
      this.teacher = d.teacher;
    },

    async doLogin() {
      this.loginError = '';
      try {
        await this.api('api/login', { method: 'POST', body: JSON.stringify({ password: this.password }) });
        this.teacher = true; this.showLogin = false; this.password = '';
        this.load(); this.loadSettings();
        this.notify('✅ Συνδέθηκες ως καθηγητής.');
      } catch (e) { this.loginError = e.message; }
    },

    async doLogout() {
      await this.api('api/logout', { method: 'POST' });
      this.teacher = false;
      this.load();
      this.notify('Αποσυνδέθηκες.');
    },

    /* --- Γρήγορη δημιουργία με πρότυπο περιεχόμενο ανά τύπο --- */
    defaultData(t) {
      switch (t) {
        case 'multichoice': return {
          question: 'Ποια είναι η σωστή απάντηση;',
          answers: [
            { text: 'Σωστή επιλογή', correct: true, feedback: 'Μπράβο! Αυτή είναι η σωστή απάντηση.', tip: '' },
            { text: 'Λάθος επιλογή Α', correct: false, feedback: 'Όχι — ξανασκέψου το.', tip: '' },
            { text: 'Λάθος επιλογή Β', correct: false, feedback: 'Όχι — δες τις σημειώσεις.', tip: '' }
          ] };
        case 'questionset': return {
          intro: 'Απάντησε στις ερωτήσεις του quiz.', passPercentage: 60,
          questions: [
            { question: 'Ερώτηση 1;', answers: [
              { text: 'Σωστό', correct: true, feedback: 'Σωστά!' },
              { text: 'Λάθος', correct: false, feedback: 'Όχι.' }] },
            { question: 'Ερώτηση 2;', answers: [
              { text: 'Σωστό', correct: true, feedback: 'Σωστά!' },
              { text: 'Λάθος', correct: false, feedback: 'Όχι.' }] }
          ] };
        case 'blanks': return {
          text: '<p>Συμπλήρωσε τα κενά στις παρακάτω προτάσεις.</p>',
          questions: ['<p>Η πρωτεύουσα της Ελλάδας είναι η *Αθήνα:Πόλη με τον Παρθενώνα*.</p>'] };
        case 'dragtext': return {
          taskDescription: '<p>Σύρε τις λέξεις στη σωστή θέση.</p>',
          textField: 'Ο Ήλιος είναι *αστέρας:Τι ουράνιο σώμα είναι;*.\nΗ Σελήνη είναι *δορυφόρος* της Γης.',
          distractors: '*πλανήτης*' };
        case 'hotspots': return { color: '#981d99', icon: 'plus', hotspots: [] };
        case 'dialogcards': return {
          description: '<p>Πάτησε την κάρτα για να δεις την απάντηση.</p>',
          cards: [{ front: 'Όρος / Ερώτηση', back: 'Ορισμός / Απάντηση', tip: '' }] };
        case 'video': return { description: '', interactions: [] };
      }
      return {};
    },

    async quickCreate(t) {
      const title = prompt('Τίτλος νέας δραστηριότητας (' + this.typeLabels[t] + '):',
                           'Νέα άσκηση — ' + this.typeLabels[t]);
      if (!title) return;
      // Οι τύποι με υποχρεωτικά media δημιουργούνται μέσω draft → editor
      if (t === 'hotspots' || t === 'video') {
        this.createDraftActivity({ type: t, title: title, data: this.defaultData(t) });
        return;
      }
      try {
        this.busy = true; this.busyMsg = 'Δημιουργία…';
        const d = await this.api('api/activities', { method: 'POST', body: JSON.stringify({
          type: t, title: title, class_slug: this.filterClass, subject: this.filterSubject,
          data: this.defaultData(t) }) });
        location.href = 'edit/' + d.id;
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; }
    },

    /* Draft (χωρίς media ακόμη): αποθηκεύεται προσωρινά & ανοίγει ο editor
       σε λειτουργία "νέας" δραστηριότητας μέσω sessionStorage. */
    createDraftActivity(d) {
      sessionStorage.setItem('h5pNewDraft', JSON.stringify(d));
      location.href = 'edit/new';
    },
    async importH5P(ev) {
      const f = ev.target.files[0];
      ev.target.value = '';
      if (!f) return;
      this.busy = true; this.busyMsg = 'Import & επικύρωση του .h5p…';
      try {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('class_slug', this.filterClass);
        fd.append('subject', this.filterSubject);
        const r = await fetch('api/import', { method: 'POST', body: fd });
        if (!r.ok) {
          let detail = 'Σφάλμα import';
          try { detail = (await r.json()).detail || detail; } catch (e) {}
          throw new Error(detail);
        }
        const d = await r.json();
        this.notify('✅ Το «' + d.title + '» προστέθηκε στη βιβλιοθήκη!');
        await this.load();
        window.open('play/' + d.id + '/', '_blank');
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; }
    },

    async del(a) {
      if (!confirm('Οριστική διαγραφή του «' + a.title + '»;')) return;
      try {
        await this.api('api/activities/' + a.id, { method: 'DELETE' });
        this.notify('🗑 Διαγράφηκε.');
        this.load();
      } catch (e) { this.notify('⚠️ ' + e.message); }
    },

    /* --- Ενσωμάτωση σε MkDocs --- */
    async openEmbed(a) {
      this.embedActivity = a; this.showEmbed = true;
      this.embedDone = false; this.embedLesson = '';
      await this.loadEmbedCode();
      if (!this.lessonGroups.length) {
        const d = await this.api('api/lessons');
        this.lessonGroups = d.groups;
      }
    },
    async loadEmbedCode() {
      if (!this.embedActivity) return;
      const d = await this.api('api/embed-code/' + this.embedActivity.id + '?height=' + this.embedHeight);
      this.embedCode = d.code;
    },
    async doEmbed() {
      this.busy = true; this.busyMsg = 'Ενσωμάτωση…';
      try {
        const d = await this.api('api/embed/' + this.embedActivity.id, { method: 'POST',
          body: JSON.stringify({ lesson: this.embedLesson, height: this.embedHeight }) });
        this.embedDone = true; this.embedDoneUrl = d.docs_url;
        this.notify('✅ Η άσκηση ενσωματώθηκε στο μάθημα!');
      } catch (e) { this.notify('⚠️ ' + e.message); }
      finally { this.busy = false; }
    },

    async copyText(text, msg) {
      try {
        await navigator.clipboard.writeText(text);
        this.notify('📋 ' + (msg || 'Αντιγράφηκε!'));
      } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta);
        ta.select(); document.execCommand('copy'); ta.remove();
        this.notify('📋 ' + (msg || 'Αντιγράφηκε!'));
      }
    },

    /* --- Ρυθμίσεις AI --- */
    async loadSettings() {
      try {
        const d = await this.api('api/settings');
        this.settings = d;
        this.aiConfigured = d.configured;
        this.settingsForm.model = d.active_model || d.model;
      } catch (e) { /* όχι συνδεδεμένος */ }
    },
    async saveSettings() {
      try {
        await this.api('api/settings', { method: 'POST', body: JSON.stringify(this.settingsForm) });
        this.settingsForm.api_key = '';
        await this.loadSettings();
        this.showSettings = false;
        this.notify('✅ Οι ρυθμίσεις AI αποθηκεύτηκαν.');
      } catch (e) { this.notify('⚠️ ' + e.message); }
    },
  };
}

