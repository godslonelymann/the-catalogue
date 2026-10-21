-- Load the CSVs from scripts/build_load_csvs.py into an EMPTY database
-- that has db/migrations/001_schema.sql applied.
--   cd /path/to/csvs && psql -v ON_ERROR_STOP=1 -f /path/to/db/tests/load_raw_sample.sql
-- (\copy paths are relative to the folder psql runs in.)
-- Staging tables hold Shopify IDs. The INSERT ... SELECT steps map them to our IDs.

\set ON_ERROR_STOP 1
BEGIN;

CREATE TEMP TABLE s_stores   (slug text, name text, base_url text);
CREATE TEMP TABLE s_raw      (store text, s3_key text, kind text, collection_handle text, page int, http_status int, bytes int, sha256 text);
CREATE TEMP TABLE s_products (store text, pid bigint, handle text, title text, body_html text, vendor text,
                              product_type text, published_at timestamptz, created_at timestamptz, updated_at timestamptz);
CREATE TEMP TABLE s_tags     (pid bigint, tag text);
CREATE TEMP TABLE s_options  (pid bigint, position int, name text, name_normalized text);
CREATE TEMP TABLE s_optvals  (pid bigint, option_position int, position int, value text);
CREATE TEMP TABLE s_variants (pid bigint, vid bigint, title text, option1 text, option2 text, option3 text, sku text,
                              position int, price numeric, compare_at_price numeric, available boolean, grams int,
                              requires_shipping boolean, taxable boolean, created_at timestamptz, updated_at timestamptz);
CREATE TEMP TABLE s_images   (iid bigint, src text, width int, height int, alt text, created_at timestamptz, updated_at timestamptz);
CREATE TEMP TABLE s_pimages  (pid bigint, iid bigint, position int);
CREATE TEMP TABLE s_vimages  (vid bigint, iid bigint);
CREATE TEMP TABLE s_colls    (store text, cid bigint, handle text, title text, description text, published_at timestamptz,
                              updated_at timestamptz, products_count int, image_id bigint, image_src text,
                              image_alt text, image_created_at timestamptz);
CREATE TEMP TABLE s_pcolls   (store text, handle text, pid bigint);

\copy s_stores FROM 'stores.csv' (FORMAT csv)
\copy s_raw FROM 'raw_files.csv' (FORMAT csv)
\copy s_products FROM 'products.csv' (FORMAT csv)
\copy s_tags FROM 'product_tags.csv' (FORMAT csv)
\copy s_options FROM 'product_options.csv' (FORMAT csv)
\copy s_optvals FROM 'product_option_values.csv' (FORMAT csv)
\copy s_variants FROM 'variants.csv' (FORMAT csv)
\copy s_images FROM 'images.csv' (FORMAT csv)
\copy s_pimages FROM 'product_images.csv' (FORMAT csv)
\copy s_vimages FROM 'variant_images.csv' (FORMAT csv)
\copy s_colls FROM 'collections.csv' (FORMAT csv)
\copy s_pcolls FROM 'product_collections.csv' (FORMAT csv)

\set run_at '''2026-10-21 02:00:00+05:30'''

INSERT INTO stores (slug, name, base_url) SELECT slug, name, base_url FROM s_stores;

INSERT INTO scrape_runs (store_id, started_at, finished_at, status, products_count, variants_count)
SELECT st.id, :run_at, :run_at::timestamptz + interval '20 seconds', 'success',
       (SELECT count(*) FROM s_products p WHERE p.store = st.slug),
       (SELECT count(*) FROM s_variants v JOIN s_products p USING (pid) WHERE p.store = st.slug)
FROM stores st;

INSERT INTO raw_files (run_id, s3_key, kind, collection_handle, page, http_status, bytes, sha256, fetched_at)
SELECT r.id, s.s3_key, s.kind, s.collection_handle, s.page, s.http_status, s.bytes, s.sha256, :run_at
FROM s_raw s JOIN stores st ON st.slug = s.store JOIN scrape_runs r ON r.store_id = st.id;

INSERT INTO products (store_id, shopify_product_id, handle, title, body_html, vendor, product_type,
                      published_at, shopify_created_at, shopify_updated_at, first_seen_at, last_seen_at)
SELECT st.id, p.pid, p.handle, p.title, p.body_html, p.vendor, p.product_type,
       p.published_at, p.created_at, p.updated_at, :run_at, :run_at
FROM s_products p JOIN stores st ON st.slug = p.store;

CREATE TEMP TABLE m_product AS SELECT shopify_product_id AS pid, id FROM products;

INSERT INTO product_tags SELECT m.id, t.tag FROM s_tags t JOIN m_product m USING (pid);
INSERT INTO product_options SELECT m.id, o.position, o.name, o.name_normalized FROM s_options o JOIN m_product m USING (pid);
INSERT INTO product_option_values SELECT m.id, v.option_position, v.position, v.value FROM s_optvals v JOIN m_product m USING (pid);

INSERT INTO variants (product_id, shopify_variant_id, title, option1, option2, option3, sku, position,
                      price, compare_at_price, available, grams, requires_shipping, taxable,
                      shopify_created_at, shopify_updated_at, first_seen_at, last_seen_at)
SELECT m.id, v.vid, v.title, v.option1, v.option2, v.option3, v.sku, v.position,
       v.price, v.compare_at_price, v.available, v.grams, v.requires_shipping, v.taxable,
       v.created_at, v.updated_at, :run_at, :run_at
FROM s_variants v JOIN m_product m USING (pid);

INSERT INTO images (shopify_image_id, src, width, height, alt, shopify_created_at, shopify_updated_at,
                    first_seen_at, last_seen_at)
SELECT iid, src, width, height, alt, created_at, updated_at, :run_at, :run_at FROM s_images;

INSERT INTO product_images
SELECT m.id, i.id, s.position FROM s_pimages s JOIN m_product m USING (pid)
JOIN images i ON i.shopify_image_id = s.iid;

INSERT INTO variant_images
SELECT v.id, i.id FROM s_vimages s
JOIN variants v ON v.shopify_variant_id = s.vid JOIN images i ON i.shopify_image_id = s.iid;

INSERT INTO collections (store_id, shopify_collection_id, handle, title, description_html, published_at,
                         shopify_updated_at, products_count, image_shopify_id, image_src, image_alt,
                         image_shopify_created_at, first_seen_at, last_seen_at)
SELECT st.id, c.cid, c.handle, c.title, c.description, c.published_at, c.updated_at, c.products_count,
       c.image_id, c.image_src, c.image_alt, c.image_created_at, :run_at, :run_at
FROM s_colls c JOIN stores st ON st.slug = c.store;

INSERT INTO product_collections (product_id, collection_id)
SELECT m.id, c.id FROM s_pcolls s
JOIN stores st ON st.slug = s.store
JOIN collections c ON c.store_id = st.id AND c.handle = s.handle
JOIN m_product m ON m.pid = s.pid;

SELECT apply_collection_visibility_rules() AS collections_hidden_or_shown;

-- First run: one "first seen" history row for every variant.
INSERT INTO variant_history (variant_id, observed_at, run_id, price, compare_at_price, available)
SELECT v.id, :run_at, r.id, v.price, v.compare_at_price, v.available
FROM variants v JOIN products p ON p.id = v.product_id JOIN scrape_runs r ON r.store_id = p.store_id;

COMMIT;
