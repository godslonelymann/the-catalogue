import "server-only";
import { pool } from "@/lib/db";
import type { PoolClient } from "pg";

/**
 * Telegram bot commands: /start <link_token>, /start, /list, /stop.
 * Telegram sends each message to /api/telegram (a webhook). The reply goes back in the
 * HTTP response, so the bot makes no extra call to Telegram.
 */

const PENDING_LINK_DAYS = 7;

export const WELCOME =
  "👋 Hi! I tell you when a product you track is <b>back in stock</b>.\n\n" +
  "Open a product on The Catalogue and tap <b>Notify me on Telegram</b>.\n\n" +
  "/list – what you track\n/stop – stop all alerts";

export type TelegramChat = { id: number; type: string; username?: string; first_name?: string };
export type TelegramMessage = { chat?: TelegramChat; text?: string };

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function variantLabel(title: string): string {
  return title === "Default Title" ? "" : title;
}

/** Create or refresh the subscriber for a Telegram chat. A returning user is un-stopped. */
async function subscriber(db: PoolClient, chat: TelegramChat): Promise<string> {
  const { rows } = await db.query<{ id: string }>(
    `INSERT INTO subscribers (telegram_chat_id, telegram_username, first_name) VALUES ($1, $2, $3)
     ON CONFLICT (telegram_chat_id) DO UPDATE
     SET telegram_username = EXCLUDED.telegram_username, first_name = EXCLUDED.first_name, stopped_at = NULL
     RETURNING id`,
    [chat.id, chat.username ?? null, chat.first_name ?? null],
  );
  return rows[0].id;
}

async function describe(db: PoolClient, productId: string, variantId: string | null): Promise<string> {
  const { rows } = await db.query<{ title: string; store: string; base_url: string; handle: string; vt: string | null }>(
    `SELECT p.title, st.name AS store, st.base_url, p.handle,
            (SELECT v.title FROM variants v WHERE v.id = $2) AS vt
     FROM products p JOIN stores st ON st.id = p.store_id WHERE p.id = $1`,
    [productId, variantId],
  );
  const r = rows[0];
  const size = r.vt && variantLabel(r.vt) ? ` · size ${escapeHtml(r.vt)}` : "";
  const link = `${r.base_url}/products/${r.handle}`;
  return `<a href="${escapeHtml(link)}">${escapeHtml(r.title)}</a> (${escapeHtml(r.store)})${size}`;
}

async function handleStart(db: PoolClient, chat: TelegramChat, token: string): Promise<string> {
  const subId = await subscriber(db, chat);
  if (!token) return WELCOME;
  const { rows } = await db.query<{ id: string; product_id: string; variant_id: string | null }>(
    `SELECT id, product_id, variant_id FROM trackers
     WHERE link_token = $1 AND status = 'pending' AND created_at > now() - make_interval(days => $2)
     FOR UPDATE`,
    [token, PENDING_LINK_DAYS],
  );
  const t = rows[0];
  if (!t) return "⚠️ This link has expired or was already used. Open the product again and tap Notify me.";
  const what = await describe(db, t.product_id, t.variant_id);
  const already = await db.query(
    `SELECT 1 FROM trackers WHERE subscriber_id = $1 AND product_id = $2
       AND variant_id IS NOT DISTINCT FROM $3 AND status = 'active'`,
    [subId, t.product_id, t.variant_id],
  );
  if (already.rowCount) {
    await db.query(`UPDATE trackers SET status = 'cancelled', cancelled_at = now() WHERE id = $1`, [t.id]);
    return `👍 You already track ${what}.`;
  }
  await db.query(
    `UPDATE trackers SET subscriber_id = $1, status = 'active', activated_at = now() WHERE id = $2`,
    [subId, t.id],
  );
  const stock = await db.query<{ in_stock: boolean | null }>(
    `SELECT bool_or(available) AS in_stock FROM variants
     WHERE product_id = $1 AND is_active AND ($2::text IS NULL OR id = $2)`,
    [t.product_id, t.variant_id],
  );
  const note = stock.rows[0]?.in_stock
    ? "\n\nIt is <b>in stock right now</b>. I will still tell you if it sells out and comes back."
    : "";
  return `✅ Tracking ${what}.\nI will message you when it is back in stock.${note}`;
}

async function handleList(db: PoolClient, chat: TelegramChat): Promise<string> {
  const { rows } = await db.query<{ product_id: string; variant_id: string | null }>(
    `SELECT t.product_id, t.variant_id FROM trackers t JOIN subscribers s ON s.id = t.subscriber_id
     WHERE s.telegram_chat_id = $1 AND t.status = 'active' ORDER BY t.activated_at`,
    [chat.id],
  );
  if (!rows.length) return "You do not track anything yet.";
  const lines = [];
  for (const r of rows) lines.push(`• ${await describe(db, r.product_id, r.variant_id)}`);
  return "You track:\n" + lines.join("\n");
}

async function handleStop(db: PoolClient, chat: TelegramChat): Promise<string> {
  const res = await db.query(
    `WITH s AS (UPDATE subscribers SET stopped_at = now() WHERE telegram_chat_id = $1 RETURNING id)
     UPDATE trackers SET status = 'cancelled', cancelled_at = now()
     WHERE subscriber_id IN (SELECT id FROM s) AND status IN ('pending', 'active')`,
    [chat.id],
  );
  return `🛑 Stopped. I cancelled ${res.rowCount ?? 0} alert(s). Send /start to begin again.`;
}

/** The reply text for one message, or null for no reply (for example in a group chat). */
export async function handleMessage(message: TelegramMessage): Promise<string | null> {
  const chat = message.chat;
  if (!chat || chat.type !== "private") return null;
  const text = (message.text ?? "").trim();
  if (!text.startsWith("/")) return WELCOME;
  const [first, ...rest] = text.split(/\s+/);
  const command = first.split("@")[0].toLowerCase(); // "/start@MyBot" in some clients
  const arg = rest.join(" ").trim();
  if (!["/start", "/list", "/stop"].includes(command)) return WELCOME;

  // One transaction per message, like the Python bot.
  const db = await pool.connect();
  try {
    await db.query("BEGIN");
    const reply =
      command === "/start"
        ? await handleStart(db, chat, arg)
        : command === "/list"
          ? await handleList(db, chat)
          : await handleStop(db, chat);
    await db.query("COMMIT");
    return reply;
  } catch (e) {
    await db.query("ROLLBACK").catch(() => {});
    throw e;
  } finally {
    db.release();
  }
}
