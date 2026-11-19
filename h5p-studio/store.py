"""
H5P Studio — SQLite schema & queries (Task 3: διάσπαση σε APIRouters).

activities/settings στο h5p.db (μέσω common.db — WAL/Row, χωρίς FK όπως πριν)
+ ρυθμίσεις AI (οι τιμές του Studio υπερισχύουν, αλλιώς .env.keys/περιβάλλον).
"""
from __future__ import annotations

import os

from common.db import session

import state

# ---------------------------------------------------------------------------
# Βάση δεδομένων (SQLite — κοινές ρυθμίσεις πύλης μέσω common.db)
# ---------------------------------------------------------------------------
def db():
    """Context manager σύνδεσης: commit/rollback ΚΑΙ close (common.db.session).

    Χωρίς FK constraints στο σχήμα — foreign_keys όπως πριν (default OFF).
    """
    return session(state.DB_PATH, foreign_keys=False)


def init_db() -> None:
    state.LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                type        TEXT NOT NULL,             -- multichoice|...|external
                main_lib    TEXT NOT NULL DEFAULT '',  -- π.χ. H5P.MultiChoice 1.16
                class_slug  TEXT NOT NULL DEFAULT '',
                subject     TEXT NOT NULL DEFAULT '',
                chapter     TEXT NOT NULL DEFAULT '',
                goal        TEXT NOT NULL DEFAULT '',
                difficulty  TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Ρυθμίσεις AI (OpenAI-compatible — Alibaba Qwen από το .env.keys της πύλης)
# ---------------------------------------------------------------------------
def read_env_keys() -> dict[str, str]:
    """Διαβάζει το .env.keys της πύλης (ALIBABA_API_KEY/BASE_URL/PLAN_MODEL)."""
    out: dict[str, str] = {}
    if state.ENV_KEYS_FILE.is_file():
        try:
            for line in state.ENV_KEYS_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    out[k.strip()] = v.strip()
        except OSError:
            pass
    return out


def get_setting(key: str, default: str = "") -> str:
    with db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def ai_config() -> dict:
    """Ρυθμίσεις AI: οι τιμές του Studio υπερισχύουν, αλλιώς .env.keys/περιβάλλον."""
    env = read_env_keys()
    key = (get_setting("ai_api_key") or os.environ.get("ALIBABA_API_KEY")
           or env.get("ALIBABA_API_KEY", ""))
    base = (get_setting("ai_base_url") or os.environ.get("ALIBABA_BASE_URL")
            or env.get("ALIBABA_BASE_URL",
                       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"))
    model = (get_setting("ai_model") or os.environ.get("PLAN_MODEL")
             or env.get("PLAN_MODEL", "qwen-plus"))
    models = (env.get("AVAILABLE_MODELS", "") or model).split(",")
    return {"configured": bool(key), "key": key, "base_url": base.rstrip("/"),
            "model": model, "models": [m.strip() for m in models if m.strip()]}
