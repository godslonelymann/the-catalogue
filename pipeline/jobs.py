"""The jobs that cron runs. Each returns a process exit code (0 = all good)."""
import logging
import time

from . import fetch, parse
from .alerts import send_restock_alerts
from .config import CONFIG
from .db import connect
from .storage import open_storage

log = logging.getLogger(__name__)


def active_stores(conn, only=None):
    rows = conn.execute("""SELECT id, slug, name, base_url FROM stores
                           WHERE is_active AND (%s::text IS NULL OR slug = %s) ORDER BY slug""",
                        (only, only)).fetchall()
    if only and not rows:
        raise SystemExit(f"no active store with slug {only!r}")
    return [dict(zip(["id", "slug", "name", "base_url"], r)) for r in rows]


def run_products(only=None):
    """Every 3 hours: fetch products, load them, record history, send restock alerts."""
    storage, failures, restocked = open_storage(), 0, []
    with connect() as conn:
        for store in active_stores(conn, only):
            run_id, started_at = fetch.start_run(conn, store["id"], "products")
            try:
                fetch.fetch_products(conn, storage, store, run_id, started_at)
                result = parse.parse_products(conn, storage, store, run_id, started_at)
                fetch.finish_run(conn, run_id, "success", products_count=result.products,
                                 variants_count=result.variants, restocked_count=len(result.restocked))
                restocked += result.restocked
                log.info("%-16s %s products=%d variants=%d restocked=%d", store["slug"], run_id,
                         result.products, result.variants, len(result.restocked))
            except Exception as e:
                conn.rollback()
                fetch.finish_run(conn, run_id, "failed", error=str(e)[:2000])
                log.exception("%s %s failed", store["slug"], run_id)
                failures += 1
            time.sleep(CONFIG.request_delay)
        send_restock_alerts(conn, restocked)
    return 1 if failures else 0


def run_collections(only=None):
    """Daily: fetch collections and which products are in them."""
    storage, failures = open_storage(), 0
    with connect() as conn:
        for store in active_stores(conn, only):
            run_id, started_at = fetch.start_run(conn, store["id"], "collections")
            try:
                fetch.fetch_collections(conn, storage, store, run_id, started_at)
                result = parse.parse_collections(conn, storage, store, run_id, started_at)
                fetch.finish_run(conn, run_id, "success", collections_count=result.collections,
                                 links_count=result.links)
                log.info("%-16s %s collections=%d links=%d skipped_links=%d", store["slug"], run_id,
                         result.collections, result.links, result.skipped_links)
            except Exception as e:
                conn.rollback()
                fetch.finish_run(conn, run_id, "failed", error=str(e)[:2000])
                log.exception("%s %s failed", store["slug"], run_id)
                failures += 1
    return 1 if failures else 0


def reparse(run_id):
    """Load an existing run again from storage (for example after a parser fix). Sends no alerts."""
    storage = open_storage()
    with connect() as conn:
        row = conn.execute("""SELECT r.kind, r.started_at, s.id, s.slug, s.name, s.base_url
                              FROM scrape_runs r JOIN stores s ON s.id = r.store_id WHERE r.id = %s""",
                           (run_id,)).fetchone()
        if not row:
            raise SystemExit(f"no run {run_id}")
        kind, started_at = row[0], row[1]
        store = dict(zip(["id", "slug", "name", "base_url"], row[2:]))
        if kind == "products":
            # restocked_count is kept: a reparse sees no new changes, so it would report 0.
            result = parse.parse_products(conn, storage, store, run_id, started_at)
            fetch.finish_run(conn, run_id, "success", products_count=result.products,
                             variants_count=result.variants)
        else:
            result = parse.parse_collections(conn, storage, store, run_id, started_at)
            fetch.finish_run(conn, run_id, "success", collections_count=result.collections,
                             links_count=result.links)
        log.info("reparsed %s: %s", run_id, result)
    return 0


def create_track_link(product_id, variant_id=None):
    """Create a pending tracker and return its Telegram link (the website will do this later)."""
    with connect() as conn:
        token = conn.execute("""INSERT INTO trackers (product_id, variant_id) VALUES (%s, %s)
                                RETURNING link_token""", (product_id, variant_id)).fetchone()[0]
        conn.commit()
    bot = CONFIG.telegram_username or "<your_bot_username>"
    return f"https://t.me/{bot}?start={token}"


def status():
    with connect() as conn:
        rows = conn.execute("""
            SELECT DISTINCT ON (s.slug, r.kind) s.slug, r.kind, r.id, r.status,
                   to_char(r.started_at AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD HH24:MI'),
                   coalesce(r.products_count, r.collections_count), coalesce(r.variants_count, r.links_count),
                   r.restocked_count, left(r.error_message, 80)
            FROM scrape_runs r JOIN stores s ON s.id = r.store_id
            ORDER BY s.slug, r.kind, r.started_at DESC""").fetchall()
    print(f"{'store':16} {'kind':11} {'run':9} {'status':8} {'started (IST)':16} {'count':>6} {'count2':>7} "
          f"{'restock':>7}  error")
    for r in rows:
        print(f"{r[0]:16} {r[1]:11} {r[2]:9} {r[3]:8} {r[4]:16} {r[5] or 0:6} {r[6] or 0:7} {r[7] or 0:7}  "
              f"{r[8] or ''}")
    return 0
