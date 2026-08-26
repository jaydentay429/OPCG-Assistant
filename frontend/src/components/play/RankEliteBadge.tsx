"use client";

export type EliteTitleKey = "pirate_king" | "emperor" | "warlord" | string | null | undefined;

export function eliteTitleClass(title: EliteTitleKey): string | null {
  const key = String(title || "").trim();
  if (key === "pirate_king") return "rank-elite-king";
  if (key === "emperor") return "rank-elite-emperor";
  if (key === "warlord") return "rank-elite-warlord";
  return null;
}

export function eliteLabelForTitle(
  title: EliteTitleKey,
  t: (key: string) => string,
  fallback?: string | null,
): string | null {
  const key = String(title || "").trim();
  if (key === "pirate_king") return t("play.rank_elite_king");
  if (key === "emperor") return t("play.rank_elite_emperor");
  if (key === "warlord") return t("play.rank_elite_warlord");
  return fallback || null;
}

export function eliteBlockClass(title: EliteTitleKey): string | null {
  const key = String(title || "").trim();
  if (key === "pirate_king") return "is-king";
  if (key === "emperor") return "is-emperor";
  if (key === "warlord") return "is-warlord";
  return null;
}

type RankEliteNameProps = {
  name: string;
  eliteTitle?: EliteTitleKey;
  eliteLabel?: string | null;
  showBadge?: boolean;
  size?: "sm" | "md" | "lg";
};

export function RankEliteName({
  name,
  eliteTitle,
  eliteLabel,
  showBadge = true,
  size = "md",
}: RankEliteNameProps) {
  const cls = eliteTitleClass(eliteTitle);
  if (!cls) {
    return <span className="rank-plain-name">{name}</span>;
  }
  return (
    <span className={`rank-elite-name ${cls} is-${size}`}>
      {showBadge && eliteLabel ? <span className="rank-elite-tag">{eliteLabel}</span> : null}
      <span className="rank-elite-name-text">{name}</span>
    </span>
  );
}

type RankEliteTierProps = {
  label: string;
  eliteTitle?: EliteTitleKey;
};

export function RankEliteTier({ label, eliteTitle }: RankEliteTierProps) {
  const cls = eliteTitleClass(eliteTitle);
  if (!cls) return <strong>{label}</strong>;
  return (
    <span className={`rank-elite-tier ${cls}`}>
      <span className="rank-elite-tier-text">{label}</span>
    </span>
  );
}
