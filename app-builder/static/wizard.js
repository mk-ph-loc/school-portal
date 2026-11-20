/*
 * Δημιουργός Custom Εφαρμογών (App Builder Wizard) — λογική UI (Alpine.js)
 * Όλα τα fetch είναι ΣΧΕΤΙΚΑ (api/…) ώστε να λειτουργούν κάτω από το /app-builder/.
 */
'use strict';

function wizard(loggedIn) {
  return {
    loggedIn: loggedIn,
    password: '',
    loginError: '',
    step: 1,
    mode: 'upload',
    busy: false,
    error: '',
    form: { id: '', title: '', description: '', access: 'all', icon: '🚀', pinned: false, replace: false },
    categoryChoice: 'Γενικά',
    customCategory: '',
    paste: { html: '', css: '', js: '' },
    fileNames: [],
    created: null,          // απάντηση /api/create (app, warnings, embed)
    apps: [],
    lessons: [],
    selectedLesson: '',
    embedTarget: null,      // εφαρμογή της λίστας για embed (παρακάμπτει το created)
    embedMsg: '',
    embedOk: false,
    copied: false,

    init() {
      if (this.loggedIn) this.afterLogin();
    },

    async api(path, options = {}) {
      const res = await fetch(path, options);
      let data = {};
      try { data = await res.json(); } catch (e) { /* κενό σώμα */ }
      if (res.status === 401 && path !== 'api/login') {
        this.loggedIn = false;
        throw new Error('Η συνεδρία έληξε — εισήγαγε ξανά τον κωδικό καθηγητή.');
      }
      if (!res.ok) throw new Error(data.detail || ('Σφάλμα HTTP ' + res.status));
      return data;
    },

    async login() {
      this.loginError = '';
      try {
        await this.api('api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: this.password }),
        });
        this.password = '';
        this.loggedIn = true;
        this.afterLogin();
      } catch (e) {
        this.loginError = e.message;
        this.password = '';
        this.$nextTick(() => { if (this.$refs.pw) this.$refs.pw.focus(); });
      }
    },

    async logout() {
      try { await this.api('api/logout', { method: 'POST' }); } catch (e) { /* αγνόησε */ }
      this.loggedIn = false;
      this.apps = [];
      this.resetWizard();
    },

    afterLogin() {
      this.loadApps();
      this.loadLessons();
    },

    async loadApps() {
      try {
        const data = await this.api('api/list');
        this.apps = data.apps || [];
      } catch (e) { this.error = e.message; }
    },

    async loadLessons() {
      try {
        const data = await this.api('api/lessons');
        this.lessons = data.lessons || [];
      } catch (e) { /* μη κρίσιμο */ }
    },

    gotoStep2() {
      this.error = '';
      const id = this.form.id.trim();
      if (!/^[a-z0-9][a-z0-9-]*$/.test(id)) {
        this.error = 'Το id πρέπει να έχει μόνο πεζά λατινικά, ψηφία και παύλες (π.χ. my-app) και να ξεκινά με γράμμα/ψηφίο.';
        return;
      }
      if (!this.form.title.trim()) {
        this.error = 'Ο τίτλος εφαρμογής είναι υποχρεωτικός.';
        return;
      }
      this.step = 2;
    },

    filesChanged(ev) {
      this.fileNames = [...ev.target.files].map(f => f.name + ' (' + Math.max(1, Math.round(f.size / 1024)) + ' KB)');
    },

    async publish() {
      this.error = '';
      this.busy = true;
      try {
        const fd = new FormData();
        fd.append('id', this.form.id.trim());
        fd.append('title', this.form.title.trim());
        fd.append('description', this.form.description.trim());
        fd.append('category', this.categoryChoice === '__custom__' ? this.customCategory.trim() : this.categoryChoice);
        fd.append('icon', this.form.icon.trim() || '🚀');
        fd.append('access', this.form.access);
        fd.append('pinned', this.form.pinned ? 'true' : 'false');
        fd.append('replace', this.form.replace ? 'true' : 'false');
        fd.append('mode', this.mode);
        if (this.mode === 'paste') {
          fd.append('paste_html', this.paste.html);
          fd.append('paste_css', this.paste.css);
          fd.append('paste_js', this.paste.js);
        } else {
          const files = this.$refs.files ? this.$refs.files.files : [];
          if (!files.length) throw new Error('Διάλεξε πρώτα αρχεία (ένα .zip ή πολλά αρχεία με index.html).');
          for (const f of files) fd.append('files', f, f.name);
        }
        this.created = await this.api('api/create', { method: 'POST', body: fd });
        this.embedTarget = null;
        this.embedMsg = '';
        this.selectedLesson = '';
        this.step = 3;
        this.loadApps();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch (e) {
        this.error = e.message;
      } finally {
        this.busy = false;
      }
    },

    resetWizard() {
      this.step = 1;
      this.error = '';
      this.created = null;
      this.embedTarget = null;
      this.embedMsg = '';
      this.copied = false;
      this.form = { id: '', title: '', description: '', access: 'all', icon: '🚀', pinned: false, replace: false };
      this.categoryChoice = 'Γενικά';
      this.customCategory = '';
      this.paste = { html: '', css: '', js: '' };
      this.fileNames = [];
      if (this.$refs.files) this.$refs.files.value = '';
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    showEmbed(a) {
      // Κουμπί «Ενσωμάτωση σε Μάθημα» της λίστας → Step 3 με snippet της εφαρμογής
      this.embedTarget = a;
      this.created = this.created || { app: a, warnings: [], embed: a.embed };
      this.embedMsg = '';
      this.selectedLesson = '';
      this.step = 3;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    currentEmbed() {
      return (this.embedTarget && this.embedTarget.embed) || (this.created && this.created.embed) || '';
    },

    currentAppId() {
      return (this.embedTarget && this.embedTarget.id) || (this.created && this.created.app && this.created.app.id) || '';
    },

    async copyEmbed() {
      const text = this.currentEmbed();
      try {
        await navigator.clipboard.writeText(text);
      } catch (e) {
        // Fallback για http (μη-secure context) χωρίς clipboard API
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }
      this.copied = true;
      setTimeout(() => { this.copied = false; }, 2000);
    },

    async embedIntoLesson() {
      this.embedMsg = '';
      this.busy = true;
      try {
        const data = await this.api('api/embed-into-lesson', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: this.currentAppId(), lesson: this.selectedLesson }),
        });
        this.embedOk = true;
        this.embedMsg = '✓ Προστέθηκε στο ' + data.lesson + ' — το μάθημα ανακατασκευάζεται αυτόματα (' + data.url + ').';
      } catch (e) {
        this.embedOk = false;
        this.embedMsg = e.message;
      } finally {
        this.busy = false;
      }
    },

    async deleteApp(a) {
      if (!confirm('Οριστική διαγραφή της εφαρμογής «' + a.title + '» (' + a.id + ');\nΟ φάκελος και η κάρτα Dashboard θα αφαιρεθούν. Συνέχεια;')) return;
      this.error = '';
      try {
        await this.api('api/delete/' + encodeURIComponent(a.id), { method: 'DELETE' });
        if (this.created && this.created.app && this.created.app.id === a.id) this.resetWizard();
        if (this.embedTarget && this.embedTarget.id === a.id) this.resetWizard();
        this.loadApps();
      } catch (e) { this.error = e.message; }
    },
  };
}