"""HTTP access to the public Shopify JSON endpoints."""
import json
import logging
import subprocess
import time

from .config import CONFIG

log = logging.getLogger(__name__)
PAGE_SIZE = 250  # Shopify's maximum for products.json and collections.json


class FetchError(Exception):
    pass


def get(url, attempts=4):
    """GET a URL and return the body bytes.

    Uses curl because Python's urllib raised IncompleteRead on large chunked
    responses during testing. Retries rate limits (429/430), server errors and
    network errors with a growing pause.
    """
    for attempt in range(1, attempts + 1):
        r = subprocess.run(
            ["curl", "-sS", "--compressed", "--max-time", "120", "-A", CONFIG.user_agent,
             "-w", "\n%{http_code}", url],
            capture_output=True,
        )
        body, _, code = r.stdout.rpartition(b"\n")
        code = code.decode() or "000"
        if r.returncode == 0 and code == "200":
            return body
        retryable = code in ("429", "430") or code.startswith("5") or r.returncode != 0
        if retryable and attempt < attempts:
            pause = 10 * attempt
            log.warning("GET %s -> HTTP %s (curl exit %s), retry in %ss", url, code, r.returncode, pause)
            time.sleep(pause)
            continue
        raise FetchError(f"GET {url} failed: HTTP {code}, curl exit {r.returncode}, "
                         f"{r.stderr.decode(errors='replace').strip()[:200]}")


def pages(base_url, endpoint, key, stop_on_short_page=False):
    """Yield (page_number, raw_bytes, items) for every page of base_url/endpoint.json.

    The last page is the first empty one, or (with stop_on_short_page) the first
    page with fewer than PAGE_SIZE items, which saves one request per collection.
    """
    page = 1
    while True:
        raw = get(f"{base_url}/{endpoint}.json?limit={PAGE_SIZE}&page={page}")
        try:
            items = json.loads(raw)[key]
        except (ValueError, KeyError, TypeError) as e:
            raise FetchError(f"{base_url}/{endpoint}.json page {page}: not the expected JSON ({e})")
        yield page, raw, items
        if not items or (stop_on_short_page and len(items) < PAGE_SIZE):
            return
        page += 1
        time.sleep(CONFIG.request_delay)
