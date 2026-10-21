"use client";

import { useState } from "react";
import { shopifyImage } from "@/lib/format";

type Image = { id: string; src: string; alt: string | null };

export function Gallery({ images, title }: { images: Image[]; title: string }) {
  const [current, setCurrent] = useState(0);
  if (images.length === 0) {
    return (
      <div className="flex aspect-[4/5] items-center justify-center rounded-xl border border-border bg-surface text-muted">
        No image
      </div>
    );
  }
  const main = images[current];
  return (
    <div className="space-y-3">
      <div className="aspect-[4/5] overflow-hidden rounded-xl border border-border bg-surface">
        {/* eslint-disable-next-line @next/next/no-img-element -- Shopify's CDN already resizes images */}
        <img src={shopifyImage(main.src, 1000)!} alt={main.alt ?? title} className="h-full w-full object-cover" />
      </div>
      {images.length > 1 && (
        <ul className="no-scrollbar flex gap-2 overflow-x-auto">
          {images.map((img, i) => (
            <li key={img.id} className="shrink-0">
              <button
                type="button"
                onClick={() => setCurrent(i)}
                aria-label={`Show image ${i + 1}`}
                aria-current={i === current}
                className={`block h-20 w-16 overflow-hidden rounded-md border-2 ${
                  i === current ? "border-foreground" : "border-transparent opacity-70 hover:opacity-100"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={shopifyImage(img.src, 160)!} alt="" loading="lazy" className="h-full w-full object-cover" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
