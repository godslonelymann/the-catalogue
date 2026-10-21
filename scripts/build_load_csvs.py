"""Turn one day of raw Shopify JSON into CSV files that match the schema.

Usage: python3 -I scripts/build_load_csvs.py data/raw/date=YYYY-MM-DD OUT_DIR
Rows are keyed by Shopify IDs. db/tests/load_raw_sample.sql loads the CSVs and
maps the Shopify IDs to our own IDs. This is a prototype of the real parser.
"""
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

STORE_NAMES = {
    "fugazee": ("Fugazee", "https://www.fugazee.com"),
    "genrage": ("Genrage", "https://genrage.com"),
    "nattygarb": ("Natty Garb", "https://www.nattygarb.com"),
    "sullitt": ("Sullitt", "https://sullitt.com"),
    "warpingtheories": ("Warping Theories", "https://warpingtheories.com"),
    "arkar": ("Arkar", "https://arkar.in"),
    "noughtone": ("NoughtOne", "https://www.noughtone.in"),
    "farak": ("Farak", "https://www.farak.co"),
    "offscript": ("Offscript", "https://offscript.co.in"),
    "urbanmonkey": ("Urban Monkey", "https://www.urbanmonkey.com"),
}

raw_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
day = raw_dir.name.split("=", 1)[1]


def blank_to_none(s):
    return s if s not in ("", None) else None


rows = {name: [] for name in (
    "stores", "raw_files", "products", "product_tags", "product_options",
    "product_option_values", "variants", "images", "product_images",
    "variant_images", "collections", "product_collections")}
images = {}           # shopify_image_id -> row (images are shared between products)
variant_images = set()
issues = Counter()

for store_dir in sorted(raw_dir.glob("store=*")):
    slug = store_dir.name.split("=", 1)[1]
    name, base_url = STORE_NAMES[slug]
    rows["stores"].append([slug, name, base_url])

    for f in sorted(store_dir.glob("*.json")):
        body = f.read_bytes()
        kind, _, page = f.stem.rpartition("_page_")
        rows["raw_files"].append([slug, f"raw/{raw_dir.name}/{store_dir.name}/{f.name}",
                                  kind, None, int(page), 200, len(body), hashlib.sha256(body).hexdigest()])
        data = json.loads(body)

        for p in data.get("products", []):
            pid = p["id"]
            rows["products"].append([
                slug, pid, p["handle"], p["title"], blank_to_none(p["body_html"]),
                blank_to_none(p["vendor"]), blank_to_none(p["product_type"]),
                p["published_at"], p["created_at"], p["updated_at"]])
            tags = list(dict.fromkeys(p["tags"]))  # keep order, drop exact repeats
            issues["duplicate tag in one product"] += len(p["tags"]) - len(tags)
            rows["product_tags"] += [[pid, t] for t in tags]
            for o in p["options"]:
                rows["product_options"].append([pid, o["position"], o["name"], o["name"].strip().lower()])
                rows["product_option_values"] += [
                    [pid, o["position"], i, v] for i, v in enumerate(o["values"], 1)]
            for img in p["images"]:
                iid = img["id"]
                old = images.get(iid)
                if old and old[1] != img["src"]:
                    issues["same image id, different src"] += 1
                images.setdefault(iid, [iid, img["src"], img["width"], img["height"],
                                        img.get("alt"), img["created_at"], img["updated_at"]])
                rows["product_images"].append([pid, iid, img["position"]])
                variant_images.update((vid, iid) for vid in img["variant_ids"])
            for v in p["variants"]:
                rows["variants"].append([
                    pid, v["id"], v["title"], v["option1"], v["option2"], v["option3"],
                    blank_to_none(v["sku"]), v["position"], v["price"], v["compare_at_price"],
                    v["available"], v["grams"], v["requires_shipping"], v["taxable"],
                    v["created_at"], v["updated_at"]])
                fi = v.get("featured_image")
                if fi:
                    variant_images.add((v["id"], fi["id"]))
                    variant_images.update((vid, fi["id"]) for vid in fi.get("variant_ids", []))
                    if fi["id"] not in images:
                        issues["featured_image not in product images"] += 1
                    if fi.get("alt") and fi["id"] in images and not images[fi["id"]][4]:
                        images[fi["id"]][4] = fi["alt"]  # only featured_image carries alt

        for c in data.get("collections", []):
            img = c.get("image") or {}
            rows["collections"].append([
                slug, c["id"], c["handle"], c["title"], blank_to_none(c.get("description")),
                c["published_at"], c["updated_at"], c["products_count"],
                img.get("id"), img.get("src"), img.get("alt"), img.get("created_at")])

    # Collection membership: store=<slug>/collection_products/<handle>_page_N.json
    product_ids = {r[1] for r in rows["products"] if r[0] == slug}
    links = set()
    for f in sorted((store_dir / "collection_products").glob("*.json")):
        body = f.read_bytes()
        handle, _, page = f.stem.rpartition("_page_")
        rows["raw_files"].append([slug, f"raw/{raw_dir.name}/{store_dir.name}/collection_products/{f.name}",
                                  "collection_products", handle, int(page), 200, len(body),
                                  hashlib.sha256(body).hexdigest()])
        for p in json.loads(body)["products"]:
            if p["id"] in product_ids:
                links.add((slug, handle, p["id"]))
            else:
                issues["collection lists a product not in products.json"] += 1
    rows["product_collections"] += sorted(links)

rows["images"] = list(images.values())
rows["variant_images"] = sorted(variant_images)

for name, data in rows.items():
    # QUOTE_NOTNULL: None -> unquoted empty (NULL in COPY), "" -> "" (empty string).
    with open(out_dir / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, quoting=csv.QUOTE_NOTNULL).writerows(data)
    print(f"{name:22} {len(data):7} rows")
(out_dir / "day.txt").write_text(day)
for k, n in issues.items():
    print(f"note: {k}: {n}")
