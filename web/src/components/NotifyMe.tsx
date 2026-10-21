"use client";

import { useState } from "react";

type Option = { id: string; label: string };

/**
 * "Notify me on Telegram" for sold-out sizes only.
 * `soldOut` lists the sold-out variants. "Any size" is offered only when every size is sold out.
 * Creates a pending tracker; the user then opens the bot link and taps Start.
 */
export function NotifyMe({ productId, soldOut, allSoldOut }: { productId: string; soldOut: Option[]; allSoldOut: boolean }) {
  const [variant, setVariant] = useState<string>(allSoldOut || soldOut.length !== 1 ? "" : soldOut[0].id);
  const [state, setState] = useState<{ status: "idle" | "loading" | "ready" | "error"; link?: string; message?: string }>(
    { status: "idle" },
  );
  if (soldOut.length === 0) return null;
  const needsChoice = !allSoldOut && soldOut.length > 1;

  async function create() {
    if (needsChoice && !variant) {
      setState({ status: "error", message: "Choose a size first." });
      return;
    }
    setState({ status: "loading" });
    try {
      const res = await fetch("/api/track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ productId, variantId: variant || null }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Something went wrong");
      setState(data.link ? { status: "ready", link: data.link } : { status: "error", message: data.message });
    } catch (e) {
      setState({ status: "error", message: e instanceof Error ? e.message : "Something went wrong" });
    }
  }

  return (
    <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
      <div>
        <p className="font-medium">
          🔔 {allSoldOut ? "Sold out? Get a Telegram message when it is back" : "Size sold out? Get a Telegram message when it is back"}
        </p>
        <p className="text-sm text-muted">We check every 3 hours. One message, then the alert stops.</p>
      </div>
      {state.status === "ready" ? (
        <a
          href={state.link}
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-11 items-center justify-center rounded-lg bg-[#229ED9] px-4 text-sm font-medium text-white hover:opacity-90"
        >
          Open Telegram and tap Start
        </a>
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row">
          {soldOut.length > 1 && (
            <select
              aria-label="Sold-out size to track"
              value={variant}
              onChange={(e) => setVariant(e.target.value)}
              className="h-11 flex-1 rounded-lg border border-border bg-background px-3 text-sm"
            >
              <option value="">{allSoldOut ? "Any size" : "Choose a size"}</option>
              {soldOut.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            onClick={create}
            disabled={state.status === "loading"}
            className="h-11 rounded-lg bg-foreground px-4 text-sm font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {state.status === "loading"
              ? "Creating link…"
              : soldOut.length === 1 && !allSoldOut
                ? `Notify me when ${soldOut[0].label} is back`
                : "Notify me on Telegram"}
          </button>
        </div>
      )}
      {state.status === "error" && <p className="text-sm text-sale">{state.message}</p>}
    </div>
  );
}
