import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { BrandTabs, TabList } from "@/components/BrandTabs";
import { getStores } from "@/lib/queries";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "The Catalogue", template: "%s · The Catalogue" },
  description: "Every product, size and stock status from 10 Indian streetwear brands, in one place.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const stores = await getStores();
  const tabs = stores.map(({ slug, name }) => ({ slug, name }));
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans">
        <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-baseline justify-between gap-4 px-4 pt-4 sm:px-6">
            <Link href="/" className="text-xl font-semibold tracking-tight">
              The Catalogue
            </Link>
            <p className="hidden text-sm text-muted sm:block">
              {stores.reduce((n, s) => n + s.products, 0).toLocaleString("en-IN")} products ·{" "}
              {stores.length} brands · updated every 3 hours
            </p>
          </div>
          <Suspense fallback={<TabList stores={tabs} active={null} />}>
            <BrandTabs stores={tabs} />
          </Suspense>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">{children}</main>
        <footer className="border-t border-border px-4 py-6 text-center text-xs text-muted sm:px-6">
          Not affiliated with any of these brands. Product data, names and images belong to each brand. Prices and
          stock can change; always check the store before buying.
        </footer>
      </body>
    </html>
  );
}
