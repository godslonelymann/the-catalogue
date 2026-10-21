# The Catalogue

Tracks the full catalogue of 10 Indian streetwear brands (all Shopify stores):
every product, size, price and stock status, with history and Telegram
"back in stock" alerts.

```
cron ─▶ fetch public Shopify JSON ─▶ gzip ─▶ S3 (raw, never changed)
                                              │
                                              ▼
                                   parse ─▶ PostgreSQL (18 tables, no JSONB)
                                              │
                                              ▼
                              price/stock history ─▶ Telegram alerts
```

## Jobs

| Command | Schedule | What it does |
|---|---|---|
| `python -m pipeline products` | every 3 hours | products.json → S3 → Postgres → history → restock alerts |
| `python -m pipeline collections` | daily | collections + which product is in which collection |
| `python -m pipeline bot` | every minute | Telegram `/start`, `/list`, `/stop` |
| `python -m pipeline backup` | daily | `pg_dump` → S3 `backups/` |
| `python -m pipeline migrate` | on deploy | applies `db/migrations`, seeds `db/seed` |
| `python -m pipeline status` | any time | latest run per store |
| `python -m pipeline reparse RUN-XXXXX` | when needed | loads a stored run again from S3 |

Cron calls them through `deploy/run.sh`, which adds a lock and a log file (`logs/<job>.log`).
The schedule is in `deploy/crontab`.

## Design notes

- **Raw first.** Every API response is stored unchanged (gzip, about 10× smaller) in S3, so any
  day can be parsed again after a parser fix.
- **No JSONB.** Every list in the JSON has its own table. Fields the parser does not know yet go
  to `extra_attributes` (with a real foreign key to their parent), so nothing is lost.
- **Short, readable IDs.** `PRD-7KQ2M`, `VAR-X4D9A`, ... Postgres domains stop a variant ID from
  going into a product column.
- **History only on change.** `variant_history` gets a row only when price or stock changes; a
  sold out → in stock change triggers the alerts.
- **Never delete.** Products and variants that disappear get `is_active = false`. A response
  with far fewer products than expected is refused instead of hiding the store.

## Layout

```
pipeline/        the Python package (config, fetch, parse, alerts, bot, backup, jobs)
db/migrations/   schema (001_schema.sql)
db/seed/         the 10 stores
db/tests/        schema rule tests and a full real-data load test
deploy/          run.sh (cron wrapper) and crontab
scripts/         research scripts used to design the schema
```

## Settings

Copy `.env.example` to `.env`. Main values: `CATALOGUE_DB`, `CATALOGUE_STORAGE`
(`s3://bucket` or a local folder for tests), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`.
