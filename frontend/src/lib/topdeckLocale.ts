/** Shared topdecks facet / field localization (tournaments list + card detail). */

export type TopdeckFacetLabels = {
  en?: string;
  "zh-Hans"?: string;
  "zh-Hant"?: string;
};

export function pickFacetLabel(
  lang: string,
  value: string,
  labels?: TopdeckFacetLabels | null,
  extra?: { label_en?: string; label_zh_Hans?: string; label_zh_Hant?: string },
): string {
  if (lang === "zh-Hans") {
    return labels?.["zh-Hans"] || extra?.label_zh_Hans || value;
  }
  if (lang === "zh-Hant") {
    return labels?.["zh-Hant"] || extra?.label_zh_Hant || value;
  }
  return labels?.en || extra?.label_en || value;
}

/** Keep "(…)" from the source text while using a localized/normalized base label. */
export function displayKeepingParens(
  lang: string,
  raw: string | undefined | null,
  key: string | undefined | null,
  labels?: TopdeckFacetLabels | null,
): string {
  const rawText = String(raw || "").trim();
  if (!rawText) return "";
  const base = pickFacetLabel(lang, key || "", labels);
  if (!base || base === key) return rawText;
  const parens = rawText.match(/\([^)]*\)/g) || [];
  if (!parens.length) return base;
  let out = base;
  for (const p of parens) {
    if (!out.includes(p)) out += p;
  }
  return out;
}

export function displayAuthor(raw: string | undefined | null, unknownLabel: string): string {
  const text = String(raw || "").trim();
  if (!text) return "";
  if (["NA", "N/A", "-"].includes(text.toUpperCase())) return unknownLabel;
  return text;
}
