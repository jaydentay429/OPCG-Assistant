"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { cardImageSources } from "@/lib/api";
import { CARD_ART_HEIGHT, CARD_ART_WIDTH } from "@/lib/cardImageFrame";
import { displayCardId } from "@/lib/cardId";
import {
  heroCardImageAttrs,
  listCardImageAttrs,
  noteHeroWebpMiss,
  noteListWebpMiss,
  previousHeroImage,
  rememberShownHero,
  webpLoadAlreadyFailed,
  type ListCardImage,
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
  /** Thumbnail WebP srcset (card wall, prices, collector, detail variant strip). */
  listThumb?: boolean;
  /** Card-detail main image only. Full-size WebP; a failed load uses the PNG URL. */
  detailHero?: boolean;
  /** Overrides the default card-wall sizes when `listThumb` is set. */
  imageSizes?: string;
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

function elementShowsSrc(img: HTMLImageElement, src: string): boolean {
  return img.currentSrc === src || img.src === src;
}

/**
 * Card image loader. The only source is cardImageUrl(id) (CDN file with ?h=).
 * An empty URL (no manifest hash) or a failed load becomes a neutral placeholder.
 * `listThumb` requests the thumbnail WebP srcset first. If that file 404s, the
 * same element retries the PNG URL. `detailHero` requests the full-size WebP
 * and falls back the same way. The hero keeps the previous picture on screen
 * until the next URL has loaded, so a variant switch does not flash empty.
 * Width and height default to the 5:7 card ratio so the slot does not collapse.
 */
export function CardImg({
  cardId,
  alt,
  className,
  localUrl,
  loading = "lazy",
  fetchPriority,
  width = CARD_ART_WIDTH,
  height = CARD_ART_HEIGHT,
  listThumb = false,
  detailHero = false,
  imageSizes,
}: Props) {
  const sources = useMemo(() => cardImageSources(cardId, localUrl), [cardId, localUrl]);
  const mode = listThumb ? "list" : detailHero ? "hero" : "png";
  const slot = `${mode}:${cardId}`;
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [webpMissSlot, setWebpMissSlot] = useState("");
  const [deadSlot, setDeadSlot] = useState("");
  const [painted, setPainted] = useState<ListCardImage | null>(null);
  const webpFailed = webpMissSlot === slot;
  const failed = deadSlot === slot;
  const enhanced = useMemo(() => {
    if (mode === "list") return listCardImageAttrs(cardId, webpFailed, imageSizes);
    if (mode === "hero") return heroCardImageAttrs(cardId, webpFailed);
    return null;
  }, [mode, cardId, webpFailed, imageSizes]);
  const heroHold =
    mode === "hero" && painted && enhanced && painted.src !== enhanced.src ? painted : null;
  const visible = heroHold ?? enhanced;

  useLayoutEffect(() => {
    if (mode !== "hero" || !enhanced || painted) return;
    const prev = previousHeroImage(enhanced.src);
    if (prev) setPainted(prev);
  }, [mode, enhanced, painted]);

  useEffect(() => {
    if (mode === "png" || !enhanced || failed) return;
    const img = imgRef.current;
    const showingTarget = img ? elementShowsSrc(img, enhanced.src) : false;

    if (showingTarget && webpLoadAlreadyFailed(img)) {
      if (enhanced.webp) {
        if (mode === "list") noteListWebpMiss(cardId);
        else noteHeroWebpMiss(cardId);
        setWebpMissSlot(slot);
      } else {
        setDeadSlot(slot);
      }
      return;
    }

    if (mode !== "hero") return;

    if (showingTarget && img && img.complete && img.naturalWidth > 0) {
      rememberShownHero(enhanced);
      setPainted((prev) => (prev?.src === enhanced.src ? prev : enhanced));
      return;
    }

    if (!painted || painted.src === enhanced.src) return;

    let cancelled = false;
    const probe = new Image();
    probe.onload = () => {
      if (cancelled) return;
      rememberShownHero(enhanced);
      setPainted(enhanced);
    };
    probe.onerror = () => {
      if (cancelled) return;
      if (enhanced.webp) {
        noteHeroWebpMiss(cardId);
        setWebpMissSlot(slot);
        return;
      }
      setDeadSlot(slot);
    };
    probe.src = enhanced.src;
    return () => {
      cancelled = true;
    };
  }, [mode, enhanced, painted, cardId, slot, failed]);

  const altText = alt || displayCardId(cardId);

  if (mode !== "png") {
    if (!visible || failed) {
      return <CardImagePlaceholder className={className} />;
    }
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        ref={imgRef}
        key={visible.webp ? "webp" : "png"}
        className={className}
        src={visible.src}
        srcSet={visible.srcSet}
        sizes={visible.sizes}
        alt={altText}
        width={width}
        height={height}
        loading={loading}
        fetchPriority={fetchPriority}
        decoding="async"
        onLoad={(event) => {
          if (mode !== "hero" || heroHold) return;
          const el = event.currentTarget;
          if (el.naturalWidth > 0 && enhanced && elementShowsSrc(el, enhanced.src)) {
            rememberShownHero(enhanced);
            setPainted(enhanced);
          }
        }}
        onError={() => {
          if (heroHold || !enhanced) return;
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
