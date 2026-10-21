import "server-only";
import { cacheLife } from "next/cache";
import { query } from "./db";

// The pipeline updates prices and stock every 3 hours, so a few minutes of caching is safe.

export type Store = { id: string; slug: string; name: string; base_url: string; products: number };

export async function getStores(): Promise<Store[]> {
  "use cache";
  cacheLife("minutes");
  return query<Store>(`
    SELECT s.id, s.slug, s.name, s.base_url, count(p.id)::int AS products
    FROM stores s LEFT JOIN products p ON p.store_id = s.id AND p.is_active
    WHERE s.is_active GROUP BY s.id ORDER BY s.name`);
}

export type Filters = {
  brand: string | null;
  category: string | null; // collection id
  size: string | null;
  q: string | null;
  inStock: boolean;
  onSale: boolean;
  sort: "featured" | "newest" | "price_asc" | "price_desc" | "discount";
  page: number;
};

export type ProductCard = {
  id: string;
  title: string;
  store_slug: string;
  store_name: string;
  price: number;
  compare_at: number | null;
  discount: number | null;
  in_stock: boolean;
  sizes_in_stock: number;
  sizes_total: number;
  image: string | null;
  total: number;
};

export const PAGE_SIZE = 48;

// The value of a variant's "Size" option, upper-cased ("s" and "S" are the same size).
const SIZE_OF_VARIANT = `upper(trim(CASE po.position WHEN 1 THEN v2.option1 WHEN 2 THEN v2.option2
                                                   ELSE v2.option3 END))`;

const ORDER_BY: Record<Filters["sort"], string> = {
  // In stock first, then take turns between brands (newest of each brand first).
  featured: "in_stock DESC, brand_rank, published_at DESC NULLS LAST, id",
  newest: "published_at DESC NULLS LAST, id",
  price_asc: "price ASC, id",
  price_desc: "price DESC, id",
  discount: "discount DESC NULLS LAST, in_stock DESC, id",
};

export async function getProducts(f: Filters): Promise<ProductCard[]> {
  "use cache";
  cacheLife("minutes");
  return query<ProductCard>(
    `
    WITH base AS (
      SELECT p.id, p.title, p.published_at, s.slug AS store_slug, s.name AS store_name,
             min(v.price) AS price,
             max(v.compare_at_price) FILTER (WHERE v.is_on_sale) AS compare_at,
             max(round(100 * (v.compare_at_price - v.price) / v.compare_at_price))
                 FILTER (WHERE v.is_on_sale)::int AS discount,
             bool_or(v.available) AS in_stock,
             bool_or(v.is_on_sale) AS on_sale,
             (count(*) FILTER (WHERE v.available))::int AS sizes_in_stock,
             count(*)::int AS sizes_total,
             row_number() OVER (PARTITION BY s.slug
                                ORDER BY bool_or(v.available) DESC, p.published_at DESC NULLS LAST) AS brand_rank
      FROM products p
      JOIN stores s ON s.id = p.store_id
      JOIN variants v ON v.product_id = p.id AND v.is_active
      WHERE p.is_active
        AND ($1::text IS NULL OR s.slug = $1)
        AND ($2::text IS NULL OR EXISTS (SELECT 1 FROM product_collections pc
                                         WHERE pc.product_id = p.id AND pc.collection_id = $2))
        AND ($3::text IS NULL OR p.title ILIKE '%' || $3 || '%' OR p.product_type ILIKE '%' || $3 || '%')
        AND ($4::text IS NULL OR EXISTS (
              SELECT 1 FROM variants v2
              JOIN product_options po ON po.product_id = v2.product_id AND po.name_normalized = 'size'
              WHERE v2.product_id = p.id AND v2.is_active AND v2.available AND ${SIZE_OF_VARIANT} = $4))
      GROUP BY p.id, s.slug, s.name
    )
    SELECT b.id, b.title, b.store_slug, b.store_name, b.price, b.compare_at, b.discount, b.in_stock,
           b.sizes_in_stock, b.sizes_total, count(*) OVER ()::int AS total,
           (SELECT i.src FROM product_images pi JOIN images i ON i.id = pi.image_id
            WHERE pi.product_id = b.id ORDER BY pi.position LIMIT 1) AS image
    FROM base b
    WHERE (NOT $5 OR b.in_stock) AND (NOT $6 OR b.on_sale)
    ORDER BY ${ORDER_BY[f.sort] ?? ORDER_BY.featured}
    LIMIT ${PAGE_SIZE} OFFSET $7`,
    [f.brand, f.category, f.size, f.q, f.inStock, f.onSale, (f.page - 1) * PAGE_SIZE],
  );
}

export type Category = { id: string; title: string; products: number };

/** Collections a person chose (or the rules chose) to show as categories, for one brand. */
export async function getCategories(brand: string): Promise<Category[]> {
  "use cache";
  cacheLife("minutes");
  return query<Category>(
    `SELECT c.id, c.title, count(p.id)::int AS products
     FROM collections c
     JOIN stores s ON s.id = c.store_id AND s.slug = $1
     JOIN product_collections pc ON pc.collection_id = c.id
     JOIN products p ON p.id = pc.product_id AND p.is_active
     WHERE c.show_on_site AND c.is_active
     GROUP BY c.id HAVING count(p.id) > 0
     ORDER BY c.title`,
    [brand],
  );
}

const STANDARD_SIZE = /^(XXS|XS|S|M|L|XL|XXL|XXXL|[2-6]XL|\d{2})$/;

/** Sizes that are in stock somewhere (in one brand, or in all brands). */
export async function getSizes(brand: string | null): Promise<string[]> {
  "use cache";
  cacheLife("minutes");
  const rows = await query<{ size: string }>(
    `SELECT ${SIZE_OF_VARIANT} AS size
     FROM variants v2
     JOIN product_options po ON po.product_id = v2.product_id AND po.name_normalized = 'size'
     JOIN products p ON p.id = v2.product_id AND p.is_active
     JOIN stores s ON s.id = p.store_id
     WHERE v2.is_active AND v2.available AND ($1::text IS NULL OR s.slug = $1)
     GROUP BY 1 HAVING count(DISTINCT p.id) >= 3`,
    [brand],
  );
  // Only standard sizes: stores also use values like "L-32 (CHEST 42\" AND WAIST 32\")".
  return rows.map((r) => r.size).filter((s) => STANDARD_SIZE.test(s));
}

// ---------------------------------------------------------------- product page

export type ProductDetail = {
  id: string;
  title: string;
  handle: string;
  body_html: string | null;
  vendor: string | null;
  product_type: string | null;
  published_at: string | null;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
  store_slug: string;
  store_name: string;
  base_url: string;
};

export type Variant = {
  id: string;
  title: string;
  option1: string | null;
  option2: string | null;
  option3: string | null;
  sku: string | null;
  price: number;
  compare_at_price: number | null;
  is_on_sale: boolean;
  available: boolean;
  grams: number | null;
  is_active: boolean;
};

export type HistoryRow = {
  variant_id: string;
  observed_at: string;
  price: number;
  compare_at_price: number | null;
  available: boolean;
};

export type ProductPage = {
  product: ProductDetail;
  images: { id: string; src: string; width: number | null; height: number | null; alt: string | null }[];
  options: { position: number; name: string }[];
  variants: Variant[];
  tags: string[];
  categories: { id: string; title: string }[];
  extras: { owner: string; field_path: string; value: string | null }[];
  history: HistoryRow[];
};

export async function getProduct(id: string): Promise<ProductPage | null> {
  "use cache";
  cacheLife("minutes");
  if (!/^PRD-[0-9A-HJKMNP-TV-Z]{5}$/.test(id)) return null;
  const [product] = await query<ProductDetail>(
    `SELECT p.id, p.title, p.handle, p.body_html, p.vendor, p.product_type,
            p.published_at::text, p.first_seen_at::text, p.last_seen_at::text, p.is_active,
            s.slug AS store_slug, s.name AS store_name, s.base_url
     FROM products p JOIN stores s ON s.id = p.store_id WHERE p.id = $1`,
    [id],
  );
  if (!product) return null;

  const [images, options, variants, tags, categories, extras, history] = await Promise.all([
    query<ProductPage["images"][number]>(
      `SELECT i.id, i.src, i.width, i.height, i.alt FROM product_images pi
       JOIN images i ON i.id = pi.image_id WHERE pi.product_id = $1 ORDER BY pi.position`, [id]),
    query<ProductPage["options"][number]>(
      `SELECT position, name FROM product_options WHERE product_id = $1 ORDER BY position`, [id]),
    query<Variant>(
      `SELECT id, title, option1, option2, option3, sku, price, compare_at_price, is_on_sale, available,
              grams, is_active
       FROM variants WHERE product_id = $1 ORDER BY is_active DESC, position`, [id]),
    query<{ tag: string }>(`SELECT tag FROM product_tags WHERE product_id = $1 ORDER BY lower(tag)`, [id]),
    query<{ id: string; title: string }>(
      `SELECT c.id, c.title FROM product_collections pc JOIN collections c ON c.id = pc.collection_id
       WHERE pc.product_id = $1 AND c.show_on_site AND c.is_active ORDER BY c.title`, [id]),
    // Unknown API fields that are still present in the latest data.
    query<ProductPage["extras"][number]>(
      `SELECT coalesce(v.title, 'product') AS owner, e.field_path, e.value
       FROM extra_attributes e
       LEFT JOIN variants v ON v.id = e.variant_id
       WHERE (e.product_id = $1 OR v.product_id = $1) AND e.last_seen_at >= $2::timestamptz
       ORDER BY e.product_id NULLS LAST, v.position, e.field_path`, [id, product.last_seen_at]),
    query<HistoryRow>(
      `SELECT h.variant_id, h.observed_at::text, h.price, h.compare_at_price, h.available
       FROM variant_history h JOIN variants v ON v.id = h.variant_id
       WHERE v.product_id = $1 ORDER BY h.observed_at`, [id]),
  ]);

  return { product, images, options, variants, tags: tags.map((t) => t.tag), categories, extras, history };
}
