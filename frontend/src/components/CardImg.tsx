"use client";

import { useEffect, useMemo, useState } from "react";
import { cardImageSources } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";
import { listCardImageAttrs, noteListWebpMiss } from "@/lib/cardImageSrcSet";
import { useI18n } from "@/lib/i18n";

type Props = {
  cardId: string;
  alt?: string;
  className?: string;
  localUrl?: string | null;
  loading?: "lazy" | "eager";
  fetchPriority?: "high" | "low" | "auto";
  width?: number;
  height?: number;
  /** Search card wall only. WebP srcset; a failed load uses the PNG URL. */
  listThumb?: boolean;
};

function joinClass(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Gray frame + localized label. Not an <img>, so it cannot carry the card name as alt. */
function CardImagePlaceholder({ className }: { className?: string }) {
  const { t } = useI18n();
  return (
    <span className={joinClass("card-img-placeholder", className)}>
      <span className="card-img-placeholder-label">{t("card.no_image")}</span>
    </span>
  );
}

/**
 * Card image loader. The only source is cardImageUrl(id) (CDN file with ?h=).
 * An empty URL (no manifest hash) or a failed load becomes a neutral placeholder.
 * `listThumb` (the search card wall) requests the WebP srcset first. If that
 * file 404s, the same element retries the PNG URL. Other callers, including
 * the card-page hero, stay on the PNG.
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
  listThumb = false,
}: Props) {
  const sources = useMemo(() => cardImageSources(cardId, localUrl), [cardId, localUrl]);
  const [webpFailed, setWebpFailed] = useState(false);
  const [failed, setFailed] = useState(false);
  const listAttrs = useMemo(
    () => (listThumb ? listCardImageAttrs(cardId, webpFailed) : null),
    [listThumb, cardId, webpFailed],
  );

  useEffect(() => {
    setWebpFailed(false);
    setFailed(false);
  }, [cardId, localUrl, listThumb]);

  const altText = alt || displayCardId(cardId);

  if (listThumb) {
    if (!listAttrs || failed) {
      return <CardImagePlaceholder className={className} />;
    }
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        key={listAttrs.webp ? "webp" : "png"}
        className={className}
        src={listAttrs.src}
        srcSet={listAttrs.srcSet}
        sizes={listAttrs.sizes}
        alt={altText}
        width={width}
        height={height}
        loading={loading}
        fetchPriority={fetchPriority}
        decoding="async"
        onError={() => {
          if (listAttrs.webp) {
            noteListWebpMiss(cardId);
            setWebpFailed(true);
            return;
          }
          setFailed(true);
        }}
      />
    );
  }

  const src = sources[0] ?? "";
  if (!src || failed) {
    return <CardImagePlaceholder className={className} />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      className={className}
      src={src}
      alt={altText}
      width={width}
      height={height}
      loading={loading}
      fetchPriority={fetchPriority}
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
