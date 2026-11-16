/*
 * Ψηφιακή Πύλη Σχολείου & Εργαστηρίου — λογική dashboard (Alpine.js)
 *
 * ΣΗΜΕΙΩΣΗ ΑΣΦΑΛΕΙΑΣ: Ο έλεγχος του κωδικού εδώ γίνεται στον browser και αποτελεί
 * πύλη χρηστικότητας (UX), ΟΧΙ μηχανισμό ασφαλείας. Η πραγματική προστασία των
 * περιοχών /pandoc/ και /docs/teachers/ εφαρμόζεται στον Nginx με HTTP Basic Auth.
 */
const TEACHER_CODE = 'teacher2026';
const STORAGE_KEY = 'schoolPortal.teacher';

function portal() {
  return {
    modal: false,
    password: '',
    error: '',
    unlocked: false,
    year: new Date().getFullYear(),

    // Δικές μου εφαρμογές (custom-apps/) — φορτώνονται από το apps-manifest.json
    // που παράγει το scripts/build-apps-manifest.py από τα app.json των υποφακέλων.
    customApps: [],
    customAppsLoaded: false,
    customAppsError: false,

    classes: [
      { slug: 'gymnasio-a', title: "Α' Γυμνασίου", level: 'Γυμνάσιο', icon: '🅰️',
        desc: 'Πρώτα βήματα στην Πληροφορική, αλγόριθμοι και εισαγωγή στην ψευδογλώσσα.',
        bg: 'bg-sky-100', badge: 'bg-sky-100 text-sky-700' },
      { slug: 'gymnasio-b', title: "Β' Γυμνασίου", level: 'Γυμνάσιο', icon: '🅱️',
        desc: 'Δομές επανάληψης, δυαδικό σύστημα και πρώτα προγράμματα Python.',
        bg: 'bg-cyan-100', badge: 'bg-cyan-100 text-cyan-700' },
      { slug: 'gymnasio-g', title: "Γ' Γυμνασίου", level: 'Γυμνάσιο', icon: '🇬',
        desc: 'Πίνακες, συναρτήσεις και επίλυση προβλημάτων με υπολογιστική σκέψη.',
        bg: 'bg-teal-100', badge: 'bg-teal-100 text-teal-700' },
      { slug: 'lykeio-a', title: "Α' Λυκείου", level: 'Λύκειο', icon: '1️⃣',
        desc: 'Αλγοριθμική, δομές δεδομένων και προγραμματισμός σε Python.',
        bg: 'bg-indigo-100', badge: 'bg-indigo-100 text-indigo-700' },
      { slug: 'lykeio-b', title: "Β' Λυκείου", level: 'Λύκειο', icon: '2️⃣',
        desc: 'Προχωρημένοι αλγόριθμοι, αναζήτηση, ταξινόμηση και πολυπλοκότητα.',
        bg: 'bg-violet-100', badge: 'bg-violet-100 text-violet-700' },
      { slug: 'lykeio-g', title: "Γ' Λυκείου", level: 'Λύκειο', icon: '3️⃣',
        desc: 'Πανελλαδική ύλη: λυμένα θέματα, προσομοιώσεις και επανάληψη.',
        bg: 'bg-fuchsia-100', badge: 'bg-fuchsia-100 text-fuchsia-700' }
    ],

    init() {
      try {
        this.unlocked = sessionStorage.getItem(STORAGE_KEY) === '1';
      } catch (e) {
        this.unlocked = false; // π.χ. απενεργοποιημένο storage
      }
      this.loadCustomApps();
    },

    async loadCustomApps() {
      try {
        const res = await fetch('/apps/apps-manifest.json', { cache: 'no-store' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.customApps = Array.isArray(data.apps) ? data.apps : [];
      } catch (e) {
        this.customApps = [];
        this.customAppsError = true; // π.χ. δεν έχει παραχθεί ακόμη το manifest
      } finally {
        this.customAppsLoaded = true;
      }
    },

    // Κάρτες ορατές στον τρέχοντα χρήστη: access "all" → όλοι,
    // "teachers" → μόνο σε ξεκλείδωτη Λειτουργία Καθηγητή (UX gate, βλ. σημείωση ασφαλείας).
    visibleCustomApps() {
      return this.customApps.filter(a => a.access !== 'teachers' || this.unlocked);
    },

    openModal() {
      this.error = '';
      this.password = '';
      this.modal = true;
      this.$nextTick(() => { if (this.$refs.pw) this.$refs.pw.focus(); });
    },

    unlock() {
      if (this.password === TEACHER_CODE) {
        this.unlocked = true;
        this.modal = false;
        this.error = '';
        this.password = '';
        try { sessionStorage.setItem(STORAGE_KEY, '1'); } catch (e) { /* αγνόησε */ }
        this.$nextTick(() => {
          const el = document.getElementById('kathigites');
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      } else {
        this.error = 'Λανθασμένος κωδικός. Προσπάθησε ξανά.';
        this.password = '';
        this.$nextTick(() => { if (this.$refs.pw) this.$refs.pw.focus(); });
      }
    },

    lock() {
      this.unlocked = false;
      try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* αγνόησε */ }
    }
  };
}