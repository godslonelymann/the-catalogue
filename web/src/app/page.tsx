import { Suspense } from "react";
import { Catalog, CatalogSkeleton } from "@/components/Catalog";

export default function HomePage({ searchParams }: PageProps<"/">) {
  return (
    <>
      <h1 className="mb-5 text-2xl font-semibold tracking-tight">All brands</h1>
      <Suspense fallback={<CatalogSkeleton />}>
        <Catalog brand={null} searchParams={searchParams} />
      </Suspense>
    </>
  );
}
