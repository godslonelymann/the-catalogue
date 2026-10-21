"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Store = { slug: string; name: string };

/** The tab row. `active` is the current path, or null while it is not known yet. */
export function TabList({ stores, active }: { stores: Store[]; active: string | null }) {
  const tabs = [{ slug: "", name: "All brands" }, ...stores];
  return (
    <nav className="mx-auto max-w-7xl px-4 sm:px-6" aria-label="Brands">
      <ul className="no-scrollbar -mb-px flex gap-1 overflow-x-auto">
        {tabs.map((t) => {
          const href = t.slug ? `/b/${t.slug}` : "/";
          const isActive = active !== null && (t.slug ? active.startsWith(href) : active === "/");
          return (
            <li key={t.slug || "all"} className="shrink-0">
              <Link
                href={href}
                aria-current={isActive ? "page" : undefined}
                className={`block border-b-2 px-3 py-3 text-sm whitespace-nowrap transition-colors ${
                  isActive
                    ? "border-foreground font-medium text-foreground"
                    : "border-transparent text-muted hover:text-foreground"
                }`}
              >
                {t.name}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Reads the URL, so the layout renders it inside <Suspense> with <TabList active={null}> as the fallback. */
export function BrandTabs({ stores }: { stores: Store[] }) {
  return <TabList stores={stores} active={usePathname()} />;
}
