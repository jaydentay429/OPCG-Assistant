"use client";

import { useMemo, useState } from "react";
import { cardImageSources } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";
import {
  heroCardImageAttrs,
  listCardImageAttrs,
  noteHeroWebpMiss,
  noteListWebpMiss,
} from "@/lib/cardImageSrcSet";
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
  /** Card-detail main image only. Full-size WebP; a failed load uses the PNG URL. */
  detailHero?: boolean;
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
 * file 404s, the same element retries the PNG URL. `detailHero` (the card-page
 * main image) requests the full-size WebP and falls back the same way.
 * Variant thumbnails and every other caller stay on the PNG.
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
  detailHero = false,
}: Props) {
  const sources = useMemo(() => cardImageSources(cardId, localUrl), [cardId, localUrl]);
  const mode = listThumb ? "list" : detailHero ? "hero" : "png";
  const slot = `${mode}:${cardId}`;
  const [webpMissSlot, setWebpMissSlot] = useState("");
  const [deadSlot, setDeadSlot] = useState("");
  const webpFailed = webpMissSlot === slot;
  const failed = deadSlot === slot;
  const enhanced = useMemo(() => {
    if (mode === "list") return listCardImageAttrs(cardId, webpFailed);
    if (mode === "hero") return heroCardImageAttrs(cardId, webpFailed);
    return null;
  }, [mode, cardId, webpFailed]);

  const altText = alt || displayCardId(cardId);

  if (mode !== "png") {
    if (!enhanced || failed) {
      return <CardImagePlaceholder className={className} />;
    }
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        key={enhanced.webp ? "webp" : "png"}
        className={className}
        src={enhanced.src}
        srcSet={enhanced.srcSet}
        sizes={enhanced.sizes}
        alt={altText}
        width={width}
        height={height}
        loading={loading}
        fetchPriority={fetchPriority}
        decoding="async"
        onError={() => {
          if (enhanced.webp) {
            if (mode === "list") noteListWebpMiss(cardId);
            else noteHeroWebpMiss(cardId);
            setWebpMissSlot(slot);
            return;
          }
          setDeadSlot(slot);
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
      onError={() => setDeadSlot(slot)}
    />
  );
}
