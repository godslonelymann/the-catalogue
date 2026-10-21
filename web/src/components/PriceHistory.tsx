import { formatDate, rupees, variantLabel } from "@/lib/format";
import type { HistoryRow, Variant } from "@/lib/queries";

type Point = { at: string; minPrice: number; inStock: number };
type Event = { at: string; text: string; kind: "in" | "out" | "price" };

/** Rebuild the product's state at each history time (history rows are only written on change). */
function timeline(history: HistoryRow[], variants: Variant[]) {
  const names = new Map(variants.map((v) => [v.id, variantLabel(v.title)]));
  const state = new Map<string, HistoryRow>();
  const points: Point[] = [];
  const events: Event[] = [];
  for (const row of history) {
    const prev = state.get(row.variant_id);
    const name = names.get(row.variant_id) ?? "";
    if (prev) {
      if (prev.available !== row.available) {
        events.push({ at: row.observed_at, kind: row.available ? "in" : "out",
                      text: `${name} ${row.available ? "back in stock" : "sold out"}` });
      }
      if (prev.price !== row.price) {
        events.push({ at: row.observed_at, kind: "price",
                      text: `${name} price ${rupees(prev.price)} → ${rupees(row.price)}` });
      }
    }
    state.set(row.variant_id, row);
    const all = [...state.values()];
    const point = { at: row.observed_at, minPrice: Math.min(...all.map((r) => r.price)),
                    inStock: all.filter((r) => r.available).length };
    if (points.at(-1)?.at === row.observed_at) points[points.length - 1] = point;
    else points.push(point);
  }
  return { points, events: events.reverse() };
}

function Chart({ points, until }: { points: Point[]; until: string }) {
  const w = 600, h = 120, pad = 6;
  const t0 = new Date(points[0].at).getTime();
  const t1 = Math.max(new Date(until).getTime(), new Date(points.at(-1)!.at).getTime());
  const prices = points.map((p) => p.minPrice);
  const lo = Math.min(...prices), hi = Math.max(...prices);
  const x = (at: string) => pad + ((new Date(at).getTime() - t0) / Math.max(1, t1 - t0)) * (w - 2 * pad);
  const y = (v: number) => (hi === lo ? h / 2 : pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad));
  // Step line: a price holds until the next change.
  let d = `M ${x(points[0].at)} ${y(points[0].minPrice)}`;
  for (const p of points.slice(1)) d += ` H ${x(p.at)} V ${y(p.minPrice)}`;
  d += ` H ${w - pad}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-28 w-full" role="img" aria-label="Lowest price over time">
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** `until` is when the product was last seen (the chart's right edge). */
export function PriceHistory({ history, variants, until }: { history: HistoryRow[]; variants: Variant[]; until: string }) {
  if (history.length === 0) return null;
  const { points, events } = timeline(history, variants);
  const prices = points.map((p) => p.minPrice);
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Price and stock history</h2>
      <p className="text-sm text-muted">
        Tracked since {formatDate(points[0].at)}.{" "}
        {events.length === 0
          ? "No price or stock changes yet."
          : `Lowest price seen ${rupees(Math.min(...prices))}, highest ${rupees(Math.max(...prices))}.`}
      </p>
      {points.length > 1 && <Chart points={points} until={until} />}
      {events.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border border-border text-sm">
          {events.slice(0, 12).map((e, i) => (
            <li key={i} className="flex justify-between gap-4 px-3 py-2">
              <span className={e.kind === "in" ? "text-ok" : e.kind === "out" ? "text-muted" : ""}>{e.text}</span>
              <span className="shrink-0 text-muted">{formatDate(e.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
