"use client";

import { useEffect, useMemo, useState } from "react";
import { cardImagePacksUrl, cardImageSources } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";

type Props = {
  cardId: string;
  alt?: string;
  className?: string;
  localUrl?: string | null;
  loading?: "lazy" | "eager";
};

/**
 * Card image loader (fast path first):
 * 1) img.optcgassistant.com CDN (or API img_local_url when same host)
 * 2) api.../packs/{id}.png
 * 3) api.../images/card/{id} proxy
 */
export function CardImg({ cardId, alt, className, localUrl, loading = "lazy" }: Props) {
  const sources = useMemo(() => cardImageSources(cardId, localUrl), [cardId, localUrl]);
  const [idx, setIdx] = useState(0);
  const src = sources[idx] ?? sources[0] ?? cardImagePacksUrl(cardId);

  useEffect(() => {
    setIdx(0);
  }, [cardId, localUrl]);

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className={className}
      src={src}
      alt={alt || displayCardId(cardId)}
      loading={loading}
      decoding="async"
      onError={() => {
        setIdx((current) => (current + 1 < sources.length ? current + 1 : current));
      }}
    />
  );
}
