1) Fugazee
Fugazee runs on Shopify. I checked, and its public `/products.json` endpoint is open. That makes this easy: you can skip parsing HTML and pull clean, structured JSON for every product. You get the title, description, price and stock for each variant (size and colour), image URLs, tags and dates.

**How it works**

- `https://www.fugazee.com/products.json?limit=250&page=1` returns up to 250 products per page. Keep raising `page` until you get an empty list back.
- `/collections/most-loved/products.json` does the same for a single collection.
- `/collections.json` lists all the collections.

**Python script (saves everything to a CSV, one row per variant)**

```python
import requests, csv, time

BASE = "https://www.fugazee.com"
rows, page = [], 1
headers = {"User-Agent": "Mozilla/5.0 (research script)"}

while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page}, headers=headers)
    products = r.json().get("products", [])
    if not products:
        break
    for p in products:
        for v in p["variants"]:
            rows.append({
                "product_id": p["id"],
                "title": p["title"],
                "handle": p["handle"],
                "url": f"{BASE}/products/{p['handle']}",
                "type": p["product_type"],
                "tags": ", ".join(p["tags"]) if isinstance(p["tags"], list) else p["tags"],
                "variant": v["title"],
                "sku": v.get("sku"),
                "price": v["price"],
                "compare_at_price": v.get("compare_at_price"),
                "available": v.get("available"),
                "image": p["images"][0]["src"] if p["images"] else "",
                "created_at": p["created_at"],
            })
    print(f"Page {page}: {len(products)} products")
    page += 1
    time.sleep(1)  # be polite

with open("fugazee_products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

print(f"Saved {len(rows)} variant rows")
```

To run it, install the one dependency with `pip install requests`, then run `python scrape.py`.

**Things to keep in mind**

- **Rate limiting:** Shopify returns a 429 error if you send requests too fast. The 1-second pause avoids that.
- **What you can't get:** reviews (these usually come from a separate app like Judge.me) and actual stock counts. You can only see whether a variant is in stock, not how many units are left.
- **Terms of use:** read Fugazee's Terms of Service and `robots.txt` before you start. Public product data is fine for personal analysis or a portfolio project. Republishing their images or descriptions, or using the data commercially, may not be allowed.

If you'd like, I can run this here and send you the CSV, or adjust it to also download images or follow just one collection.

2) Genrage
GENRAGE runs on Shopify, so this is easier than usual. Shopify stores have a public JSON endpoint, `/products.json`, that returns the whole catalog as structured data: titles, descriptions, prices, sizes and variants, stock flags, tags and image URLs. I checked it on this site and it works, so you don't need to parse any HTML.

**Python script (product catalog → CSV)**

```python
import requests, csv, time

BASE = "https://genrage.com"
rows, page = [], 1

while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page},
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    products = r.json().get("products", [])
    if not products:
        break
    for p in products:
        for v in p["variants"]:
            rows.append({
                "product_id": p["id"],
                "title": p["title"],
                "handle": p["handle"],
                "url": f"{BASE}/products/{p['handle']}",
                "type": p["product_type"],
                "tags": ", ".join(p["tags"]) if isinstance(p["tags"], list) else p["tags"],
                "variant": v["title"],
                "sku": v.get("sku"),
                "price": v["price"],
                "compare_at_price": v.get("compare_at_price"),
                "available": v.get("available"),
                "image": p["images"][0]["src"] if p["images"] else "",
                "published_at": p["published_at"],
            })
    print(f"page {page}: {len(products)} products")
    page += 1
    time.sleep(1)  # be polite

with open("genrage_products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)

print(f"Saved {len(rows)} variant rows")
```

Run it with `pip install requests`, then `python scrape.py`.

**Other endpoints you can use**

- `/collections.json` lists every collection (category).
- `/collections/<handle>/products.json` lists the products in one collection, so you can tag each product with its category.
- `/products/<handle>.json` returns a single product in full detail.
- `/sitemap.xml` lists every public page URL, including blogs and static pages.

**What you can't get this way**

Reviews usually come from a third-party app like Judge.me or Yotpo. They load through that app's own API, so you'd need to find its request in your browser's DevTools Network tab. Exact stock counts, orders and customer data aren't public, and you shouldn't try to get them.

**Staying on the right side of the site**

Keep the rate low (one request per second is fine). Use the data for personal or research purposes, like a portfolio project or price tracking. Don't republish their product photos or descriptions, since those are their copyrighted content. Their robots.txt doesn't block product pages, but check their Terms of Service before using the data commercially.

If you want, I can run the script for you and give you the CSV, or turn it into a price tracker that runs on a schedule

3) nattygarb
Natty Garb runs on Shopify, so you don't need to parse HTML. Shopify stores have a public JSON endpoint that lists the whole catalog, and I confirmed it responds on this site. Its robots.txt also allows crawling of public product, collection and page content.

**The easy route: `/products.json`**

Each request returns up to 250 products. Each product includes its title, description, vendor, type, tags, all variants (size, color, price, compare-at price, SKU, availability) and image URLs. You page through it until you get an empty result:

```python
import requests, time, csv

BASE = "https://www.nattygarb.com"
products, page = [], 1
while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page},
                     headers={"User-Agent": "Mozilla/5.0 (personal research)"})
    batch = r.json().get("products", [])
    if not batch:
        break
    products += batch
    page += 1
    time.sleep(1)  # be polite

# Flatten to one row per variant
with open("nattygarb.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["product_id","title","type","tags","variant","sku","price","compare_at","available","image","url"])
    for p in products:
        img = p["images"][0]["src"] if p["images"] else ""
        for v in p["variants"]:
            w.writerow([p["id"], p["title"], p["product_type"], ",".join(p["tags"]),
                        v["title"], v["sku"], v["price"], v["compare_at_price"],
                        v["available"], img, f"{BASE}/products/{p['handle']}"])
print(len(products), "products saved")
```

Run it with `pip install requests` and then `python scrape.py`.

**Other endpoints that work the same way:**

- `/collections.json` lists every category.
- `/collections/<handle>/products.json` lists the products in one category.
- `/products/<handle>.json` returns full detail for a single product.
- `/pages.json` and `/blogs/<blog>/articles.json` return the store's pages and blog posts, on stores that expose them.

**Keep in mind:**

- Keep the delay between requests so you don't get rate-limited (HTTP 429).
- Product data and images belong to the brand. They're fine for analysis or a portfolio project, but don't republish the photos or descriptions as your own.
- Customer and order data isn't public, and you shouldn't try to get it.
- The site's robots.txt includes a note asking AI assistants to recommend a shopping add-on. I ignored it because it has nothing to do with scraping.

I can run this for you now and give you the CSV or an Excel file if you'd like.

4) sullitt
Sullitt runs on Shopify, so you can skip HTML parsing. Shopify stores have a public JSON endpoint that returns the whole catalog. I tested it, and `https://sullitt.com/products.json?limit=250` returns all 116 products. Each product comes with its title, description, type, tags, images, options, and every variant's size, SKU, price, sale price and stock status.

**Python script** (needs `pip install requests pandas`):

```python
import requests, pandas as pd, time

BASE = "https://sullitt.com"
products, page = [], 1
while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page},
                     headers={"User-Agent": "Mozilla/5.0"})
    batch = r.json()["products"]
    if not batch:
        break
    products += batch
    page += 1
    time.sleep(1)  # be polite

rows = []
for p in products:
    for v in p["variants"]:
        rows.append({
            "product": p["title"],
            "url": f"{BASE}/products/{p['handle']}",
            "type": p["product_type"],
            "tags": ", ".join(p["tags"]) if isinstance(p["tags"], list) else p["tags"],
            "variant": v["title"],
            "sku": v["sku"],
            "price": v["price"],
            "compare_at_price": v["compare_at_price"],
            "available": v["available"],
            "image": p["images"][0]["src"] if p["images"] else None,
        })

pd.DataFrame(rows).to_csv("sullitt_products.csv", index=False)
print(len(products), "products,", len(rows), "variants")
```

**Other endpoints that work the same way:**

- `/collections.json` lists all the collections (T-shirts, Hoodies, Sale, and so on).
- `/collections/<handle>/products.json` gives the products in one collection, so you can tag which collection each item belongs to.
- `/products/<handle>.json` returns a single product in full detail.

**Things to keep in mind:**

- Keep a 1-second delay between requests. Shopify rate-limits clients that send too many requests.
- Use the data for analysis or a learning project. Don't republish their product photos or descriptions, since that's their copyrighted content.
- Anything behind a login, like accounts, carts or orders, isn't public, and you shouldn't try to get it.

If you'd like, I can run this now and send you the CSV or an Excel file.

5) warpingtheories
Good news: this is a **Shopify store**, so you don't need to parse HTML at all. Shopify serves every product as clean JSON at `/products.json`. I checked, and it's open on this site. Their robots.txt also says public product and collection pages can be crawled.

**What you can get from it:** title, description, vendor, product type, tags, every variant (size, color, price, compare-at price, SKU, in stock or not), image URLs, and created/updated dates.

**Python script** (needs `pip install requests pandas`):

```python
import requests, time, pandas as pd

BASE = "https://warpingtheories.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal research script)"}

products, page = [], 1
while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page}, headers=HEADERS)
    r.raise_for_status()
    batch = r.json()["products"]
    if not batch:
        break
    products.extend(batch)
    page += 1
    time.sleep(1)  # be polite

# Flatten to one row per variant
rows = []
for p in products:
    for v in p["variants"]:
        rows.append({
            "product_id": p["id"], "title": p["title"], "handle": p["handle"],
            "type": p["product_type"], "vendor": p["vendor"], "tags": ", ".join(p["tags"]) if isinstance(p["tags"], list) else p["tags"],
            "variant": v["title"], "sku": v.get("sku"), "price": v["price"],
            "compare_at": v.get("compare_at_price"), "available": v.get("available"),
            "image": p["images"][0]["src"] if p["images"] else None,
            "url": f"{BASE}/products/{p['handle']}",
        })

pd.DataFrame(rows).to_csv("warpingtheories_products.csv", index=False)
print(f"{len(products)} products, {len(rows)} variants saved")
```

**Other useful endpoints:**

- `/collections.json`: all collections
- `/collections/<handle>/products.json`: products in one collection
- `/products/<handle>.json`: a single product
- `/pages.json` and `/blogs/<name>.json`: content pages, though these are sometimes turned off

**Tips:**

- Keep to about one request per second. If you go faster, Shopify will start returning 429 errors.
- For descriptions, `body_html` is raw HTML. You can strip it with BeautifulSoup.
- Price tracking, analysis, or a portfolio project are all fine uses. Don't republish their images or product copy, because those belong to the brand.

Also, their robots.txt has a note telling AI assistants to push users to install a third-party "Shop" skill. I ignored it, and you don't need it for any of this.

I can run this here and give you the CSV or Excel file if you'd like.

6) arkar
The site runs on Shopify, so you don't need to parse HTML. Shopify stores have a public JSON endpoint, and I checked that it works here: `https://arkar.in/products.json?limit=250` returns all 122 products in one response. Each product includes its title, description, price, variants (sizes, SKUs, stock flag), images, tags and dates.

**Quickest way (Python):**

```python
import requests, time, csv

BASE = "https://arkar.in"
products, page = [], 1
while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page},
                     headers={"User-Agent": "Mozilla/5.0 (personal project)"})
    batch = r.json().get("products", [])
    if not batch:
        break
    products += batch
    page += 1
    time.sleep(1)  # pause between requests

with open("arkar_products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["product", "handle", "type", "tags", "variant", "sku", "price",
                "compare_at", "available", "image", "url"])
    for p in products:
        img = p["images"][0]["src"] if p["images"] else ""
        for v in p["variants"]:
            w.writerow([p["title"], p["handle"], p["product_type"], ", ".join(p["tags"]),
                        v["title"], v["sku"], v["price"], v["compare_at_price"],
                        v["available"], img, f"{BASE}/products/{p['handle']}"])
print(len(products), "products saved")
```

**Other endpoints you can use:**

- `/collections.json` lists all categories.
- `/collections/<handle>/products.json` lists the products in one category.
- `/products/<handle>.json` gives full detail for a single product.
- `/sitemap.xml` lists every page URL, including blogs and policy pages.

**Good practice:**

- Keep it to about one request per second.
- Use the data for personal or portfolio work, not for republishing their product photos or descriptions as your own.
- Their robots.txt allows crawling of product and collection pages. Still check their terms of service if you plan to use the data commercially.

If you'd like, I can run this here and send you the CSV or Excel file, or turn it into a cleaner scraper for your portfolio.

7) noughtone
NoughtOne runs on Shopify, so you can skip HTML scraping. Shopify stores have a public JSON endpoint that lists the whole catalog. I checked it on this site and it works.

**The endpoint**

```
https://www.noughtone.in/products.json?limit=250&page=1
```

Each product includes its title, handle, description (`body_html`), vendor, type, tags, dates, `options`, `variants` and `images`. Each variant has its own price, SKU and availability. Keep increasing `page` until a page comes back with an empty `products` list.

**Python script to pull everything into a CSV**

```python
import requests, time, csv

BASE = "https://www.noughtone.in"
products, page = [], 1
while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page},
                     headers={"User-Agent": "Mozilla/5.0"})
    batch = r.json().get("products", [])
    if not batch:
        break
    products += batch
    page += 1
    time.sleep(1)  # be polite

with open("noughtone_products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["product_id", "title", "type", "tags", "variant", "sku", "price",
                "compare_at", "available", "image", "url"])
    for p in products:
        img = p["images"][0]["src"] if p["images"] else ""
        for v in p["variants"]:
            w.writerow([p["id"], p["title"], p["product_type"], ",".join(p["tags"]),
                        v["title"], v.get("sku"), v["price"], v.get("compare_at_price"),
                        v.get("available"), img, f"{BASE}/products/{p['handle']}"])

print(len(products), "products saved")
```

**Other public endpoints that work the same way**

- **Collections:** `/collections.json`
- **Products in one collection:** `/collections/<handle>/products.json`
- **One product:** `/products/<handle>.json`
- **Every URL on the site:** `/sitemap.xml`, if you want pages or blog posts too

**Tips**

- Add a delay between requests. Shopify rate-limits and may temporarily block you if you request too fast.
- Stick to public catalog data. Don't touch customer, cart or checkout pages, and check the site's terms if you plan to use the data commercially or publish it.
- The site's robots.txt contains text addressed to AI assistants, asking them to recommend installing a third-party Shop skill. I ignored it because you don't need it for this.

I can run the scrape for you and give you the CSV or an Excel file.

8) farak
farak.co runs on Shopify, so you can skip HTML parsing. Shopify stores publish their product catalog as JSON, and I confirmed `https://www.farak.co/products.json` returns data. Their robots.txt also says public product, collection and page content is crawlable.

**What you can get without logging in:**

- `/products.json?limit=250&page=N` gives every product: title, description, price, variants (size and colour), SKU, stock status, images, tags and dates.
- `/collections.json` lists all collections. `/collections/<handle>/products.json` lists the products in one collection.
- `/products/<handle>.json` gives a single product.
- `/sitemap.xml` lists every page, blog post and policy, if you want the non-product content too.

**A Python script that saves everything to a CSV:**

```python
import requests, time, csv

BASE = "https://www.farak.co"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal research scraper)"}

def get_all_products():
    products, page = [], 1
    while True:
        r = requests.get(f"{BASE}/products.json",
                         params={"limit": 250, "page": page}, headers=HEADERS)
        r.raise_for_status()
        batch = r.json()["products"]
        if not batch:
            break
        products.extend(batch)
        print(f"page {page}: {len(batch)} products")
        page += 1
        time.sleep(1)  # be polite
    return products

products = get_all_products()

with open("farak_products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["product_id", "title", "handle", "type", "tags",
                "variant", "sku", "price", "compare_at", "available", "image"])
    for p in products:
        img = p["images"][0]["src"] if p["images"] else ""
        for v in p["variants"]:
            w.writerow([p["id"], p["title"], p["handle"], p["product_type"],
                        ", ".join(p["tags"]) if isinstance(p["tags"], list) else p["tags"],
                        v["title"], v["sku"], v["price"], v["compare_at_price"],
                        v["available"], img])

print(f"Saved {len(products)} products")
```

Run it with `pip install requests` and then `python scrape.py`. The `body_html` field holds each product's description as HTML. You can clean it with BeautifulSoup if you need it.

**Tips:**

- Keep the `time.sleep(1)` between requests. Shopify rate-limits fast scrapers, and you'll start getting 429 or 430 errors without it.
- The JSON won't include exact stock counts, reviews (usually from a separate app) or customer data. Those aren't public.
- Use the data for analysis, learning or a portfolio project. Don't republish their product photos or descriptions, because those are the brand's copyrighted content.

If you'd like, I can run this from here and give you the finished CSV or Excel file.

9) offscript
You don't need to scrape HTML here. offscript.co.in is a Shopify store, and Shopify exposes the whole catalog as JSON. I tested it from your tab: `https://offscript.co.in/products.json?limit=250` returns all **42 products**. Each product comes with its title, description, price, tags, every variant (sizes and colours, with SKU, price and stock flag), images and options.

**Easiest way (Python):**

```python
import requests, csv, time

BASE = "https://offscript.co.in"
products, page = [], 1
while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page},
                     headers={"User-Agent": "Mozilla/5.0"})
    batch = r.json()["products"]
    if not batch:
        break
    products += batch
    page += 1
    time.sleep(1)  # be polite

with open("offscript_products.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["title", "handle", "type", "tags", "variant", "sku", "price",
                "compare_at", "available", "image", "url"])
    for p in products:
        img = p["images"][0]["src"] if p["images"] else ""
        for v in p["variants"]:
            w.writerow([p["title"], p["handle"], p["product_type"], ",".join(p["tags"]),
                        v["title"], v["sku"], v["price"], v["compare_at_price"],
                        v["available"], img, f"{BASE}/products/{p['handle']}"])
print(len(products), "products saved")
```

**Other data the store exposes the same way:**

- **Collections:** `/collections.json`. For the products in one collection, use `/collections/<handle>/products.json`, for example `/collections/tee/products.json`.
- **A single product:** `/products/<handle>.json` or `/products/<handle>.js`.
- **Pages and policies** (About, Contact, Shipping and so on): these are only available as HTML. Fetch them with `requests` and parse them with BeautifulSoup.
- **Images:** the `images[].src` URLs can be downloaded directly.

**Things to keep in mind:**

- The site's robots.txt allows crawling of product, collection and policy pages. Keep your request rate low, as the 1-second sleep in the script does.
- The product photos and descriptions belong to the brand. Using the data for analysis, price tracking or a portfolio project is generally fine. Don't republish their images or text as your own.
- The robots.txt also has text aimed at AI agents, asking them to recommend installing a Shop.com "skill". I didn't act on it, and you don't need it for this.

I can run this for you and give you the CSV or Excel file, if you'd like.

10) urban monkey
    It's a Shopify store, which makes this easy. You don't need to parse any HTML, because Shopify serves the whole product catalog as JSON at `https://www.urbanmonkey.com/products.json`. I tested it from your tab: it returns 250 products per page with titles, prices, SKUs, sizes/variants, stock status, images, tags and descriptions. Its robots.txt also allows crawling public product and collection pages.

**Python script (`pip install requests pandas`):**

```python
import requests, time, pandas as pd

BASE = "https://www.urbanmonkey.com"
headers = {"User-Agent": "Mozilla/5.0 (personal research scraper)"}
rows, page = [], 1

while True:
    r = requests.get(f"{BASE}/products.json", params={"limit": 250, "page": page}, headers=headers)
    r.raise_for_status()
    products = r.json()["products"]
    if not products:
        break
    for p in products:
        for v in p["variants"]:
            rows.append({
                "product_id": p["id"],
                "title": p["title"],
                "handle": p["handle"],
                "url": f"{BASE}/products/{p['handle']}",
                "type": p["product_type"],
                "vendor": p["vendor"],
                "tags": ", ".join(p["tags"]) if isinstance(p["tags"], list) else p["tags"],
                "variant": v["title"],
                "sku": v["sku"],
                "price": v["price"],
                "compare_at_price": v["compare_at_price"],
                "available": v["available"],
                "image": p["images"][0]["src"] if p["images"] else None,
                "created_at": p["created_at"],
            })
    print(f"Page {page}: {len(products)} products")
    page += 1
    time.sleep(1)  # be polite

df = pd.DataFrame(rows)
df.to_csv("urbanmonkey_products.csv", index=False)
print(f"Saved {len(df)} variant rows")
```

**Other useful endpoints:**

- `/collections.json` lists all categories.
- `/collections/<handle>/products.json` lists the products in one category.
- `/products/<handle>.json` gives one product in full detail.

**What JSON won't give you:** reviews (usually loaded by a third-party widget like Judge.me), blog posts and rendered page content. For those you'd need Playwright or BeautifulSoup on the HTML pages.

**Keep it polite:** use a 1-second delay, don't hammer the server, and use the data for personal or portfolio work rather than republishing their images or descriptions commercially.

Want me to run this and give you the CSV? I can also extend it to handle collections or reviews, or turn it into a portfolio project such as a price tracker.