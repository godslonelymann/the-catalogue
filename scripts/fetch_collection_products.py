"""Fetch which products are in which collection (collection membership).

Usage: python3 -I scripts/fetch_collection_products.py data/raw/date=YYYY-MM-DD
Reads the collections_page_N.json files already in that folder, then saves
store=<slug>/collection_products/<handle>_page_N.json for every collection.
Collections with products_count = 0 are skipped.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works with python -I too
from fetch_sample import STORES, fetch_paged  # noqa: E402

day_dir = Path(sys.argv[1])
started = time.time()
requests = failures = 0

for slug, base in STORES.items():
    store_dir = day_dir / f"store={slug}"
    collections = [c for f in sorted(store_dir.glob("collections_page_*.json"))
                   for c in json.loads(f.read_bytes())["collections"]]
    out = store_dir / "collection_products"
    out.mkdir(exist_ok=True)
    links = skipped = 0
    for c in collections:
        if not c.get("products_count"):
            skipped += 1
            continue
        try:
            n = fetch_paged(base, f"collections/{c['handle']}/products", "products", out,
                            name=c["handle"], stop_on_short_page=True)
            links += n
            requests += len(list(out.glob(f"{c['handle']}_page_*.json")))
        except Exception as e:
            failures += 1
            print(f"  {slug}/{c['handle']}: FAILED {e}", file=sys.stderr)
        time.sleep(1)
    print(f"{slug:16} collections={len(collections):4} skipped_empty={skipped:3} "
          f"links={links:6}  ({time.time() - started:5.0f}s)", flush=True)

print(f"done: {requests} requests, {failures} failures, {time.time() - started:.0f}s")
