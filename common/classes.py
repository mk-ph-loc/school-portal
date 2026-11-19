"""
common.classes — Οι 6 τάξεις του mkdocs-site & ασφαλής μετατροπή τίτλων σε slug.

Ενοποιεί τις λίστες CLASSES/CLASS_GROUPS που ήταν αντιγραμμένες σε exams,
lesson-wizard, h5p-studio, hedgedoc-bridge, classroom-hub και pandoc, καθώς
και τις greek_slug()/slugify() (exams/pandoc) που είχαν ίδιο χάρτη Greeklish.
"""
from __future__ import annotations

import re
import unicodedata

# Οι 6 τάξεις του mkdocs-site (ίδιοι φάκελοι με το nav του mkdocs.yml)
CLASS_GROUPS = [
    {"slug": "gymnasio-a", "label": "Α' Γυμνασίου"},
    {"slug": "gymnasio-b", "label": "Β' Γυμνασίου"},
    {"slug": "gymnasio-g", "label": "Γ' Γυμνασίου"},
    {"slug": "lykeio-a",   "label": "Α' Λυκείου"},
    {"slug": "lykeio-b",   "label": "Β' Λυκείου"},
    {"slug": "lykeio-g",   "label": "Γ' Λυκείου"},
]
CLASS_SLUGS = {c["slug"] for c in CLASS_GROUPS}
CLASS_LABELS = {c["slug"]: c["label"] for c in CLASS_GROUPS}

# Το Pandoc Studio προσφέρει ΕΠΙΠΛΕΟΝ την προστατευμένη περιοχή καθηγητών.
TEACHERS_AREA = {"slug": "teachers", "label": "🔐 Περιοχή Καθηγητών"}
CLASSES_WITH_TEACHERS = CLASS_GROUPS + [TEACHERS_AREA]

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")        # πεζά λατινικά/greeklish

_GREEK_MAP = {
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y",
    "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o",
}


def greek_slug(text: str, limit: int = 60, fallback: str = "mathitis") -> str:
    """Μετατρέπει ελληνικό/λατινικό κείμενο σε ασφαλές όνομα αρχείου (Greeklish).

    limit/fallback: τα defaults είναι του exams-app (ονόματα μαθητών)· το
    Pandoc Studio καλεί greek_slug(title, limit=80, fallback="mathima").
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(_GREEK_MAP.get(ch, ch) for ch in text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:limit] or fallback
