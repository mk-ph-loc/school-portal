/*
 * Ψηφιακή Πύλη Σχολείου & Εργαστηρίου — λογική dashboard (Alpine.js)
 *
 * ΣΗΜΕΙΩΣΗ ΑΣΦΑΛΕΙΑΣ: Ο έλεγχος του κωδικού εδώ γίνεται στον browser και αποτελεί
 * πύλη χρηστικότητας (UX), ΟΧΙ μηχανισμό ασφαλείας. Η πραγματική προστασία των
 * περιοχών /pandoc/ και /docs/teachers/ εφαρμόζεται στον Nginx με HTTP Basic Auth.
 */
/* Ο κωδικός φορτώνεται από το assets/teacher-code.js (παράγεται από το
 * install.sh — ίδιος με τα apps/common.auth). Fallback μόνο για dev χωρίς install. */
const TEACHER_CODE_FALLBACK = 'teacher2026';
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

    // Ομαδοποίηση & αναζήτηση στην ενότητα «Δικές μου Εφαρμογές»
    categoryFilter: 'all',
    searchQuery: '',

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
      this.preferHttpsForSecureContextTools();
    },

    // Εργαλεία που χρειάζονται Web Crypto API (π.χ. Excalidraw live collaboration
    // & Export to Link) λειτουργούν ΜΟΝΟ σε secure context (HTTPS/localhost).
    // Αν το dashboard ανοίχτηκε με plain HTTP σε LAN IP, οι κάρτες με
    // data-https-hint οδηγούν αυτόματα στην https:// έκδοση της ίδιας σελίδας.
    preferHttpsForSecureContextTools() {
      if (window.isSecureContext) return; // ήδη HTTPS ή localhost
      document.querySelectorAll('a[data-https-hint]').forEach(a => {
        try {
          const url = new URL(a.getAttribute('href'), window.location.href);
          url.protocol = 'https:';
          a.setAttribute('href', url.toString());
        } catch (e) { /* αγνόησε άκυρα href */ }
      });
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

    // Κανονικοποίηση για αναζήτηση: πεζά + αφαίρεση τόνων (NFD), ώστε π.χ.
    // «δυαδικό» να βρίσκει «Δυαδικού» ανεξάρτητα από τόνους/κεφαλαία.
    normalizeText(s) {
      return String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    },

    // Πρόσβαση ανά ρόλο: access "all" → όλοι, "teachers" → μόνο σε ξεκλείδωτη
    // Λειτουργία Καθηγητή (UX gate, βλ. σημείωση ασφαλείας στην κορυφή του αρχείου).
    accessibleCustomApps() {
      return this.customApps.filter(a => a.access !== 'teachers' || this.unlocked);
    },

    // Κάρτες ορατές στον τρέχοντα χρήστη: access-filter + tab κατηγορίας +
    // αναζήτηση σε title/description. ΔΙΑΤΗΡΕΙ τη σειρά του manifest
    // (pinned-first, μετά αλφαβητικά) — δεν γίνεται επαναταξινόμηση εδώ.
    visibleCustomApps() {
      const q = this.normalizeText(this.searchQuery.trim());
      return this.accessibleCustomApps().filter(a => {
        if (this.categoryFilter !== 'all' && a.category !== this.categoryFilter) return false;
        if (!q) return true;
        return this.normalizeText(a.title + ' ' + a.description).includes(q);
      });
    },

    // Μετρητές ανά κατηγορία ΥΠΟΨΗ του access-filter: οι teachers-only κάρτες
    // δεν μετράνε όσο η Λειτουργία Καθηγητή είναι κλειδωμένη.
    categoryCounts() {
      const counts = { all: 0 };
      for (const a of this.accessibleCustomApps()) {
        counts.all++;
        counts[a.category] = (counts[a.category] || 0) + 1;
      }
      return counts;
    },

    // Σταθερές τυποποιημένες κατηγορίες + δυναμικά όποιες άλλες υπάρχουν στο
    // manifest (π.χ. παλιές ταξικές ή ελεύθερες), ώστε να μη χάνονται κάρτες.
    categoryTabs() {
      const tabs = [
        { id: 'all', label: '🗂️ Όλες' },
        { id: 'Προγραμματισμός', icon: '💻' },
        { id: 'Γραφικά & Πολυμέσα', icon: '🎨' },
        { id: 'Τεχνολογία & ΤΝ', icon: '🤖' },
        { id: 'Υλικό & Δεδομένα', icon: '🔢' }
      ];
      const known = new Set(tabs.map(t => t.id));
      for (const a of this.customApps) {
        if (a.category && !known.has(a.category)) {
          known.add(a.category);
          tabs.push({ id: a.category, icon: '🏷️' });
        }
      }
      return tabs;
    },

    // Χρώματα badge ανά κατηγορία — ΜΟΝΟ κλάσεις που χρησιμοποιούνται ήδη στο
    // dashboard (sky/violet/amber/emerald), με ασφαλές slate fallback.
    categoryBadgeClass(cat) {
      const map = {
        'Προγραμματισμός': 'bg-sky-100 text-sky-700',
        'Γραφικά & Πολυμέσα': 'bg-violet-100 text-violet-700',
        'Τεχνολογία & ΤΝ': 'bg-amber-100 text-amber-700',
        'Υλικό & Δεδομένα': 'bg-emerald-100 text-emerald-700'
      };
      return map[cat] || 'bg-slate-100 text-slate-600';
    },

    // Κενή κατάσταση αναζήτησης/φίλτρου: υπάρχουν εφαρμογές αλλά καμία δεν ταιριάζει.
    noCustomAppMatches() {
      return this.customAppsLoaded && !this.customAppsError &&
             this.accessibleCustomApps().length > 0 && this.visibleCustomApps().length === 0;
    },

    openModal() {
      this.error = '';
      this.password = '';
      this.modal = true;
      this.$nextTick(() => { if (this.$refs.pw) this.$refs.pw.focus(); });
    },

    unlock() {
      const code = (typeof TEACHER_CODE !== 'undefined') ? TEACHER_CODE : TEACHER_CODE_FALLBACK;
      if (this.password === code) {
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