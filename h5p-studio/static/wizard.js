/* H5P Studio — AI Οδηγός Δημιουργίας (Wizard 3 βημάτων).
   Επεκτείνει το studio() component της κεντρικής σελίδας. */
(function () {
  const base = window.studio;
  window.studio = function () {
    const s = base();
    Object.assign(s, {
      showWizard: false, wizStep: 1,
      wiz: { class_slug: 'gymnasio-a', subject: 'Πληροφορική', chapter: '',
             goal: 'practice', difficulty: 'medium', notes: '', type: '' },
      wizSuggestions: [], wizPrompts: { content_prompt: '', image_prompt: '' },
      wizPaste: '',

      goalLabel(g) {
        return { intro: 'Εισαγωγή εννοιών', practice: 'Εξάσκηση & Εμπέδωση',
                 visual: 'Οπτική εξερεύνηση', assessment: 'Αξιολόγηση' }[g] || g;
      },

      openWizard() {
        this.showWizard = true; this.wizStep = 1;
        if (this.filterClass) this.wiz.class_slug = this.filterClass;
        if (this.filterSubject) this.wiz.subject = this.filterSubject;
        this.loadSettings();
      },

      async wizNext2() {
        try {
          const d = await this.api('api/wizard/suggest', { method: 'POST', body: JSON.stringify(this.wiz) });
          this.wizSuggestions = d.suggestions;
          this.wiz.type = d.suggestions.length ? d.suggestions[0].type : 'multichoice';
          this.wizStep = 2;
        } catch (e) { this.notify('⚠️ ' + e.message); }
      },

      async wizNext3() {
        try {
          const d = await this.api('api/wizard/prompts', { method: 'POST', body: JSON.stringify(this.wiz) });
          this.wizPrompts = d;
          this.wizStep = 3;
        } catch (e) { this.notify('⚠️ ' + e.message); }
      },

      async wizGenerate() {
        this.busy = true; this.busyMsg = 'Το AI δημιουργεί την άσκηση… (έως ~1 λεπτό)';
        try {
          const d = await this.api('api/wizard/generate', { method: 'POST', body: JSON.stringify(this.wiz) });
          if (d.draft) {
            // hotspots/video: χρειάζονται media → editor με draft
            sessionStorage.setItem('h5pNewDraft', JSON.stringify({
              type: this.wiz.type, title: d.title, data: d.data, meta: this.wiz }));
            location.href = 'edit/new';
          } else {
            location.href = 'edit/' + d.id;
          }
        } catch (e) { this.notify('⚠️ ' + e.message); }
        finally { this.busy = false; }
      },

      async wizPasteJson() {
        this.busy = true; this.busyMsg = 'Μετατροπή JSON σε H5P…';
        try {
          const payload = Object.assign({}, this.wiz, { json_text: this.wizPaste });
          const d = await this.api('api/wizard/paste-json', { method: 'POST', body: JSON.stringify(payload) });
          if (d.draft) {
            sessionStorage.setItem('h5pNewDraft', JSON.stringify({
              type: d.data.type, title: d.title, data: d.data, meta: this.wiz }));
            location.href = 'edit/new';
          } else {
            location.href = 'edit/' + d.id;
          }
        } catch (e) { this.notify('⚠️ ' + e.message); }
        finally { this.busy = false; }
      },
    });
    return s;
  };
})();
