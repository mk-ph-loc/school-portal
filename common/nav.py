"""
common.nav — Single owner του αυτόματου nav στο mkdocs.yml (Task 4).

Πριν γράφανε 2 writers με διαφορετική λογική: το Lesson Wizard rebuild_nav()
(block rewrite μεταξύ BEGIN/END AUTO-NAV) και το MD-Bridge add_to_nav() (text
insertion ΕΚΤΟΣ block → κίνδυνος απώλειας σε επόμενο rebuild + race χωρίς lock).

Τώρα ΟΛΟΙ γράφουν μόνο τα αρχεία τους και καλούν τη rebuild_nav(): folder-driven
και idempotent — ξαναχτίζει ΟΛΟ το αυτόματο μπλοκ από τους φακέλους:

    # BEGIN AUTO-NAV MATHIMATA …
      - 📖 Βιβλιοθήκη: vivliothiki/index.md          (αν υπάρχουν PDF)
      - Μαθήματα: <τάξη>/<μάθημα>/…                   (mathimata/, φάσεις)
      - Παλιό Υλικό (Παράδειγμα): …                   (_paradeigma/, όλοι οι φάκελοι)
    # END AUTO-NAV MATHIMATA

Text-based rewrite (ΟΧΙ yaml round-trip): σχόλια, !!python/name tags και η
υπόλοιπη μορφοποίηση του mkdocs.yml μένουν ανέπαφα. Κάθε ανάγνωση+εγγραφή
γίνεται κάτω από flock στο data/nav.lock (κοινό για root/systemd & www-data,
όπως το mkdocs-build.lock) και η εγγραφή είναι ατομική (tmp + os.replace).
Πριν από κάθε αλλαγή κρατιέται ιστορικό .bak στον φάκελο backups/ του caller.
"""
from __future__ import annotations

import fcntl
import logging
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .classes import CLASS_GROUPS, CLASS_LABELS
from .fs import backup_history
from .lessons import FM_RE, list_all_lessons

log = logging.getLogger("common.nav")

PORTAL_DIR = Path(__file__).resolve().parent.parent      # /opt/school-portal
NAV_LOCK = PORTAL_DIR / "data" / "nav.lock"

# Δείκτες του αυτόματου μπλοκ (legacy ονομασία MATHIMATA — τώρα περιλαμβάνει
# και το _paradeigma/ ώστε οι δημοσιεύσεις του MD-Bridge να επιβιώνουν).
NAV_BEGIN = "# BEGIN AUTO-NAV MATHIMATA"
NAV_END = "# END AUTO-NAV MATHIMATA"
NAV_HEADER = NAV_BEGIN + " (διαχειρίζεται αυτόματα από την πύλη — μην επεξεργάζεστε χειροκίνητα)"


@contextmanager
def nav_lock() -> Iterator[None]:
    """Αποκλειστικό flock γύρω από κάθε ανάγνωση+εγγραφή του mkdocs.yml."""
    NAV_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(NAV_LOCK, "a+") as lf:
        try:
            os.chmod(NAV_LOCK, 0o664)   # root (systemd) & www-data συνεργάζονται
        except OSError:
            pass                        # μη-idιοκτήτης: αρκεί το group-write που ήδη υπάρχει
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _yaml_sq(title: str) -> str:
    """Ασφαλές single-quoted YAML scalar (ίδια σύμβαση με το παλιό wizard)."""
    return "'" + title.replace("'", "''") + "'"


def _subject_label(docs_dir: Path, cls_slug: str, subj: str) -> str:
    """Τίτλος ενότητας: front-matter title του index.md, αλλιώς το slug."""
    label = subj.replace("-", " ").capitalize()
    idx = docs_dir / "mathimata" / cls_slug / subj / "index.md"
    if idx.is_file():
        fm = FM_RE.match(idx.read_text(encoding="utf-8", errors="ignore"))
        if fm:
            tm = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", fm.group(1), re.MULTILINE)
            if tm:
                label = tm.group(1).strip()
    return label


def _first_heading(path: Path, fallback: str) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        log.warning("nav: δεν διαβάστηκε το %s", path)
    return fallback



def _paradeigma_lines(par_dir: Path) -> list[str]:
    """Folder-driven ενότητα «Παλιό Υλικό» — ΟΛΟΙ οι φάκελοι του _paradeigma/.

    Ίδια διάταξη με το χειροκίνητο nav που αντικαθιστά: index πρώτο, μετά τα
    .md αλφαβητικά· Γυμνάσιο/Λύκειο ομαδοποιημένα, οι υπόλοιποι φάκελοι
    (games/media/teachers/…) στο τέλος με τίτλο από το H1 τους.
    """
    if not par_dir.is_dir():
        return []
    lines = ["  - Παλιό Υλικό (Παράδειγμα):"]
    if (par_dir / "index.md").is_file():
        lines.append("      - _paradeigma/index.md")

    def class_entries(slug: str) -> list[str]:
        cdir = par_dir / slug
        out = [f"          - {CLASS_LABELS[slug]}:"]
        if (cdir / "index.md").is_file():
            out.append(f"              - _paradeigma/{slug}/index.md")
        for p in sorted(cdir.glob("*.md")):
            if p.name == "index.md":
                continue
            title = _first_heading(p, p.stem)
            out.append(f"              - {_yaml_sq(title)}: _paradeigma/{slug}/{p.name}")
        return out

    gym = [c["slug"] for c in CLASS_GROUPS if c["slug"].startswith("gymnasio")]
    lyk = [c["slug"] for c in CLASS_GROUPS if c["slug"].startswith("lykeio")]
    if any((par_dir / s).is_dir() for s in gym):
        lines.append("      - Γυμνάσιο:")
        for s in gym:
            if (par_dir / s).is_dir():
                lines.extend(class_entries(s))
    if any((par_dir / s).is_dir() for s in lyk):
        lines.append("      - Λύκειο:")
        for s in lyk:
            if (par_dir / s).is_dir():
                lines.extend(class_entries(s))
    known = set(gym) | set(lyk)
    for d in sorted(par_dir.iterdir()):
        if not d.is_dir() or d.name in known or d.name.startswith("."):
            continue
        idx = d / "index.md"
        label = _first_heading(idx, d.name.capitalize()) if idx.is_file() else d.name.capitalize()
        lines.append(f"      - {_yaml_sq(label)}:")
        if idx.is_file():
            lines.append(f"          - _paradeigma/{d.name}/index.md")
        for p in sorted(d.glob("*.md")):
            if p.name == "index.md":
                continue
            title = _first_heading(p, p.stem)
            lines.append(f"          - {_yaml_sq(title)}: _paradeigma/{d.name}/{p.name}")
    return lines


def build_nav_block(docs_dir: Path) -> list[str]:
    """Ολόκληρο το αυτόματο μπλοκ (δείκτες μαζί) από τους φακέλους του docs/."""
    docs_dir = Path(docs_dir)
    lines = ["  " + NAV_HEADER]
    lib = docs_dir / "vivliothiki"
    if lib.is_dir() and any(lib.glob("*.pdf")):
        lines.append("  - 📖 Βιβλιοθήκη: vivliothiki/index.md")
    lessons = list_all_lessons(docs_dir / "mathimata")
    by_class: dict[str, dict[str, list]] = {}
    for les in lessons:
        by_class.setdefault(les["class_slug"], {}).setdefault(les["subject"], []).append(les)
    math_lines: list[str] = []
    for cls in CLASS_GROUPS:
        subjects = by_class.get(cls["slug"])
        if not subjects:
            continue
        math_lines.append(f"      - {cls['label']}:")
        for subj, items in subjects.items():
            idx_rel = f"mathimata/{cls['slug']}/{subj}/index.md"
            if (docs_dir / idx_rel).is_file():
                label = _subject_label(docs_dir, cls["slug"], subj)
                math_lines.append(f"          - {_yaml_sq(label)}: {idx_rel}")
            for les in items:
                rel = f"mathimata/{cls['slug']}/{subj}/{les['lesson']}/index.md"
                math_lines.append(f"          - {_yaml_sq(les['title'])}: {rel}")
    if math_lines:
        lines.append("  - Μαθήματα:")
        lines.extend(math_lines)
    lines.extend(_paradeigma_lines(docs_dir / "_paradeigma"))
    lines.append("  " + NAV_END)
    return lines


def rebuild_nav(mkdocs_yml: Path, *, backup_dir: Path | None = None) -> bool:
    """Idempotent folder-driven rebuild του αυτόματου nav μπλοκ.

    Επιστρέφει True αν το αρχείο άλλαξε. Χωρίς δείκτες BEGIN/END δεν πειράζει
    τίποτα (όπως πάντα). Το backup_dir είναι το backups/ του app που καλεί.
    """
    mkdocs_yml = Path(mkdocs_yml).resolve()
    docs_dir = mkdocs_yml.parent / "docs"
    with nav_lock():
        text = mkdocs_yml.read_text(encoding="utf-8")
        i = text.find(NAV_BEGIN)
        j = text.find(NAV_END)
        if i == -1 or j == -1:
            log.warning("nav: δεν βρέθηκαν οι δείκτες AUTO-NAV στο %s — καμία αλλαγή", mkdocs_yml)
            return False
        j_end = text.find("\n", j)
        if j_end == -1:
            j_end = len(text)
        # Ο δείκτης BEGIN πρέπει να ξεκινά στην αρχή της γραμμής του (όχι μετά
        # τα κενά indent — θα διπλασιάζονταν σε κάθε rebuild).
        i = text.rfind("\n", 0, i) + 1
        new_text = text[:i] + "\n".join(build_nav_block(docs_dir)) + text[j_end:]
        if new_text == text:
            return False
        if backup_dir is not None:
            backup_history(mkdocs_yml, backup_dir, relative_to=PORTAL_DIR)
        # Ατομική αντικατάσταση: οι μαθητές/builds δεν βλέπουν ποτέ μισό αρχείο.
        tmp = mkdocs_yml.with_name(mkdocs_yml.name + ".nav-tmp")
        tmp.write_text(new_text, encoding="utf-8")
        try:
            os.chmod(tmp, 0o664)        # root & www-data συνεργάζονται (install.sh)
        except OSError:
            pass
        os.replace(tmp, mkdocs_yml)
        log.info("nav: ενημερώθηκε το αυτόματο μπλοκ στο %s", mkdocs_yml.name)
        return True
