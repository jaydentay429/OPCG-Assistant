import { HANS_PHRASE_FIXES } from "@/locales/hansPhraseFixes.generated";

/**
 * Taiwan Traditional → Mainland Simplified for server-rendered metadata and
 * server components on /zh-hans URLs. Same dictionaries as the browser
 * (`openccLazy.ts` tw2s) plus the site's phrase fixes. Loaded once per server
 * process; a load failure returns the original text.
 */
type Convert = (text: string) => string;

let convertPromise: Promise<Convert | null> | null = null;

function asDict(mod: unknown): string {
  let cur: unknown = mod;
  for (let i = 0; i < 3; i += 1) {
    if (typeof cur === "string") return cur;
    if (cur && typeof cur === "object" && "default" in cur) {
      cur = (cur as { default: unknown }).default;
      continue;
    }
    break;
  }
  throw new Error("OpenCC dictionary failed to load");
}

type Builder = (preset: unknown) => (options: { from: string; to: string }) => Convert;

async function load(): Promise<Convert | null> {
  try {
    const [core, cjk, tsPhrases, tsChars, twVarPhrases, twVar] = await Promise.all([
      import("opencc-js/core"),
      import("opencc-js/dict/CJK_Compatibility_Ideographs"),
      import("opencc-js/dict/TSPhrases"),
      import("opencc-js/dict/TSCharacters"),
      import("opencc-js/dict/TWVariantsRevPhrases"),
      import("opencc-js/dict/TWVariantsRev"),
    ]);
    const build = core.ConverterBuilder as Builder;
    const phrases = asDict(tsPhrases);
    const chars = asDict(tsChars);
    const variantsPhrases = asDict(twVarPhrases);
    const variants = asDict(twVar);
    const compat = asDict(cjk);
    return build({
      from: { tw: [[variantsPhrases, variants]] },
      to: { cn: [[phrases, chars]] },
      configs: {
        tw2s: {
          normalizationChain: [[compat]],
          segmentation: [phrases],
          conversionChain: [
            [variantsPhrases, variants],
            [phrases, chars],
          ],
        },
      },
    })({ from: "tw", to: "cn" });
  } catch {
    return null;
  }
}

function applyFixes(text: string): string {
  let out = text;
  for (const [from, to] of HANS_PHRASE_FIXES) {
    if (!from || from === to) continue;
    out = out.split(from).join(to);
  }
  return out;
}

/** Converter for this request: identity unless `lang` is zh-Hans. */
export async function serverHansConverter(lang: string): Promise<(text: string) => string> {
  if (lang !== "zh-Hans") return (text) => text;
  if (!convertPromise) convertPromise = load();
  const convert = await convertPromise;
  if (!convert) return (text) => text;
  return (text) => {
    if (!text) return text;
    try {
      return applyFixes(convert(text));
    } catch {
      return text;
    }
  };
}
