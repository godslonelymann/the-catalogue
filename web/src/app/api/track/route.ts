import { createHash } from "node:crypto";
import { query } from "@/lib/db";

const LIMIT_PER_HOUR = 10;
const PRODUCT_ID = /^PRD-[0-9A-HJKMNP-TV-Z]{5}$/;
const VARIANT_ID = /^VAR-[0-9A-HJKMNP-TV-Z]{5}$/;

/**
 * A hash of the visitor's IP address, so we can count requests without keeping the address.
 * Vercel sets x-forwarded-for; the first address in it is the visitor.
 */
function requesterHash(request: Request): string {
  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() || request.headers.get("x-real-ip") || "unknown";
  return createHash("sha256")
    .update(`${process.env.RATE_LIMIT_SALT ?? ""}:${ip}`)
    .digest("hex");
}

/** Create a pending tracker and return the Telegram link that activates it. */
export async function POST(request: Request) {
  let body: { productId?: unknown; variantId?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Invalid request" }, { status: 400 });
  }
  const productId = typeof body.productId === "string" ? body.productId : "";
  const variantId = typeof body.variantId === "string" && body.variantId ? body.variantId : null;
  if (!PRODUCT_ID.test(productId) || (variantId && !VARIANT_ID.test(variantId))) {
    return Response.json({ error: "Invalid product" }, { status: 400 });
  }

  // Alerts are only for things that are sold out right now:
  //   a size  -> that variant must be sold out,
  //   no size -> every size of the product must be sold out.
  const [state] = await query<{ product_active: boolean; variant_ok: boolean | null; any_in_stock: boolean }>(
    `SELECT p.is_active AS product_active,
            (SELECT v.is_active AND NOT v.available FROM variants v WHERE v.id = $2 AND v.product_id = p.id)
                AS variant_ok,
            EXISTS (SELECT 1 FROM variants v WHERE v.product_id = p.id AND v.is_active AND v.available)
                AS any_in_stock
     FROM products p WHERE p.id = $1`,
    [productId, variantId],
  );
  if (!state?.product_active) return Response.json({ error: "Product not found" }, { status: 404 });
  if (variantId && !state.variant_ok) {
    return Response.json({ error: "This size is in stock right now, so there is nothing to wait for." }, { status: 409 });
  }
  if (!variantId && state.any_in_stock) {
    return Response.json({ error: "Some sizes are in stock right now. Choose a sold-out size." }, { status: 409 });
  }

  const bot = process.env.TELEGRAM_BOT_USERNAME?.replace(/^@/, "");
  if (!bot) {
    return Response.json({ link: null, message: "Telegram alerts are not set up yet. Please try again later." });
  }

  const requester = requesterHash(request);
  const [recent] = await query<{ n: number }>(
    `SELECT count(*)::int AS n FROM trackers
     WHERE requester_hash = $1 AND created_at > now() - interval '1 hour'`,
    [requester],
  );
  if (recent.n >= LIMIT_PER_HOUR) {
    return Response.json({ error: "Too many requests. Please try again in an hour." }, { status: 429 });
  }

  const [row] = await query<{ link_token: string }>(
    `INSERT INTO trackers (product_id, variant_id, requester_hash) VALUES ($1, $2, $3) RETURNING link_token`,
    [productId, variantId, requester],
  );
  return Response.json({ link: `https://t.me/${bot}?start=${row.link_token}` });
}
