import { notFound } from "next/navigation";
import { Suspense } from "react";
import { Catalog, CatalogSkeleton } from "@/components/Catalog";
import { getStores } from "@/lib/queries";

export async function generateStaticParams() {
  const stores = await getStores();
  return stores.map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({ params }: PageProps<"/b/[slug]">) {
  const { slug } = await params;
  const store = (await getStores()).find((s) => s.slug === slug);
  return { title: store?.name ?? "Brand" };
}

async function BrandContent({ params, searchParams }: PageProps<"/b/[slug]">) {
  const { slug } = await params;
  const store = (await getStores()).find((s) => s.slug === slug);
  if (!store) notFound();
  return (
    <>
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{store.name}</h1>
        <a
          href={store.base_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-muted underline-offset-4 hover:text-foreground hover:underline"
        >
          Visit {store.base_url.replace(/^https:\/\/(www\.)?/, "")} ↗
        </a>
      </div>
      <Suspense fallback={<CatalogSkeleton />}>
        <Catalog brand={slug} searchParams={searchParams} />
      </Suspense>
    </>
  );
}

export default function BrandPage(props: PageProps<"/b/[slug]">) {
  return (
    <Suspense
      fallback={
        <>
          <div className="mb-5 h-8 w-40 animate-pulse rounded bg-border" />
          <CatalogSkeleton />
        </>
      }
    >
      <BrandContent {...props} />
    </Suspense>
  );
}
