export function rupees(value: number | null | undefined): string {
  if (value == null) return "";
  return "₹" + Math.round(value).toLocaleString("en-IN");
}

export function discountPercent(price: number, compareAt: number | null): number | null {
  if (!compareAt || compareAt <= price) return null;
  return Math.round(((compareAt - price) / compareAt) * 100);
}

/** Ask the Shopify CDN for a smaller image. */
export function shopifyImage(src: string | null, width: number): string | null {
  if (!src) return null;
  return src + (src.includes("?") ? "&" : "?") + `width=${width}`;
}

export function productUrl(baseUrl: string, handle: string): string {
  return `${baseUrl}/products/${handle}`;
}

/** Variant titles like "Default Title" mean the product has no options. */
export function variantLabel(title: string): string {
  return title === "Default Title" ? "One size" : title;
}

const SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "XXXL", "3XL", "4XL", "5XL", "6XL"];

/** Sort sizes in a natural order: letter sizes first (XS..5XL), then numbers, then the rest. */
export function compareSizes(a: string, b: string): number {
  const ia = SIZE_ORDER.indexOf(a.toUpperCase());
  const ib = SIZE_ORDER.indexOf(b.toUpperCase());
  if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  const na = parseFloat(a);
  const nb = parseFloat(b);
  if (!isNaN(na) && !isNaN(nb)) return na - nb;
  if (!isNaN(na)) return -1;
  if (!isNaN(nb)) return 1;
  return a.localeCompare(b);
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
