"""Profile the raw Shopify JSON so we can design the Postgres schema.

Usage: python3 -I scripts/analyze_sample.py data/raw/date=YYYY-MM-DD
For every object type (product, variant, image, option, collection, ...) it reports
each field's JSON types, null/empty rate, max length and examples.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

root = Path(sys.argv[1])


class Profile:
    def __init__(self):
        self.count = 0
        self.types = defaultdict(Counter)
        self.empty = Counter()
        self.maxlen = Counter()
        self.examples = defaultdict(list)
        self.distinct = defaultdict(set)

    def add(self, obj):
        self.count += 1
        for k, v in obj.items():
            t = type(v).__name__
            self.types[k][t] += 1
            if v is None or v == "" or v == []:
                self.empty[k] += 1
            if isinstance(v, (str, list)):
                self.maxlen[k] = max(self.maxlen[k], len(v))
            if isinstance(v, (str, int, float, bool)) and len(self.distinct[k]) < 50:
                self.distinct[k].add(v)
            if v not in (None, "", []) and len(self.examples[k]) < 2 and not isinstance(v, (dict, list)):
                s = str(v)
                self.examples[k].append(s[:60] + ("…" if len(s) > 60 else ""))

    def report(self, name):
        print(f"\n=== {name}  (n={self.count}) ===")
        print(f"{'field':24} {'types':22} {'empty%':>7} {'maxlen':>7} {'distinct':>8}  example")
        for k in self.types:
            types = ",".join(f"{t}" for t, _ in self.types[k].most_common())
            missing = self.count - sum(self.types[k].values())
            emp = 100 * (self.empty[k] + missing) / self.count
            d = len(self.distinct[k])
            d = f"{d}+" if d >= 50 else str(d)
            ex = " | ".join(self.examples[k])
            print(f"{k:24} {types:22} {emp:6.1f}% {self.maxlen[k] or '':>7} {d:>8}  {ex}")


P = defaultdict(Profile)
stats = defaultdict(Counter)
per_store = {}
product_ids, variant_ids, image_ids, collection_ids = Counter(), Counter(), Counter(), Counter()
sku_by_store = defaultdict(Counter)
vendor_by_store = defaultdict(Counter)
product_type_by_store = defaultdict(Counter)
option_names = Counter()
variants_per_product, images_per_product, tags_per_product = [], [], []
option_count = Counter()
handle_pairs = Counter()
tag_lengths = []
price_formats = Counter()
default_title = 0
variant_img_variant_ids = Counter()
image_variant_link_counts = []
fi_keys = Profile()

for store_dir in sorted(root.glob("store=*")):
    store = store_dir.name.split("=", 1)[1]
    n_p = n_v = n_avail = n_c = 0
    for f in sorted(store_dir.glob("products_page_*.json")):
        for p in json.loads(f.read_text())["products"]:
            n_p += 1
            P["product"].add(p)
            product_ids[p["id"]] += 1
            handle_pairs[(store, p["handle"])] += 1
            vendor_by_store[store][p.get("vendor")] += 1
            product_type_by_store[store][p.get("product_type")] += 1
            tags = p.get("tags")
            stats["tags_type"][type(tags).__name__] += 1
            tags_per_product.append(len(tags) if isinstance(tags, list) else -1)
            if isinstance(tags, list):
                tag_lengths += [len(t) for t in tags]
            variants_per_product.append(len(p["variants"]))
            images_per_product.append(len(p.get("images", [])))
            option_count[len(p.get("options", []))] += 1
            for o in p.get("options", []):
                P["option"].add(o)
                option_names[o["name"]] += 1
            for i in p.get("images", []):
                P["image"].add(i)
                image_ids[i["id"]] += 1
                image_variant_link_counts.append(len(i.get("variant_ids", [])))
            for v in p["variants"]:
                n_v += 1
                n_avail += bool(v.get("available"))
                P["variant"].add(v)
                variant_ids[v["id"]] += 1
                if v.get("sku"):
                    sku_by_store[store][v["sku"]] += 1
                if v.get("title") == "Default Title":
                    default_title += 1
                for k in ("price", "compare_at_price"):
                    val = v.get(k)
                    price_formats[(k, type(val).__name__)] += 1
                fi = v.get("featured_image")
                if isinstance(fi, dict):
                    fi_keys.add(fi)
    for f in sorted(store_dir.glob("collections_page_*.json")):
        for c in json.loads(f.read_text())["collections"]:
            n_c += 1
            P["collection"].add(c)
            collection_ids[c["id"]] += 1
            if isinstance(c.get("image"), dict):
                P["collection.image"].add(c["image"])
    per_store[store] = (n_p, n_v, n_avail, n_c)

print("=== per store ===")
print(f"{'store':16} {'products':>8} {'variants':>8} {'avail%':>7} {'collections':>11}  vendors / top product_types")
for s, (p, v, a, c) in per_store.items():
    vend = ", ".join(f"{k}({n})" for k, n in vendor_by_store[s].most_common(3))
    pt = ", ".join(f"{k or '∅'}({n})" for k, n in product_type_by_store[s].most_common(4))
    print(f"{s:16} {p:8} {v:8} {100*a/max(v,1):6.1f}% {c:11}  {vend}  /  {pt}")

for name, prof in P.items():
    prof.report(name)
fi_keys.report("variant.featured_image (nested object)")


def dist(xs):
    xs = sorted(xs)
    return f"min={xs[0]} median={xs[len(xs)//2]} p95={xs[int(len(xs)*.95)]} max={xs[-1]}"


print("\n=== shapes ===")
print("variants/product :", dist(variants_per_product))
print("images/product   :", dist(images_per_product))
print("tags/product     :", dist(tags_per_product), " tags type:", dict(stats["tags_type"]))
print("tag length       :", dist(tag_lengths) if tag_lengths else "-")
print("options/product  :", dict(sorted(option_count.items())))
print("top option names :", option_names.most_common(15))
print("variant_ids per image:", dist(image_variant_link_counts))
print("'Default Title' variants:", default_title)
print("price JSON types :", dict(price_formats))

print("\n=== uniqueness ===")
print("product ids dup across stores:", sum(1 for n in product_ids.values() if n > 1))
print("variant ids dup:", sum(1 for n in variant_ids.values() if n > 1))
print("image ids dup  :", sum(1 for n in image_ids.values() if n > 1))
print("collection ids dup:", sum(1 for n in collection_ids.values() if n > 1))
print("(store, handle) dup:", sum(1 for n in handle_pairs.values() if n > 1))
for s, c in sku_by_store.items():
    dups = sum(1 for n in c.values() if n > 1)
    print(f"sku dup within {s:16}: {dups}")
