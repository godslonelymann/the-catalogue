import Link from "next/link";
import { rupees, shopifyImage } from "@/lib/format";
import type { ProductCard as Card } from "@/lib/queries";

export function ProductCard({ p, showBrand }: { p: Card; showBrand: boolean }) {
  const img = shopifyImage(p.image, 480);
  return (
    <Link href={`/p/${p.id}`} className="group block">
      <div className="relative aspect-[4/5] overflow-hidden rounded-lg border border-border bg-surface">
        {img ? (
          // eslint-disable-next-line @next/next/no-img-element -- Shopify's CDN already resizes images
          <img
            src={img}
            alt={p.title}
            loading="lazy"
            className={`h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03] ${
              p.in_stock ? "" : "opacity-50 grayscale"
            }`}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted">No image</div>
        )}
        <div className="absolute left-2 top-2 flex flex-col items-start gap-1">
          {!p.in_stock && (
            <span className="rounded bg-foreground px-1.5 py-0.5 text-[11px] font-medium text-background">
              Sold out
            </span>
          )}
          {p.in_stock && p.discount ? (
            <span className="rounded bg-sale px-1.5 py-0.5 text-[11px] font-medium text-white">-{p.discount}%</span>
          ) : null}
        </div>
      </div>
      <div className="mt-2 space-y-0.5">
        {showBrand && <p className="text-[11px] uppercase tracking-wide text-muted">{p.store_name}</p>}
        <h3 className="line-clamp-2 text-sm leading-snug group-hover:underline">{p.title}</h3>
        <p className="text-sm">
          <span className="font-medium">{rupees(p.price)}</span>
          {p.compare_at && p.compare_at > p.price ? (
            <span className="ml-1.5 text-muted line-through">{rupees(p.compare_at)}</span>
          ) : null}
        </p>
        {p.sizes_total > 1 && (
          <p className="text-xs text-muted">
            {p.sizes_in_stock} of {p.sizes_total} sizes in stock
          </p>
        )}
      </div>
    </Link>
  );
}
