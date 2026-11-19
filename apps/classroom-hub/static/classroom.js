/*
 * classroom.js — Ζωντανή Τάξη (/classroom/): Alpine component.
 *
 * Κεντρικό παράθυρο με μόνιμο μενού ανά ρόλο, εφαρμογές σε iframe,
 * dock/float εργαλειοθήκες (draggable/resizable, vanilla JS), WebSocket
 * heartbeat παρουσίας & εντολές τάξης (ανακοινώσεις, poll, quiz, timers…).
 * Καμία εξωτερική εξάρτηση πέρα από τα τοπικά Tailwind/Alpine της πύλης.
 */
function classroom() {
  return {
    // --- κατάσταση σύνδεσης / ρυθμίσεων ---
    identity: null, role: 'guest', menu: [], toolbars: [],
    tmimataList: [], periodsList: [], timetable: {},
    messagesBank: [], pollsBank: [], quizzesBank: [], timersCfg: [], eventsCfg: [],
    allowedApps: '*', guestChat: true, guestForum: false,
    joinRole: 'guest', joinName: '', joinTmima: '', joinCode: '',
    joinError: '', joining: false,
    // --- ζωντανή κατάσταση ---
    ws: null, wsOk: false, roster: [], announcements: [], toasts: [],
    chatMsgs: [], chatText: '', activeTimers: [], clockTick: 0, serverSkew: 0,
    activePoll: null, pollResults: null, activeQuiz: null, quizAnswers: [], quizResult: null,
    quizProgress: [], cfgSummary: '', mutedUntil: 0, mutes: [],
    answeredPolls: {}, answeredQuizzes: {},   // τοπικά «έχω ήδη απαντήσει» (και για guests)
    // --- κεντρικό παράθυρο ---
    activeUrl: '', activeTitle: '', frameSrc: 'about:blank',
    panels: [],            // {id,title,mode,x,y,w,h,open}
    cmd: { audience: 'students', tmima: '', text: '', msgId: '', navUrl: '',
           pollId: '', pollQ: '', pollOpts: '', pollShow: true, quizBankId: '',
           pollAuto: true, pollMin: 0, quizAuto: true, quizMin: 0,
           timerLabel: '', timerMin: 5, timerVis: 'public', timerPeriod: 0,
           timerEdge: 'end', timerOffset: 0 },
    // --- σύνθετη ανακοίνωση ---
    advMode: false, advKind: 'announce', advLinks: [], advNavigate: false,
    catalog: { lessons: [], apps: [], custom_links: [] },
    linkFilter: { q: '', cls: '', tag: '', fav: false },
    newLink: { title: '', url: '' },
    // --- κονσόλα διαχείρισης ---
    manageTab: 'announcements', mgAnnouncements: [], mgPolls: [], mgQuizzes: [], mgChat: [],
    mgSel: {},             // id → true (επιλεγμένα ανά καρτέλα, καθαρίζεται σε αλλαγή tab)
    mgEdit: null,          // {type:'announcement'|'poll'|'quiz', item:{...}}
    mgDays: 7, mgBusy: false,

    get roleLabel() {
      return { guest: 'επισκέπτης', student: 'μαθητής', teacher: 'καθηγητής' }[this.role] || '';
    },
    get dockedPanels() { return this.panels.filter(p => p.mode === 'dock'); },
    get floatingPanels() { return this.panels.filter(p => p.mode === 'float'); },

    async init() {
      // προφόρτωση λίστας τμημάτων για την οθόνη εισόδου
      try {
        const cfg = await this.api('api/config/public');
        this.tmimataList = cfg.tmimata || [];
      } catch (e) {}
      const me = await this.api('api/me');
      if (me.identity) { this.identity = me.identity; await this.enter(); }
      setInterval(() => { this.clockTick++; }, 1000);   // re-render countdowns
      window.addEventListener('beforeunload', () => { try { this.ws && this.ws.close(); } catch (e) {} });
    },

    async api(path, payload, method) {
      const opt = { headers: { 'Content-Type': 'application/json' } };
      if (payload !== undefined) { opt.method = method || 'POST'; opt.body = JSON.stringify(payload); }
      else if (method) opt.method = method;
      const res = await fetch(path, opt);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ('Σφάλμα ' + res.status));
      return data;
    },

    async join() {
      this.joining = true; this.joinError = '';
      try {
        const body = { role: this.joinRole, name: this.joinName, tmima: this.joinTmima, code: this.joinCode };
        const r = await this.api('api/join', body);
        this.identity = r.identity;
        await this.enter();
      } catch (e) { this.joinError = e.message; }
      this.joining = false;
    },

    async leave() {
      try { await this.api('api/leave', {}); } catch (e) {}
      try { this.ws && this.ws.close(); } catch (e) {}
      location.reload();
    },

    async enter() {
      await this.loadConfig();
      this.connectWs();
      this.loadChatHistory();
      this.loadMutes();
    },

    async loadConfig() {
      const cfg = await this.api('api/config/public');
      this.role = cfg.role;
      this.menu = cfg.menu; this.tmimataList = cfg.tmimata;
      this.periodsList = cfg.periods; this.timetable = cfg.timetable;
      this.messagesBank = cfg.messages; this.pollsBank = cfg.polls_bank;
      this.quizzesBank = cfg.quizzes_bank; this.timersCfg = cfg.timers_cfg;
      this.eventsCfg = cfg.events_cfg; this.allowedApps = cfg.allowed_apps;
      this.guestChat = cfg.guest_chat; this.guestForum = cfg.guest_forum;
      this.announcements = cfg.announcements || [];
      this.catalog.custom_links = cfg.announce_links || [];
      this.serverSkew = (cfg.server_now || Date.now() / 1000) - Date.now() / 1000;
      this.buildPanels(cfg.toolbars);
    },

    buildPanels(toolbars) {
      // διατήρηση θέσεων/mode στο localStorage ανά χρήστη
      let saved = {};
      try { saved = JSON.parse(localStorage.getItem('classroom.panels') || '{}'); } catch (e) {}
      // Κρατάμε ζωντανές αναφορές των widgets ΠΡΙΝ αλλάξουν τα panels — το Alpine
      // x-for μπορεί να καταστρέψει τα παλιά slots μαζί με το περιεχόμενό τους.
      this._widgets = this._widgets || {};
      document.querySelectorAll('[data-widget]').forEach(w => { this._widgets[w.dataset.widget] = w; });
      this.panels = toolbars.map(t => Object.assign(
        { id: t.id, title: t.title, mode: t.mode, x: t.x, y: t.y, w: t.w, h: t.h, open: true },
        saved[t.id] || {}));
      this.scheduleMount();
    },

    savePanels() {
      const out = {};
      this.panels.forEach(p => { out[p.id] = { mode: p.mode, x: p.x, y: p.y, w: p.w, h: p.h, open: p.open }; });
      try { localStorage.setItem('classroom.panels', JSON.stringify(out)); } catch (e) {}
    },

    mountWidgets() {
      // Μετακίνηση των ζωντανών widget nodes στα slots (dock ή float).
      // Τα nodes κρατιούνται και σε ΙΔΙΩΤΙΚΗ αναφορά (this._widgets): όταν το
      // Alpine x-for καταστρέφει το παλιό slot, το node αποσυνδέεται από το DOM
      // και δεν το βρίσκει πια κανένας querySelector — γι' αυτό το float άδειαζε.
      this._widgets = this._widgets || {};
      this.panels.forEach(p => {
        let src = this._widgets[p.id];
        if (!src || !src.isConnected) {
          const found = document.querySelector(`[data-widget="${p.id}"]`);
          if (found) src = this._widgets[p.id] = found;
        }
        const slot = document.getElementById((p.mode === 'dock' ? 'dock-slot-' : 'float-slot-') + p.id);
        if (src && slot && src.parentElement !== slot) slot.appendChild(src);
      });
    },

    scheduleMount() {
      // Το Alpine x-for δημιουργεί/καταστρέφει τα slots ΑΣΥΓΧΡΟΝΑ (queueMicrotask
      // μετά το reactive effect) — ένα μόνο $nextTick μπορεί να τρέξει ΠΡΙΝ την
      // ενημέρωση του DOM. Δοκιμάζουμε ξανά μέχρι να τοποθετηθούν όλα τα widgets.
      let tries = 0;
      const attempt = () => {
        this.mountWidgets();
        const missing = this.panels.some(p => {
          const slot = document.getElementById((p.mode === 'dock' ? 'dock-slot-' : 'float-slot-') + p.id);
          return !slot || !slot.querySelector(`[data-widget="${p.id}"]`);
        });
        if (missing && ++tries < 20) setTimeout(attempt, 50);
      };
      this.$nextTick(attempt);
    },

    toggleMode(p) {
      // ΠΡΩΤΑ σώζουμε τη ζωντανή αναφορά του widget — μετά το mode change το
      // Alpine μπορεί να καταστρέψει το παλιό slot μαζί με το περιεχόμενο.
      const w = document.querySelector(`[data-widget="${p.id}"]`);
      if (w) (this._widgets = this._widgets || {})[p.id] = w;
      p.mode = p.mode === 'dock' ? 'float' : 'dock';
      p.open = true;
      this.savePanels();
      this.scheduleMount();
    },


    // --- drag & resize για float εργαλειοθήκες (Pointer Events) ---
    dragStart(ev, p) {
      if (ev.target.tagName === 'BUTTON') return;
      ev.preventDefault();
      const sx = ev.clientX - p.x, sy = ev.clientY - p.y;
      const move = e => {
        p.x = Math.max(0, Math.min(window.innerWidth - 80, e.clientX - sx));
        p.y = Math.max(0, Math.min(window.innerHeight - 40, e.clientY - sy));
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        this.savePanels();
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },

    resizeStart(ev, p) {
      ev.preventDefault(); ev.stopPropagation();
      const sw = p.w - ev.clientX, sh = p.h - ev.clientY;
      const move = e => {
        p.w = Math.max(220, e.clientX + sw);
        p.h = Math.max(140, e.clientY + sh);
      };
      const up = () => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        this.savePanels();
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },

    // --- κεντρικό μενού & iframe εφαρμογών ---
    appAllowed(url) {
      if (this.allowedApps === '*' || !Array.isArray(this.allowedApps)) return true;
      return this.allowedApps.some(prefix => url.startsWith(prefix));
    },

    openMenu(m) {
      if (m.url.startsWith('#')) { this.openPanelPage(m); return; }
      if (!this.appAllowed(m.url)) {
        this.toast({ id: 'na' + Date.now(), kind: 'announce', text: 'Η εφαρμογή δεν είναι διαθέσιμη για τον ρόλο σου.' });
        return;
      }
      this.activeUrl = m.url; this.activeTitle = m.icon + ' ' + m.title;
      this.frameSrc = m.url;
    },

    navigateTo(url, title) {
      this.activeUrl = url; this.activeTitle = title || url;
      this.frameSrc = url;
    },

    reloadFrame() {
      const f = document.getElementById('app-frame');
      if (f) f.src = this.frameSrc;
    },

    async openPanelPage(m) {
      this.activeUrl = m.url; this.activeTitle = m.icon + ' ' + m.title;
      const host = document.getElementById('panel-host');
      if (!host) return;
      if (m.url === '#announcements') host.innerHTML = this.renderAnnouncements();
      else if (m.url === '#chat') {
        host.innerHTML = '<div class="rounded-2xl bg-white ring-1 ring-slate-200 p-4 shadow-sm"><h2 class="font-extrabold mb-2">💬 Chat Τάξης</h2><div id="page-chat-slot"></div></div>';
        const src = document.querySelector('[data-widget="chat"]');
        const inToolbar = this.panels.some(p => p.id === 'chat');
        if (!inToolbar && src) document.getElementById('page-chat-slot').appendChild(src);
        else document.getElementById('page-chat-slot').innerHTML =
          '<p class="text-sm text-slate-500">Το chat είναι ήδη ανοιχτό στην εργαλειοθήκη 💬 (αριστερά ή πλωτή).</p>';
      }
      else if (m.url === '#manage') await this.renderManage(host);
      else if (m.url === '#forum') await this.renderForum(host);
      else if (m.url === '#help') host.innerHTML = this.renderHelp();
      else host.innerHTML = '';
    },

    renderAnnouncements() {
      const items = [...this.announcements].reverse().map(a => {
        const icon = a.kind === 'award' ? '🏆' : (a.kind === 'congrats' ? '🎉' : '📣');
        const time = new Date(a.ts * 1000).toLocaleTimeString('el-GR', { hour: '2-digit', minute: '2-digit' });
        const links = (a.links || []).map(l =>
          `<button data-nav="${this.esc(l.url)}" data-title="${this.esc(l.title)}"
             class="ann-link inline-flex items-center gap-1 rounded-lg bg-blue-50 hover:bg-blue-100 ring-1 ring-blue-200 text-blue-700 text-[11px] font-bold px-2 py-1 mt-1 mr-1 transition">🔗 ${this.esc(l.title)}</button>`).join('');
        return `<div class="rounded-xl bg-white ring-1 ring-slate-200 p-3 flex gap-3 items-start shadow-sm">
          <span class="text-xl">${icon}</span>
          <div class="flex-1"><div class="text-sm font-semibold">${this.esc(a.text)}</div>
          ${links ? `<div>${links}</div>` : ''}
          <div class="text-[10px] text-slate-400 mt-0.5">${time}${a.target_name ? ' → ' + this.esc(a.target_name) : ''}</div></div></div>`;
      }).join('');
      // Τα κουμπιά συνδέσμων δένονται μετά την εισαγωγή του HTML (openPanelPage).
      setTimeout(() => document.querySelectorAll('#panel-host .ann-link').forEach(b =>
        b.addEventListener('click', () => this.navigateTo(b.dataset.nav, '🔗 ' + b.dataset.title))), 0);
      return `<h2 class="font-extrabold text-lg mb-3">📣 Ανακοινώσεις</h2>
        <div class="space-y-2">${items || '<p class="text-sm text-slate-400 italic">Δεν υπάρχουν ανακοινώσεις ακόμα.</p>'}</div>`;
    },

    renderHelp() {
      return `<div class="rounded-2xl bg-white ring-1 ring-slate-200 p-6 shadow-sm space-y-3 text-sm">
        <h2 class="font-extrabold text-lg">❓ Βοήθεια — Ζωντανή Τάξη</h2>
        <p><b>🧭 Κεντρικό μενού:</b> όλα όσα ανοίγεις εμφανίζονται στο κεντρικό παράθυρο· το μενού μένει πάντα πάνω-πάνω.</p>
        <p><b>🧰 Εργαλειοθήκες:</b> με το ⇱ ξεκουμπώνεις μια εργαλειοθήκη και γίνεται πλωτή (σύρε την από την μπλε μπάρα, άλλαξε μέγεθος από τη γωνία κάτω-δεξιά). Με το ⇲ την ξανακουμπώνεις αριστερά.</p>
        <p><b>🎲 Επισκέπτης (guest):</b> μπαίνεις με τυχαίο παιχνιδιάρικο όνομα. Τα quiz είναι εξάσκηση — δεν καταγράφονται.</p>
        <p><b>👨‍🎓 Μαθητής:</b> τα αποτελέσματα των quiz καταγράφονται με το όνομα και το τμήμα σου.</p>
        <p><b>🧑‍🏫 Καθηγητής:</b> βλέπεις ζωντανά ποιος είναι συνδεδεμένος, στέλνεις ανακοινώσεις / συγχαρητήρια / βραβεία, κάνεις τυχαία επιλογή, polls, quiz, timers (ιδιωτικούς ή δημόσιους, συγχρονισμένους με το ωράριο ±offset) και υποχρεωτικές μεταβάσεις σελίδας.</p>
        <p><b>⚙️ Ρυθμίσεις:</b> όλα παραμετροποιούνται από το ενιαίο Excel (καρτέλες με χρωματικούς κώδικες) — κατέβασε το πρότυπο από την εργαλειοθήκη «Εντολές Τάξης».</p>
        <p class="text-xs text-slate-400">Χρειάζεσαι κάτι άλλο; Ρώτα τον καθηγητή σου ή γράψε στο chat της τάξης.</p>
      </div>`;
    },

    esc(s) {
      return String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    },


    // --- Forum (νήματα & απαντήσεις μέσω REST + WS) ---
    forumThreads: [], forumOpen: null,

    async renderForum(host) {
      if (this.role === 'guest' && !this.guestForum) {
        host.innerHTML = '<div class="rounded-2xl bg-white ring-1 ring-slate-200 p-6 text-sm text-slate-500 shadow-sm">🔒 Το forum είναι διαθέσιμο μόνο στους μαθητές και τους καθηγητές.</div>';
        return;
      }
      try { this.forumThreads = (await this.api('api/forum/threads')).threads; } catch (e) { this.forumThreads = []; }
      const list = this.forumThreads.map(t => `
        <button data-thread="${t.id}" class="forum-open w-full text-left rounded-xl bg-white ring-1 ring-slate-200 hover:ring-blue-400 p-3 shadow-sm transition">
          <div class="font-bold text-sm">${t.locked ? '🔒 ' : ''}${this.esc(t.title)}</div>
          <div class="text-[10px] text-slate-400 mt-0.5">${this.esc(t.name)} · ${new Date(t.ts * 1000).toLocaleString('el-GR')} · ${t.posts} απαντήσεις</div>
        </button>`).join('');
      host.innerHTML = `
        <h2 class="font-extrabold text-lg mb-3">🗂️ Forum Τάξης</h2>
        <div id="forum-view">
          <div class="space-y-2">${list || '<p class="text-sm text-slate-400 italic">Δεν υπάρχουν νήματα — ξεκίνα το πρώτο!</p>'}</div>
          <div class="mt-4 rounded-2xl bg-white ring-1 ring-slate-200 p-4 shadow-sm">
            <h3 class="font-bold text-sm mb-2">✍️ Νέο νήμα</h3>
            <input id="forum-title" maxlength="150" placeholder="Τίτλος" class="w-full mb-2 rounded border border-slate-300 px-3 py-2 text-sm">
            <textarea id="forum-text" rows="3" maxlength="2000" placeholder="Γράψε την ερώτηση ή το θέμα σου…" class="w-full rounded border border-slate-300 px-3 py-2 text-sm"></textarea>
            <button id="forum-new" class="mt-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold px-4 py-2">Δημοσίευση</button>
          </div>
        </div>`;
      host.querySelectorAll('.forum-open').forEach(b =>
        b.addEventListener('click', () => this.openThread(parseInt(b.dataset.thread))));
      host.querySelector('#forum-new').addEventListener('click', async () => {
        const title = host.querySelector('#forum-title').value.trim();
        const text = host.querySelector('#forum-text').value.trim();
        if (!title || !text) return;
        try { await this.api('api/forum/threads', { title, text }); this.renderForum(host); }
        catch (e) { alert(e.message); }
      });
    },


    async openThread(tid) {
      const host = document.getElementById('panel-host');
      let data;
      try { data = await this.api('api/forum/threads/' + tid); } catch (e) { return; }
      this.forumOpen = tid;
      const posts = data.posts.map(p => `
        <div class="rounded-xl bg-white ring-1 ring-slate-200 p-3 shadow-sm">
          <div class="text-[10px] text-slate-400">${p.role === 'teacher' ? '🧑‍🏫 ' : ''}${this.esc(p.name)} · ${new Date(p.ts * 1000).toLocaleString('el-GR')}</div>
          <div class="text-sm mt-1 whitespace-pre-wrap">${this.esc(p.text)}</div>
        </div>`).join('');
      const teacherBtns = this.role === 'teacher' ? `
        <button id="forum-lock" class="rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-bold px-3 py-1.5">${data.thread.locked ? '🔓 Ξεκλείδωμα' : '🔒 Κλείδωμα'}</button>
        <button id="forum-del" class="rounded-lg bg-red-100 hover:bg-red-200 text-red-700 text-xs font-bold px-3 py-1.5">🗑 Διαγραφή</button>` : '';
      host.innerHTML = `
        <button id="forum-back" class="text-xs text-blue-700 hover:underline mb-2">← όλα τα νήματα</button>
        <h2 class="font-extrabold text-lg mb-3">${data.thread.locked ? '🔒 ' : ''}${this.esc(data.thread.title)}</h2>
        <div class="space-y-2" id="forum-posts">${posts}</div>
        ${data.thread.locked && this.role !== 'teacher' ? '<p class="text-xs text-amber-700 mt-2">Το νήμα έχει κλειδωθεί από τον καθηγητή.</p>' : `
        <div class="mt-3 flex gap-2">
          <textarea id="forum-reply" rows="2" maxlength="2000" placeholder="Η απάντησή σου…" class="flex-1 rounded border border-slate-300 px-3 py-2 text-sm"></textarea>
          <button id="forum-send" class="rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold px-4">➤</button>
        </div>`}
        <div class="mt-3 flex gap-2">${teacherBtns}</div>`;
      host.querySelector('#forum-back').addEventListener('click', () => { this.forumOpen = null; this.renderForum(host); });
      const send = host.querySelector('#forum-send');
      if (send) send.addEventListener('click', () => {
        const text = host.querySelector('#forum-reply').value.trim();
        if (!text) return;
        this.wsSend({ type: 'forum_post', thread_id: tid, text });
        host.querySelector('#forum-reply').value = '';
      });
      const lock = host.querySelector('#forum-lock');
      if (lock) lock.addEventListener('click', async () => {
        await this.api(`api/forum/threads/${tid}/lock`, { locked: !data.thread.locked });
        this.openThread(tid);
      });
      const del = host.querySelector('#forum-del');
      if (del) del.addEventListener('click', async () => {
        if (!confirm('Διαγραφή νήματος;')) return;
        await this.api('api/forum/threads/' + tid, undefined, 'DELETE');
        this.forumOpen = null; this.renderForum(host);
      });
    },

    appendForumPost(msg) {
      if (this.forumOpen !== msg.thread_id) return;
      const box = document.getElementById('forum-posts');
      if (!box) return;
      const div = document.createElement('div');
      div.className = 'rounded-xl bg-white ring-1 ring-slate-200 p-3 shadow-sm';
      div.innerHTML = `<div class="text-[10px] text-slate-400">${msg.role === 'teacher' ? '🧑‍🏫 ' : ''}${this.esc(msg.name)} · ${new Date(msg.ts * 1000).toLocaleString('el-GR')}</div>
        <div class="text-sm mt-1 whitespace-pre-wrap">${this.esc(msg.text)}</div>`;
      box.appendChild(div);
      div.scrollIntoView({ behavior: 'smooth' });
    },


    // --- WebSocket: heartbeat παρουσίας & λήψη εντολών ---
    connectWs() {
      const proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
      const base = location.pathname.replace(/\/$/, '');   // /classroom
      this.ws = new WebSocket(proto + location.host + base + '/ws');
      this.ws.onopen = () => {
        this.wsOk = true;
        this.ping();
        this._pingTimer = setInterval(() => this.ping(), 15000);
      };
      this.ws.onmessage = ev => { try { this.onWs(JSON.parse(ev.data)); } catch (e) {} };
      this.ws.onclose = ev => {
        this.wsOk = false;
        clearInterval(this._pingTimer);
        if (ev.code === 4003) { this.identity = null; return; }  // χρειάζεται νέο join
        if (this.identity) setTimeout(() => this.connectWs(), 2500);
      };
      this.ws.onerror = () => { try { this.ws.close(); } catch (e) {} };
    },

    ping() {
      this.wsSend({ type: 'ping', page: this.activeUrl || '(αρχική)' });
    },

    wsSend(obj) {
      if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(obj));
    },

    onWs(m) {
      switch (m.type) {
        case 'welcome':
          this.serverSkew = m.server_now - Date.now() / 1000;
          this.announcements = m.announcements || [];
          this.activeTimers = m.timers || [];
          this.mutedUntil = m.muted_until || 0;
          // Ο server στέλνει ΜΟΝΟ polls/quizzes που δεν έχω απαντήσει· επιπλέον
          // φιλτράρουμε τοπικά (guest quiz δεν καταγράφεται στη βάση).
          if (m.polls && m.polls.length && this.role !== 'teacher') {
            const p = m.polls.filter(x => !this.answeredPolls[x.id]).pop();
            if (p) this.showPoll(p);
          }
          if (m.quizzes && m.quizzes.length && this.role !== 'teacher') {
            const q = m.quizzes.filter(x => !this.answeredQuizzes[x.id]).pop();
            if (q) this.showQuiz(q);
          }
          break;
        case 'pong': this.serverSkew = m.server_now - Date.now() / 1000; break;
        case 'roster': {
          const seen = new Set();
          this.roster = m.clients.filter(c => !seen.has(c.uid) && seen.add(c.uid));
          break;
        }
        case 'announcement':
          this.announcements.push(m);
          this.toast(m);
          if (m.kind !== 'announce') this.confetti();
          if (this.activeUrl === '#announcements')
            document.getElementById('panel-host').innerHTML = this.renderAnnouncements();
          break;
        case 'announcement_updated': {
          const i = this.announcements.findIndex(a => a.id === m.id);
          if (i >= 0) this.announcements[i] = Object.assign({}, this.announcements[i], m);
          if (this.activeUrl === '#announcements')
            document.getElementById('panel-host').innerHTML = this.renderAnnouncements();
          if (this.activeUrl === '#manage' && this.manageTab === 'announcements') this.loadManage();
          break;
        }
        case 'announcement_deleted':
          this.announcements = this.announcements.filter(a => a.id !== m.id);
          this.toasts = this.toasts.filter(t => t.id !== m.id);
          if (this.activeUrl === '#announcements')
            document.getElementById('panel-host').innerHTML = this.renderAnnouncements();
          if (this.activeUrl === '#manage' && this.manageTab === 'announcements') this.loadManage();
          break;
        case 'announcements_bulk_deleted':
          this.announcements = this.announcements.filter(a => !m.ids.includes(a.id));
          if (this.activeUrl === '#announcements')
            document.getElementById('panel-host').innerHTML = this.renderAnnouncements();
          if (this.activeUrl === '#manage' && this.manageTab === 'announcements') this.loadManage();
          break;
        case 'random_pick':
          this.toast({ id: 'pick' + m.ts, kind: m.uid === this.identity.uid ? 'award' : 'congrats',
                       text: `🎲 Επιλέχθηκε: ${m.emoji} ${m.name}${m.tmima ? ' (' + m.tmima + ')' : ''}!` });
          this.confetti();
          break;
        case 'navigate':
          if (this.role !== 'teacher') {
            this.navigateTo(m.url, '➡️ ' + (m.title || m.url));
            this.toast({ id: 'nav' + m.ts, kind: 'announce', text: 'Ο καθηγητής μας μεταφέρει σε νέα σελίδα: ' + (m.title || m.url) });
          }
          break;
        case 'poll':
          // ενημέρωση ενεργού poll (edit) ή νέο poll — ποτέ επανεμφάνιση απαντημένου
          if (m.updated && this.activePoll && this.activePoll.id === m.id) {
            Object.assign(this.activePoll, { question: m.question, options: m.options, show_results: m.show_results });
          } else if (!this.answeredPolls[m.id]) this.showPoll(m);
          break;
        case 'poll_voted':
          this.answeredPolls[m.id] = true;
          if (this.activePoll && this.activePoll.id === m.id) {
            this.activePoll.answered = true;
            // χωρίς ζωντανά αποτελέσματα → αυτόματη απόκρυψη μετά από λίγο
            if (!this.activePoll.show_results && this.role !== 'teacher')
              setTimeout(() => {
                if (this.activePoll && this.activePoll.id === m.id && !this.activePoll.closed)
                  this.hidePoll();
              }, 6000);
          }
          break;
        case 'poll_results':
          if (this.activePoll && this.activePoll.id === m.id) {
            this.pollResults = m;
            if (m.closed) { this.activePoll.closed = true; this.activePoll.show_results = true; }
          } else if (m.closed && this.role === 'teacher') {
            this.pollResults = m;                       // τελικά αποτελέσματα για τον καθηγητή
          }
          break;
        case 'poll_deleted':
          if (this.activePoll && this.activePoll.id === m.id) this.hidePoll();
          if (this.activeUrl === '#manage' && this.manageTab === 'polls') this.loadManage();
          break;
        case 'poll_updated':
          if (this.activeUrl === '#manage' && this.manageTab === 'polls') this.loadManage();
          break;
        case 'quiz':
          if (m.updated && this.activeQuiz && this.activeQuiz.id === m.id && !this.quizResult) {
            Object.assign(this.activeQuiz, { title: m.title, questions: m.questions });
            this.quizAnswers = new Array(m.questions.length).fill(-1);
          } else if (!this.answeredQuizzes[m.id]) this.showQuiz(m);
          break;
        case 'quiz_result':
          this.quizResult = m;
          if (this.activeQuiz) this.answeredQuizzes[this.activeQuiz.id] = true;
          if (m.recorded || m.score === m.total) this.confetti();
          break;
        case 'quiz_progress':
          this.quizProgress = this.quizProgress.filter(r => r.uid !== m.uid).concat([m]);
          break;
        case 'quiz_closed':
          if (this.activeQuiz && this.activeQuiz.id === m.id && !this.quizResult) {
            this.activeQuiz = null;
            this.toast({ id: 'qc' + m.id, kind: 'announce', text: 'Το quiz έκλεισε.' });
          }
          if (this.activeUrl === '#manage' && this.manageTab === 'quizzes') this.loadManage();
          break;
        case 'quiz_deleted':
          if (this.activeQuiz && this.activeQuiz.id === m.id) { this.activeQuiz = null; this.quizResult = null; }
          if (this.activeUrl === '#manage' && this.manageTab === 'quizzes') this.loadManage();
          break;
        case 'quiz_updated':
          if (this.activeUrl === '#manage' && this.manageTab === 'quizzes') this.loadManage();
          break;
        case 'timer':
          this.activeTimers = this.activeTimers.filter(t => t.id !== m.id).concat([m]);
          this.ensureTimerPanel();
          break;
        case 'timer_stop': this.activeTimers = this.activeTimers.filter(t => t.id !== m.id); break;
        case 'timer_done':
          this.activeTimers = this.activeTimers.filter(t => t.id !== m.id);
          this.toast({ id: 'td' + m.id, kind: 'congrats', text: '⏱️ ' + m.label + ': ο χρόνος τελείωσε!' + (m.message ? ' ' + m.message : '') });
          this.beep();
          break;
        case 'chat':
          this.chatMsgs.push(m);
          if (this.chatMsgs.length > 200) this.chatMsgs.shift();
          this.$nextTick(() => {
            const log = document.getElementById('chat-log');
            if (log) log.scrollTop = log.scrollHeight;
          });
          break;
        case 'chat_deleted':
          this.chatMsgs = this.chatMsgs.filter(x => !m.ids.includes(x.id));
          if (this.activeUrl === '#manage' && this.manageTab === 'chat') this.loadManage();
          break;
        case 'muted':
          this.mutedUntil = m.until_ts;
          this.toast({ id: 'mute' + m.until_ts, kind: 'announce',
                       text: '🔇 Ο καθηγητής επέβαλε σιωπή στο chat/forum έως τις ' + this.fmtTime(m.until_ts) + '.' });
          break;
        case 'unmuted':
          this.mutedUntil = 0;
          this.toast({ id: 'unmute' + Date.now(), kind: 'congrats', text: '🔊 Η σιωπή σου αρθηκε — μπορείς να ξαναγράψεις!' });
          break;
        case 'mute_changed':
          this.loadMutes();
          break;
        case 'forum_post': this.appendForumPost(m); break;
        case 'forum_thread':
          if (this.activeUrl === '#forum' && !this.forumOpen)
            this.renderForum(document.getElementById('panel-host'));
          break;
        case 'config_updated':
          this.loadConfig().then(() =>
            this.toast({ id: 'cfg' + Date.now(), kind: 'announce', text: '⚙️ Οι ρυθμίσεις της τάξης ενημερώθηκαν.' }));
          break;
      }
    },


    // --- poll / quiz / chat helpers ---
    showPoll(m) {
      this.activePoll = Object.assign({ answered: false, closed: false }, m);
      this.pollResults = null;
    },
    hidePoll() { this.activePoll = null; this.pollResults = null; },
    votePoll(i) { this.wsSend({ type: 'poll_vote', id: this.activePoll.id, choice: i }); },
    async closePoll() {
      if (!this.activePoll) return;
      try { await this.api('api/cmd/poll/' + this.activePoll.id + '/close', {}); } catch (e) {}
    },
    showQuiz(m) {
      this.activeQuiz = m; this.quizAnswers = new Array(m.questions.length).fill(-1);
      this.quizResult = null;
    },
    hideQuiz() { this.activeQuiz = null; this.quizResult = null; this.quizAnswers = []; },
    submitQuiz() {
      this.wsSend({ type: 'quiz_submit', id: this.activeQuiz.id, answers: this.quizAnswers });
    },
    async loadChatHistory() {
      try { this.chatMsgs = (await this.api('api/chat/history')).messages; } catch (e) {}
    },
    sendChat() {
      const text = this.chatText.trim();
      if (!text) return;
      this.wsSend({ type: 'chat', text });
      this.chatText = '';
    },

    // --- timers ---
    now() { return Date.now() / 1000 + this.serverSkew; },
    timerLeft(t) {
      this.clockTick;
      const left = Math.max(0, t.ends_at - this.now());
      // Watchdog: αν το timer_done χάθηκε (reconnect/ασθενές ρολόι), δεν μένει
      // «κολλημένο» στο 00:00 — καθαρίζεται τοπικά 10s μετά τη λήξη.
      if (left === 0 && this.now() - t.ends_at > 10) {
        setTimeout(() => { this.activeTimers = this.activeTimers.filter(x => x.id !== t.id); }, 0);
      }
      return left;
    },
    dismissTimer(t) {
      // ✕ για ΟΛΟΥΣ: ο μαθητής/guest κρύβει τοπικά· ο καθηγητής σταματά για όλους.
      if (this.role === 'teacher') this.stopTimer(t.id);
      else this.activeTimers = this.activeTimers.filter(x => x.id !== t.id);
    },
    fmtLeft(sec) {
      sec = Math.ceil(sec);
      const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
      return (h ? h + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    },
    fmtTime(ts) {
      return new Date(ts * 1000).toLocaleTimeString('el-GR', { hour: '2-digit', minute: '2-digit' });
    },
    ensureTimerPanel() {
      // αν ο ρόλος δεν έχει timer toolbar από το Excel, προσθέτουμε προσωρινή float
      if (!this.panels.some(p => p.id === 'timer')) {
        this.panels.push({ id: 'timer', title: '⏱️ Χρονομετρητής', mode: 'float',
                           x: 60, y: 120, w: 280, h: 220, open: true });
        this.scheduleMount();
      } else {
        const p = this.panels.find(p => p.id === 'timer');
        p.open = true;
      }
    },
    async stopTimer(id) { try { await this.api('api/cmd/timer/' + id + '/stop', {}); } catch (e) {} },
    async startCfgTimer(id) {
      try { await this.api('api/cmd/timer-from-config/' + id, {}); }
      catch (e) { alert(e.message); }
    },


    // --- εντολές καθηγητή ---
    cmdBody(extra) {
      return Object.assign({ audience: this.cmd.audience, tmima: this.cmd.tmima }, extra || {});
    },
    applyMessage() {
      const m = this.messagesBank.find(x => x.id === this.cmd.msgId);
      if (m) this.cmd.text = m.text;
    },
    applyPoll() {
      const p = this.pollsBank.find(x => x.id === this.cmd.pollId);
      if (p) { this.cmd.pollQ = p.question; this.cmd.pollOpts = p.options.join(', '); this.cmd.pollShow = p.show_results; }
    },
    async sendAnnounce(kind) {
      if (!this.cmd.text.trim()) return;
      try {
        await this.api('api/cmd/announce', this.cmdBody({ kind, text: this.cmd.text }));
        this.cmd.text = '';
      } catch (e) { alert(e.message); }
    },
    async awardTo(c) {
      const tpl = this.messagesBank.find(m => m.kind === 'award');
      const text = (tpl ? tpl.text : '🏆 Βραβείο για τον/τη {name}!').replace('{name}', c.name);
      try { await this.api('api/cmd/announce', { kind: 'award', text, target_uid: c.uid }); }
      catch (e) { alert(e.message); }
    },
    async congratsTo(c) {
      const tpl = this.messagesBank.find(m => m.kind === 'congrats');
      const text = (tpl ? tpl.text : 'Μπράβο {name}! 🎉').replace('{name}', c.name);
      try { await this.api('api/cmd/announce', { kind: 'congrats', text, target_uid: c.uid }); }
      catch (e) { alert(e.message); }
    },
    async randomPick() {
      try { await this.api('api/cmd/random-pick', this.cmdBody({ celebrate: true })); }
      catch (e) { alert(e.message); }
    },
    async sendNavigate() {
      if (!this.cmd.navUrl.trim()) return;
      try { await this.api('api/cmd/navigate', this.cmdBody({ url: this.cmd.navUrl.trim() })); }
      catch (e) { alert(e.message); }
    },
    async sendPoll() {
      const options = this.cmd.pollOpts.split(',').map(s => s.trim()).filter(Boolean);
      if (!this.cmd.pollQ.trim() || options.length < 2) { alert('Χρειάζεται ερώτηση και ≥2 επιλογές (με κόμμα).'); return; }
      try {
        await this.api('api/cmd/poll', this.cmdBody({
          question: this.cmd.pollQ, options, show_results: this.cmd.pollShow,
          auto_close: this.cmd.pollAuto, duration_sec: Math.max(0, this.cmd.pollMin || 0) * 60 }));
        this.cmd.pollQ = ''; this.cmd.pollOpts = '';
      } catch (e) { alert(e.message); }
    },
    async sendQuizBank() {
      if (!this.cmd.quizBankId) return;
      this.quizProgress = [];
      try {
        await this.api('api/cmd/quiz', this.cmdBody({
          bank_id: this.cmd.quizBankId, auto_close: this.cmd.quizAuto,
          duration_sec: Math.max(0, this.cmd.quizMin || 0) * 60 }));
      } catch (e) { alert(e.message); }
    },
    async sendTimer() {
      const body = this.cmdBody({ label: this.cmd.timerLabel || 'Χρονομετρητής',
                                  visibility: this.cmd.timerVis });
      if (this.cmd.timerPeriod > 0) {
        body.period = this.cmd.timerPeriod; body.edge = this.cmd.timerEdge;
        body.offset_min = this.cmd.timerOffset || 0;
      } else {
        body.duration_sec = Math.max(1, this.cmd.timerMin || 5) * 60;
      }
      try { await this.api('api/cmd/timer', body); } catch (e) { alert(e.message); }
    },
    async uploadConfig(ev) {
      const file = ev.target.files[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      try {
        const res = await fetch('api/config/upload', { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Σφάλμα ανεβάσματος');
        const s = data.summary;
        this.cfgSummary = `✓ ${s.tmimata} τμήματα · ${s.menu} μενού · ${s.toolbars} εργαλειοθήκες · ${s.timers} timers · ${s.events} γεγονότα · ${s.quizzes} quiz`;
      } catch (e) { alert(e.message); }
      ev.target.value = '';
    },

    // --- 🔇 chat moderation (καθηγητής) ---
    async loadMutes() {
      if (this.role !== 'teacher') return;
      try { this.mutes = (await this.api('api/mutes')).mutes; } catch (e) {}
    },
    isMuted(uid) { this.clockTick; return this.mutes.some(m => m.uid === uid && m.until_ts > this.now()); },
    async muteUser(c, minutes) {
      try { await this.api('api/mutes', { uid: c.uid, name: c.name, minutes }); await this.loadMutes(); }
      catch (e) { alert(e.message); }
    },
    async unmuteUser(uid) {
      try { await this.api('api/mutes', { uid, minutes: 0 }); await this.loadMutes(); }
      catch (e) { alert(e.message); }
    },
    async deleteChatMsg(id) {
      try { await this.api('api/chat/messages/' + id, undefined, 'DELETE'); }
      catch (e) { alert(e.message); }
    },

    // --- 📣 σύνθετη ανακοίνωση ---
    async toggleAdvMode() {
      this.advMode = !this.advMode;
      if (this.advMode && !this.catalog.lessons.length) await this.loadCatalog();
    },
    async loadCatalog() {
      try {
        const d = await this.api('api/lessons-catalog');
        this.catalog = { lessons: d.lessons, apps: d.apps, custom_links: d.custom_links };
      } catch (e) { alert(e.message); }
    },
    catalogTags() { return [...new Set(this.catalog.lessons.flatMap(l => l.tags || []))].sort(); },
    catalogClasses() {
      const seen = {};
      this.catalog.lessons.forEach(l => { seen[l.class_slug] = l.class_label; });
      return Object.entries(seen).map(([slug, label]) => ({ slug, label }));
    },
    filteredCatalog() {
      const f = this.linkFilter, q = f.q.trim().toLowerCase();
      return this.catalog.lessons.filter(l =>
        (!f.fav || l.favorite) && (!f.cls || l.class_slug === f.cls) &&
        (!f.tag || (l.tags || []).includes(f.tag)) &&
        (!q || l.title.toLowerCase().includes(q) || l.lesson.includes(q)));
    },
    linkAdded(url) { return this.advLinks.some(l => l.url === url); },
    toggleLink(item) {
      if (this.linkAdded(item.url)) this.advLinks = this.advLinks.filter(l => l.url !== item.url);
      else if (this.advLinks.length < 8) this.advLinks.push({ title: item.title, url: item.url });
    },
    async addCustomLink() {
      if (!this.newLink.url.trim()) return;
      try {
        const d = await this.api('api/announce-links',
          { action: 'add', title: this.newLink.title, url: this.newLink.url.trim() });
        this.catalog.custom_links = d.links;
        this.newLink = { title: '', url: '' };
      } catch (e) { alert(e.message); }
    },
    async removeCustomLink(url) {
      try {
        const d = await this.api('api/announce-links', { action: 'remove', url });
        this.catalog.custom_links = d.links;
        this.advLinks = this.advLinks.filter(l => l.url !== url);
      } catch (e) { alert(e.message); }
    },
    async sendAdvanced() {
      if (!this.cmd.text.trim()) { alert('Γράψε το κείμενο της ανακοίνωσης.'); return; }
      try {
        await this.api('api/cmd/announce', this.cmdBody({
          kind: this.advKind, text: this.cmd.text, links: this.advLinks, navigate: this.advNavigate }));
        this.cmd.text = ''; this.advLinks = []; this.advNavigate = false;
      } catch (e) { alert(e.message); }
    },

    // --- 🗄️ κονσόλα διαχείρισης ---
    async renderManage(host) {
      if (this.role !== 'teacher') {
        host.innerHTML = '<div class="rounded-2xl bg-white ring-1 ring-slate-200 p-6 text-sm text-slate-500 shadow-sm">🔒 Η διαχείριση είναι διαθέσιμη μόνο στους καθηγητές.</div>';
        return;
      }
      host.innerHTML = `
        <h2 class="font-extrabold text-lg mb-3">🗄️ Διαχείριση Τάξης</h2>
        <div class="flex gap-1.5 flex-wrap mb-3" id="mg-tabs">
          ${[['announcements', '📣 Ανακοινώσεις'], ['polls', '📊 Δημοσκοπήσεις'], ['quizzes', '📝 Quiz & Αποτελέσματα'], ['chat', '💬 Chat & Σιωπές']]
            .map(([id, label]) => `<button data-tab="${id}" class="mg-tab rounded-lg px-3 py-1.5 text-xs font-bold transition ${this.manageTab === id ? 'bg-indigo-600 text-white' : 'bg-white ring-1 ring-slate-200 text-slate-600 hover:bg-indigo-50'}">${label}</button>`).join('')}
        </div>
        <div id="mg-body" class="space-y-2"></div>`;
      host.querySelectorAll('.mg-tab').forEach(b => b.addEventListener('click', () => {
        this.manageTab = b.dataset.tab; this.mgSel = {}; this.renderManage(host);
      }));
      await this.loadManage();
    },

    async loadManage() {
      const body = document.getElementById('mg-body');
      if (!body || this.role !== 'teacher') return;
      this.mgBusy = true;
      try {
        if (this.manageTab === 'announcements') {
          this.mgAnnouncements = (await this.api('api/announcements?limit=200')).announcements.reverse();
          body.innerHTML = this.mgAnnouncementsHtml();
        } else if (this.manageTab === 'polls') {
          this.mgPolls = (await this.api('api/polls')).polls;
          body.innerHTML = this.mgPollsHtml();
        } else if (this.manageTab === 'quizzes') {
          this.mgQuizzes = (await this.api('api/quizzes')).quizzes;
          body.innerHTML = this.mgQuizzesHtml();
        } else if (this.manageTab === 'chat') {
          this.mgChat = (await this.api('api/chat/history?limit=300')).messages.reverse();
          await this.loadMutes();
          body.innerHTML = this.mgChatHtml();
        }
        this.bindManage(body);
      } catch (e) { body.innerHTML = `<p class="text-sm text-red-600">${this.esc(e.message)}</p>`; }
      this.mgBusy = false;
    },

    mgToolbar(kind, extra = '') {
      const n = Object.values(this.mgSel).filter(Boolean).length;
      return `<div class="rounded-xl bg-white ring-1 ring-slate-200 p-2.5 flex items-center gap-2 flex-wrap text-xs shadow-sm">
        <label class="flex items-center gap-1.5 font-bold"><input type="checkbox" id="mg-all" class="rounded"> Όλα</label>
        <span class="text-slate-400" id="mg-count">${n} επιλεγμένα</span>
        <button id="mg-del-sel" class="rounded-lg bg-red-100 hover:bg-red-200 text-red-700 font-bold px-2.5 py-1">🗑 Διαγραφή επιλεγμένων</button>
        ${extra}
        <span class="ml-auto flex items-center gap-1">Παλαιότερα των
          <input id="mg-days" type="number" min="1" value="${this.mgDays}" class="w-14 rounded border border-slate-300 px-1.5 py-0.5"> ημερών:
          <button id="mg-del-old" class="rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold px-2.5 py-1">🧹 Καθαρισμός</button>
        </span></div>`;
    },

    mgRow(id, inner, extraBtns = '') {
      return `<div class="rounded-xl bg-white ring-1 ring-slate-200 p-3 flex gap-2.5 items-start shadow-sm">
        <input type="checkbox" data-sel="${this.esc(String(id))}" class="mg-check mt-1 rounded" ${this.mgSel[id] ? 'checked' : ''}>
        <div class="flex-1 min-w-0">${inner}</div>
        <div class="flex gap-1 shrink-0">${extraBtns}
          <button data-del="${this.esc(String(id))}" class="mg-del rounded-lg bg-red-50 hover:bg-red-100 text-red-600 text-xs font-bold px-2 py-1" title="Διαγραφή">🗑</button>
        </div></div>`;
    },

    mgAnnouncementsHtml() {
      const rows = this.mgAnnouncements.map(a => {
        const icon = a.kind === 'award' ? '🏆' : (a.kind === 'congrats' ? '🎉' : '📣');
        const links = (a.links || []).map(l => `<span class="inline-block rounded bg-blue-50 text-blue-700 text-[10px] px-1.5 py-0.5 mr-1">🔗 ${this.esc(l.title)}</span>`).join('');
        return this.mgRow(a.id, `
          <div class="text-sm font-semibold">${icon} ${this.esc(a.text)}</div>
          ${links ? `<div class="mt-0.5">${links}</div>` : ''}
          <div class="text-[10px] text-slate-400 mt-0.5">${new Date(a.ts * 1000).toLocaleString('el-GR')} · κοινό: ${this.esc(a.audience)}${a.tmima ? ' (' + this.esc(a.tmima) + ')' : ''}${a.target_name ? ' → ' + this.esc(a.target_name) : ''}</div>`,
          `<button data-edit="${a.id}" class="mg-edit rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-bold px-2 py-1" title="Επεξεργασία">✏️</button>`);
      }).join('');
      return this.mgToolbar('announcements') + (rows || '<p class="text-sm text-slate-400 italic p-2">Καμία αποθηκευμένη ανακοίνωση.</p>');
    },

    mgPollsHtml() {
      const rows = this.mgPolls.map(p => {
        const bars = p.options.map((o, i) => `
          <div class="text-[11px] mt-0.5"><div class="flex justify-between"><span>${this.esc(o)}</span><b>${p.counts[i]}</b></div>
          <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-cyan-500" style="width:${p.total ? 100 * p.counts[i] / p.total : 0}%"></div></div></div>`).join('');
        return this.mgRow(p.id, `
          <div class="text-sm font-semibold">📊 ${this.esc(p.question)}
            <span class="text-[9px] px-1.5 py-0.5 rounded-full font-bold ${p.closed ? 'bg-slate-100 text-slate-500' : 'bg-emerald-100 text-emerald-700'}">${p.closed ? 'ΚΛΕΙΣΤΟ' : 'ΕΝΕΡΓΟ'}</span></div>
          <div class="max-w-sm">${bars}</div>
          <div class="text-[10px] text-slate-400 mt-0.5">${new Date(p.ts * 1000).toLocaleString('el-GR')} · ${p.total} ψήφοι</div>`,
          `${p.closed ? '' : `<button data-close="${p.id}" class="mg-close rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-bold px-2 py-1" title="Κλείσιμο">🔒</button>`}
           <button data-edit="${p.id}" class="mg-edit rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-bold px-2 py-1" title="Επεξεργασία">✏️</button>`);
      }).join('');
      return this.mgToolbar('polls', '<button id="mg-close-sel" class="rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold px-2.5 py-1">🔒 Κλείσιμο επιλεγμένων</button>')
        + (rows || '<p class="text-sm text-slate-400 italic p-2">Καμία δημοσκόπηση.</p>');
    },

    mgQuizzesHtml() {
      const rows = this.mgQuizzes.map(q => {
        const results = q.results.map(r => `
          <div class="flex items-center justify-between text-[11px] bg-fuchsia-50 rounded px-1.5 py-0.5 mt-0.5">
            <span>${this.esc(r.name)}${r.tmima ? ' (' + this.esc(r.tmima) + ')' : ''}</span>
            <span class="flex items-center gap-1.5"><b>${r.score}/${r.total}</b>
              <button data-rdel="${r.id}" class="mg-rdel text-red-400 hover:text-red-600" title="Διαγραφή αποτελέσματος">✕</button></span>
          </div>`).join('');
        return this.mgRow(q.id, `
          <div class="text-sm font-semibold">📝 ${this.esc(q.title)}
            <span class="text-[9px] px-1.5 py-0.5 rounded-full font-bold ${q.closed ? 'bg-slate-100 text-slate-500' : 'bg-emerald-100 text-emerald-700'}">${q.closed ? 'ΚΛΕΙΣΤΟ' : 'ΕΝΕΡΓΟ'}</span></div>
          <div class="text-[10px] text-slate-400 mt-0.5">${new Date(q.ts * 1000).toLocaleString('el-GR')} · ${q.results.length} υποβολές</div>
          <div class="max-w-sm mt-1">${results || '<span class="text-[10px] text-slate-400 italic">Χωρίς αποτελέσματα ακόμα.</span>'}</div>
          ${q.results.length ? `<button data-rclear="${q.id}" class="mg-rclear text-[10px] text-red-500 hover:underline mt-1">🧹 διαγραφή όλων των αποτελεσμάτων</button>` : ''}`,
          `${q.closed ? '' : `<button data-close="${q.id}" class="mg-close rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-bold px-2 py-1" title="Κλείσιμο">🔒</button>`}
           <button data-edit="${q.id}" class="mg-edit rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-bold px-2 py-1" title="Επεξεργασία τίτλου">✏️</button>`);
      }).join('');
      return this.mgToolbar('quizzes', '<button id="mg-close-sel" class="rounded-lg bg-amber-100 hover:bg-amber-200 text-amber-800 font-bold px-2.5 py-1">🔒 Κλείσιμο επιλεγμένων</button>')
        + (rows || '<p class="text-sm text-slate-400 italic p-2">Κανένα quiz.</p>');
    },

    mgChatHtml() {
      const muteRows = this.mutes.map(m => `
        <div class="flex items-center justify-between text-xs bg-amber-50 ring-1 ring-amber-200 rounded-lg px-2.5 py-1.5">
          <span>🔇 <b>${this.esc(m.name || m.uid)}</b> έως ${this.fmtTime(m.until_ts)} (από ${this.esc(m.by_name)})</span>
          <button data-unmute="${this.esc(m.uid)}" class="mg-unmute rounded bg-emerald-100 hover:bg-emerald-200 text-emerald-700 font-bold px-2 py-0.5">🔊 Άρση</button>
        </div>`).join('');
      const rows = this.mgChat.map(m => this.mgRow(m.id, `
        <div class="text-xs"><b style="color:${this.esc(m.color || '#334155')}">${this.esc(m.name)}</b>
          <span class="text-slate-400 text-[9px]">${new Date(m.ts * 1000).toLocaleString('el-GR')}</span>
          <span class="text-[9px] text-slate-400">(${this.esc(m.role)}${m.tmima ? ' · ' + this.esc(m.tmima) : ''})</span>
          <div class="bg-slate-50 rounded px-2 py-1 mt-0.5 break-words">${this.esc(m.text)}</div></div>`,
        m.role !== 'teacher' ? `<button data-mute="${this.esc(m.uid)}" data-name="${this.esc(m.name)}" class="mg-mute rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-700 text-xs font-bold px-2 py-1" title="Σιωπή">🔇</button>` : '')).join('');
      return this.mgToolbar('chat', '<button id="mg-clear-chat" class="rounded-lg bg-red-600 hover:bg-red-700 text-white font-bold px-2.5 py-1">🧨 Εκκαθάριση ΟΛΟΥ του chat</button>')
        + (muteRows ? `<div class="space-y-1">${muteRows}</div>` : '')
        + (rows || '<p class="text-sm text-slate-400 italic p-2">Άδειο chat.</p>');
    },

    bindManage(body) {
      const refreshCount = () => {
        const n = Object.values(this.mgSel).filter(Boolean).length;
        const el = body.querySelector('#mg-count'); if (el) el.textContent = n + ' επιλεγμένα';
      };
      body.querySelectorAll('.mg-check').forEach(ch => ch.addEventListener('change', () => {
        this.mgSel[ch.dataset.sel] = ch.checked; refreshCount();
      }));
      const all = body.querySelector('#mg-all');
      if (all) all.addEventListener('change', () => {
        body.querySelectorAll('.mg-check').forEach(ch => { ch.checked = all.checked; this.mgSel[ch.dataset.sel] = all.checked; });
        refreshCount();
      });
      const selIds = () => Object.keys(this.mgSel).filter(k => this.mgSel[k]);
      const tab = this.manageTab;
      const bulkPath = { announcements: 'api/announcements/bulk', polls: 'api/polls/bulk', quizzes: 'api/quizzes/bulk', chat: 'api/chat/bulk' }[tab];
      const doBulk = async (payload, confirmMsg) => {
        if (confirmMsg && !confirm(confirmMsg)) return;
        try { await this.api(bulkPath, payload); this.mgSel = {}; await this.loadManage(); }
        catch (e) { alert(e.message); }
      };
      const delSel = body.querySelector('#mg-del-sel');
      if (delSel) delSel.addEventListener('click', () => {
        const ids = selIds();
        if (!ids.length) { alert('Διάλεξε πρώτα στοιχεία με τα checkboxes.'); return; }
        doBulk(tab === 'chat' ? { ids } : { action: 'delete', ids }, `Διαγραφή ${ids.length} στοιχείων;`);
      });
      const closeSel = body.querySelector('#mg-close-sel');
      if (closeSel) closeSel.addEventListener('click', () => {
        const ids = selIds();
        if (!ids.length) { alert('Διάλεξε πρώτα στοιχεία.'); return; }
        doBulk({ action: 'close', ids });
      });
      const days = body.querySelector('#mg-days');
      const delOld = body.querySelector('#mg-del-old');
      if (delOld) delOld.addEventListener('click', () => {
        const d = Math.max(1, parseFloat(days.value) || 7); this.mgDays = d;
        doBulk(tab === 'chat' ? { older_than_days: d } : { action: 'delete', older_than_days: d },
               `Διαγραφή όσων είναι παλαιότερα των ${d} ημερών;`);
      });
      const clearChat = body.querySelector('#mg-clear-chat');
      if (clearChat) clearChat.addEventListener('click', () => doBulk({ clear_all: true }, 'Διαγραφή ΟΛΟΥ του ιστορικού chat;'));
      body.querySelectorAll('.mg-del').forEach(b => b.addEventListener('click', async () => {
        if (!confirm('Διαγραφή;')) return;
        const id = b.dataset.del;
        const path = { announcements: 'api/announcements/', polls: 'api/polls/', quizzes: 'api/quizzes/', chat: 'api/chat/messages/' }[tab] + id;
        try { await this.api(path, undefined, 'DELETE'); delete this.mgSel[id]; await this.loadManage(); }
        catch (e) { alert(e.message); }
      }));
      body.querySelectorAll('.mg-close').forEach(b => b.addEventListener('click', async () => {
        const path = (tab === 'polls' ? 'api/cmd/poll/' : 'api/cmd/quiz/') + b.dataset.close + '/close';
        try { await this.api(path, {}); await this.loadManage(); } catch (e) { alert(e.message); }
      }));
      body.querySelectorAll('.mg-edit').forEach(b => b.addEventListener('click', () => this.openMgEdit(tab, b.dataset.edit)));
      body.querySelectorAll('.mg-rdel').forEach(b => b.addEventListener('click', async () => {
        try { await this.api('api/quiz-results/' + b.dataset.rdel, undefined, 'DELETE'); await this.loadManage(); }
        catch (e) { alert(e.message); }
      }));
      body.querySelectorAll('.mg-rclear').forEach(b => b.addEventListener('click', async () => {
        if (!confirm('Διαγραφή ΟΛΩΝ των αποτελεσμάτων αυτού του quiz;')) return;
        try { await this.api('api/quiz-results/bulk-delete', { quiz_id: b.dataset.rclear, all: true }); await this.loadManage(); }
        catch (e) { alert(e.message); }
      }));
      body.querySelectorAll('.mg-mute').forEach(b => b.addEventListener('click', async () => {
        const mins = prompt('Σιωπή (λεπτά) για τον/τη ' + b.dataset.name + ':', '15');
        if (mins === null) return;
        try { await this.api('api/mutes', { uid: b.dataset.mute, name: b.dataset.name, minutes: parseFloat(mins) || 15 }); await this.loadManage(); }
        catch (e) { alert(e.message); }
      }));
      body.querySelectorAll('.mg-unmute').forEach(b => b.addEventListener('click', () => this.unmuteUser(b.dataset.unmute).then(() => this.loadManage())));
    },

    openMgEdit(tab, id) {
      if (tab === 'announcements') {
        const a = this.mgAnnouncements.find(x => x.id === id);
        if (a) this.mgEdit = { type: 'announcement', id, kind: a.kind, text: a.text };
      } else if (tab === 'polls') {
        const p = this.mgPolls.find(x => x.id === id);
        if (p) this.mgEdit = { type: 'poll', id, question: p.question, options: p.options.join(', '), show_results: p.show_results };
      } else if (tab === 'quizzes') {
        const q = this.mgQuizzes.find(x => x.id === id);
        if (q) this.mgEdit = { type: 'quiz', id, title: q.title };
      }
    },
    async saveMgEdit() {
      const e = this.mgEdit; if (!e) return;
      try {
        if (e.type === 'announcement')
          await this.api('api/announcements/' + e.id, { kind: e.kind, text: e.text }, 'PUT');
        else if (e.type === 'poll')
          await this.api('api/polls/' + e.id, { question: e.question,
            options: e.options.split(',').map(s => s.trim()).filter(Boolean), show_results: e.show_results }, 'PUT');
        else if (e.type === 'quiz')
          await this.api('api/quizzes/' + e.id, { title: e.title }, 'PUT');
        this.mgEdit = null; await this.loadManage();
      } catch (err) { alert(err.message); }
    },

    // --- εφέ: toasts, confetti, beep ---
    toast(a) {
      this.toasts.push(a);
      setTimeout(() => this.dismissToast(a.id), a.kind === 'announce' ? 12000 : 9000);
    },
    dismissToast(id) { this.toasts = this.toasts.filter(t => t.id !== id); },
    confetti() {
      const emojis = ['🎉', '⭐', '🎊', '✨', '🏆', '💫'];
      for (let i = 0; i < 26; i++) {
        const el = document.createElement('div');
        el.className = 'confetti';
        el.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        el.style.left = Math.random() * 100 + 'vw';
        el.style.animationDuration = (2.2 + Math.random() * 2.5) + 's';
        el.style.fontSize = (0.9 + Math.random() * 1.2) + 'rem';
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 5200);
      }
    },
    beep() {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [0, 0.25, 0.5].forEach(t => {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.connect(g); g.connect(ctx.destination);
          o.frequency.value = 880; g.gain.value = 0.08;
          o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.18);
        });
      } catch (e) {}
    },
  };
}
