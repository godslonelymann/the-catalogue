"""Send "back in stock" Telegram messages for variants that were just restocked."""
import html
import logging
from collections import defaultdict

from .telegram import Telegram, TelegramError

log = logging.getLogger(__name__)


def product_url(base_url, handle):
    return f"{base_url}/products/{handle}"


def rupees(value):
    return f"₹{value:,.0f}"


def variant_label(title):
    return "" if title == "Default Title" else title


def _message(row, sizes):
    title, store, url = html.escape(row["title"]), html.escape(row["store"]), row["url"]
    lines = ["🎉 <b>Back in stock</b>", f"<b>{title}</b> · {store}"]
    labels = [html.escape(s) for s in sizes if variant_label(s)]
    if labels:
        lines.append(f"Size: {', '.join(labels)}")
    price = rupees(row["price"])
    if row["compare_at_price"] and row["compare_at_price"] > row["price"]:
        price += f" <s>{rupees(row['compare_at_price'])}</s>"
    lines += [price, f'<a href="{html.escape(url, quote=True)}">Buy on {store}</a>']
    return "\n".join(lines)


def send_restock_alerts(conn, restocked_variant_ids, telegram=None):
    """Message every active tracker that matches a restocked variant. Returns messages sent."""
    if not restocked_variant_ids:
        return 0
    telegram = telegram or Telegram()
    rows = conn.execute("""
        SELECT t.id AS tracker_id, s.id AS subscriber_id, s.telegram_chat_id AS chat_id,
               v.id AS variant_id, v.title AS variant_title, v.price, v.compare_at_price,
               p.title, st.name AS store, st.base_url, p.handle
        FROM trackers t
        JOIN subscribers s ON s.id = t.subscriber_id AND s.stopped_at IS NULL
        JOIN variants v ON v.product_id = t.product_id AND (t.variant_id IS NULL OR t.variant_id = v.id)
        JOIN products p ON p.id = t.product_id
        JOIN stores st ON st.id = p.store_id
        WHERE t.status = 'active' AND v.id = ANY(%s) AND v.available
        ORDER BY t.id, v.position""", (list(restocked_variant_ids),)).fetchall()
    cols = ["tracker_id", "subscriber_id", "chat_id", "variant_id", "variant_title", "price",
            "compare_at_price", "title", "store", "base_url", "handle"]

    # An "any size" tracker can match several restocked sizes: send one message.
    by_tracker = defaultdict(list)
    for r in rows:
        by_tracker[r[0]].append(dict(zip(cols, r)))

    sent = 0
    for tracker_id, matches in by_tracker.items():
        # Claim the tracker before we send. If this run stops after the send, the tracker is
        # already 'notified', so a later run cannot send the same message again.
        claimed = conn.execute("""UPDATE trackers SET status = 'notified', notified_at = now()
                                  WHERE id = %s AND status = 'active'""", (tracker_id,)).rowcount
        conn.commit()
        if not claimed:
            continue  # another run or a /stop got there first
        first = matches[0]
        first["url"] = product_url(first["base_url"], first["handle"])
        text = _message(first, [m["variant_title"] for m in matches])
        try:
            message_id = telegram.send_message(first["chat_id"], text)
        except TelegramError as e:
            log.warning("tracker %s: %s", tracker_id, e)
            conn.execute("""INSERT INTO notifications (tracker_id, variant_id, status, error_message)
                            VALUES (%s, %s, 'failed', %s)""", (tracker_id, first["variant_id"], str(e)))
            if e.user_blocked_bot:
                conn.execute("UPDATE subscribers SET stopped_at = now() WHERE id = %s", (first["subscriber_id"],))
                conn.execute("""UPDATE trackers SET status = 'cancelled', cancelled_at = now(), notified_at = NULL
                                WHERE subscriber_id = %s AND (status = 'active' OR id = %s)""",
                             (first["subscriber_id"], tracker_id))
            else:
                # Not sent: make the tracker active again, so the next restock can try again.
                conn.execute("""UPDATE trackers SET status = 'active', notified_at = NULL
                                WHERE id = %s AND status = 'notified'""", (tracker_id,))
            conn.commit()
            continue
        conn.execute("""INSERT INTO notifications (tracker_id, variant_id, status, telegram_message_id)
                        VALUES (%s, %s, 'sent', %s)""", (tracker_id, first["variant_id"], message_id))
        conn.commit()
        sent += 1
    log.info("restocked variants: %d, alerts sent: %d", len(restocked_variant_ids), sent)
    return sent
