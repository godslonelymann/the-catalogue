"""Parse the raw files of one run into Postgres.

The pages come from memory (just fetched) or, for a reparse, are read back from storage.

Both parsers work on one store and one database transaction:
  * stage the JSON as rows in temporary tables with COPY,
  * upsert the main tables (keyed by Shopify IDs, so our short IDs never change),
  * replace child lists (tags, options, images, links) of the products we saw,
  * never delete: things that are gone get is_active = false.
Fields we do not know yet go to extra_attributes, so nothing in the API is lost.
"""
import json
import logging
from dataclasses import dataclass, field

from .storage import get_json

log = logging.getLogger(__name__)

PRODUCT_KEYS = {"id", "title", "handle", "body_html", "published_at", "created_at", "updated_at",
                "vendor", "product_type", "tags", "variants", "images", "options"}
OPTION_KEYS = {"name", "position", "values"}
IMAGE_KEYS = {"id", "created_at", "position", "updated_at", "product_id", "variant_ids", "src",
              "width", "height", "alt"}
VARIANT_KEYS = {"id", "title", "option1", "option2", "option3", "sku", "requires_shipping", "taxable",
                "featured_image", "available", "price", "grams", "compare_at_price", "position",
                "product_id", "created_at", "updated_at"}
COLLECTION_KEYS = {"id", "title", "handle", "description", "published_at", "updated_at", "image",
                   "products_count"}
COLLECTION_IMAGE_KEYS = {"id", "created_at", "src", "alt", "width", "height"}

REQUIRED_PRODUCT_KEYS = {"id", "title", "handle", "variants"}
REQUIRED_VARIANT_KEYS = {"id", "price", "available"}

# A products fetch with less than this share of the store's active products is
# treated as a broken response, so we do not mark the whole store as gone.
MIN_SHARE_OF_ACTIVE = 0.5


class ParseError(Exception):
    pass


@dataclass
class ProductsResult:
    products: int = 0
    variants: int = 0
    restocked: list = field(default_factory=list)  # our variant IDs: sold out -> in stock


@dataclass
class CollectionsResult:
    collections: int = 0
    links: int = 0
    skipped_links: int = 0  # membership rows for products we do not have yet


def blank(value):
    return None if value in ("", None) else value


def flatten(value, path):
    """Turn any JSON value into (path, text, type) rows: 'a.b', 'a[0]'."""
    if isinstance(value, dict):
        rows = []
        for k, v in value.items():
            rows += flatten(v, f"{path}.{k}")
        return rows or [(path, None, "null")]
    if isinstance(value, list):
        rows = []
        for i, v in enumerate(value):
            rows += flatten(v, f"{path}[{i}]")
        return rows or [(path, None, "null")]
    if value is None:
        return [(path, None, "null")]
    if isinstance(value, bool):
        return [(path, "true" if value else "false", "boolean")]
    if isinstance(value, (int, float)):
        return [(path, str(value), "number")]
    return [(path, str(value), "string")]


class Extras:
    """Collects unknown fields as extra_attributes rows, one per (kind, Shopify ID, path)."""

    def __init__(self):
        self.rows = {}
        self.new_fields = set()

    def add(self, kind, shopify_id, raw_file_id, obj, known, prefix=""):
        for key in obj.keys() - known:
            self.new_fields.add(f"{kind}.{prefix}{key}")
            for path, value, vtype in flatten(obj[key], f"{prefix}{key}"):
                self.rows[(kind, shopify_id, path)] = (kind, shopify_id, raw_file_id, path, value, vtype)


def load_raw(conn, storage, run_id, kind):
    rows = conn.execute(
        """SELECT id, s3_key, collection_handle FROM raw_files
           WHERE run_id = %s AND kind = %s ORDER BY collection_handle NULLS FIRST, page""",
        (run_id, kind)).fetchall()
    return [(fid, handle, json.loads(get_json(storage, key))) for fid, key, handle in rows]


def copy_rows(cur, table, columns, rows):
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)


def _stage_extras(cur, extras):
    cur.execute("""CREATE TEMP TABLE s_extra (kind text, sid bigint, raw_file_id text, path text,
                                               value text, vtype text) ON COMMIT DROP""")
    copy_rows(cur, "s_extra", ["kind", "sid", "raw_file_id", "path", "value", "vtype"], extras.rows.values())


def _upsert_extras(cur, kind, column, id_join, params):
    cur.execute(f"""
        INSERT INTO extra_attributes ({column}, field_path, value, value_type, raw_file_id,
                                      first_seen_at, last_seen_at)
        SELECT t.id, e.path, e.value, e.vtype, e.raw_file_id, %(at)s, %(at)s
        FROM s_extra e JOIN {id_join} t ON t.sid = e.sid
        WHERE e.kind = %(kind)s
        ON CONFLICT (product_id, variant_id, image_id, collection_id, field_path) DO UPDATE
        SET value = EXCLUDED.value, value_type = EXCLUDED.value_type,
            raw_file_id = EXCLUDED.raw_file_id, last_seen_at = EXCLUDED.last_seen_at""",
                {**params, "kind": kind})


# ---------------------------------------------------------------------------- products

def _product_rows(files):
    """Turn products pages into staging rows. Raises ParseError if the format changed."""
    r = {name: [] for name in ("products", "tags", "options", "optvals", "variants", "pimages", "vimages")}
    images, seen = {}, set()
    extras = Extras()

    for fid, _, data in files:
        for p in data["products"]:
            missing = REQUIRED_PRODUCT_KEYS - p.keys()
            if missing:
                raise ParseError(f"product {p.get('id')} has no {sorted(missing)}; the format may have changed")
            pid = p["id"]
            if pid in seen:  # the catalog can shift between pages while we fetch
                continue
            seen.add(pid)
            r["products"].append((pid, p["handle"], p["title"], blank(p.get("body_html")),
                                  blank(p.get("vendor")), blank(p.get("product_type")),
                                  p.get("published_at"), p.get("created_at"), p.get("updated_at")))
            tags = p.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            r["tags"] += [(pid, t) for t in dict.fromkeys(t for t in tags if t)]

            for i, o in enumerate(p.get("options") or []):
                pos = o.get("position", i + 1)
                r["options"].append((pid, pos, o["name"], o["name"].strip().lower()))
                r["optvals"] += [(pid, pos, j, v) for j, v in enumerate(o.get("values") or [], 1)]
                extras.add("product", pid, fid, o, OPTION_KEYS, prefix=f"options[{i}].")

            for img in p.get("images") or []:
                iid = img["id"]
                images.setdefault(iid, [iid, img["src"], img.get("width"), img.get("height"), blank(img.get("alt")),
                                        img.get("created_at"), img.get("updated_at")])
                r["pimages"].append((pid, iid, img.get("position", 1)))
                r["vimages"] += [(vid, iid) for vid in img.get("variant_ids") or []]
                extras.add("image", iid, fid, img, IMAGE_KEYS)

            for v in p["variants"]:
                missing = REQUIRED_VARIANT_KEYS - v.keys()
                if missing:
                    raise ParseError(f"variant {v.get('id')} has no {sorted(missing)}; the format may have changed")
                r["variants"].append((pid, v["id"], v.get("title") or "", v.get("option1"), v.get("option2"),
                                      v.get("option3"), blank(v.get("sku")), v.get("position", 1), v["price"],
                                      blank(v.get("compare_at_price")), v["available"], v.get("grams"),
                                      v.get("requires_shipping"), v.get("taxable"),
                                      v.get("created_at"), v.get("updated_at")))
                fi = v.get("featured_image")
                if fi:
                    r["vimages"].append((v["id"], fi["id"]))
                    r["vimages"] += [(vid, fi["id"]) for vid in fi.get("variant_ids") or []]
                    if fi["id"] in images and fi.get("alt") and not images[fi["id"]][4]:
                        images[fi["id"]][4] = fi["alt"]  # only featured_image carries alt text
                extras.add("variant", v["id"], fid, v, VARIANT_KEYS)

            extras.add("product", pid, fid, p, PRODUCT_KEYS)

    r["images"] = list(images.values())
    r["pimages"] = list(dict.fromkeys(r["pimages"]))
    r["vimages"] = list(dict.fromkeys(r["vimages"]))
    return r, extras


def parse_products(conn, storage, store, run_id, at, files=None):
    """Load a 'products' run. Commits on success. Returns ProductsResult.

    files: the pages from fetch_products. None = read them from storage (reparse).
    """
    if files is None:
        files = load_raw(conn, storage, run_id, "products")
    rows, extras = _product_rows(files)
    if extras.new_fields:
        log.warning("%s: new fields stored in extra_attributes: %s", store["slug"], sorted(extras.new_fields))

    params = {"store": store["id"], "run": run_id, "at": at}
    with conn.cursor() as cur:
        active = cur.execute("SELECT count(*) FROM products WHERE store_id = %(store)s AND is_active",
                             params).fetchone()[0]
        if active >= 20 and len(rows["products"]) < MIN_SHARE_OF_ACTIVE * active:
            raise ParseError(f"only {len(rows['products'])} products fetched but {active} are active; "
                             "refusing to mark the rest as gone")

        cur.execute("""
            CREATE TEMP TABLE s_products (pid bigint, handle text, title text, body_html text, vendor text,
                product_type text, published_at timestamptz, created_at timestamptz, updated_at timestamptz)
                ON COMMIT DROP;
            CREATE TEMP TABLE s_tags (pid bigint, tag text) ON COMMIT DROP;
            CREATE TEMP TABLE s_options (pid bigint, position int, name text, name_normalized text) ON COMMIT DROP;
            CREATE TEMP TABLE s_optvals (pid bigint, option_position int, position int, value text) ON COMMIT DROP;
            CREATE TEMP TABLE s_variants (pid bigint, vid bigint, title text, option1 text, option2 text,
                option3 text, sku text, position int, price numeric, compare_at_price numeric,
                available boolean, grams int, requires_shipping boolean, taxable boolean,
                created_at timestamptz, updated_at timestamptz) ON COMMIT DROP;
            CREATE TEMP TABLE s_images (iid bigint, src text, width int, height int, alt text,
                created_at timestamptz, updated_at timestamptz) ON COMMIT DROP;
            CREATE TEMP TABLE s_pimages (pid bigint, iid bigint, position int) ON COMMIT DROP;
            CREATE TEMP TABLE s_vimages (vid bigint, iid bigint) ON COMMIT DROP;""")
        copy_rows(cur, "s_products", ["pid", "handle", "title", "body_html", "vendor", "product_type",
                                      "published_at", "created_at", "updated_at"], rows["products"])
        copy_rows(cur, "s_tags", ["pid", "tag"], rows["tags"])
        copy_rows(cur, "s_options", ["pid", "position", "name", "name_normalized"], rows["options"])
        copy_rows(cur, "s_optvals", ["pid", "option_position", "position", "value"], rows["optvals"])
        copy_rows(cur, "s_variants", ["pid", "vid", "title", "option1", "option2", "option3", "sku", "position",
                                      "price", "compare_at_price", "available", "grams", "requires_shipping",
                                      "taxable", "created_at", "updated_at"], rows["variants"])
        copy_rows(cur, "s_images", ["iid", "src", "width", "height", "alt", "created_at", "updated_at"],
                  rows["images"])
        copy_rows(cur, "s_pimages", ["pid", "iid", "position"], rows["pimages"])
        copy_rows(cur, "s_vimages", ["vid", "iid"], rows["vimages"])

        # Products: gone ones become inactive first, so a reused handle does not clash.
        cur.execute("""
            UPDATE products SET is_active = false
            WHERE store_id = %(store)s AND is_active AND shopify_product_id NOT IN (SELECT pid FROM s_products)""",
                    params)
        cur.execute("""
            INSERT INTO products (store_id, shopify_product_id, handle, title, body_html, vendor, product_type,
                                  published_at, shopify_created_at, shopify_updated_at,
                                  first_seen_at, last_seen_at, is_active)
            SELECT %(store)s, pid, handle, title, body_html, vendor, product_type,
                   published_at, created_at, updated_at, %(at)s, %(at)s, true
            FROM s_products
            ON CONFLICT (store_id, shopify_product_id) DO UPDATE
            SET handle = EXCLUDED.handle, title = EXCLUDED.title, body_html = EXCLUDED.body_html,
                vendor = EXCLUDED.vendor, product_type = EXCLUDED.product_type,
                published_at = EXCLUDED.published_at, shopify_created_at = EXCLUDED.shopify_created_at,
                shopify_updated_at = EXCLUDED.shopify_updated_at,
                last_seen_at = EXCLUDED.last_seen_at, is_active = true""", params)
        cur.execute("""
            CREATE TEMP TABLE m_product ON COMMIT DROP AS
            SELECT shopify_product_id AS pid, shopify_product_id AS sid, id FROM products
            WHERE store_id = %(store)s AND shopify_product_id IN (SELECT pid FROM s_products)""", params)

        # Child lists: replace them for the products in this run.
        cur.execute("""
            DELETE FROM product_tags WHERE product_id IN (SELECT id FROM m_product);
            INSERT INTO product_tags (product_id, tag)
                SELECT DISTINCT m.id, t.tag FROM s_tags t JOIN m_product m USING (pid);
            DELETE FROM product_options WHERE product_id IN (SELECT id FROM m_product);
            INSERT INTO product_options (product_id, position, name, name_normalized)
                SELECT m.id, o.position, o.name, o.name_normalized FROM s_options o JOIN m_product m USING (pid);
            INSERT INTO product_option_values (product_id, option_position, position, value)
                SELECT m.id, o.option_position, o.position, o.value FROM s_optvals o JOIN m_product m USING (pid);""")

        cur.execute("""
            INSERT INTO images (shopify_image_id, src, width, height, alt, shopify_created_at, shopify_updated_at,
                                first_seen_at, last_seen_at)
            SELECT iid, src, width, height, alt, created_at, updated_at, %(at)s, %(at)s FROM s_images
            ON CONFLICT (shopify_image_id) DO UPDATE
            SET src = EXCLUDED.src, width = EXCLUDED.width, height = EXCLUDED.height,
                alt = coalesce(EXCLUDED.alt, images.alt), shopify_updated_at = EXCLUDED.shopify_updated_at,
                last_seen_at = EXCLUDED.last_seen_at""", params)
        cur.execute("""
            DELETE FROM product_images WHERE product_id IN (SELECT id FROM m_product);
            INSERT INTO product_images (product_id, image_id, position)
                SELECT m.id, i.id, s.position FROM s_pimages s JOIN m_product m USING (pid)
                JOIN images i ON i.shopify_image_id = s.iid
            ON CONFLICT DO NOTHING;""")

        # Variants: same pattern as products.
        cur.execute("""
            UPDATE variants SET is_active = false
            WHERE is_active AND product_id IN (SELECT id FROM products WHERE store_id = %(store)s)
              AND (product_id, shopify_variant_id) NOT IN
                  (SELECT m.id, s.vid FROM s_variants s JOIN m_product m USING (pid))""", params)
        cur.execute("""
            INSERT INTO variants (product_id, shopify_variant_id, title, option1, option2, option3, sku, position,
                                  price, compare_at_price, available, grams, requires_shipping, taxable,
                                  shopify_created_at, shopify_updated_at, first_seen_at, last_seen_at, is_active)
            SELECT m.id, s.vid, s.title, s.option1, s.option2, s.option3, s.sku, s.position,
                   s.price, s.compare_at_price, s.available, s.grams, s.requires_shipping, s.taxable,
                   s.created_at, s.updated_at, %(at)s, %(at)s, true
            FROM s_variants s JOIN m_product m USING (pid)
            ON CONFLICT (product_id, shopify_variant_id) DO UPDATE
            SET title = EXCLUDED.title, option1 = EXCLUDED.option1, option2 = EXCLUDED.option2,
                option3 = EXCLUDED.option3, sku = EXCLUDED.sku, position = EXCLUDED.position,
                price = EXCLUDED.price, compare_at_price = EXCLUDED.compare_at_price,
                available = EXCLUDED.available, grams = EXCLUDED.grams,
                requires_shipping = EXCLUDED.requires_shipping, taxable = EXCLUDED.taxable,
                shopify_created_at = EXCLUDED.shopify_created_at, shopify_updated_at = EXCLUDED.shopify_updated_at,
                last_seen_at = EXCLUDED.last_seen_at, is_active = true""", params)
        cur.execute("""
            DELETE FROM variant_images
            WHERE variant_id IN (SELECT v.id FROM variants v JOIN m_product m ON m.id = v.product_id);
            INSERT INTO variant_images (variant_id, image_id)
                SELECT v.id, i.id FROM s_vimages s
                JOIN variants v ON v.shopify_variant_id = s.vid
                JOIN m_product m ON m.id = v.product_id
                JOIN images i ON i.shopify_image_id = s.iid
            ON CONFLICT DO NOTHING;""")

        # History: one row per variant when it is new or its price/stock changed.
        # Returns the variants that went from sold out to in stock (for alerts).
        restocked = [r[0] for r in cur.execute("""
            WITH current AS (
                SELECT v.id, v.price, v.compare_at_price, v.available,
                       last.variant_id IS NOT NULL AS had_history, last.available AS was_available,
                       (last.variant_id IS NULL
                        OR last.price IS DISTINCT FROM v.price
                        OR last.compare_at_price IS DISTINCT FROM v.compare_at_price
                        OR last.available IS DISTINCT FROM v.available) AS changed
                FROM variants v
                JOIN m_product m ON m.id = v.product_id
                LEFT JOIN LATERAL (
                    SELECT h.variant_id, h.price, h.compare_at_price, h.available
                    FROM variant_history h WHERE h.variant_id = v.id
                    ORDER BY h.observed_at DESC LIMIT 1) last ON true
                WHERE v.is_active
            ), inserted AS (
                INSERT INTO variant_history (variant_id, observed_at, run_id, price, compare_at_price, available)
                SELECT id, %(at)s, %(run)s, price, compare_at_price, available FROM current WHERE changed
                ON CONFLICT DO NOTHING
                RETURNING variant_id
            )
            SELECT id FROM current WHERE changed AND had_history AND NOT was_available AND available""",
                                                params).fetchall()]

        # Unknown fields.
        _stage_extras(cur, extras)
        _upsert_extras(cur, "product", "product_id", "m_product", params)
        _upsert_extras(cur, "variant", "variant_id",
                       "(SELECT v.shopify_variant_id AS sid, v.id FROM variants v "
                       " JOIN m_product m ON m.id = v.product_id)", params)
        _upsert_extras(cur, "image", "image_id",
                       "(SELECT shopify_image_id AS sid, id FROM images "
                       " WHERE shopify_image_id IN (SELECT iid FROM s_images))", params)

    conn.commit()
    return ProductsResult(len(rows["products"]), len(rows["variants"]), restocked)


# ---------------------------------------------------------------------------- collections

def parse_collections(conn, storage, store, run_id, at, files=None):
    """Load a 'collections' run: collections + which product is in which collection. Commits.

    files: the pages from fetch_collections. None = read them from storage (reparse).
    """
    if files is None:
        files = {kind: load_raw(conn, storage, run_id, kind) for kind in ("collections", "collection_products")}
    colls, extras = [], Extras()
    for fid, _, data in files["collections"]:
        for c in data["collections"]:
            img = c.get("image") or {}
            colls.append((c["id"], c["handle"], c["title"], blank(c.get("description")), c.get("published_at"),
                          c.get("updated_at"), c.get("products_count"), img.get("id"), img.get("src"),
                          blank(img.get("alt")), img.get("created_at")))
            extras.add("collection", c["id"], fid, c, COLLECTION_KEYS)
            if img:
                extras.add("collection", c["id"], fid, img, COLLECTION_IMAGE_KEYS, prefix="image.")
    links = {(handle, p["id"])
             for _, handle, data in files["collection_products"]
             for p in data["products"]}
    if extras.new_fields:
        log.warning("%s: new fields stored in extra_attributes: %s", store["slug"], sorted(extras.new_fields))

    params = {"store": store["id"], "at": at}
    with conn.cursor() as cur:
        active = cur.execute("SELECT count(*) FROM collections WHERE store_id = %(store)s AND is_active",
                             params).fetchone()[0]
        if active and not colls:
            raise ParseError(f"no collections fetched but {active} are active")

        cur.execute("""
            CREATE TEMP TABLE s_colls (cid bigint, handle text, title text, description text,
                published_at timestamptz, updated_at timestamptz, products_count int, image_id bigint,
                image_src text, image_alt text, image_created_at timestamptz) ON COMMIT DROP;
            CREATE TEMP TABLE s_links (handle text, pid bigint) ON COMMIT DROP;""")
        copy_rows(cur, "s_colls", ["cid", "handle", "title", "description", "published_at", "updated_at",
                                   "products_count", "image_id", "image_src", "image_alt", "image_created_at"],
                  colls)
        copy_rows(cur, "s_links", ["handle", "pid"], links)

        cur.execute("""
            UPDATE collections SET is_active = false
            WHERE store_id = %(store)s AND is_active
              AND shopify_collection_id NOT IN (SELECT cid FROM s_colls)""", params)
        cur.execute("""
            INSERT INTO collections (store_id, shopify_collection_id, handle, title, description_html,
                                     published_at, shopify_updated_at, products_count, image_shopify_id,
                                     image_src, image_alt, image_shopify_created_at,
                                     first_seen_at, last_seen_at, is_active)
            SELECT %(store)s, cid, handle, title, description, published_at, updated_at, products_count,
                   image_id, image_src, image_alt, image_created_at, %(at)s, %(at)s, true
            FROM s_colls
            ON CONFLICT (store_id, shopify_collection_id) DO UPDATE
            SET handle = EXCLUDED.handle, title = EXCLUDED.title, description_html = EXCLUDED.description_html,
                published_at = EXCLUDED.published_at, shopify_updated_at = EXCLUDED.shopify_updated_at,
                products_count = EXCLUDED.products_count, image_shopify_id = EXCLUDED.image_shopify_id,
                image_src = EXCLUDED.image_src, image_alt = EXCLUDED.image_alt,
                image_shopify_created_at = EXCLUDED.image_shopify_created_at,
                last_seen_at = EXCLUDED.last_seen_at, is_active = true""", params)

        cur.execute("""
            DELETE FROM product_collections
            WHERE collection_id IN (SELECT id FROM collections WHERE store_id = %(store)s)""", params)
        cur.execute("""
            INSERT INTO product_collections (product_id, collection_id)
            SELECT p.id, c.id FROM s_links l
            JOIN collections c ON c.store_id = %(store)s AND c.handle = l.handle AND c.is_active
            JOIN products p ON p.store_id = %(store)s AND p.shopify_product_id = l.pid
            ON CONFLICT DO NOTHING""", params)
        n_links = cur.rowcount

        _stage_extras(cur, extras)
        _upsert_extras(cur, "collection", "collection_id",
                       "(SELECT shopify_collection_id AS sid, id FROM collections "
                       " WHERE store_id = %(store)s)", params)
        cur.execute("SELECT apply_collection_visibility_rules()")

    conn.commit()
    return CollectionsResult(len(colls), n_links, len(links) - n_links)
