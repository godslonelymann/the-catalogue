import { timingSafeEqual } from "node:crypto";
import { handleMessage, type TelegramMessage } from "@/lib/bot";

/**
 * Telegram webhook. Telegram sends every bot message here (set up once with setWebhook).
 *
 * 1. Check the secret header. Telegram sends the secret_token we gave to setWebhook.
 *    Any request without it is not from Telegram, so it gets 401.
 * 2. Answer the message. The reply goes back in the response body as a sendMessage call.
 * 3. After the secret check, always answer 200, also on an error.
 *    Telegram sends a message again and again until it gets 200.
 */

function secretOk(request: Request): boolean {
  const expected = process.env.TELEGRAM_WEBHOOK_SECRET ?? "";
  const got = request.headers.get("x-telegram-bot-api-secret-token") ?? "";
  if (!expected || got.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
}

export async function POST(request: Request) {
  if (!secretOk(request)) return new Response("Unauthorized", { status: 401 });

  let message: TelegramMessage | undefined;
  try {
    message = ((await request.json()) as { message?: TelegramMessage }).message;
  } catch {
    return new Response(null, { status: 200 }); // not JSON: nothing to answer
  }
  if (!message?.chat) return new Response(null, { status: 200 });

  let text: string | null;
  try {
    text = await handleMessage(message);
  } catch (e) {
    console.error("telegram webhook failed", e);
    text = "Sorry, something went wrong. Please try again later.";
  }
  if (!text) return new Response(null, { status: 200 });

  return Response.json({
    method: "sendMessage",
    chat_id: message.chat.id,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
  });
}
