"""Fetch the full public catalog from each store and save the raw JSON locally.

Output: data/raw/date=<YYYY-MM-DD>/store=<slug>/{products_page_N,collections_page_N}.json
Uses only the standard library so it runs without installing anything.
"""
import json
import sys
import time
import subprocess
from datetime import date
from pathlib import Path

STORES = {
    "fugazee": "https://www.fugazee.com",
    "genrage": "https://genrage.com",
    "nattygarb": "https://www.nattygarb.com",
    "sullitt": "https://sullitt.com",
    "warpingtheories": "https://warpingtheories.com",
    "arkar": "https://arkar.in",
    "noughtone": "https://www.noughtone.in",
    "farak": "https://www.farak.co",
    "offscript": "https://offscript.co.in",
    "urbanmonkey": "https://www.urbanmonkey.com",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (the-catalogue research script)"}
OUT = Path(__file__).resolve().parent.parent / "data" / "raw" / f"date={date.today()}"


def get(url):
    # curl instead of urllib: urllib raised IncompleteRead on large chunked responses.
    for attempt in range(4):
        r = subprocess.run(
            ["curl", "-sS", "--compressed", "-A", HEADERS["User-Agent"],
             "-w", "\n%{http_code}", url],
            capture_output=True, timeout=120,
        )
        body, _, code = r.stdout.rpartition(b"\n")
        if r.returncode == 0 and code == b"200":
            return body
        if code in (b"429", b"430") and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"{url}: curl exit {r.returncode}, HTTP {code.decode()}")


def fetch_paged(base, endpoint, key, folder, name=None, stop_on_short_page=False):
    """Save every page of base/endpoint.json as folder/<name>_page_N.json.

    Shopify returns at most 250 items per page. With stop_on_short_page, a page
    with fewer than 250 items is the last one, so we skip the empty extra request.
    """
    name = name or endpoint
    page, total = 1, 0
    while True:
        body = get(f"{base}/{endpoint}.json?limit=250&page={page}")
        (folder / f"{name}_page_{page}.json").write_bytes(body)
        items = json.loads(body).get(key, [])
        total += len(items)
        if not items or (stop_on_short_page and len(items) < 250):
            return total
        page += 1
        time.sleep(1)


if __name__ == "__main__":
    for slug, base in STORES.items():
        folder = OUT / f"store={slug}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            n_products = fetch_paged(base, "products", "products", folder)
            n_collections = fetch_paged(base, "collections", "collections", folder)
            print(f"{slug:16} products={n_products:5} collections={n_collections:4}")
        except Exception as e:
            print(f"{slug:16} FAILED: {e}", file=sys.stderr)
