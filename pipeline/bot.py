"""Telegram bot commands: /start <link_token>, /start, /list, /stop.

Cron runs `python -m pipeline bot` every minute. Each run long-polls Telegram
for up to 50 seconds, answers the messages and saves the update offset in
bot_state, so no message is handled twice.
"""
import html
import logging

from .alerts import product_url, variant_label
from .telegram import Telegram

log = logging.getLogger(__name__)
OFFSET_KEY = "telegram_update_offset"
PENDING_LINK_DAYS = 7

WELCOME = ("👋 Hi! I tell you when a product you track is <b>back in stock</b>.\n\n"
           "Open a product on The Catalogue and tap <b>Notify me on Telegram</b>.\n\n"
           "/list – what you track\n/stop – stop all alerts")


def _get_offset(conn):
    row = conn.execute("SELECT value FROM bot_state WHERE key = %s", (OFFSET_KEY,)).fetchone()
    return int(row[0]) if row else 0


def _save_offset(conn, offset):
    conn.execute("""INSERT INTO bot_state (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
                 (OFFSET_KEY, str(offset)))


def _subscriber(conn, chat):
    """Create or refresh the subscriber for a Telegram chat. A returning user is un-stopped."""
    return conn.execute("""
        INSERT INTO subscribers (telegram_chat_id, telegram_username, first_name) VALUES (%s, %s, %s)
        ON CONFLICT (telegram_chat_id) DO UPDATE
        SET telegram_username = EXCLUDED.telegram_username, first_name = EXCLUDED.first_name, stopped_at = NULL
        RETURNING id""", (chat["id"], chat.get("username"), chat.get("first_name"))).fetchone()[0]


def _describe(conn, product_id, variant_id):
    title, store, base_url, handle = conn.execute("""
        SELECT p.title, st.name, st.base_url, p.handle FROM products p JOIN stores st ON st.id = p.store_id
        WHERE p.id = %s""", (product_id,)).fetchone()
    size = ""
    if variant_id:
        vt = conn.execute("SELECT title FROM variants WHERE id = %s", (variant_id,)).fetchone()[0]
        size = f" · size {html.escape(vt)}" if variant_label(vt) else ""
    link = product_url(base_url, handle)
    return f'<a href="{html.escape(link, quote=True)}">{html.escape(title)}</a> ({html.escape(store)}){size}'


def handle_start(conn, chat, token):
    sub_id = _subscriber(conn, chat)
    if not token:
        return WELCOME
    t = conn.execute("""
        SELECT id, product_id, variant_id FROM trackers
        WHERE link_token = %s AND status = 'pending'
          AND created_at > now() - make_interval(days => %s)""", (token, PENDING_LINK_DAYS)).fetchone()
    if not t:
        return "⚠️ This link has expired or was already used. Open the product again and tap Notify me."
    tracker_id, product_id, variant_id = t
    what = _describe(conn, product_id, variant_id)
    already = conn.execute("""
        SELECT 1 FROM trackers WHERE subscriber_id = %s AND product_id = %s
          AND variant_id IS NOT DISTINCT FROM %s AND status = 'active'""",
                           (sub_id, product_id, variant_id)).fetchone()
    if already:
        conn.execute("UPDATE trackers SET status = 'cancelled', cancelled_at = now() WHERE id = %s", (tracker_id,))
        return f"👍 You already track {what}."
    conn.execute("""UPDATE trackers SET subscriber_id = %s, status = 'active', activated_at = now()
                    WHERE id = %s""", (sub_id, tracker_id))
    in_stock = conn.execute("""
        SELECT bool_or(available) FROM variants
        WHERE product_id = %s AND is_active AND (%s::text IS NULL OR id = %s)""",
                            (product_id, variant_id, variant_id)).fetchone()[0]
    note = "\n\nIt is <b>in stock right now</b>. I will still tell you if it sells out and comes back." \
        if in_stock else ""
    return f"✅ Tracking {what}.\nI will message you when it is back in stock.{note}"


def handle_list(conn, chat):
    rows = conn.execute("""
        SELECT t.product_id, t.variant_id FROM trackers t JOIN subscribers s ON s.id = t.subscriber_id
        WHERE s.telegram_chat_id = %s AND t.status = 'active' ORDER BY t.activated_at""", (chat["id"],)).fetchall()
    if not rows:
        return "You do not track anything yet."
    return "You track:\n" + "\n".join(f"• {_describe(conn, p, v)}" for p, v in rows)


def handle_stop(conn, chat):
    n = conn.execute("""
        WITH s AS (UPDATE subscribers SET stopped_at = now() WHERE telegram_chat_id = %s RETURNING id)
        UPDATE trackers SET status = 'cancelled', cancelled_at = now()
        WHERE subscriber_id IN (SELECT id FROM s) AND status IN ('pending', 'active')""", (chat["id"],)).rowcount
    return f"🛑 Stopped. I cancelled {n} alert(s). Send /start to begin again."


def handle_message(conn, message):
    chat = message.get("chat") or {}
    text = (message.get("text") or "").strip()
    if chat.get("type") != "private" or not text.startswith("/"):
        return WELCOME if chat.get("type") == "private" else None
    command, _, arg = text.partition(" ")
    command = command.split("@")[0].lower()  # "/start@MyBot" in some clients
    if command == "/start":
        return handle_start(conn, chat, arg.strip())
    if command == "/list":
        return handle_list(conn, chat)
    if command == "/stop":
        return handle_stop(conn, chat)
    return WELCOME


def poll(conn, telegram=None, timeout=50):
    """Handle new messages once. Returns the number of updates handled."""
    telegram = telegram or Telegram()
    if not telegram.enabled:
        return 0  # no token configured yet
    updates = telegram.get_updates(_get_offset(conn), timeout=timeout)
    for u in updates:
        message = u.get("message")
        reply = None
        if message:
            try:
                reply = handle_message(conn, message)
            except Exception:
                conn.rollback()
                log.exception("update %s failed", u["update_id"])
                reply = "Sorry, something went wrong. Please try again later."
        _save_offset(conn, u["update_id"] + 1)
        conn.commit()
        if reply:
            try:
                telegram.send_message(message["chat"]["id"], reply)
            except Exception as e:  # for example the user blocked the bot right after writing
                log.warning("reply to update %s failed: %s", u["update_id"], e)
    return len(updates)
