-- Loads the sample data (3 real products from 2026-10-21) and checks that the
-- schema rejects bad data. Run on an EMPTY database after 001_schema.sql:
--   psql -v ON_ERROR_STOP=1 -f db/tests/001_schema_test.sql
-- Everything runs in one transaction and is rolled back at the end.

BEGIN;

-- expect_error(sql, label): passes only if sql raises an error.
CREATE FUNCTION pg_temp.expect_error(stmt text, label text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE stmt;
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'PASS  % -> %', label, SQLERRM;
        RETURN;
    END;
    RAISE EXCEPTION 'FAIL  % (no error raised)', label;
END $$;

-- ---------------------------------------------------------------- sample data
INSERT INTO stores (slug, name, base_url) VALUES
    ('sullitt',     'Sullitt',      'https://sullitt.com'),
    ('urbanmonkey', 'Urban Monkey', 'https://www.urbanmonkey.com');

INSERT INTO products (store_id, shopify_product_id, handle, title, vendor, product_type, published_at)
SELECT s.id, v.pid, v.handle, v.title, v.vendor, v.ptype, v.pub::timestamptz
FROM (VALUES
    ('sullitt',     7761744789563,  'grey-heritage-panther-tank',          'Blue Heritage Panther Waffle Tee',       'SULLITT',       '',              '2026-08-17T16:11:56+05:30'),
    ('urbanmonkey', 10209488470297, 'pack-of-2-puffer-bags-neon-on-black', 'Pack of 2 Puffer bags // Neon On Black', 'Urban Monkey®', 'Acc_bags',      '2025-12-03T16:25:07+05:30'),
    ('urbanmonkey', 9784308695321,  'custom-patch-cap-black',              'Custom Patch Cap // Black',              'Urban Monkey®', 'Snapback Caps', '2025-02-13T16:02:23+05:30')
) AS v(store, pid, handle, title, vendor, ptype, pub)
JOIN stores s ON s.slug = v.store;

INSERT INTO product_tags (product_id, tag)
SELECT p.id, t.tag FROM products p
JOIN (VALUES (7761744789563, 'Tee'), (7761744789563, 'virtual-tryon'),
             (10209488470297, 'accessories'), (10209488470297, 'Backpack'),
             (9784308695321, '100% Nylon')) AS t(pid, tag) ON t.pid = p.shopify_product_id;

INSERT INTO product_options (product_id, position, name, name_normalized)
SELECT p.id, 1, o.name, lower(trim(o.name)) FROM products p
JOIN (VALUES (7761744789563, 'Size'), (10209488470297, 'Title'), (9784308695321, 'Size'))
    AS o(pid, name) ON o.pid = p.shopify_product_id;

INSERT INTO product_option_values (product_id, option_position, position, value)
SELECT p.id, 1, ov.pos, ov.val FROM products p
JOIN (VALUES (7761744789563, 1, 's'), (7761744789563, 2, 'm'), (7761744789563, 3, 'l'),
             (7761744789563, 4, 'xl'), (7761744789563, 5, '2xl'),
             (10209488470297, 1, 'Default Title'),
             (9784308695321, 1, 'BLK_001'), (9784308695321, 2, 'BLK_002'))
    AS ov(pid, pos, val) ON ov.pid = p.shopify_product_id;

INSERT INTO variants (product_id, shopify_variant_id, title, option1, sku, position,
                      price, compare_at_price, available, grams, requires_shipping, taxable)
SELECT p.id, v.vid, v.t, v.t, v.sku, v.pos, v.price, v.cap, v.avail, v.grams, true, true
FROM products p
JOIN (VALUES
    (7761744789563,  43994252967995, 's',             'BLHP0401',         1, 2288.00, 3888.00, true,  850),
    (7761744789563,  43994253000763, 'm',             'BLHP0402',         2, 2288.00, 3888.00, true,  850),
    (7761744789563,  43994253033531, 'l',             'BLHP0403',         3, 2288.00, 3888.00, true,  850),
    (7761744789563,  43994253066299, 'xl',            'BLHP0404',         4, 2288.00, 3888.00, false, 850),
    (7761744789563,  43994253099067, '2xl',           'BLHP0405',         5, 2288.00, 3888.00, false, 850),
    (10209488470297, 51725580271897, 'Default Title', '25DFTB_PL05_PL06', 1, 3500.00, 4500.00, true,  950),
    (9784308695321,  50334056579353, 'BLK_001',       '24S194_BLK_001',   1, 999.00,  NULL,    false, 0),
    (9784308695321,  50334056612121, 'BLK_002',       '24S194_BLK_002',   2, 999.00,  NULL,    false, 0)
) AS v(pid, vid, t, sku, pos, price, cap, avail, grams) ON v.pid = p.shopify_product_id;

INSERT INTO images (shopify_image_id, src, width, height) VALUES
    (35714486534203, 'https://cdn.shopify.com/s/files/1/0624/7478/0731/files/BlueHeritagePanther1.png', 1080, 1440),
    (48692926185753, 'https://cdn.shopify.com/s/files/1/0661/7423/files/custom-patch-cap-black-blk-001.jpg', 759, 386);

INSERT INTO product_images (product_id, image_id, position)
SELECT p.id, i.id, 1 FROM products p, images i
WHERE (p.shopify_product_id, i.shopify_image_id) IN ((7761744789563, 35714486534203), (9784308695321, 48692926185753));

INSERT INTO variant_images (variant_id, image_id)
SELECT v.id, i.id FROM variants v, images i
WHERE v.shopify_variant_id = 50334056579353 AND i.shopify_image_id = 48692926185753;

INSERT INTO collections (store_id, shopify_collection_id, handle, title, products_count)
SELECT id, 314904870971, '2026-blu-collection', '2026 BLU COLLECTION', 21 FROM stores WHERE slug = 'sullitt';

INSERT INTO product_collections
SELECT p.id, c.id FROM products p, collections c WHERE p.shopify_product_id = 7761744789563;

INSERT INTO scrape_runs (store_id, status, products_count, variants_count, finished_at)
SELECT id, 'success', 116, 623, now() FROM stores WHERE slug = 'sullitt';

INSERT INTO raw_files (run_id, s3_key, kind, page, http_status, bytes, sha256)
SELECT id, 'raw/date=2026-10-21/store=sullitt/products_page_1.json', 'products', 1, 200, 652866, repeat('a', 64)
FROM scrape_runs;

-- xl: sold out on 21 Oct, back in stock on 23 Oct.
INSERT INTO variant_history (variant_id, observed_at, run_id, price, compare_at_price, available)
SELECT v.id, h.at::timestamptz, r.id, 2288.00, 3888.00, h.avail
FROM variants v, scrape_runs r,
     (VALUES ('2026-10-21 02:00+05:30', false), ('2026-10-23 05:00+05:30', true)) AS h(at, avail)
WHERE v.shopify_variant_id = 43994253066299;

INSERT INTO extra_attributes (product_id, field_path, value, value_type, raw_file_id)
SELECT p.id, 'material', 'cotton', 'string', r.id FROM products p, raw_files r
WHERE p.shopify_product_id = 7761744789563;
INSERT INTO extra_attributes (variant_id, field_path, value, value_type)
SELECT id, 'unit_price.amount', '2288.00', 'number' FROM variants WHERE shopify_variant_id = 43994252967995;

INSERT INTO subscribers (telegram_chat_id, telegram_username, first_name) VALUES (111222333, 'user1', 'User One');

INSERT INTO trackers (subscriber_id, product_id, variant_id, status)
SELECT s.id, v.product_id, v.id, 'active' FROM subscribers s, variants v
WHERE v.shopify_variant_id = 43994253066299;
INSERT INTO trackers (subscriber_id, product_id, variant_id, status)
SELECT s.id, p.id, NULL, 'active' FROM subscribers s, products p
WHERE p.shopify_product_id = 9784308695321;

INSERT INTO notifications (tracker_id, variant_id, status, telegram_message_id)
SELECT t.id, t.variant_id, 'sent', 42 FROM trackers t WHERE t.variant_id IS NOT NULL;
-- A pending tracker from the website: no subscriber yet.
INSERT INTO trackers (product_id) SELECT id FROM products WHERE shopify_product_id = 10209488470297;

-- ---------------------------------------------------------------- show it
\echo '--- products'
SELECT p.id, s.slug AS store, p.title FROM products p JOIN stores s ON s.id = p.store_id ORDER BY s.slug, p.title;
\echo '--- variants of the tee'
SELECT v.id, v.title, v.price, v.compare_at_price, v.is_on_sale, v.available
FROM variants v JOIN products p ON p.id = v.product_id
WHERE p.shopify_product_id = 7761744789563 ORDER BY v.position;
\echo '--- extra_attributes with their parent'
SELECT coalesce(product_id, variant_id, image_id, collection_id) AS parent, field_path, value, raw_file_id
FROM extra_attributes ORDER BY field_path;
\echo '--- trackers'
SELECT id, subscriber_id, product_id, variant_id, status FROM trackers ORDER BY variant_id NULLS LAST;

-- ---------------------------------------------------------------- rules must hold
SELECT pg_temp.expect_error(
    $$INSERT INTO products (id, store_id, shopify_product_id, handle, title)
      SELECT 'VAR-AAAAA', id, 1, 'x', 'x' FROM stores LIMIT 1$$,
    'product id must start with PRD-');
SELECT pg_temp.expect_error(
    $$INSERT INTO products (id, store_id, shopify_product_id, handle, title)
      SELECT 'PRD-OOOOO', id, 1, 'x', 'x' FROM stores LIMIT 1$$,
    'ID must not use O, I, L or U');
SELECT pg_temp.expect_error(
    $$INSERT INTO products (store_id, shopify_product_id, handle, title)
      SELECT store_id, shopify_product_id, 'other', 'dup' FROM products LIMIT 1$$,
    'same Shopify product twice in a store');
SELECT pg_temp.expect_error(
    $$INSERT INTO products (store_id, shopify_product_id, handle, title)
      SELECT store_id, 1, handle, 'dup' FROM products LIMIT 1$$,
    'two active products with the same handle');
SELECT pg_temp.expect_error(
    $$UPDATE variants SET price = -1 WHERE position = 1$$,
    'negative price');
SELECT pg_temp.expect_error(
    $$INSERT INTO extra_attributes (field_path, value, value_type) VALUES ('x', 'y', 'string')$$,
    'extra attribute with no parent');
SELECT pg_temp.expect_error(
    $$INSERT INTO extra_attributes (product_id, variant_id, field_path, value_type)
      SELECT p.id, v.id, 'x', 'null' FROM variants v JOIN products p ON p.id = v.product_id LIMIT 1$$,
    'extra attribute with two parents');
SELECT pg_temp.expect_error(
    $$INSERT INTO extra_attributes (product_id, field_path, value_type) VALUES ('PRD-ZZZZZ', 'x', 'null')$$,
    'extra attribute pointing to a product that does not exist');
SELECT pg_temp.expect_error(
    $$INSERT INTO trackers (subscriber_id, product_id, variant_id)
      SELECT s.id, p.id, v.id FROM subscribers s, products p, variants v
      WHERE p.shopify_product_id = 10209488470297 AND v.shopify_variant_id = 43994252967995$$,
    'tracker variant from a different product');
SELECT pg_temp.expect_error(
    $$INSERT INTO trackers (subscriber_id, product_id, variant_id, status)
      SELECT subscriber_id, product_id, variant_id, 'active' FROM trackers WHERE variant_id IS NULL AND status = 'active'$$,
    'second active "any size" tracker for the same product');
SELECT pg_temp.expect_error(
    $$INSERT INTO trackers (product_id, status) SELECT id, 'active' FROM products LIMIT 1$$,
    'active tracker must have a subscriber');
SELECT pg_temp.expect_error(
    $$INSERT INTO subscribers (telegram_chat_id) VALUES (111222333)$$,
    'same Telegram chat twice');
SELECT pg_temp.expect_error(
    $$INSERT INTO raw_files (run_id, s3_key, kind, page, http_status, bytes, sha256)
      SELECT id, 'k2', 'collection_products', 1, 200, 1, repeat('a', 64) FROM scrape_runs$$,
    'collection_products file without a collection handle');

-- show_on_site: rules hide noise, and a manual choice is never overwritten.
INSERT INTO collections (store_id, shopify_collection_id, handle, title)
SELECT id, v.cid, v.handle, v.title FROM stores, (VALUES
    (900001, 'frontpage', 'Home page'),
    (900002, '888', '888'),
    (900003, 'hoodie', 'Hoodie'),
    (900004, 'shop-all', 'Shop All')) AS v(cid, handle, title)
WHERE slug = 'sullitt';
INSERT INTO product_collections
SELECT p.id, c.id FROM products p, collections c
WHERE p.shopify_product_id = 7761744789563 AND c.shopify_collection_id IN (900001, 900002, 900003, 900004);
-- A person decides to show 'Shop All' anyway.
UPDATE collections SET show_on_site = true, show_on_site_set_by = 'manual' WHERE handle = 'shop-all';
SELECT apply_collection_visibility_rules();
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT handle, show_on_site, expected FROM collections
             JOIN (VALUES ('frontpage', false), ('888', false), ('hoodie', true), ('shop-all', true))
                  AS e(h, expected) ON e.h = handle
    LOOP
        IF r.show_on_site <> r.expected THEN
            RAISE EXCEPTION 'FAIL  show_on_site for %: got %, expected %', r.handle, r.show_on_site, r.expected;
        END IF;
    END LOOP;
    RAISE NOTICE 'PASS  rules hide frontpage and 888, show hoodie, keep manual shop-all';
END $$;
SELECT pg_temp.expect_error(
    $$UPDATE collections SET show_on_site_set_by = 'someone' WHERE handle = 'hoodie'$$,
    'show_on_site_set_by must be auto or manual');

-- Deleting a product removes its extra attributes (ON DELETE CASCADE).
DELETE FROM notifications; DELETE FROM trackers; DELETE FROM variants WHERE product_id IN
    (SELECT id FROM products WHERE shopify_product_id = 7761744789563);
DELETE FROM products WHERE shopify_product_id = 7761744789563;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM extra_attributes WHERE field_path = 'material') THEN
        RAISE EXCEPTION 'FAIL  cascade delete of extra_attributes';
    END IF;
    RAISE NOTICE 'PASS  extra_attributes rows deleted with their product';
END $$;

-- new_id() makes many unique IDs without error.
DO $$
DECLARE n int;
BEGIN
    INSERT INTO images (shopify_image_id, src) SELECT g, 'https://x/' || g FROM generate_series(1, 20000) g;
    SELECT count(DISTINCT id) INTO n FROM images;
    RAISE NOTICE 'PASS  % unique image IDs, e.g. %', n, (SELECT min(id) FROM images);
END $$;

ROLLBACK;
