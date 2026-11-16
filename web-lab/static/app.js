/* ===========================================================================
 * Εργαστήριο Web (HTML / CSS / JS) — κύρια λογική (Alpine.js + CodeMirror 5)
 * Solo mode: localStorage · Team rooms: WebSockets + SQLite στον server.
 * Όλα τα assets είναι τοπικά — λειτουργεί 100% offline στο σχολικό LAN.
 * =========================================================================== */

// Base URL πίσω από τον Nginx (/web-lab/) ή απευθείας στο uvicorn (/)
const BASE = location.pathname.endsWith("/") ? location.pathname : location.pathname + "/";
const LS_KEY = "weblab.solo.v1";
const LS_PREFS = "weblab.prefs.v1";
const LS_ROOM = "weblab.room.v1";

// Γέφυρα κονσόλας: μπαίνει ΠΡΩΤΗ στην <head> του iframe και στέλνει κάθε
// console.log/warn/error & κάθε σφάλμα JS στον γονέα με postMessage.
const CONSOLE_BRIDGE = `<script>
(function () {
  function fmt(x) {
    if (typeof x === "string") return x;
    if (x instanceof Error) return x.name + ": " + x.message;
    try { return JSON.stringify(x); } catch (e) { return String(x); }
  }
  function send(kind, args) {
    try {
      parent.postMessage({ __weblab: true, kind: kind,
        text: Array.prototype.map.call(args, fmt).join(" ") }, "*");
    } catch (e) {}
  }
  ["log", "info", "warn", "error"].forEach(function (k) {
    var orig = console[k] ? console[k].bind(console) : function () {};
    console[k] = function () { send(k, arguments); orig.apply(null, arguments); };
  });
  window.addEventListener("error", function (e) {
    send("error", [(e.message || "Σφάλμα") + (e.lineno ? " (γραμμή " + e.lineno + ")" : "")]);
  });
  window.addEventListener("unhandledrejection", function (e) {
    send("error", ["Unhandled Promise: " + fmt(e.reason)]);
  });
})();
<\/script>`;

const DEFAULT_CODE = {
  html: `<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <title>Η Σελίδα μου</title>
</head>
<body>
  <h1>Καλώς ήρθες στο Εργαστήριο Web! 🌐</h1>
  <p>Γράψε HTML, CSS και JavaScript στα αριστερά πάνελ και δες το
  αποτέλεσμα ζωντανά εδώ. Δοκίμασε τα <strong>Έτοιμα Snippets</strong>!</p>
  <button id="koumpi">Πάτησέ με</button>
</body>
</html>`,
  css: `body { font-family: Arial, sans-serif; padding: 24px; background: #f8fafc; }
h1 { color: #4f46e5; }
button {
  padding: 10px 22px; font-size: 15px; cursor: pointer;
  background: #4f46e5; color: white; border: none; border-radius: 8px;
}
button:hover { background: #6366f1; }`,
  js: `document.getElementById("koumpi").addEventListener("click", function () {
  console.log("Γεια από την JavaScript! 👋");
  alert("Μπράβο! Η JavaScript δουλεύει! 🎉");
});`
};

function weblab() {
  return {
    // --- Κατάσταση UI ---
    dark: true, autoRun: true, snipOpen: false, activeTab: "html",
    modal: "", modalError: "", toasts: [], lastRun: "", savedAt: "",
    consoleLines: [], consoleErrors: 0,
    snippetCats: window.WEBLAB_SNIPPETS,
    panels: [
      { id: "html", label: "HTML — Δομή", icon: "🧱", color: "text-orange-400", hint: "τα tags κλείνουν αυτόματα" },
      { id: "css", label: "CSS — Εμφάνιση", icon: "🎨", color: "text-sky-400", hint: "χρώματα, γραμματοσειρές, διάταξη" },
      { id: "js", label: "JavaScript — Διαδραστικότητα", icon: "⚡", color: "text-yellow-400", hint: "console.log → κονσόλα κάτω δεξιά" }
    ],
    editors: {},            // CodeMirror instances ανά πάνελ
    applyingRemote: false,  // μην ξαναστείλεις κώδικα που ήρθε από WS
    runTimer: null, saveTimer: null, wsTimer: null, pingTimer: null,

    // --- Συνεργασία ---
    isTeacher: window.LOGGED_IN === true,
    teacherPass: "", myName: "", joinPin: "",
    room: { pin: "", name: "", locked: false },
    members: [], ws: null, wsOk: false,

    // --- Δημοσίευση ---
    pub: { id: "", title: "", description: "", icon: "🌐", access: "all", replace: false },
    publishing: false, pubUrl: "",

    // ------------------------------------------------------------------ init
    init() {
      const prefs = this.loadJSON(LS_PREFS, {});
      this.dark = prefs.dark !== false;
      this.autoRun = prefs.autoRun !== false;
      this.myName = prefs.name || "";

      this.$nextTick(() => {
        this.makeEditors();
        // Solo code από localStorage (αλλιώς το καλωσόρισμα)
        const solo = this.loadJSON(LS_KEY, null);
        this.setCode(solo && solo.html !== undefined ? solo : DEFAULT_CODE);

        // Αυτόματη επανασύνδεση σε δωμάτιο μετά από refresh
        const saved = this.loadJSON(LS_ROOM, null);
        if (saved && saved.pin) { this.connectRoom(saved.pin); }
        else { this.run(); }

        window.addEventListener("message", (e) => this.onConsoleMessage(e));
        window.addEventListener("keydown", (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); this.run(); }
        });
        window.addEventListener("beforeunload", () => this.saveSolo(true));
      });
    },

    makeEditors() {
      if (this._editorsMade) return;   // guard: το Alpine init τρέχει 2 φορές (reactive proxy)
      this._editorsMade = true;
      const modes = { html: "htmlmixed", css: "css", js: "javascript" };
      for (const p of this.panels) {
        const ta = document.getElementById("code-" + p.id);
        if (!ta || ta.dataset.cmReady) continue;
        ta.dataset.cmReady = "1";
        const cm = CodeMirror.fromTextArea(ta, {
          mode: modes[p.id],
          lineNumbers: true,
          autoCloseTags: p.id === "html",
          autoCloseBrackets: true,
          matchBrackets: true,
          matchTags: p.id === "html" ? { bothTags: true } : false,
          indentUnit: 2, tabSize: 2,
          lineWrapping: true,
          extraKeys: { "Ctrl-Enter": () => this.run(), "Cmd-Enter": () => this.run() }
        });
        cm.on("change", (inst, change) => {
          if (this.applyingRemote || change.origin === "setValue") return;
          this.onLocalEdit(p.id);
        });
        cm.on("focus", () => { this.activeTab = p.id; });
        this.editors[p.id] = cm;
      }
    },

    refreshEditors() {
      this.$nextTick(() => Object.values(this.editors).forEach(cm => cm.refresh()));
    },

    // -------------------------------------------------------------- editors
    getCode() {
      return { html: this.editors.html.getValue(), css: this.editors.css.getValue(), js: this.editors.js.getValue() };
    },
    setCode(code) {
      this.applyingRemote = true;
      for (const p of ["html", "css", "js"]) {
        const cm = this.editors[p];
        if (cm.getValue() !== (code[p] || "")) {
          const cur = cm.getCursor();
          cm.setValue(code[p] || "");
          try { cm.setCursor(cur); } catch (e) {}
        }
      }
      this.applyingRemote = false;
    },
    setPanel(panel, code) {
      this.applyingRemote = true;
      const cm = this.editors[panel];
      if (cm.getValue() !== code) {
        const cur = cm.getCursor();
        cm.setValue(code);
        try { cm.setCursor(cur); } catch (e) {}
      }
      this.applyingRemote = false;
    },

    onLocalEdit(panel) {
      if (this.room.pin) {
        // Ζωντανός συγχρονισμός: throttle ~180ms ανά πάνελ
        clearTimeout(this.wsTimer);
        this.wsTimer = setTimeout(() => this.wsSend({ type: "edit", panel: panel, code: this.editors[panel].getValue() }), 180);
      } else {
        this.saveSolo();
      }
      if (this.autoRun) {
        clearTimeout(this.runTimer);
        this.runTimer = setTimeout(() => this.run(), 700);
      }
    },

    // --------------------------------------------------- preview & κονσόλα
    buildPreviewDoc(code) {
      let doc = code.html || "";
      const style = code.css.trim() ? "<style>\n" + code.css + "\n</style>" : "";
      const script = code.js.trim() ? "<script>\n" + code.js + "\n<\/script>" : "";
      if (!/<html\b/i.test(doc)) {
        doc = '<!DOCTYPE html><html lang="el"><head><meta charset="utf-8">' +
              CONSOLE_BRIDGE + style + "</head><body>\n" + doc + "\n" + script + "</body></html>";
      } else {
        // Η γέφυρα κονσόλας μπαίνει αμέσως μετά το <head> (ή πριν τα πάντα)
        if (/<head[^>]*>/i.test(doc)) {
          doc = doc.replace(/<head[^>]*>/i, (m) => m + "\n" + CONSOLE_BRIDGE);
        } else {
          doc = CONSOLE_BRIDGE + doc;
        }
        if (style) {
          doc = /<\/head>/i.test(doc) ? doc.replace(/<\/head>/i, style + "\n</head>") : style + doc;
        }
        if (script) {
          doc = /<\/body>/i.test(doc) ? doc.replace(/<\/body>/i, script + "\n</body>") : doc + script;
        }
      }
      return doc;
    },

    run() {
      this.consoleLines = [];
      this.consoleErrors = 0;
      const frame = document.getElementById("preview");
      frame.srcdoc = this.buildPreviewDoc(this.getCode());
      this.lastRun = new Date().toLocaleTimeString("el-GR");
    },

    onConsoleMessage(e) {
      const d = e.data;
      if (!d || d.__weblab !== true) return;
      const kind = ["log", "info", "warn", "error"].includes(d.kind) ? d.kind : "log";
      this.consoleLines.push({ kind: kind, text: String(d.text), time: new Date().toLocaleTimeString("el-GR") });
      if (this.consoleLines.length > 300) this.consoleLines.shift();
      if (kind === "error") this.consoleErrors++;
      this.$nextTick(() => {
        const box = document.getElementById("console-box");
        if (box) box.scrollTop = box.scrollHeight;
      });
    },

    // ------------------------------------------------------------- snippets
    insertSnippet(s) {
      this.snipOpen = false;
      if (s.starter) {
        if (!confirm("Το «" + s.name + "» είναι ολόκληρο πρότυπο και θα ΑΝΤΙΚΑΤΑΣΤΗΣΕΙ τον τρέχοντα κώδικα και στα 3 πάνελ. Συνέχεια;")) return;
        this.setCode({ html: s.html || "", css: s.css || "", js: s.js || "" });
        this.toast("Φορτώθηκε το πρότυπο: " + s.name);
      } else {
        // Προσθήκη στο τέλος του αντίστοιχου πάνελ (με κενή γραμμή διαχωρισμού)
        for (const p of ["html", "css", "js"]) {
          if (s[p]) {
            const cm = this.editors[p];
            const old = cm.getValue();
            cm.setValue(old.trim() ? old.replace(/\s+$/, "") + "\n\n" + s[p] : s[p]);
            this.activeTab = p;
          }
        }
        this.toast("Προστέθηκε: " + s.name);
      }
      this.refreshEditors();
      this.onLocalEdit(this.activeTab);
      this.run();
    },

    // ------------------------------------------------------ αποθήκευση/theme
    loadJSON(key, fallback) {
      try { const v = JSON.parse(localStorage.getItem(key)); return v === null ? fallback : v; }
      catch (e) { return fallback; }
    },
    saveSolo(now) {
      if (this.room.pin) return;   // σε δωμάτιο αποθηκεύει ο server (SQLite)
      clearTimeout(this.saveTimer);
      const doSave = () => {
        localStorage.setItem(LS_KEY, JSON.stringify(this.getCode()));
        this.savedAt = "Αποθηκεύτηκε " + new Date().toLocaleTimeString("el-GR");
      };
      if (now) doSave(); else this.saveTimer = setTimeout(doSave, 500);
    },
    savePrefs() {
      localStorage.setItem(LS_PREFS, JSON.stringify({ dark: this.dark, autoRun: this.autoRun, name: this.myName }));
    },
    toggleTheme() {
      this.dark = !this.dark;
      this.savePrefs();
      this.refreshEditors();
    },

    // ---------------------------------------------------------------- toast
    toast(text, kind) {
      const id = Date.now() + Math.random();
      this.toasts.push({ id: id, text: text, kind: kind || "ok" });
      setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 4200);
    },
    openModal(name) { this.modalError = ""; this.pubUrl = ""; this.modal = name; },

    async api(path, payload, method) {
      const res = await fetch(BASE + path, {
        method: method || (payload ? "POST" : "GET"),
        headers: payload ? { "Content-Type": "application/json" } : {},
        body: payload ? JSON.stringify(payload) : undefined
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("Σφάλμα " + res.status));
      return data;
    },

    // ----------------------------------------------------- δωμάτια (WS)
    async createRoom() {
      this.modalError = "";
      if (!this.myName.trim()) { this.modalError = "Γράψε πρώτα το όνομά σου."; return; }
      this.savePrefs();
      try {
        const code = this.getCode();
        const data = await this.api("api/rooms", { name: "Ομάδα: " + this.myName.trim(), ...code });
        this.connectRoom(data.pin);
        this.modal = "";
        this.toast("Δημιουργήθηκε το δωμάτιο " + data.pin + " — μοιράσου τον κωδικό! 📣");
      } catch (e) { this.modalError = e.message; }
    },

    async joinRoom() {
      this.modalError = "";
      const pin = (this.joinPin || "").trim();
      if (!/^\d{4}$/.test(pin)) { this.modalError = "Ο κωδικός πρέπει να είναι 4 ψηφία (π.χ. 7342)."; return; }
      if (!this.myName.trim()) { this.modalError = "Γράψε πρώτα το όνομά σου."; return; }
      this.savePrefs();
      try {
        await this.api("api/rooms/" + pin);   // έλεγχος ύπαρξης πριν τη σύνδεση
        this.connectRoom(pin);
        this.modal = "";
      } catch (e) { this.modalError = e.message; }
    },

    connectRoom(pin) {
      this.disconnectWS();
      this.room.pin = pin;
      localStorage.setItem(LS_ROOM, JSON.stringify({ pin: pin }));
      const proto = location.protocol === "https:" ? "wss://" : "ws://";
      const url = proto + location.host + BASE + "ws/" + pin + "?name=" + encodeURIComponent(this.myName.trim() || "Μαθητής");
      const ws = new WebSocket(url);
      this.ws = ws;

      ws.onopen = () => { this.wsOk = true; };
      ws.onmessage = (ev) => {
        let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
        this.onWsMessage(msg);
      };
      ws.onclose = (ev) => {
        this.wsOk = false;
        if (this.ws !== ws) return;         // αντικαταστάθηκε από νέα σύνδεση
        if (ev.code === 4404) {
          this.toast("Το δωμάτιο " + pin + " δεν υπάρχει πλέον.", "error");
          this.leaveRoom(true);
        } else if (ev.code === 4429) {
          this.toast("Το δωμάτιο είναι γεμάτο (60 άτομα).", "error");
          this.leaveRoom(true);
        } else if (this.room.pin) {
          // Αυτόματη επανασύνδεση (refresh δικτύου, sleep laptop κ.λπ.)
          setTimeout(() => { if (this.room.pin === pin) this.connectRoom(pin); }, 2500);
        }
      };
      // keepalive ping ώστε ο Nginx/proxy να μη κλείνει αδρανείς συνδέσεις
      clearInterval(this.pingTimer);
      this.pingTimer = setInterval(() => this.wsSend({ type: "ping" }), 30000);
    },

    onWsMessage(msg) {
      switch (msg.type) {
        case "state":       // πλήρες snapshot κατά την είσοδο/επανασύνδεση
          this.room.name = msg.name || "";
          this.room.locked = !!msg.locked;
          this.setCode(msg.code);
          this.applyReadOnly();
          this.run();
          break;
        case "code":        // ζωντανή αλλαγή ενός πάνελ από συμμαθητή
          this.setPanel(msg.panel, msg.code);
          if (this.autoRun) {
            clearTimeout(this.runTimer);
            this.runTimer = setTimeout(() => this.run(), 700);
          }
          break;
        case "full":        // «Αποστολή Κώδικα σε Όλους» από τον καθηγητή
          this.setCode(msg.code);
          this.run();
          if (msg.announce) this.toast("📡 Ο καθηγητής έστειλε νέο κώδικα σε όλους!", "warn");
          break;
        case "lock":
          this.room.locked = !!msg.locked;
          this.applyReadOnly();
          this.toast(msg.locked ? "🔒 Μόνο Ανάγνωση — παρακολούθησε την παρουσίαση." : "🔓 Το δωμάτιο ξεκλειδώθηκε — γράψε ξανά!", "warn");
          break;
        case "members":
          this.members = msg.members || [];
          break;
        case "denied":
          this.toast(msg.reason || "Η αλλαγή απορρίφθηκε.", "error");
          break;
        case "error":
          this.toast(msg.message || "Σφάλμα δωματίου.", "error");
          break;
      }
    },

    applyReadOnly() {
      const ro = this.room.locked && !this.isTeacher;
      for (const cm of Object.values(this.editors)) cm.setOption("readOnly", ro ? "nocursor" : false);
    },

    wsSend(payload) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(payload));
    },
    disconnectWS() {
      clearInterval(this.pingTimer);
      const ws = this.ws;
      this.ws = null;
      if (ws) { try { ws.close(); } catch (e) {} }
      this.wsOk = false;
    },
    leaveRoom(silent) {
      this.disconnectWS();
      this.room = { pin: "", name: "", locked: false };
      this.members = [];
      localStorage.removeItem(LS_ROOM);
      this.applyReadOnly();
      // Επιστροφή στο solo project του μαθητή
      const solo = this.loadJSON(LS_KEY, null);
      if (solo && solo.html !== undefined) this.setCode(solo);
      this.run();
      if (!silent) this.toast("Βγήκες από το δωμάτιο — συνεχίζεις ατομικά (Solo).");
    },

    broadcastCode() {
      if (!confirm("Ο τρέχων κώδικάς σου θα ΑΝΤΙΚΑΤΑΣΤΗΣΕΙ τον κώδικα όλων στο δωμάτιο. Συνέχεια;")) return;
      const code = this.getCode();
      this.wsSend({ type: "broadcast", ...code });
      this.toast("📡 Ο κώδικας στάλθηκε σε όλους!");
    },
    toggleLock() {
      this.wsSend({ type: "lock", locked: !this.room.locked });
    },

    // ------------------------------------------------------ καθηγητής/export
    async teacherLogin() {
      this.modalError = "";
      try {
        await this.api("api/teacher/login", { password: this.teacherPass });
        this.isTeacher = true;
        this.teacherPass = "";
        this.modal = "";
        this.applyReadOnly();
        this.toast("✓ Λειτουργία Καθηγητή ενεργή.");
        // Αν είμαστε ήδη σε δωμάτιο, επανασύνδεση ώστε το WS να δει το cookie
        if (this.room.pin) this.connectRoom(this.room.pin);
      } catch (e) { this.modalError = e.message; }
    },
    async teacherLogout() {
      try { await this.api("api/teacher/logout", {}); } catch (e) {}
      this.isTeacher = false;
      this.applyReadOnly();
      if (this.room.pin) this.connectRoom(this.room.pin);
      this.toast("Έξοδος από τη λειτουργία καθηγητή.");
    },

    mergedDocument(title) {
      // Ίδια λογική με το merge_document() του server (για τοπική λήψη)
      const code = this.getCode();
      let doc = (code.html || "").trim();
      const style = code.css.trim() ? "<style>\n" + code.css.trim() + "\n</style>" : "";
      const script = code.js.trim() ? "<script>\n" + code.js.trim() + "\n<\/script>" : "";
      title = title || "Η Ιστοσελίδα μου";
      if (!/<html\b/i.test(doc)) {
        return '<!DOCTYPE html>\n<html lang="el">\n<head>\n<meta charset="utf-8">\n' +
          '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
          "<title>" + title + "</title>\n" + (style ? style + "\n" : "") +
          "</head>\n<body>\n" + doc + "\n" + (script ? script + "\n" : "") + "</body>\n</html>\n";
      }
      if (/<title>[\s\S]*?<\/title>/i.test(doc)) {
        doc = doc.replace(/<title>[\s\S]*?<\/title>/i, "<title>" + title + "</title>");
      }
      if (style) {
        doc = /<\/head>/i.test(doc) ? doc.replace(/<\/head>/i, style + "\n</head>") : style + "\n" + doc;
      }
      if (script) {
        doc = /<\/body>/i.test(doc) ? doc.replace(/<\/body>/i, script + "\n</body>") : doc + "\n" + script;
      }
      return doc + "\n";
    },

    downloadHtml() {
      const title = (this.pub.title || "Ιστοσελίδα").trim() || "Ιστοσελίδα";
      const blob = new Blob([this.mergedDocument(title)], { type: "text/html;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "istorseilida.html";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      this.toast("💾 Το αρχείο istorseilida.html κατέβηκε — παρέδωσέ το στο /exams/!");
    },

    openPublish() {
      if (!this.pub.title) {
        // Πρόταση τίτλου από το <title> του HTML
        const m = this.editors.html.getValue().match(/<title>([^<]*)<\/title>/i);
        this.pub.title = m ? m[1].trim() : "Η Ιστοσελίδα της Τάξης";
      }
      this.openModal("publish");
    },

    async publish() {
      this.modalError = ""; this.pubUrl = "";
      if (!this.isTeacher) {
        if (!this.teacherPass) { this.modalError = "Απαιτείται ο κωδικός καθηγητή για δημοσίευση."; return; }
        try {
          await this.api("api/teacher/login", { password: this.teacherPass });
          this.isTeacher = true;
          this.teacherPass = "";
          if (this.room.pin) this.connectRoom(this.room.pin);
        } catch (e) { this.modalError = e.message; return; }
      }
      this.publishing = true;
      try {
        const data = await this.api("api/publish", { ...this.pub, ...this.getCode() });
        this.pubUrl = data.url;
        this.toast("🚀 Δημοσιεύτηκε στο Dashboard: " + data.title);
      } catch (e) {
        this.modalError = e.message;
      } finally {
        this.publishing = false;
      }
    }
  };
}