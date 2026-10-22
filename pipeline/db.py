"""Postgres connection and schema migrations."""
import logging
import os

import psycopg
from psycopg import sql

from .config import CONFIG, ROOT

log = logging.getLogger(__name__)
MIGRATIONS = ROOT / "db" / "migrations"
SEEDS = ROOT / "db" / "seed"


# The libpq inside psycopg[binary] has its own OpenSSL, which does not know where this
# computer keeps its trusted certificates. So sslrootcert=system (used for Neon) fails with
# "certificate verify failed". OpenSSL reads SSL_CERT_FILE, so point it to the system file.
CA_BUNDLES = ("/etc/ssl/certs/ca-certificates.crt",  # Ubuntu / Debian (GitHub runners)
              "/etc/ssl/cert.pem",                   # macOS
              "/etc/pki/tls/certs/ca-bundle.crt")    # Fedora / Amazon Linux


def _use_system_certificates():
    if os.environ.get("SSL_CERT_FILE"):
        return
    for path in CA_BUNDLES:
        if os.path.exists(path):
            os.environ["SSL_CERT_FILE"] = path
            return


def connect(autocommit=False):
    if "sslrootcert=system" in CONFIG.db:
        _use_system_certificates()
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


# ---------------------------------------------------------------------------- database users

APP_ROLES = ("pipeline", "website")
URL_KEYS = {"pipeline": "PIPELINE_DB_URL", "website": "WEBSITE_DB_URL"}
SECRET_KEYS = ("TELEGRAM_WEBHOOK_SECRET", "RATE_LIMIT_SALT")


def _role_url(info, role, password, pooled):
    """Connection URL for one role, on the same server and database as `info` (the owner connection)."""
    if info.host.startswith("/"):  # local socket: no SSL
        return f"postgresql://{role}:{password}@/{info.dbname}?host={info.host}&port={info.port}"
    host = info.host
    if pooled and host.endswith(".neon.tech") and "-pooler." not in host:
        endpoint, _, rest = host.partition(".")
        host = f"{endpoint}-pooler.{rest}"  # Neon's PgBouncer address for the same endpoint
    # verify-full checks the certificate and the host name. sslrootcert=system (libpq 16+) uses the
    # normal list of trusted certificates. Node's pg reads sslrootcert as a file, so the website URL
    # leaves it out: Node checks against its own trusted list.
    params = "sslmode=verify-full&sslrootcert=system&channel_binding=require" if role == "pipeline" \
        else "sslmode=verify-full"
    return f"postgresql://{role}:{password}@{host}/{info.dbname}?{params}"


def _write_env(path, values, only_if_missing=()):
    """Set KEY=value lines in an env file. Keys in only_if_missing keep an existing value."""
    lines = path.read_text().splitlines() if path.exists() else []
    existing = {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}
    out = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
        if key in values and key not in only_if_missing:
            out.append(f"{key}={values[key]}")
        else:
            out.append(line)
    new = [k for k in values if k not in existing]
    if new:
        out += ["", "# Written by `python -m pipeline set-db-passwords`. Copy these to GitHub / Vercel."]
        out += [f"{k}={values[k]}" for k in new]
    path.write_text("\n".join(out) + "\n")


def set_db_passwords(env_file):
    """Give the pipeline and website roles new random passwords and turn on login.

    Run it as the owner, after `migrate`. The passwords go only to env_file (git ignores .env).
    Neon accepts only plain-text passwords in ALTER ROLE, so the password goes over this
    (SSL) connection and Postgres stores only its SCRAM hash. Running it again makes new
    passwords, so the old addresses stop working.
    """
    import secrets

    values = {}
    with connect(autocommit=True) as conn:
        for role in APP_ROLES:
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                raise SystemExit(f"role {role!r} does not exist: run `python -m pipeline migrate` first")
            password = secrets.token_urlsafe(32)
            conn.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)))
            values[URL_KEYS[role]] = _role_url(conn.info, role, password, pooled=(role == "website"))
            log.info("role %s: login on, new password set", role)
    values.update({k: secrets.token_urlsafe(32) for k in SECRET_KEYS})
    _write_env(env_file, values, only_if_missing=SECRET_KEYS)
    log.info("wrote %s to %s", ", ".join(values), env_file)
