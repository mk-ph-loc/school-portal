"""
common.db — Κοινές συνδέσεις SQLite για όλα τα apps της πύλης.

Ενοποιεί τις db() που ήταν αντιγραμμένες σε exams / live-quiz / web-lab /
h5p-studio / classroom-hub: timeout 15s, Row factory, WAL journal. Το
foreign_keys=ON είναι προαιρετικό (web-lab & h5p-studio δεν το είχαν — δεν
έχουν FK constraints), ώστε η συμπεριφορά κάθε app να μένει ακριβώς ίδια.

Οι βάσεις παραμένουν στις διαδρομές που όριζε πάντα το κάθε app.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator


def connect(db_path: Path, *, foreign_keys: bool = True,
            create_parent: bool = False, timeout: int = 15) -> sqlite3.Connection:
    """Σύνδεση SQLite με τις κοινές ρυθμίσεις της πύλης (WAL + Row factory)."""
    if create_parent:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys=ON")   # τα ON DELETE CASCADE να ισχύουν πραγματικά
    return conn


def connect_ro(db_path: Path) -> sqlite3.Connection:
    """Read-only σύνδεση (mode=ro — ποτέ δεν γράφουμε), π.χ. βάση HedgeDoc."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def session(db_path: Path, *, foreign_keys: bool = True,
            create_parent: bool = False, timeout: int = 15) -> Iterator[sqlite3.Connection]:
    """Σύνδεση ως context manager που ΚΛΕΙΝΕΙ πραγματικά τη σύνδεση.

    Το σκέτο `with connect(...) as conn:` κάνει μόνο commit/rollback — ΔΕΝ
    κλείνει τη σύνδεση (οι WAL readers/fds μαζεύονταν μέχρι το GC). Εδώ:
    επιτυχία → commit, εξαίρεση → rollback, και ΠΑΝΤΑ close στο τέλος.

        with session(DB_PATH) as conn:
            conn.execute(...)
    """
    with closing(connect(db_path, foreign_keys=foreign_keys,
                         create_parent=create_parent, timeout=timeout)) as conn:
        with conn:                                # commit/rollback όπως πριν
            yield conn


@contextmanager
def session_ro(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Read-only εκδοχή του session() — πάντα close (π.χ. βάση HedgeDoc)."""
    with closing(connect_ro(db_path)) as conn:
        yield conn


def add_columns(conn: sqlite3.Connection, migrations: tuple[tuple[str, str, str], ...]) -> None:
    """Ήπιες migrations για υπάρχουσες βάσεις: ALTER TABLE ADD COLUMN αν λείπει.

    migrations: iterable από (table, column, ddl) — όπως στο classroom-hub.
    """
    for table, col, ddl in migrations:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
