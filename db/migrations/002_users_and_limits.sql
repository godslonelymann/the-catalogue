-- The Catalogue: database users and the "Notify me" request limit.
--
-- Two users, each with only the access it needs:
--   pipeline  GitHub Actions: loads products and collections, sends alerts.
--   website   Vercel: reads the catalog, creates trackers, runs the Telegram bot.
-- The owner (who runs migrations) is used only from the developer's Mac.
--
-- This file makes the roles WITHOUT login and without a password, so no secret is in git.
-- `python -m pipeline set-db-passwords` turns on login and sets the passwords.
-- A later migration that adds a table must also GRANT access on it to the user that needs it.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pipeline') THEN
        CREATE ROLE pipeline NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'website') THEN
        CREATE ROLE website NOLOGIN;
    END IF;
    -- CONNECT and TEMP (the parser stages rows in temporary tables).
    EXECUTE format('GRANT CONNECT, TEMP ON DATABASE %I TO pipeline, website', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO pipeline, website;

-- ---------------------------------------------------------------- pipeline
-- Read and write every table, but never delete a main row and never change the schema.
GRANT SELECT, INSERT, UPDATE ON
    stores, products, product_tags, product_options, product_option_values, variants,
    images, product_images, variant_images, collections, product_collections,
    scrape_runs, raw_files, variant_history, extra_attributes,
    subscribers, trackers, notifications, bot_state
TO pipeline;
-- The daily backup (pg_dump) runs as pipeline, so it must read every table.
GRANT SELECT ON schema_migrations TO pipeline;
-- The parser replaces these child lists for the products it sees (see pipeline/parse.py).
GRANT DELETE ON product_tags, product_options, product_images, variant_images, product_collections
TO pipeline;

-- ---------------------------------------------------------------- website
-- Read the catalog.
GRANT SELECT ON
    stores, products, product_tags, product_options, product_option_values, variants,
    images, product_images, variant_images, collections, product_collections,
    variant_history, extra_attributes, scrape_runs
TO website;
-- "Notify me" and the Telegram bot.
GRANT SELECT, INSERT, UPDATE ON trackers, subscribers TO website;

-- ---------------------------------------------------------------- request limit
-- sha256 of (visitor IP address + a secret salt). We never store the address itself.
ALTER TABLE trackers ADD COLUMN requester_hash char(64);
CREATE INDEX trackers_requester_idx ON trackers (requester_hash, created_at)
    WHERE requester_hash IS NOT NULL;

COMMIT;
