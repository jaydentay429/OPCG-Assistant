"use client";

import { useEffect, useMemo, useState } from "react";
import { cardImageSources } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";

type Props = {
  cardId: string;
  alt?: string;
  className?: string;
  localUrl?: string | null;
  loading?: "lazy" | "eager";
  fetchPriority?: "high" | "low" | "auto";
  width?: number;
  height?: number;
};

/**
 * Card image loader. The only source is cardImageUrl(id) (CDN file with ?h=).
 * An id missing from the manifest has no src here; the placeholder is unchanged.
 */
export function CardImg({
  cardId,
  alt,
  className,
  localUrl,
  loading = "lazy",
  fetchPriority,
  width,
  height,
}: Props) {
  const sources = useMemo(() => cardImageSources(cardId, localUrl), [cardId, localUrl]);
  const [idx, setIdx] = useState(0);
  const src = sources[idx] ?? sources[0] ?? "";

  useEffect(() => {
    setIdx(0);
  }, [cardId, localUrl]);

  if (!src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        className={className}
        src="/battle/card-back.png"
        alt={alt || displayCardId(cardId)}
        loading={loading}
        decoding="async"
      />
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className={className}
      src={src}
      alt={alt || displayCardId(cardId)}
      width={width}
      height={height}
      loading={loading}
      fetchPriority={fetchPriority}
      decoding="async"
      onError={() => {
        setIdx((current) => (current + 1 < sources.length ? current + 1 : current));
      }}
    />
  );
}
