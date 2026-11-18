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
    quizProgress: [], cfgSummary: '',
    // --- κεντρικό παράθυρο ---
    activeUrl: '', activeTitle: '', frameSrc: 'about:blank',
    panels: [],            // {id,title,mode,x,y,w,h,open}
    cmd: { audience: 'students', tmima: '', text: '', msgId: '', navUrl: '',
           pollId: '', pollQ: '', pollOpts: '', pollShow: true, quizBankId: '',
           timerLabel: '', timerMin: 5, timerVis: 'public', timerPeriod: 0,
           timerEdge: 'end', timerOffset: 0 },

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
      this.serverSkew = (cfg.server_now || Date.now() / 1000) - Date.now() / 1000;
      this.buildPanels(cfg.toolbars);
    },

    buildPanels(toolbars) {
      // διατήρηση θέσεων/mode στο localStorage ανά χρήστη
      let saved = {};
      try { saved = JSON.parse(localStorage.getItem('classroom.panels') || '{}'); } catch (e) {}
      this.panels = toolbars.map(t => Object.assign(
        { id: t.id, title: t.title, mode: t.mode, x: t.x, y: t.y, w: t.w, h: t.h, open: true },
        saved[t.id] || {}));
      this.$nextTick(() => this.mountWidgets());
    },

    savePanels() {
      const out = {};
      this.panels.forEach(p => { out[p.id] = { mode: p.mode, x: p.x, y: p.y, w: p.w, h: p.h, open: p.open }; });
      try { localStorage.setItem('classroom.panels', JSON.stringify(out)); } catch (e) {}
    },

    mountWidgets() {
      // μετακίνηση των ζωντανών widget templates στα slots (dock ή float)
      this.panels.forEach(p => {
        const src = document.querySelector(`#widget-templates [data-widget="${p.id}"]`);
        const slot = document.getElementById((p.mode === 'dock' ? 'dock-slot-' : 'float-slot-') + p.id);
        if (src && slot && src.parentElement !== slot) slot.appendChild(src);
      });
    },

    toggleMode(p) {
      p.mode = p.mode === 'dock' ? 'float' : 'dock';
      p.open = true;
      this.savePanels();
      this.$nextTick(() => this.mountWidgets());
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
        const src = document.querySelector('#widget-templates [data-widget="chat"]');
        const inToolbar = this.panels.some(p => p.id === 'chat');
        if (!inToolbar && src) document.getElementById('page-chat-slot').appendChild(src);
        else document.getElementById('page-chat-slot').innerHTML =
          '<p class="text-sm text-slate-500">Το chat είναι ήδη ανοιχτό στην εργαλειοθήκη 💬 (αριστερά ή πλωτή).</p>';
      }
      else if (m.url === '#forum') await this.renderForum(host);
      else if (m.url === '#help') host.innerHTML = this.renderHelp();
      else host.innerHTML = '';
    },

    renderAnnouncements() {
      const items = [...this.announcements].reverse().map(a => {
        const icon = a.kind === 'award' ? '🏆' : (a.kind === 'congrats' ? '🎉' : '📣');
        const time = new Date(a.ts * 1000).toLocaleTimeString('el-GR', { hour: '2-digit', minute: '2-digit' });
        return `<div class="rounded-xl bg-white ring-1 ring-slate-200 p-3 flex gap-3 items-start shadow-sm">
          <span class="text-xl">${icon}</span>
          <div class="flex-1"><div class="text-sm font-semibold">${this.esc(a.text)}</div>
          <div class="text-[10px] text-slate-400 mt-0.5">${time}${a.target_name ? ' → ' + this.esc(a.target_name) : ''}</div></div></div>`;
      }).join('');
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
          if (m.polls && m.polls.length && this.role !== 'teacher') this.showPoll(m.polls[m.polls.length - 1]);
          if (m.quizzes && m.quizzes.length && this.role !== 'teacher') this.showQuiz(m.quizzes[m.quizzes.length - 1]);
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
        case 'poll': this.showPoll(m); break;
        case 'poll_voted':
          if (this.activePoll && this.activePoll.id === m.id) this.activePoll.answered = true;
          break;
        case 'poll_results':
          if (this.activePoll && this.activePoll.id === m.id) {
            this.pollResults = m;
            if (m.closed) { this.activePoll.closed = true; this.activePoll.show_results = true; }
          }
          break;
        case 'quiz': this.showQuiz(m); break;
        case 'quiz_result': this.quizResult = m; if (m.recorded || m.score === m.total) this.confetti(); break;
        case 'quiz_progress':
          this.quizProgress = this.quizProgress.filter(r => r.uid !== m.uid).concat([m]);
          break;
        case 'quiz_closed':
          if (this.activeQuiz && this.activeQuiz.id === m.id && !this.quizResult) {
            this.activeQuiz = null;
            this.toast({ id: 'qc' + m.id, kind: 'announce', text: 'Το quiz έκλεισε από τον καθηγητή.' });
          }
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
    votePoll(i) { this.wsSend({ type: 'poll_vote', id: this.activePoll.id, choice: i }); },
    async closePoll() {
      if (!this.activePoll) return;
      try { await this.api('api/cmd/poll/' + this.activePoll.id + '/close', {}); } catch (e) {}
    },
    showQuiz(m) {
      this.activeQuiz = m; this.quizAnswers = new Array(m.questions.length).fill(-1);
      this.quizResult = null;
    },
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
    timerLeft(t) { this.clockTick; return Math.max(0, t.ends_at - this.now()); },
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
        this.$nextTick(() => this.mountWidgets());
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
        await this.api('api/cmd/poll', this.cmdBody({ question: this.cmd.pollQ, options, show_results: this.cmd.pollShow }));
        this.cmd.pollQ = ''; this.cmd.pollOpts = '';
      } catch (e) { alert(e.message); }
    },
    async sendQuizBank() {
      if (!this.cmd.quizBankId) return;
      this.quizProgress = [];
      try { await this.api('api/cmd/quiz', this.cmdBody({ bank_id: this.cmd.quizBankId })); }
      catch (e) { alert(e.message); }
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
