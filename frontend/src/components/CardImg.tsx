"use client";

import { useEffect, useMemo, useState } from "react";
import { cardImageSources } from "@/lib/api";
import { displayCardId } from "@/lib/cardId";
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
  const [failed, setFailed] = useState(false);
  const src = sources[0] ?? "";

  useEffect(() => {
    setFailed(false);
  }, [cardId, localUrl]);

  if (!src || failed) {
    return <CardImagePlaceholder className={className} />;
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
      onError={() => setFailed(true)}
    />
  );
}
