import Link from "next/link";
import { Suspense } from "react";
import { FilterBar } from "@/components/FilterBar";
import { ProductCard } from "@/components/ProductCard";
import { compareSizes } from "@/lib/format";
import { getCategories, getProducts, getSizes, PAGE_SIZE, type Filters } from "@/lib/queries";

type SearchParams = Record<string, string | string[] | undefined>;

const SORTS = new Set<Filters["sort"]>(["featured", "newest", "price_asc", "price_desc", "discount"]);

function one(v: string | string[] | undefined): string | null {
  const s = Array.isArray(v) ? v[0] : v;
  return s && s.trim() ? s.trim() : null;
}

export function parseFilters(brand: string | null, sp: SearchParams): Filters {
  const sort = one(sp.sort) as Filters["sort"] | null;
  const page = Math.max(1, Math.min(500, parseInt(one(sp.page) ?? "1", 10) || 1));
  return {
    brand,
    category: one(sp.category)?.match(/^COL-[0-9A-HJKMNP-TV-Z]{5}$/) ? one(sp.category) : null,
    size: one(sp.size)?.toUpperCase().slice(0, 20) ?? null,
    q: one(sp.q)?.slice(0, 80) ?? null,
    inStock: one(sp.stock) === "in",
    onSale: one(sp.sale) === "1",
    sort: sort && SORTS.has(sort) ? sort : "featured",
    page,
  };
}

function pageHref(sp: SearchParams, page: number) {
  const next = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    const s = one(v);
    if (s && k !== "page") next.set(k, s);
  }
  if (page > 1) next.set("page", String(page));
  return next.size ? `?${next}` : "?";
}

/** Brand tab or "All brands": filters + product grid. Reads the URL, so it streams inside Suspense. */
export async function Catalog({ brand, searchParams }: { brand: string | null; searchParams: Promise<SearchParams> }) {
  const sp = await searchParams;
  const filters = parseFilters(brand, sp);
  const [products, categories, sizes] = await Promise.all([
    getProducts(filters),
    brand ? getCategories(brand) : Promise.resolve([]),
    getSizes(brand),
  ]);
  const total = products[0]?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-5">
      <Suspense>
        <FilterBar categories={categories} sizes={[...sizes].sort(compareSizes)} />
      </Suspense>
      <p className="text-sm text-muted">
        {total.toLocaleString("en-IN")} {total === 1 ? "product" : "products"}
        {pages > 1 && ` · page ${filters.page} of ${pages}`}
      </p>
      {products.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-16 text-center text-muted">
          No products match these filters.
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {products.map((p) => (
            <li key={p.id}>
              <ProductCard p={p} showBrand={!brand} />
            </li>
          ))}
        </ul>
      )}
      {pages > 1 && (
        <nav className="flex items-center justify-center gap-2 pt-4" aria-label="Pages">
          {filters.page > 1 && (
            <Link href={pageHref(sp, filters.page - 1)} className="rounded-md border border-border px-3 py-2 text-sm hover:border-foreground">
              ← Previous
            </Link>
          )}
          <span className="px-2 text-sm text-muted">
            {filters.page} / {pages}
          </span>
          {filters.page < pages && (
            <Link href={pageHref(sp, filters.page + 1)} className="rounded-md border border-border px-3 py-2 text-sm hover:border-foreground">
              Next →
            </Link>
          )}
        </nav>
      )}
    </div>
  );
}

export function CatalogSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true">
      <div className="h-9 w-full max-w-xl animate-pulse rounded-md bg-border" />
      <ul className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 10 }, (_, i) => (
          <li key={i} className="space-y-2">
            <div className="aspect-[4/5] animate-pulse rounded-lg bg-border" />
            <div className="h-3 w-3/4 animate-pulse rounded bg-border" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-border" />
          </li>
        ))}
      </ul>
    </div>
  );
}
