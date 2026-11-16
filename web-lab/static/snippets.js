/* ===========================================================================
 * Έτοιμα Snippets & Πρότυπα — Εργαστήριο Web (HTML / CSS / JS)
 * 4 κατηγορίες, αποκλειστικά στα Ελληνικά. Κάθε snippet δηλώνει τα πάνελ που
 * γεμίζει (html/css/js). Τα starter:true ΑΝΤΙΚΑΘΙΣΤΟΥΝ όλο το project.
 * =========================================================================== */
window.WEBLAB_SNIPPETS = [
{
  title: "HTML Βασικά", icon: "🧱", open: true,
  items: [
    {
      name: "Βασικός σκελετός σελίδας",
      html: `<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Η Σελίδα μου</title>
</head>
<body>
  <h1>Γεια σου κόσμε!</h1>
  <p>Αυτή είναι η πρώτη μου ιστοσελίδα.</p>
</body>
</html>`
    },
    {
      name: "Επικεφαλίδες & Παράγραφοι",
      html: `<h1>Κεντρικός Τίτλος (h1)</h1>
<h2>Δευτερεύων Τίτλος (h2)</h2>
<h3>Μικρότερη Επικεφαλίδα (h3)</h3>
<p>Αυτή είναι μια <strong>παράγραφος</strong> με <em>έμφαση</em>
και <mark>υπογράμμιση</mark>. Οι παράγραφοι χωρίζουν το κείμενο
σε λογικές ενότητες.</p>
<p>Δεύτερη παράγραφος με <br> αλλαγή γραμμής.</p>`
    },
    {
      name: "Λίστες (ul / ol)",
      html: `<h2>Αγαπημένα Μαθήματα (μη αριθμημένη λίστα)</h2>
<ul>
  <li>Πληροφορική</li>
  <li>Μαθηματικά</li>
  <li>Φυσική</li>
</ul>

<h2>Βήματα Δημιουργίας Ιστοσελίδας (αριθμημένη λίστα)</h2>
<ol>
  <li>Γράφω τη δομή σε HTML</li>
  <li>Μορφοποιώ με CSS</li>
  <li>Προσθέτω διαδραστικότητα με JavaScript</li>
</ol>`
    },
    {
      name: "Σύνδεσμος & Εικόνα",
      html: `<h2>Σύνδεσμος &amp; Εικόνα</h2>
<p><a href="https://el.wikipedia.org" target="_blank">
  Άνοιγμα της Βικιπαίδειας σε νέα καρτέλα
</a></p>

<!-- Εικόνα από το Διαδίκτυο (χρειάζεται σύνδεση) -->
<img src="https://picsum.photos/400/200" alt="Τυχαία φωτογραφία" width="400">

<!-- Τοπική εικόνα: βάλε το αρχείο δίπλα στο .html σου -->
<!-- <img src="foto.jpg" alt="Η φωτογραφία μου" width="300"> -->`
    },
    {
      name: "Πίνακας (table)",
      html: `<h2>Ωρολόγιο Πρόγραμμα</h2>
<table border="1" cellpadding="8">
  <thead>
    <tr><th>Ώρα</th><th>Δευτέρα</th><th>Τρίτη</th></tr>
  </thead>
  <tbody>
    <tr><td>08:15</td><td>Πληροφορική</td><td>Μαθηματικά</td></tr>
    <tr><td>09:10</td><td>Γλώσσα</td><td>Φυσική</td></tr>
    <tr><td>10:05</td><td>Ιστορία</td><td>Αγγλικά</td></tr>
  </tbody>
</table>`,
      css: `table { border-collapse: collapse; }
th { background: #1e3a8a; color: white; }
tr:nth-child(even) { background: #e0e7ff; }`
    },
    {
      name: "Φόρμα Επικοινωνίας (form)",
      html: `<h2>Φόρμα Επικοινωνίας</h2>
<form id="forma">
  <label>Ονοματεπώνυμο:<br>
    <input type="text" name="onoma" placeholder="π.χ. Μαρία Παπαδοπούλου" required>
  </label><br><br>
  <label>Email:<br>
    <input type="email" name="email" placeholder="mou@example.gr" required>
  </label><br><br>
  <label>Το μήνυμά σου:<br>
    <textarea name="minyma" rows="4" cols="40"></textarea>
  </label><br><br>
  <button type="submit">📨 Αποστολή</button>
</form>`,
      js: `document.getElementById("forma").addEventListener("submit", function (e) {
  e.preventDefault(); // μην φύγει η σελίδα
  alert("Ευχαριστούμε! Το μήνυμά σου στάλθηκε. ✅");
});`
    }
  ]
},
{
  title: "CSS Μορφοποίηση", icon: "🎨", open: false,
  items: [
    {
      name: "Χρώματα & Γραμματοσειρές",
      css: `/* Χρώματα & γραμματοσειρές για όλη τη σελίδα */
body {
  background-color: #f0f9ff;      /* ανοιχτό γαλάζιο φόντο */
  color: #0f172a;                 /* σκούρο κείμενο */
  font-family: Georgia, "Times New Roman", serif;
  font-size: 18px;
}
h1 {
  color: #7c3aed;                 /* μοβ τίτλος */
  text-align: center;
  text-shadow: 2px 2px 4px rgba(0,0,0,.2);
}
p { line-height: 1.6; }`
    },
    {
      name: "Box Model (Margin / Padding / Border)",
      html: `<div class="kouti">Είμαι ένα κουτί! 📦</div>`,
      css: `.kouti {
  width: 260px;
  margin: 30px;          /* εξωτερική απόσταση από άλλα στοιχεία */
  padding: 20px;         /* εσωτερική απόσταση από το περιεχόμενο */
  border: 4px solid #0ea5e9;   /* περίγραμμα */
  border-radius: 12px;   /* στρογγυλεμένες γωνίες */
  background: #e0f2fe;
  box-shadow: 4px 4px 12px rgba(0,0,0,.15);
}`
    },
    {
      name: "Flexbox Διάταξη 3 Καρτών",
      html: `<div class="kartes">
  <div class="karta"><h3>🚀 Ταχύτητα</h3><p>Οι σελίδες φορτώνουν ακαριαία.</p></div>
  <div class="karta"><h3>🎨 Ομορφιά</h3><p>Μοντέρνα εμφάνιση με CSS.</p></div>
  <div class="karta"><h3>🔒 Ασφάλεια</h3><p>HTTPS παντού!</p></div>
</div>`,
      css: `.kartes {
  display: flex;          /* τα παιδιά μπαίνουν στη σειρά */
  gap: 16px;              /* κενό ανάμεσα στις καρτέλες */
  flex-wrap: wrap;        /* αλλαγή γραμμής σε μικρές οθόνες */
  justify-content: center;
}
.karta {
  flex: 1 1 180px;        /* μεγαλώνουν/μικραίνουν ισότιμα */
  max-width: 240px;
  padding: 20px;
  border-radius: 16px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  text-align: center;
}`
    },
    {
      name: "Hover Εφέ Κουμπιού",
      html: `<button class="koumpi">Πέρνα τον δείκτη από πάνω μου! ✨</button>`,
      css: `.koumpi {
  padding: 12px 28px;
  font-size: 16px;
  font-weight: bold;
  color: white;
  background: #059669;
  border: none;
  border-radius: 999px;
  cursor: pointer;
  transition: all .25s ease;   /* ομαλή μετάβαση */
}
.koumpi:hover {
  background: #10b981;
  transform: translateY(-3px) scale(1.05);
  box-shadow: 0 10px 20px rgba(5,150,105,.4);
}
.koumpi:active { transform: scale(.97); }`
    }
  ]
},
{
  title: "JavaScript Διαδραστικότητα", icon: "⚡", open: false,
  items: [
    {
      name: "Αλλαγή Κειμένου με Κουμπί (getElementById)",
      html: `<h2 id="keimeno">Αρχικό κείμενο 👋</h2>
<button id="koumpi">Άλλαξε το κείμενο!</button>`,
      js: `// Βρίσκουμε τα στοιχεία της σελίδας με το id τους
const keimeno = document.getElementById("keimeno");
const koumpi = document.getElementById("koumpi");

koumpi.addEventListener("click", function () {
  keimeno.textContent = "Το κείμενο άλλαξε με JavaScript! 🎉";
  keimeno.style.color = "#dc2626";
  console.log("Το κουμπί πατήθηκε!");
});`
    },
    {
      name: "Ανάγνωση Πεδίου Εισόδου (input)",
      html: `<label>Πώς σε λένε; <input type="text" id="onoma" placeholder="Γράψε το όνομά σου"></label>
<button id="xeretismos">Χαιρέτησέ με!</button>
<p id="apotellesma"></p>`,
      js: `document.getElementById("xeretismos").addEventListener("click", function () {
  const onoma = document.getElementById("onoma").value.trim();
  if (onoma === "") {
    alert("Γράψε πρώτα το όνομά σου!");
    return;
  }
  document.getElementById("apotellesma").textContent =
    "Γεια σου " + onoma + "! Καλώς ήρθες στην ιστοσελίδα μου. 🌟";
  console.log("Όνομα χρήστη:", onoma);
});`
    },
    {
      name: "Απλός Μετρητής (Counter)",
      html: `<h2>Μετρητής: <span id="timh">0</span></h2>
<button id="minus">➖ Μείωση</button>
<button id="plus">➕ Αύξηση</button>
<button id="miden">🔄 Μηδενισμός</button>`,
      css: `#timh { color: #2563eb; font-size: 1.4em; }
button { padding: 8px 16px; margin: 4px; font-size: 16px; cursor: pointer; }`,
      js: `let metritis = 0;   // η μεταβλητή-μετρητής

function enimerosi() {
  document.getElementById("timh").textContent = metritis;
  console.log("Νέα τιμή μετρητή:", metritis);
}

document.getElementById("plus").addEventListener("click", () => { metritis++; enimerosi(); });
document.getElementById("minus").addEventListener("click", () => { metritis--; enimerosi(); });
document.getElementById("miden").addEventListener("click", () => { metritis = 0; enimerosi(); });`
    },
    {
      name: "Αλλαγή Θέματος (Dark / Light Mode)",
      html: `<button id="thema">🌙 Σκοτεινό Θέμα</button>
<h1>Δοκίμασε το Dark Mode!</h1>
<p>Η JavaScript αλλάζει μια κλάση CSS στο body.</p>`,
      css: `body { background: #ffffff; color: #1e293b; transition: all .4s ease; font-family: sans-serif; }
body.skoteino { background: #0f172a; color: #e2e8f0; }
button { padding: 10px 20px; font-size: 15px; border-radius: 8px; cursor: pointer; }`,
      js: `const koumpi = document.getElementById("thema");

koumpi.addEventListener("click", function () {
  document.body.classList.toggle("skoteino");
  const einaiSkoteino = document.body.classList.contains("skoteino");
  koumpi.textContent = einaiSkoteino ? "☀️ Φωτεινό Θέμα" : "🌙 Σκοτεινό Θέμα";
  console.log("Θέμα:", einaiSkoteino ? "σκοτεινό" : "φωτεινό");
});`
    }
  ]
},
{
  title: "Ολοκληρωμένα Πρότυπα (Starter Projects)", icon: "🏗️", open: false,
  items: [
    {
      name: "Η Πρώτη μου Ιστοσελίδα", starter: true,
      html: `<!DOCTYPE html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Η Πρώτη μου Ιστοσελίδα</title>
</head>
<body>
  <header>
    <h1>🌍 Η Πρώτη μου Ιστοσελίδα</h1>
    <p class="slogan">Φτιάχτηκε με HTML, CSS &amp; JavaScript στο Εργαστήριο Web!</p>
  </header>

  <main>
    <section>
      <h2>Σχετικά με εμένα</h2>
      <p>Γεια! Είμαι μαθητής/μαθήτρια και μόλις έφτιαξα την πρώτη μου
      ιστοσελίδα. Μου αρέσει η πληροφορική, τα παιχνίδια και η μουσική.</p>
    </section>

    <section>
      <h2>Τα αγαπημένα μου</h2>
      <ul>
        <li>🎮 Βιντεοπαιχνίδια</li>
        <li>🎵 Μουσική</li>
        <li>⚽ Ποδόσφαιρο</li>
        <li>💻 Προγραμματισμός</li>
      </ul>
    </section>

    <button id="koumpi">Πάτησέ με!</button>
    <p id="minyma"></p>
  </main>

  <footer>© 2026 — Φτιάχτηκε στην τάξη της Πληροφορικής</footer>
</body>
</html>`,
      css: `body {
  margin: 0;
  font-family: "Segoe UI", Arial, sans-serif;
  background: #f1f5f9;
  color: #1e293b;
}
header {
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: white;
  text-align: center;
  padding: 40px 20px;
}
.slogan { opacity: .85; }
main { max-width: 640px; margin: 24px auto; padding: 0 16px; }
section {
  background: white;
  border-radius: 14px;
  padding: 20px 24px;
  margin-bottom: 16px;
  box-shadow: 0 4px 14px rgba(0,0,0,.08);
}
h2 { color: #2563eb; margin-top: 0; }
button {
  padding: 12px 24px; font-size: 16px; font-weight: bold;
  background: #059669; color: white; border: none;
  border-radius: 999px; cursor: pointer; transition: transform .2s;
}
button:hover { transform: scale(1.06); }
#minyma { font-weight: bold; color: #7c3aed; }
footer { text-align: center; padding: 20px; font-size: 13px; color: #64748b; }`,
      js: `let patimata = 0;
document.getElementById("koumpi").addEventListener("click", function () {
  patimata++;
  document.getElementById("minyma").textContent =
    "Με πάτησες " + patimata + (patimata === 1 ? " φορά!" : " φορές!") + " 🎉";
  console.log("Πατήματα κουμπιού:", patimata);
});`
    },
    {
      name: "Ψηφιακή Κάρτα Προφίλ", starter: true,
      html: `<div class="karta">
  <div class="avatar">🧑‍🚀</div>
  <h1 id="onoma">Μαρία Παπαδοπούλου</h1>
  <p class="titlos">Μαθήτρια Β' Γυμνασίου · Λάτρης της τεχνολογίας</p>

  <div class="statistika">
    <div><strong id="likes">0</strong><span>❤️ Likes</span></div>
    <div><strong>12</strong><span>📁 Projects</span></div>
    <div><strong>Β2</strong><span>🏫 Τμήμα</span></div>
  </div>

  <p class="bio">Μου αρέσει να φτιάχνω ιστοσελίδες, να λύνω γρίφους
  και να μαθαίνω νέα πράγματα για τους υπολογιστές!</p>

  <button id="like">❤️ Like</button>
  <button id="epafi">📧 Επικοινωνία</button>
</div>`,
      css: `body {
  min-height: 100vh; margin: 0;
  display: grid; place-items: center;
  background: linear-gradient(135deg, #0ea5e9, #6366f1);
  font-family: "Segoe UI", Arial, sans-serif;
}
.karta {
  width: 320px; padding: 28px; text-align: center;
  background: white; border-radius: 24px;
  box-shadow: 0 24px 60px rgba(0,0,0,.35);
}
.avatar {
  width: 90px; height: 90px; margin: 0 auto;
  display: grid; place-items: center; font-size: 48px;
  background: #e0e7ff; border-radius: 50%;
  border: 4px solid #6366f1;
}
h1 { font-size: 22px; margin: 14px 0 4px; color: #1e293b; }
.titlos { font-size: 13px; color: #64748b; margin: 0 0 16px; }
.statistika { display: flex; justify-content: space-around; margin-bottom: 16px; }
.statistika strong { display: block; font-size: 20px; color: #6366f1; }
.statistika span { font-size: 11px; color: #64748b; }
.bio { font-size: 13.5px; color: #475569; line-height: 1.5; }
button {
  margin: 4px; padding: 10px 18px; border: none; border-radius: 999px;
  font-weight: bold; cursor: pointer; transition: transform .15s;
}
#like { background: #fecdd3; color: #be123c; }
#epafi { background: #e0e7ff; color: #4338ca; }
button:hover { transform: scale(1.07); }`,
      js: `let likes = 0;
document.getElementById("like").addEventListener("click", function () {
  likes++;
  document.getElementById("likes").textContent = likes;
  console.log("Likes:", likes);
});
document.getElementById("epafi").addEventListener("click", function () {
  alert("📧 Στείλε μου μήνυμα στο: maria@example.gr");
});`
    },
    {
      name: "Διαδραστικό Κουίζ 3 Ερωτήσεων", starter: true,
      html: `<div class="kouiz">
  <h1>🧠 Κουίζ Πληροφορικής</h1>
  <p id="proodos"></p>
  <h2 id="erotisi"></h2>
  <div id="apantiseis"></div>
  <p id="apotelesma"></p>
</div>`,
      css: `body {
  min-height: 100vh; margin: 0; display: grid; place-items: center;
  background: #0f172a; color: #e2e8f0;
  font-family: "Segoe UI", Arial, sans-serif;
}
.kouiz {
  width: min(480px, 92vw); padding: 28px;
  background: #1e293b; border-radius: 20px;
  box-shadow: 0 20px 50px rgba(0,0,0,.5);
}
h1 { margin-top: 0; text-align: center; }
#proodos { text-align: center; color: #94a3b8; font-size: 13px; }
#apantiseis button {
  display: block; width: 100%; margin: 8px 0; padding: 12px;
  font-size: 15px; text-align: left; cursor: pointer;
  background: #334155; color: #e2e8f0;
  border: 2px solid transparent; border-radius: 12px;
  transition: all .2s;
}
#apantiseis button:hover { border-color: #38bdf8; transform: translateX(4px); }
#apantiseis button.sosto { background: #059669; }
#apantiseis button.lathos { background: #dc2626; }
#apotelesma { text-align: center; font-weight: bold; min-height: 24px; }`,
      js: `const erotiseis = [
  { e: "Τι σημαίνει HTML;",
    a: ["HyperText Markup Language", "High Tech Modern Language", "Home Tool Making Links"], sosti: 0 },
  { e: "Ποια γλώσσα μορφοποιεί την εμφάνιση μιας σελίδας;",
    a: ["JavaScript", "CSS", "Python"], sosti: 1 },
  { e: "Πόσα bit έχει ένα byte;",
    a: ["4", "16", "8"], sosti: 2 }
];

let trexousa = 0, skore = 0;

function deikseErotisi() {
  const q = erotiseis[trexousa];
  document.getElementById("proodos").textContent =
    "Ερώτηση " + (trexousa + 1) + " από " + erotiseis.length;
  document.getElementById("erotisi").textContent = q.e;
  document.getElementById("apotelesma").textContent = "";
  const kouti = document.getElementById("apantiseis");
  kouti.innerHTML = "";
  q.a.forEach(function (keimeno, i) {
    const b = document.createElement("button");
    b.textContent = keimeno;
    b.addEventListener("click", function () { apantisi(i, b); });
    kouti.appendChild(b);
  });
}

function apantisi(i, koumpi) {
  const q = erotiseis[trexousa];
  const buttons = document.querySelectorAll("#apantiseis button");
  buttons.forEach(b => b.disabled = true);
  if (i === q.sosti) {
    koumpi.classList.add("sosto"); skore++;
    console.log("Σωστή απάντηση! Σκορ:", skore);
  } else {
    koumpi.classList.add("lathos");
    buttons[q.sosti].classList.add("sosto");
    console.log("Λάθος απάντηση.");
  }
  setTimeout(function () {
    trexousa++;
    if (trexousa < erotiseis.length) { deikseErotisi(); }
    else { telos(); }
  }, 1200);
}

function telos() {
  document.getElementById("proodos").textContent = "Τέλος κουίζ!";
  document.getElementById("erotisi").textContent =
    "🏆 Σκορ: " + skore + " / " + erotiseis.length;
  document.getElementById("apantiseis").innerHTML = "";
  const xana = document.createElement("button");
  xana.textContent = "🔄 Παίξε ξανά";
  xana.addEventListener("click", function () {
    trexousa = 0; skore = 0; deikseErotisi();
  });
  document.getElementById("apantiseis").appendChild(xana);
}

deikseErotisi();   // ξεκινάμε!`
    }
  ]
}
];