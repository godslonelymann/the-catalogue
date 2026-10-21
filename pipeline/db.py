"""Postgres connection and schema migrations."""
import logging

import psycopg

from .config import CONFIG, ROOT

log = logging.getLogger(__name__)
MIGRATIONS = ROOT / "db" / "migrations"
SEEDS = ROOT / "db" / "seed"


def connect(autocommit=False):
    return psycopg.connect(CONFIG.db, autocommit=autocommit)


def migrate():
    """Apply db/migrations/*.sql files that are not applied yet, then run db/seed/*.sql.

    Each migration file runs once, in name order. Seed files must be safe to run many times.
    """
    with connect(autocommit=True) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename    text        PRIMARY KEY,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )""")
        applied = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            log.info("applying migration %s", path.name)
            # No parameters, so psycopg sends the whole file as one script.
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        for path in sorted(SEEDS.glob("*.sql")):
            log.info("running seed %s", path.name)
            conn.execute(path.read_text())
    log.info("database is up to date")
