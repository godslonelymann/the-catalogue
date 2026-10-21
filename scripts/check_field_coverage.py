"""Check that every field in the raw Shopify JSON has a place in the schema.

Usage: python3 -I scripts/check_field_coverage.py data/raw/date=YYYY-MM-DD
Walks every key path in every file and prints where each one is stored.
Any path without a mapping is printed as UNMAPPED.
"""
import json
import sys
from collections import Counter
from pathlib import Path

# JSON key path -> where it goes. "[]" marks a list element.
MAPPING = {
    # products_page_N.json
    "products[]":                          "products (one row per product)",
    "products[].id":                       "products.shopify_product_id",
    "products[].title":                    "products.title",
    "products[].handle":                   "products.handle",
    "products[].body_html":                "products.body_html",
    "products[].published_at":             "products.published_at",
    "products[].created_at":               "products.shopify_created_at",
    "products[].updated_at":               "products.shopify_updated_at",
    "products[].vendor":                   "products.vendor",
    "products[].product_type":             "products.product_type",
    "products[].tags":                     "product_tags",
    "products[].tags[]":                   "product_tags.tag",
    "products[].options":                  "product_options",
    "products[].options[]":                "product_options (one row per option)",
    "products[].options[].name":           "product_options.name (+ name_normalized)",
    "products[].options[].position":       "product_options.position",
    "products[].options[].values":         "product_option_values",
    "products[].options[].values[]":       "product_option_values.value (+ position)",
    "products[].images":                   "images + product_images",
    "products[].images[]":                 "images (one row per image)",
    "products[].images[].id":              "images.shopify_image_id",
    "products[].images[].created_at":      "images.shopify_created_at",
    "products[].images[].updated_at":      "images.shopify_updated_at",
    "products[].images[].position":        "product_images.position",
    "products[].images[].product_id":      "product_images.product_id (same as parent)",
    "products[].images[].variant_ids":     "variant_images",
    "products[].images[].variant_ids[]":   "variant_images.variant_id",
    "products[].images[].src":             "images.src",
    "products[].images[].width":           "images.width",
    "products[].images[].height":          "images.height",
    "products[].images[].alt":             "images.alt",
    "products[].variants":                 "variants",
    "products[].variants[]":               "variants (one row per variant)",
    "products[].variants[].id":            "variants.shopify_variant_id",
    "products[].variants[].product_id":    "variants.product_id (same as parent)",
    "products[].variants[].title":         "variants.title",
    "products[].variants[].option1":       "variants.option1",
    "products[].variants[].option2":       "variants.option2",
    "products[].variants[].option3":       "variants.option3",
    "products[].variants[].sku":           "variants.sku",
    "products[].variants[].position":      "variants.position",
    "products[].variants[].price":         "variants.price",
    "products[].variants[].compare_at_price": "variants.compare_at_price",
    "products[].variants[].available":     "variants.available",
    "products[].variants[].grams":         "variants.grams",
    "products[].variants[].requires_shipping": "variants.requires_shipping",
    "products[].variants[].taxable":       "variants.taxable",
    "products[].variants[].created_at":    "variants.shopify_created_at",
    "products[].variants[].updated_at":    "variants.shopify_updated_at",
    # featured_image is a copy of one of the product's images
    "products[].variants[].featured_image":            "variant_images (+ images)",
    "products[].variants[].featured_image.id":         "images.shopify_image_id",
    "products[].variants[].featured_image.product_id": "product_images.product_id (same as parent)",
    "products[].variants[].featured_image.position":   "product_images.position",
    "products[].variants[].featured_image.created_at": "images.shopify_created_at",
    "products[].variants[].featured_image.updated_at": "images.shopify_updated_at",
    "products[].variants[].featured_image.alt":        "images.alt",
    "products[].variants[].featured_image.width":      "images.width",
    "products[].variants[].featured_image.height":     "images.height",
    "products[].variants[].featured_image.src":        "images.src",
    "products[].variants[].featured_image.variant_ids":   "variant_images",
    "products[].variants[].featured_image.variant_ids[]": "variant_images.variant_id",
    # collections_page_N.json
    "collections[]":                       "collections (one row per collection)",
    "collections[].id":                    "collections.shopify_collection_id",
    "collections[].title":                 "collections.title",
    "collections[].handle":                "collections.handle",
    "collections[].description":           "collections.description_html",
    "collections[].published_at":          "collections.published_at",
    "collections[].updated_at":            "collections.shopify_updated_at",
    "collections[].products_count":        "collections.products_count",
    "collections[].image":                 "collections.image_* (flattened, 1:1)",
    "collections[].image.id":              "collections.image_shopify_id",
    "collections[].image.created_at":      "collections.image_shopify_created_at",
    "collections[].image.src":             "collections.image_src",
    "collections[].image.alt":             "collections.image_alt",
}
# Keys that hold the page list itself, not data.
CONTAINERS = {"products", "collections"}


def walk(value, path, seen):
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{path}.{k}" if path else k
            if p not in CONTAINERS:
                seen[p] += 1
            walk(v, p, seen)
    elif isinstance(value, list):
        for item in value:
            seen[f"{path}[]"] += 1
            walk(item, f"{path}[]", seen)


seen = Counter()
files = sorted(Path(sys.argv[1]).glob("store=*/*.json"))
for f in files:
    walk(json.loads(f.read_bytes()), "", seen)

unmapped = [p for p in seen if p not in MAPPING]
print(f"files: {len(files)}   distinct key paths: {len(seen)}   mapped: {len(seen) - len(unmapped)}")
for p in sorted(seen):
    print(f"{'UNMAPPED' if p in unmapped else 'ok':8} {seen[p]:7}  {p:50} -> {MAPPING.get(p, '-')}")
unused = sorted(set(MAPPING) - set(seen))
if unused:
    print("\nmapped but not seen in this data:", ", ".join(unused))
sys.exit(1 if unmapped else 0)
