"""Download raw JSON from one store into storage, and record each file in raw_files.

The fetch functions also return the pages they saved, as (raw_file_id, collection_handle, data),
so the parser can use them from memory. Each page is saved to storage before it is returned.
"""
import logging
import time
from zoneinfo import ZoneInfo

from . import shopify
from .config import CONFIG
from .storage import put_json

log = logging.getLogger(__name__)


def start_run(conn, store_id, kind):
    run_id, started_at = conn.execute(
        "INSERT INTO scrape_runs (store_id, kind) VALUES (%s, %s) RETURNING id, started_at",
        (store_id, kind)).fetchone()
    conn.commit()
    return run_id, started_at


def finish_run(conn, run_id, status, error=None, **counts):
    sets = ", ".join(f"{k} = %({k})s" for k in counts)
    conn.execute(
        f"UPDATE scrape_runs SET status = %(status)s, finished_at = now(), error_message = %(error)s"
        f"{', ' + sets if sets else ''} WHERE id = %(run_id)s",
        {"status": status, "error": error, "run_id": run_id, **counts})
    conn.commit()


def _prefix(store_slug, run_id, started_at):
    day = started_at.astimezone(ZoneInfo(CONFIG.timezone)).date()
    return f"raw/date={day}/store={store_slug}/run={run_id}"


def _save(conn, storage, run_id, key, raw, kind, page, collection_handle=None):
    """Store one raw page and record it. Returns the raw_files ID."""
    stored = put_json(storage, key, raw)
    raw_file_id = conn.execute(
        """INSERT INTO raw_files (run_id, s3_key, kind, collection_handle, page, http_status,
                                  bytes, stored_bytes, sha256)
           VALUES (%s, %s, %s, %s, %s, 200, %s, %s, %s) RETURNING id""",
        (run_id, stored.key, kind, collection_handle, page, stored.bytes, stored.stored_bytes,
         stored.sha256)).fetchone()[0]
    conn.commit()
    return raw_file_id


def fetch_products(conn, storage, store, run_id, started_at):
    """Save every products.json page. Returns the saved pages for parse_products."""
    prefix, files = _prefix(store["slug"], run_id, started_at), []
    for page, raw, items in shopify.pages(store["base_url"], "products", "products"):
        fid = _save(conn, storage, run_id, f"{prefix}/products_page_{page}", raw, "products", page)
        files.append((fid, None, {"products": items}))
    return files


def fetch_collections(conn, storage, store, run_id, started_at):
    """Save collections.json, then the product list of every non-empty collection.

    Returns the saved pages for parse_collections: {"collections": [...], "collection_products": [...]}.
    """
    prefix = _prefix(store["slug"], run_id, started_at)
    files = {"collections": [], "collection_products": []}
    collections = []
    for page, raw, items in shopify.pages(store["base_url"], "collections", "collections"):
        fid = _save(conn, storage, run_id, f"{prefix}/collections_page_{page}", raw, "collections", page)
        files["collections"].append((fid, None, {"collections": items}))
        collections += items
    time.sleep(CONFIG.request_delay)

    for c in collections:
        if not c.get("products_count"):
            continue  # nothing public to fetch
        handle = c["handle"]
        for page, raw, items in shopify.pages(store["base_url"], f"collections/{handle}/products", "products",
                                              stop_on_short_page=True):
            fid = _save(conn, storage, run_id, f"{prefix}/collection_products/{handle}_page_{page}", raw,
                        "collection_products", page, collection_handle=handle)
            files["collection_products"].append((fid, handle, {"products": items}))
        time.sleep(CONFIG.request_delay)
    return files
