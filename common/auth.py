"""
common.auth — Αυθεντικοποίηση καθηγητή με υπογεγραμμένα cookies (HMAC-SHA256).

Ενοποιεί το μοτίβο που ήταν αντιγραμμένο σε exams / live-quiz / web-lab /
h5p-studio / app-builder / md-publish / lesson-wizard / classroom-hub:

  * Legacy token «<expires>.<sig>» (τα 7 πρώτα apps) — make_token()/token_valid().
  * Payload token «<expires>:<b64url(payload)>.<sig>» (Classroom Hub) —
    signed_token()/token_payload()· base64url ώστε τα ελληνικά ονόματα να
    είναι latin-1 safe μέσα στο cookie.

Το μυστικό παραμένει ΑΝΑ APP στο <app_dir>/.cookie-secret (0600, εκτός git),
οπότε τα υπάρχοντα cookies ΔΕΝ ακυρώνονται μετά τη μεταφορά στο common.
Χρήση από κάθε app:

    auth = TeacherAuth(BASE_DIR, COOKIE_NAME)
    auth.require_teacher(request)          # 401 χωρίς έγκυρο cookie
    auth.login_cookie(response)            # μετά τον έλεγχο του TEACHER_CODE
    auth.logout_cookie(response)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path

from fastapi import HTTPException, Request, Response

# ---------------------------------------------------------------------------
# Κοινές σταθερές αυθεντικοποίησης (ίδιες σε όλη την πύλη)
# ---------------------------------------------------------------------------
TEACHER_CODE = "teacher2026"                 # ίδιος κωδικός με όλη την πύλη
COOKIE_MAX_AGE = 8 * 3600                    # μία σχολική ημέρα


def secret_key(app_dir: Path) -> bytes:
    """Σταθερό μυστικό ανά εγκατάσταση (δημιουργείται μία φορά, εκτός git)."""
    key_file = Path(app_dir) / ".cookie-secret"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
        key_file.chmod(0o600)
    return key_file.read_text().strip().encode()


class TeacherAuth:
    """HMAC cookies καθηγητή για ένα app (ίδια μορφή token με πριν το refactor)."""

    def __init__(self, app_dir: Path, cookie_name: str,
                 max_age: int = COOKIE_MAX_AGE) -> None:
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.secret = secret_key(app_dir)

    # --- Legacy μορφή: "<expires>.<sig>" -----------------------------------
    def make_token(self) -> str:
        expires = int(time.time()) + self.max_age
        payload = str(expires)
        sig = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def token_valid(self, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        payload, _, sig = token.partition(".")
        expected = hmac.new(self.secret, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        try:
            return int(payload) > time.time()
        except ValueError:
            return False

    # --- Payload μορφή: "<expires>:<b64url(payload)>.<sig>" ------------------
    def signed_token(self, payload: str, max_age: int | None = None) -> str:
        # base64url: τα ονόματα είναι ελληνικά — τα cookies πρέπει να είναι latin-1 safe
        expires = int(time.time()) + (self.max_age if max_age is None else max_age)
        b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        body = f"{expires}:{b64}"
        sig = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{sig}"

    def token_payload(self, token: str | None) -> str | None:
        """Επιστρέφει το payload αν η υπογραφή & η λήξη είναι έγκυρες, αλλιώς None."""
        if not token or "." not in token:
            return None
        body, _, sig = token.rpartition(".")
        expected = hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        exp, _, b64 = body.partition(":")
        try:
            if int(exp) <= time.time():
                return None
            return base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    # --- Helpers επιπέδου request/response ----------------------------------
    def is_teacher(self, request: Request) -> bool:
        return self.token_valid(request.cookies.get(self.cookie_name))

    def require_teacher(self, request: Request) -> None:
        if not self.is_teacher(request):
            raise HTTPException(401, "Απαιτείται κωδικός καθηγητή.")

    def login_cookie(self, response: Response) -> None:
        response.set_cookie(self.cookie_name, self.make_token(), max_age=self.max_age,
                            httponly=True, samesite="lax", path="/")

    def logout_cookie(self, response: Response) -> None:
        response.delete_cookie(self.cookie_name, path="/")
