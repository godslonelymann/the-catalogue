"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

type Props = {
  categories: { id: string; title: string; products: number }[];
  sizes: string[];
};

const SORTS = [
  ["featured", "Featured"],
  ["newest", "Newest"],
  ["price_asc", "Price: low to high"],
  ["price_desc", "Price: high to low"],
  ["discount", "Biggest discount"],
] as const;

/** Filters live in the URL, so every view can be shared and the server renders it. */
export function FilterBar({ categories, sizes }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();

  function set(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page"); // a new filter starts at page 1
    startTransition(() => router.push(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false }));
  }

  const select =
    "h-9 rounded-md border border-border bg-surface px-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent";
  const toggle = (on: boolean) =>
    `h-9 rounded-md border px-3 text-sm transition-colors ${
      on ? "border-foreground bg-foreground text-background" : "border-border bg-surface hover:border-foreground"
    }`;

  return (
    <div className={`flex flex-wrap items-center gap-2 transition-opacity ${pending ? "opacity-60" : ""}`}>
      <form
        className="w-full sm:w-auto"
        onSubmit={(e) => {
          e.preventDefault();
          const q = new FormData(e.currentTarget).get("q")?.toString().trim();
          set("q", q || null);
        }}
      >
        <input
          name="q"
          type="search"
          defaultValue={params.get("q") ?? ""}
          placeholder="Search products"
          className={`${select} w-full sm:w-56`}
          aria-label="Search products"
        />
      </form>
      {categories.length > 0 && (
        <select
          aria-label="Category"
          className={`${select} max-w-[12rem]`}
          value={params.get("category") ?? ""}
          onChange={(e) => set("category", e.target.value || null)}
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title} ({c.products})
            </option>
          ))}
        </select>
      )}
      {sizes.length > 0 && (
        <select
          aria-label="Size in stock"
          className={select}
          value={params.get("size") ?? ""}
          onChange={(e) => set("size", e.target.value || null)}
        >
          <option value="">Any size</option>
          {sizes.map((s) => (
            <option key={s} value={s}>
              Size {s}
            </option>
          ))}
        </select>
      )}
      <button
        type="button"
        className={toggle(params.get("stock") === "in")}
        onClick={() => set("stock", params.get("stock") === "in" ? null : "in")}
      >
        In stock
      </button>
      <button
        type="button"
        className={toggle(params.get("sale") === "1")}
        onClick={() => set("sale", params.get("sale") === "1" ? null : "1")}
      >
        On sale
      </button>
      <select
        aria-label="Sort"
        className={`${select} ml-auto`}
        value={params.get("sort") ?? "featured"}
        onChange={(e) => set("sort", e.target.value === "featured" ? null : e.target.value)}
      >
        {SORTS.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
}
