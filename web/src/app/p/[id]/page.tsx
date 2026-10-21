import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import sanitizeHtml from "sanitize-html";
import { Gallery } from "@/components/Gallery";
import { NotifyMe } from "@/components/NotifyMe";
import { PriceHistory } from "@/components/PriceHistory";
import { discountPercent, formatDate, productUrl, rupees, variantLabel } from "@/lib/format";
import { getProduct, type Variant } from "@/lib/queries";

export async function generateMetadata({ params }: PageProps<"/p/[id]">) {
  const { id } = await params;
  const data = await getProduct(id);
  return { title: data ? `${data.product.title} – ${data.product.store_name}` : "Product" };
}

/** Store HTML: keep text, lists, tables and links; drop styles, scripts and layout junk. */
function cleanDescription(html: string | null): string {
  if (!html) return "";
  return sanitizeHtml(html, {
    allowedTags: ["p", "br", "strong", "b", "em", "i", "u", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5",
                  "table", "thead", "tbody", "tr", "th", "td", "a", "span", "div", "img", "blockquote"],
    allowedAttributes: { a: ["href"], img: ["src", "alt"], td: ["colspan", "rowspan"], th: ["colspan", "rowspan"] },
    allowedSchemes: ["https"],
    transformTags: { a: sanitizeHtml.simpleTransform("a", { target: "_blank", rel: "noopener noreferrer nofollow" }) },
    exclusiveFilter: (frame) => ["p", "span", "div"].includes(frame.tag) && !frame.text.trim() && !frame.mediaChildren.length,
  });
}

function SizeGrid({ variants, optionNames }: { variants: Variant[]; optionNames: string[] }) {
  const active = variants.filter((v) => v.is_active);
  if (active.length === 1 && active[0].title === "Default Title") {
    const v = active[0];
    return (
      <p className={`text-sm font-medium ${v.available ? "text-ok" : "text-muted"}`}>
        {v.available ? "● In stock" : "○ Sold out"}
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted">
        {optionNames.join(" / ") || "Options"} · {active.filter((v) => v.available).length} of {active.length} in stock
      </p>
      <ul className="flex flex-wrap gap-2">
        {active.map((v) => (
          <li
            key={v.id}
            title={`${v.sku ? `SKU ${v.sku} · ` : ""}${rupees(v.price)}${v.available ? "" : " · sold out"}`}
            className={`min-w-12 rounded-md border px-3 py-2 text-center text-sm ${
              v.available
                ? "border-foreground/40 bg-surface"
                : "border-border text-sold-out line-through decoration-1"
            }`}
          >
            {variantLabel(v.title)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

async function ProductContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await getProduct(id);
  if (!data) notFound();
  const { product: p, images, options, variants, tags, categories, extras, history } = data;

  const active = variants.filter((v) => v.is_active);
  const prices = active.map((v) => v.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const cheapest = active.find((v) => v.price === minPrice);
  const compareAt = cheapest?.is_on_sale ? cheapest.compare_at_price : null;
  const discount = cheapest ? discountPercent(cheapest.price, compareAt) : null;
  const inStock = active.some((v) => v.available);
  const storeLink = productUrl(p.base_url, p.handle);
  const description = cleanDescription(p.body_html);
  const grams = cheapest?.grams;

  return (
    <article className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-12">
      <Gallery images={images} title={p.title} />

      <div className="space-y-6">
        <div className="space-y-2">
          <Link href={`/b/${p.store_slug}`} className="text-xs uppercase tracking-wide text-muted hover:text-foreground">
            {p.store_name}
          </Link>
          <h1 className="text-2xl font-semibold leading-tight tracking-tight sm:text-3xl">{p.title}</h1>
          <p className="flex flex-wrap items-baseline gap-x-2 text-xl">
            <span className="font-semibold">
              {rupees(minPrice)}
              {maxPrice > minPrice && <span className="text-base font-normal text-muted"> – {rupees(maxPrice)}</span>}
            </span>
            {compareAt && <span className="text-base text-muted line-through">{rupees(compareAt)}</span>}
            {discount && <span className="rounded bg-sale px-1.5 py-0.5 text-xs font-medium text-white">-{discount}%</span>}
          </p>
          {!p.is_active && (
            <p className="rounded-md bg-accent-soft px-3 py-2 text-sm">
              This product is no longer listed on {p.store_name}. Last seen {formatDate(p.last_seen_at)}.
            </p>
          )}
        </div>

        <SizeGrid variants={variants} optionNames={options.map((o) => o.name)} />

        <a
          href={storeLink}
          target="_blank"
          rel="noopener noreferrer"
          className="flex h-12 items-center justify-center rounded-lg bg-foreground px-4 font-medium text-background hover:opacity-90"
        >
          {inStock ? `Buy on ${p.store_name}` : `View on ${p.store_name}`} ↗
        </a>

        {p.is_active && active.some((v) => !v.available) && (
          <NotifyMe
            productId={p.id}
            soldOut={active.filter((v) => !v.available).map((v) => ({ id: v.id, label: variantLabel(v.title) }))}
            allSoldOut={!inStock}
          />
        )}

        {description && (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Description</h2>
            <div className="description text-sm" dangerouslySetInnerHTML={{ __html: description }} />
          </section>
        )}

        <section className="space-y-1">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Details</h2>
          <dl className="divide-y divide-border">
            {p.product_type && <Detail label="Type">{p.product_type}</Detail>}
            {categories.length > 0 && (
              <Detail label="Categories">
                {categories.map((c, i) => (
                  <span key={c.id}>
                    {i > 0 && ", "}
                    <Link href={`/b/${p.store_slug}?category=${c.id}`} className="hover:underline">
                      {c.title}
                    </Link>
                  </span>
                ))}
              </Detail>
            )}
            {p.vendor && <Detail label="Vendor">{p.vendor}</Detail>}
            {grams ? <Detail label="Shipping weight">{grams} g</Detail> : null}
            {p.published_at && <Detail label="Listed by store">{formatDate(p.published_at)}</Detail>}
            <Detail label="First seen by us">{formatDate(p.first_seen_at)}</Detail>
            <Detail label="Last checked">{formatDate(p.last_seen_at)}</Detail>
          </dl>
        </section>

        {tags.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Tags</h2>
            <ul className="flex flex-wrap gap-1.5">
              {tags.map((t) => (
                <li key={t} className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted">
                  {t}
                </li>
              ))}
            </ul>
          </section>
        )}

        {extras.length > 0 && (
          <section className="space-y-1">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">More details</h2>
            <dl className="divide-y divide-border">
              {extras.map((e, i) => (
                <Detail key={i} label={`${e.field_path}${e.owner !== "product" ? ` (${variantLabel(e.owner)})` : ""}`}>
                  {e.value ?? "—"}
                </Detail>
              ))}
            </dl>
          </section>
        )}

        <PriceHistory history={history} variants={variants} until={p.last_seen_at} />
      </div>
    </article>
  );
}

function ProductSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-2 lg:gap-12" aria-busy="true">
      <div className="aspect-[4/5] animate-pulse rounded-xl bg-border" />
      <div className="space-y-4">
        <div className="h-3 w-24 animate-pulse rounded bg-border" />
        <div className="h-8 w-3/4 animate-pulse rounded bg-border" />
        <div className="h-6 w-32 animate-pulse rounded bg-border" />
        <div className="h-12 w-full animate-pulse rounded-lg bg-border" />
      </div>
    </div>
  );
}

export default function ProductPage({ params }: PageProps<"/p/[id]">) {
  return (
    <Suspense fallback={<ProductSkeleton />}>
      <ProductContent params={params} />
    </Suspense>
  );
}
