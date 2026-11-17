#!/usr/bin/env python3
"""
make-pilot-assets.py — Παραγωγή υλικού για τον πιλότο (Ε1 Αλγοριθμική, Γ' Γυμνασίου).

Δημιουργεί σε κάθε φάκελο ημερήσιου μαθήματος:
  * aformisi.png  — εικόνα αφόρμησης (Pillow, ελληνικά με DejaVu)
  * slides.pdf    — παρουσίαση διαφανειών (WeasyPrint, ήδη στο requirements)

Επαναεκτελέσιμο (idempotent). Χρήση:
  /opt/school-portal/venv/bin/python scripts/make-pilot-assets.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path("/opt/school-portal/mkdocs-site/docs/mathimata/gymnasio-g/pliroforiki")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_B if bold else FONT, size)


# ---------------------------------------------------------------------------
# Εικόνες αφόρμησης
# ---------------------------------------------------------------------------
def sierpinski(draw, ax, ay, bx, by, cx, cy, depth, color):
    if depth == 0:
        draw.polygon([(ax, ay), (bx, by), (cx, cy)], fill=color)
        return
    abx, aby = (ax + bx) / 2, (ay + by) / 2
    bcx, bcy = (bx + cx) / 2, (by + cy) / 2
    cax, cay = (cx + ax) / 2, (cy + ay) / 2
    sierpinski(draw, ax, ay, abx, aby, cax, cay, depth - 1, color)
    sierpinski(draw, abx, aby, bx, by, bcx, bcy, depth - 1, color)
    sierpinski(draw, cax, cay, bcx, bcy, cx, cy, depth - 1, color)


def img_m01(path: Path):
    """Αφόρμηση Μ01: «κάθε εικόνα περιέχει τον εαυτό της» — ένθετα πλαίσια + σπιράλ."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#1a237e")
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = 60, 120, 560, 570
    for i in range(9):
        shade = 40 + i * 22
        d.rectangle([x0, y0, x1, y1], outline=(shade + 80, shade + 90, 255), width=3)
        nx0 = x0 + (x1 - x0) * 0.16
        ny0 = y0 + (y1 - y0) * 0.16
        nx1 = x1 - (x1 - x0) * 0.16
        ny1 = y1 - (y1 - y0) * 0.16
        x0, y0, x1, y1 = nx0, ny0, nx1, ny1
    cx, cy = 880, 350
    x, y = cx, cy
    heading = 0.0
    length = 6
    pts = [(x, y)]
    for _ in range(46):
        x += length * math.cos(math.radians(heading))
        y += length * math.sin(math.radians(heading))
        pts.append((x, y))
        heading += 90
        length += 6
    d.line(pts, fill="#ffca28", width=5)
    d.text((60, 30), "Τι βλέπεις μέσα στην εικόνα;", font=font(44, True), fill="white")
    d.text((620, 560), "…και μέσα σε αυτήν, ξανά η ίδια εικόνα!", font=font(26), fill="#c5cae9")
    im.save(path)


def img_m02(path: Path):
    """Αφόρμηση Μ02: οι τρεις στύλοι και οι δίσκοι του Ανόι."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#004d40")
    d = ImageDraw.Draw(im)
    d.text((60, 30), "Μετακίνησε όλη τη στοίβα στον στύλο Γ", font=font(42, True), fill="white")
    d.text((60, 90), "Ένας δίσκος τη φορά · ποτέ μεγάλος πάνω σε μικρό", font=font(26), fill="#b2dfdb")
    base_y = 540
    d.rectangle([80, base_y, 1120, base_y + 18], fill="#80cbc4")
    poles = {"Α": 260, "Β": 600, "Γ": 940}
    for name, px in poles.items():
        d.rectangle([px - 8, 200, px + 8, base_y], fill="#80cbc4")
        d.text((px - 12, base_y + 30), name, font=font(34, True), fill="white")
    colors = ["#ef5350", "#ffa726", "#ffee58", "#66bb6a"]
    widths = [300, 240, 180, 120]
    for i, (w, c) in enumerate(zip(widths, colors)):
        y = base_y - (i + 1) * 52
        d.rounded_rectangle([poles["Α"] - w / 2, y, poles["Α"] + w / 2, y + 46], radius=14, fill=c)
    im.save(path)


def img_m03(path: Path):
    """Αφόρμηση Μ03: τρίγωνο Sierpinski βάθους 5."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), "#263238")
    d = ImageDraw.Draw(im)
    sierpinski(d, 600, 130, 130, 590, 1070, 590, 5, "#4dd0e1")
    d.text((60, 30), "Ένα τρίγωνο που περιέχει… τον εαυτό του!", font=font(42, True), fill="white")
    d.text((820, 600), "Τρίγωνο Sierpinski", font=font(24), fill="#b0bec5")
    im.save(path)
# ---------------------------------------------------------------------------
# Παρουσιάσεις (HTML → PDF με WeasyPrint)
# ---------------------------------------------------------------------------
SLIDE_CSS = """
@page { size: 297mm 167mm; margin: 0; }
* { box-sizing: border-box; }
body { font-family: 'DejaVu Sans', sans-serif; margin: 0; color: #1a237e; }
.slide { width: 297mm; height: 167mm; padding: 14mm 18mm; page-break-after: always;
         position: relative; background: linear-gradient(135deg,#f5f7ff 0%,#e8eaf6 100%); }
.slide:last-child { page-break-after: auto; }
h1 { font-size: 30pt; margin: 0 0 8mm; }
h2 { font-size: 22pt; margin: 0 0 6mm; color: #283593; }
p, li { font-size: 15pt; line-height: 1.5; }
ul { margin: 4mm 0; }
.big { font-size: 20pt; font-weight: bold; text-align: center; margin-top: 14mm; }
.code { font-family: 'DejaVu Sans Mono', monospace; font-size: 13.5pt; background: #1a237e;
        color: #fff; padding: 6mm 8mm; border-radius: 3mm; white-space: pre; }
.footer { position: absolute; bottom: 7mm; left: 18mm; right: 18mm; font-size: 9pt;
          color: #7986cb; display: flex; justify-content: space-between; }
.accent { color: #d81b60; font-weight: bold; }
table { border-collapse: collapse; font-size: 14pt; margin: 4mm auto; }
td, th { border: 0.5mm solid #9fa8da; padding: 2.5mm 6mm; text-align: center; }
th { background: #c5cae9; }
"""


def make_slides(folder: str, title: str, slides_html: list[str]):
    from weasyprint import HTML

    parts = []
    n = len(slides_html)
    for i, body in enumerate(slides_html, 1):
        parts.append(
            f'<section class="slide">{body}'
            f'<div class="footer"><span>Πληροφορική Γ΄ Γυμνασίου — Ενότητα 1: Αλγοριθμική</span>'
            f"<span>{i} / {n}</span></div></section>"
        )
    html = f"<html><head><meta charset='utf-8'><style>{SLIDE_CSS}</style></head><body>{''.join(parts)}</body></html>"
    out = BASE / folder / "slides.pdf"
    HTML(string=html).write_pdf(str(out))
    print("OK", out)


def slides_m01():
    make_slides("m01-anadromi-aformisi-spiral", "Αναδρομή", [
        "<h1>🌀 Αναδρομή</h1><p class='big'>Όταν κάτι ορίζεται… με τον εαυτό του!</p>"
        "<p>Ενότητα 1 — Αλγοριθμική · Βιβλίο σελ. 7–8</p>",
        "<h2>Αυτοομοιότητα γύρω μας</h2><ul>"
        "<li>📱 Φωτογραφίζω έναν καθρέπτη: μέσα στη φωτογραφία φαίνεται το κινητό, μέσα στο κινητό ο καθρέπτης…</li>"
        "<li>🍫 Φαινόμενο <b>Droste</b>: το κουτί κακάο έχει ετικέτα… τον εαυτό του (Jan Misset, 1904)</li>"
        "<li>🔺 Fractals: σχήματα που <span class='accent'>περιέχουν τον εαυτό τους</span> (τρίγωνο Sierpinski)</li></ul>",
        "<h2>Αναδρομικός αλγόριθμος</h2>"
        "<p>Χωρίζει ένα πρόβλημα σε <b>μικρότερα υποπροβλήματα του ίδιου είδους</b> και εφαρμόζει σε κάθε μέρος "
        "<span class='accent'>την ίδια ακριβώς διαδικασία</span>.</p>"
        "<p class='big'>Η λύση του προβλήματος… χρησιμοποιεί τη λύση του προβλήματος!</p>",
        "<h2>Παράδειγμα: το σπιράλ</h2>"
        "<div class='code'>Ορισμός Σχεδίασε_Σπιράλ(βήματα)\n    Προχώρα βήματα\n    Στρίψε αριστερά 90°\n    Σχεδίασε_Σπιράλ(βήματα + 5)</div>"
        "<p>Η εντολή <b>καλεί τον εαυτό της</b> με λίγο μεγαλύτερο μήκος. Κάθε πλευρά μεγαλώνει κατά 5.</p>",
        "<h2>⚠️ Θα σταματήσει ποτέ;</h2>"
        "<p>Χωρίς έλεγχο, το σπιράλ <span class='accent'>δεν σταματά ποτέ</span> → παραβιάζεται η <b>περατότητα</b>!</p>"
        "<p>Λύση: <b>συνθήκη διακοπής</b> — καλούμε το επόμενο βήμα <b>μόνο αν</b> το μήκος ≤ 360 βήματα (το ύψος της σκηνής).</p>"
        "<div class='code'>ΑΝ μήκος &lt; 360 ΤΟΤΕ\n    Σχεδίασε_Σπιράλ(μήκος + 5)</div>",
        "<h2>Τι κρατάμε 🎒</h2><ul>"
        "<li>Αναδρομή = ορισμός/λύση που αναφέρεται στον εαυτό της</li>"
        "<li>Κάθε αναδρομή χρειάζεται <span class='accent'>βήμα διακοπής</span></li>"
        "<li>Χωρίς αυτό → άπειρη εκτέλεση (ή κρασάρισμα!)</li></ul>"
        "<p class='big'>Σειρά σας: δοκιμάστε το σπιράλ στη δραστηριότητα! ✍️</p>",
    ])
def slides_m02():
    make_slides("m02-pyrgoi-anoy", "Ανόι", [
        "<h1>🗼 Οι Πύργοι του Ανόι</h1><p class='big'>Ένας θρύλος, τρεις στύλοι και Ν δίσκοι</p>"
        "<p>Ενότητα 1 — Δραστηριότητα 1 · Βιβλίο σελ. 9</p>",
        "<h2>Οι κανόνες</h2><ul>"
        "<li>Οι δίσκοι ξεκινούν στον στύλο <b>Α</b>, από τον μεγαλύτερο (κάτω) ως τον μικρότερο (πάνω)</li>"
        "<li>Στόχος: όλη η στοίβα στον στύλο <b>Γ</b>· ο <b>Β</b> είναι βοηθητικός</li>"
        "<li>Μετακινούμε <span class='accent'>έναν δίσκο τη φορά</span> (τον πάνω-πάνω)</li>"
        "<li><span class='accent'>Ποτέ</span> μεγάλος δίσκος πάνω σε μικρότερο</li></ul>",
        "<h2>Ξεκινάμε μικρά: 1 και 2 δίσκοι</h2>"
        "<table><tr><th>Δίσκοι</th><th>Ελάχιστες κινήσεις</th></tr>"
        "<tr><td>1</td><td>1</td></tr><tr><td>2</td><td>3</td></tr><tr><td>3</td><td>;</td></tr></table>"
        "<p>Με 2 δίσκους: μικρός Α→Β, μεγάλος Α→Γ, μικρός Β→Γ. <b>3 κινήσεις.</b></p>",
        "<h2>3 δίσκοι: η «έξυπνη» ιδέα</h2>"
        "<div class='code'>Μετακίνησε_3_δίσκους(Α, Γ):\n    Μετακίνησε_2_δίσκους(Α, Β)   # οι 2 πάνω στον βοηθητικό\n    Μετακίνησε(Α, Γ)           # ο μεγαλύτερος στον στόχο\n    Μετακίνησε_2_δίσκους(Β, Γ)   # οι 2 πάνω του</div>"
        "<p>Λύνουμε το πρόβλημα των 3… <span class='accent'>χρησιμοποιώντας τη λύση των 2!</span></p>",
        "<h2>Γενίκευση: Ν δίσκοι</h2>"
        "<div class='code'>Μετακίνησε_Ν(Χ, Υ, βοηθ):\n    ΑΝ Ν == 1: Μετακίνησε(Χ, Υ)\n    ΑΛΛΙΩΣ:\n        Μετακίνησε_Ν-1(Χ, βοηθ, Υ)\n        Μετακίνησε(Χ, Υ)\n        Μετακίνησε_Ν-1(βοηθ, Υ, Χ)</div>"
        "<p>Κάθε πρόβλημα <b>ανάγεται στο ίδιο πρόβλημα με έναν δίσκο λιγότερο</b>. Βήμα διακοπής: Ν = 1.</p>",
        "<h2>Πόσες κινήσεις; Το μοτίβο 🔍</h2>"
        "<table><tr><th>Ν</th><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td></tr>"
        "<tr><th>Κινήσεις</th><td>1</td><td>3</td><td>7</td><td>15</td><td>31</td></tr></table>"
        "<p class='big'>Κ(N) = 2 × Κ(N−1) + 1 = 2<sup>Ν</sup> − 1</p>"
        "<p>Για 64 δίσκους: 2<sup>64</sup> − 1 ≈ 1,8 × 10<sup>19</sup> κινήσεις — ο θρύλος λέει ότι τότε τελειώνει ο κόσμος! 😅</p>",
    ])


def slides_m03():
    make_slides("m03-trigono-sierpinski", "Sierpinski", [
        "<h1>🔺 Το Τρίγωνο Sierpinski</h1><p class='big'>Ζωγραφίζοντας την αναδρομή</p>"
        "<p>Ενότητα 1 — Δραστηριότητα 2 · Βιβλίο σελ. 10</p>",
        "<h2>Ο αλγόριθμος</h2><ul>"
        "<li>Παίρνουμε ένα τρίγωνο και το χωρίζουμε σε <b>4 ίσα τρίγωνα</b></li>"
        "<li>Αφήνουμε το μεσαίο <b>κενό</b> → μένουν 3 χρωματισμένα</li>"
        "<li>Σε <span class='accent'>κάθε ένα από τα 3</span> εφαρμόζουμε τον ίδιο αλγόριθμο</li>"
        "<li>…και ξανά, και ξανά!</li></ul>",
        "<h2>Σε ψευδογλώσσα</h2>"
        "<div class='code'>Ορισμός Sierpinski(τρίγωνο, βάθος)\n    ΑΝ βάθος == 0 ΤΟΤΕ\n        Γέμισε_το_τρίγωνο(τρίγωνο)\n    ΑΛΛΙΩΣ\n        Sierpinski(πάνω, βάθος - 1)\n        Sierpinski(αριστερά, βάθος - 1)\n        Sierpinski(δεξιά, βάθος - 1)</div>"
        "<p><b>Τρεις</b> αναδρομικές κλήσεις σε κάθε βήμα — το βάθος μικραίνει κατά 1.</p>",
        "<h2>Πότε τερματίζει; ⏹️</h2>"
        "<p>Όταν το <b>βάθος φτάσει στο 0</b> — το βήμα διακοπής!</p>"
        "<p>Στο χαρτί: τερματίζει πρακτικά όταν τα τριγωνάκια γίνουν τόσο μικρά που δεν ζωγραφίζονται άλλο.</p>"
        "<p class='big'>Βάθος 1 → 3 τρίγωνα · Βάθος 2 → 9 · Βάθος 3 → 27 … 3<sup>Ν</sup></p>",
        "<h2>Αναδρομή παντού 🌍</h2><ul>"
        "<li>🥦 Μπρόκολο Romanesco, νιφάδες χιονιού, ακτογραμμές</li>"
        "<li>📁 Φάκελοι μέσα σε φακέλους στον υπολογιστή</li>"
        "<li>🧬 Δέντρα αποφάσεων, αναζήτηση σε δομές — θεμέλιο της Πληροφορικής</li></ul>"
        "<p class='big'>Σειρά σας: χαρτί, μολύβι… και υπομονή! ✏️</p>",
    ])


def main():
    img_m01(BASE / "m01-anadromi-aformisi-spiral" / "aformisi.png")
    img_m02(BASE / "m02-pyrgoi-anoy" / "aformisi.png")
    img_m03(BASE / "m03-trigono-sierpinski" / "aformisi.png")
    print("OK εικόνες αφόρμησης")
    slides_m01()
    slides_m02()
    slides_m03()


if __name__ == "__main__":
    main()