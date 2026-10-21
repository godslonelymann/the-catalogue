"""Command line: python -m pipeline <command>

  migrate                     apply db/migrations and db/seed
  products [--store SLUG]     fetch products -> S3 -> Postgres -> restock alerts   (every 3 hours)
  collections [--store SLUG]  fetch collections + membership                       (daily)
  bot                         answer Telegram messages for up to 50 seconds         (every minute)
  backup                      pg_dump -> S3 backups/                                (daily)
  reparse RUN-XXXXX           load a stored run again (no alerts)
  track-link PRD-XXXXX [VAR-XXXXX]   create a tracker link (for testing the bot)
  status                      latest run per store
"""
import argparse
import logging
import sys

from . import jobs
from .db import connect, migrate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    for name in ("products", "collections"):
        p = sub.add_parser(name)
        p.add_argument("--store", help="only this store slug")
    sub.add_parser("bot")
    sub.add_parser("backup")
    p = sub.add_parser("reparse")
    p.add_argument("run_id")
    p = sub.add_parser("track-link")
    p.add_argument("product_id")
    p.add_argument("variant_id", nargs="?")
    sub.add_parser("status")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "migrate":
        migrate()
        return 0
    if args.command == "products":
        return jobs.run_products(args.store)
    if args.command == "collections":
        return jobs.run_collections(args.store)
    if args.command == "bot":
        from .bot import poll
        with connect() as conn:
            poll(conn)
        return 0
    if args.command == "backup":
        from .backup import backup
        from .storage import open_storage
        backup(open_storage())
        return 0
    if args.command == "reparse":
        return jobs.reparse(args.run_id)
    if args.command == "track-link":
        print(jobs.create_track_link(args.product_id, args.variant_id))
        return 0
    if args.command == "status":
        return jobs.status()
    return 2


if __name__ == "__main__":
    sys.exit(main())
