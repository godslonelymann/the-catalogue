-- The Catalogue: initial schema (PostgreSQL 18).
--
-- Rules:
--   * No JSONB. Every list in the Shopify JSON has its own table.
--   * Main tables use short prefixed IDs: PRD-7KQ2M, VAR-X4D9A, ...
--     (prefix + 5 characters from Crockford base32, which has no I, L, O or U).
--   * Shopify IDs are normal columns. The parser uses them to find existing rows.
--   * Rows are never deleted by the pipeline. Missing items get is_active = false.
--   * shopify_* timestamps come from the store. first_seen_at / last_seen_at are ours.

BEGIN;

-- ---------------------------------------------------------------------------
-- IDs
-- ---------------------------------------------------------------------------

-- Returns '<prefix>-XXXXX' that is not yet used in table tbl.
-- The PRIMARY KEY is the final guard if two inserts race for the same value.
CREATE FUNCTION new_id(prefix text, tbl text) RETURNS text
LANGUAGE plpgsql VOLATILE AS $$
DECLARE
    alphabet  constant text := '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
    candidate text;
    taken     boolean;
BEGIN
    LOOP
        candidate := prefix || '-';
        FOR i IN 1..5 LOOP
            candidate := candidate || substr(alphabet, 1 + floor(random() * 32)::int, 1);
        END LOOP;
        EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE id = $1)', tbl)
            INTO taken USING candidate;
        EXIT WHEN NOT taken;
    END LOOP;
    RETURN candidate;
END $$;

-- One domain per ID type, so a variant ID can never go into a product column.
CREATE DOMAIN id_store        AS varchar(9) CHECK (VALUE ~ '^STR-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_product      AS varchar(9) CHECK (VALUE ~ '^PRD-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_variant      AS varchar(9) CHECK (VALUE ~ '^VAR-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_image        AS varchar(9) CHECK (VALUE ~ '^IMG-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_collection   AS varchar(9) CHECK (VALUE ~ '^COL-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_run          AS varchar(9) CHECK (VALUE ~ '^RUN-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_raw_file     AS varchar(9) CHECK (VALUE ~ '^RAW-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_attribute    AS varchar(9) CHECK (VALUE ~ '^ATR-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_subscriber   AS varchar(9) CHECK (VALUE ~ '^SUB-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_tracker      AS varchar(9) CHECK (VALUE ~ '^TRK-[0-9A-HJKMNP-TV-Z]{5}$');
CREATE DOMAIN id_notification AS varchar(9) CHECK (VALUE ~ '^NTF-[0-9A-HJKMNP-TV-Z]{5}$');

CREATE DOMAIN money_inr AS numeric(12, 2) CHECK (VALUE >= 0);

-- ---------------------------------------------------------------------------
-- A. Catalog
-- ---------------------------------------------------------------------------

CREATE TABLE stores (
    id          id_store    PRIMARY KEY DEFAULT new_id('STR', 'stores'),
    slug        text        NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]+$'),
    name        text        NOT NULL,
    base_url    text        NOT NULL UNIQUE CHECK (base_url ~ '^https://'),
    platform    text        NOT NULL DEFAULT 'shopify',
    currency    char(3)     NOT NULL DEFAULT 'INR',
    is_active   boolean     NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id                  id_product  PRIMARY KEY DEFAULT new_id('PRD', 'products'),
    store_id            id_store    NOT NULL REFERENCES stores (id),
    shopify_product_id  bigint      NOT NULL,
    handle              text        NOT NULL,
    title               text        NOT NULL,
    body_html           text,
    vendor              text,
    product_type        text,
    published_at        timestamptz,
    shopify_created_at  timestamptz,
    shopify_updated_at  timestamptz,
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    is_active           boolean     NOT NULL DEFAULT true,
    UNIQUE (store_id, shopify_product_id)
);
-- A store can delete a product and reuse its handle, so only active rows must be unique.
CREATE UNIQUE INDEX products_active_handle_uq ON products (store_id, handle) WHERE is_active;

CREATE TABLE product_tags (
    product_id  id_product NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    tag         text       NOT NULL,
    PRIMARY KEY (product_id, tag)
);
CREATE INDEX product_tags_tag_idx ON product_tags (tag);

CREATE TABLE product_options (
    product_id       id_product NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    position         smallint   NOT NULL CHECK (position BETWEEN 1 AND 3),
    name             text       NOT NULL,
    name_normalized  text       NOT NULL,  -- lower(trim(name)): 'SIZE ' -> 'size'
    PRIMARY KEY (product_id, position)
);

CREATE TABLE product_option_values (
    product_id       id_product NOT NULL,
    option_position  smallint   NOT NULL,
    position         smallint   NOT NULL,
    value            text       NOT NULL,
    PRIMARY KEY (product_id, option_position, position),
    FOREIGN KEY (product_id, option_position)
        REFERENCES product_options (product_id, position) ON DELETE CASCADE
);

CREATE TABLE variants (
    id                  id_variant  PRIMARY KEY DEFAULT new_id('VAR', 'variants'),
    product_id          id_product  NOT NULL REFERENCES products (id),
    shopify_variant_id  bigint      NOT NULL,
    title               text        NOT NULL,
    option1             text,
    option2             text,
    option3             text,
    sku                 text,       -- not unique: empty or repeated in some stores
    position            smallint    NOT NULL,
    price               money_inr   NOT NULL,
    compare_at_price    money_inr,  -- stores also send 0 or the same value as price
    is_on_sale          boolean     GENERATED ALWAYS AS
                            (coalesce(compare_at_price > price, false)) STORED,
    available           boolean     NOT NULL,
    grams               integer     CHECK (grams >= 0),
    requires_shipping   boolean,
    taxable             boolean,
    shopify_created_at  timestamptz,
    shopify_updated_at  timestamptz,
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now(),
    is_active           boolean     NOT NULL DEFAULT true,
    UNIQUE (product_id, shopify_variant_id),
    UNIQUE (id, product_id)  -- target of the composite FK in trackers
);
CREATE INDEX variants_product_idx ON variants (product_id);

-- Shopify can use one image on more than one product, so images are shared rows.
CREATE TABLE images (
    id                  id_image    PRIMARY KEY DEFAULT new_id('IMG', 'images'),
    shopify_image_id    bigint      NOT NULL UNIQUE,
    src                 text        NOT NULL,
    width               integer,
    height              integer,
    alt                 text,
    shopify_created_at  timestamptz,
    shopify_updated_at  timestamptz,
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_seen_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE product_images (
    product_id  id_product NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    image_id    id_image   NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    position    smallint   NOT NULL,
    PRIMARY KEY (product_id, image_id)
);
CREATE INDEX product_images_image_idx ON product_images (image_id);

CREATE TABLE variant_images (
    variant_id  id_variant NOT NULL REFERENCES variants (id) ON DELETE CASCADE,
    image_id    id_image   NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    PRIMARY KEY (variant_id, image_id)
);
CREATE INDEX variant_images_image_idx ON variant_images (image_id);

CREATE TABLE collections (
    id                     id_collection PRIMARY KEY DEFAULT new_id('COL', 'collections'),
    store_id               id_store      NOT NULL REFERENCES stores (id),
    shopify_collection_id  bigint        NOT NULL,
    handle                 text          NOT NULL,
    title                  text          NOT NULL,
    description_html       text,
    published_at           timestamptz,
    shopify_updated_at     timestamptz,
    products_count         integer,
    image_shopify_id       bigint,       -- collection image is 1:1, so it is flattened
    image_src              text,
    image_alt              text,
    image_shopify_created_at timestamptz,
    -- Show this collection as a category on the website?
    -- 'auto' rows are set by apply_collection_visibility_rules() on every run.
    -- 'manual' rows were set by a person, and the pipeline never changes them.
    show_on_site           boolean       NOT NULL DEFAULT true,
    show_on_site_set_by    text          NOT NULL DEFAULT 'auto'
                               CHECK (show_on_site_set_by IN ('auto', 'manual')),
    first_seen_at          timestamptz   NOT NULL DEFAULT now(),
    last_seen_at           timestamptz   NOT NULL DEFAULT now(),
    is_active              boolean       NOT NULL DEFAULT true,
    UNIQUE (store_id, shopify_collection_id)
);

CREATE TABLE product_collections (
    product_id     id_product    NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    collection_id  id_collection NOT NULL REFERENCES collections (id) ON DELETE CASCADE,
    PRIMARY KEY (product_id, collection_id)
);
CREATE INDEX product_collections_collection_idx ON product_collections (collection_id);

-- Hides collections that are store-internal lists, not real categories.
-- The pipeline calls it after it loads collections and product_collections.
-- It changes only 'auto' rows and returns how many rows it changed.
CREATE FUNCTION apply_collection_visibility_rules() RETURNS integer
LANGUAGE sql AS $$
    WITH decided AS (
        SELECT c.id,
               NOT (
                   -- lists of every product or of the home page
                   c.handle IN ('frontpage', 'all', 'all-products', 'shop-all', 'home', 'homepage')
                   OR lower(c.title) IN ('home page', 'homepage', 'all', 'shop all', 'all products')
                   -- backups, tests and hidden lists
                   OR c.handle ~ '(backup|test|hidden|draft)'
                   -- names that are only numbers, such as '888'
                   OR c.handle ~ '^[0-9]+$'
                   -- no public products (products_count is not reliable, so count the links)
                   OR NOT EXISTS (SELECT 1 FROM product_collections pc WHERE pc.collection_id = c.id)
               ) AS show
        FROM collections c
        WHERE c.show_on_site_set_by = 'auto'
    ), changed AS (
        UPDATE collections c SET show_on_site = d.show
        FROM decided d
        WHERE c.id = d.id AND c.show_on_site IS DISTINCT FROM d.show
        RETURNING 1
    )
    SELECT count(*)::int FROM changed;
$$;

-- ---------------------------------------------------------------------------
-- C. Pipeline (before history, because history points to runs)
-- ---------------------------------------------------------------------------

CREATE TABLE scrape_runs (
    id                 id_run      PRIMARY KEY DEFAULT new_id('RUN', 'scrape_runs'),
    store_id           id_store    NOT NULL REFERENCES stores (id),
    -- 'products': products.json (every 3 hours)
    -- 'collections': collections.json + collection membership (daily)
    kind               text        NOT NULL DEFAULT 'products'
                           CHECK (kind IN ('products', 'collections')),
    started_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz,
    status             text        NOT NULL DEFAULT 'running'
                           CHECK (status IN ('running', 'success', 'failed')),
    products_count     integer,
    variants_count     integer,
    collections_count  integer,
    links_count        integer,    -- product_collections rows written
    restocked_count    integer,    -- variants that went from sold out to in stock
    error_message      text
);
CREATE INDEX scrape_runs_store_started_idx ON scrape_runs (store_id, started_at DESC);

CREATE TABLE raw_files (
    id                 id_raw_file PRIMARY KEY DEFAULT new_id('RAW', 'raw_files'),
    run_id             id_run      NOT NULL REFERENCES scrape_runs (id),
    s3_key             text        NOT NULL UNIQUE,
    kind               text        NOT NULL
                           CHECK (kind IN ('products', 'collections', 'collection_products')),
    collection_handle  text,       -- set only when kind = 'collection_products'
    page               integer     NOT NULL CHECK (page >= 1),
    http_status        integer     NOT NULL,
    bytes              integer     NOT NULL,  -- size of the JSON as received
    stored_bytes       integer,               -- size of the gzip file in storage
    sha256             char(64)    NOT NULL,  -- of the JSON as received (not the gzip)
    fetched_at         timestamptz NOT NULL DEFAULT now(),
    CHECK ((kind = 'collection_products') = (collection_handle IS NOT NULL))
);
CREATE INDEX raw_files_run_idx ON raw_files (run_id);

-- ---------------------------------------------------------------------------
-- B. History: a row only when price, sale price or stock changes
-- ---------------------------------------------------------------------------

CREATE TABLE variant_history (
    variant_id        id_variant  NOT NULL REFERENCES variants (id) ON DELETE CASCADE,
    observed_at       timestamptz NOT NULL,
    run_id            id_run      NOT NULL REFERENCES scrape_runs (id),
    price             money_inr   NOT NULL,
    compare_at_price  money_inr,
    available         boolean     NOT NULL,
    PRIMARY KEY (variant_id, observed_at)
);

-- ---------------------------------------------------------------------------
-- Fields the parser does not know yet (see the "promote" process)
-- ---------------------------------------------------------------------------

CREATE TABLE extra_attributes (
    id             id_attribute  PRIMARY KEY DEFAULT new_id('ATR', 'extra_attributes'),
    -- Exactly one parent is set. Each is a real FK.
    product_id     id_product    REFERENCES products (id)    ON DELETE CASCADE,
    variant_id     id_variant    REFERENCES variants (id)    ON DELETE CASCADE,
    image_id       id_image      REFERENCES images (id)      ON DELETE CASCADE,
    collection_id  id_collection REFERENCES collections (id) ON DELETE CASCADE,
    field_path     text          NOT NULL,  -- 'material', 'unit_price.amount', 'badges[0]'
    value          text,                    -- NULL when the JSON value is null
    value_type     text          NOT NULL
                       CHECK (value_type IN ('string', 'number', 'boolean', 'null')),
    raw_file_id    id_raw_file   REFERENCES raw_files (id),  -- last S3 file it came from
    first_seen_at  timestamptz   NOT NULL DEFAULT now(),
    last_seen_at   timestamptz   NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(product_id, variant_id, image_id, collection_id) = 1),
    UNIQUE NULLS NOT DISTINCT (product_id, variant_id, image_id, collection_id, field_path)
);
CREATE INDEX extra_attributes_product_idx    ON extra_attributes (product_id)    WHERE product_id IS NOT NULL;
CREATE INDEX extra_attributes_variant_idx    ON extra_attributes (variant_id)    WHERE variant_id IS NOT NULL;
CREATE INDEX extra_attributes_image_idx      ON extra_attributes (image_id)      WHERE image_id IS NOT NULL;
CREATE INDEX extra_attributes_collection_idx ON extra_attributes (collection_id) WHERE collection_id IS NOT NULL;
CREATE INDEX extra_attributes_field_idx      ON extra_attributes (field_path);

-- ---------------------------------------------------------------------------
-- D. Alerts
-- ---------------------------------------------------------------------------

-- Telegram users who talked to the bot.
CREATE TABLE subscribers (
    id                 id_subscriber PRIMARY KEY DEFAULT new_id('SUB', 'subscribers'),
    telegram_chat_id   bigint        NOT NULL UNIQUE,
    telegram_username  text,
    first_name         text,
    linked_at          timestamptz   NOT NULL DEFAULT now(),
    stopped_at         timestamptz,  -- set by /stop or when the user blocks the bot
    created_at         timestamptz   NOT NULL DEFAULT now()
);

-- A tracker starts as 'pending' with a random link_token (made by the website).
-- The user opens t.me/<bot>?start=<link_token> and taps Start; the bot then
-- sets subscriber_id and status = 'active'.
CREATE TABLE trackers (
    id             id_tracker    PRIMARY KEY DEFAULT new_id('TRK', 'trackers'),
    subscriber_id  id_subscriber REFERENCES subscribers (id) ON DELETE CASCADE,
    product_id     id_product    NOT NULL REFERENCES products (id),
    variant_id     id_variant,   -- NULL = any variant of the product
    link_token     text          NOT NULL UNIQUE DEFAULT replace(gen_random_uuid()::text, '-', ''),
    status         text          NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'active', 'notified', 'cancelled')),
    created_at     timestamptz   NOT NULL DEFAULT now(),
    activated_at   timestamptz,
    notified_at    timestamptz,
    cancelled_at   timestamptz,
    CHECK (status = 'pending' OR subscriber_id IS NOT NULL),
    -- The variant must belong to the same product.
    FOREIGN KEY (variant_id, product_id) REFERENCES variants (id, product_id)
);
-- One active tracker per subscriber + product + variant (NULL variant counts as one value).
CREATE UNIQUE INDEX trackers_active_uq ON trackers (subscriber_id, product_id, variant_id)
    NULLS NOT DISTINCT WHERE status = 'active';
CREATE INDEX trackers_active_product_idx ON trackers (product_id) WHERE status = 'active';

CREATE TABLE notifications (
    id                   id_notification PRIMARY KEY DEFAULT new_id('NTF', 'notifications'),
    tracker_id           id_tracker      NOT NULL REFERENCES trackers (id) ON DELETE CASCADE,
    variant_id           id_variant      NOT NULL REFERENCES variants (id),
    status               text            NOT NULL CHECK (status IN ('sent', 'failed')),
    telegram_message_id  bigint,
    error_message        text,
    sent_at              timestamptz     NOT NULL DEFAULT now()
);
CREATE INDEX notifications_tracker_idx ON notifications (tracker_id);

-- Small key/value settings the bot keeps between runs (for example the Telegram update offset).
CREATE TABLE bot_state (
    key         text        PRIMARY KEY,
    value       text        NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMIT;
