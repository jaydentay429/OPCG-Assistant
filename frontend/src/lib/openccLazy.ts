import { OPENCC_READY_EVENT } from "@/lib/openccEvents";

/**
 * Lazy Traditional↔Simplified converters.
 *
 * The full `opencc-js` entry is ~1.2MB because it inlines the simplified→traditional
 * phrase dictionary. Card text only needs Taiwan→Mainland (`tw2s`, tens of KB).
 * Collection search also needs Mainland→Taiwan (`s2tw`, the large phrase dictionary).
 * Both stay out of the initial bundle and load only when a call site asks.
 *
 * Until a converter is ready — and if it fails — callers keep the original text.
 */

type Convert = (text: string) => string;
type LoadState = "idle" | "loading" | "ready" | "failed";

let hansConvert: Convert | null = null;
let hantConvert: Convert | null = null;
let hansState: LoadState = "idle";
let hantState: LoadState = "idle";
let hansPromise: Promise<Convert | null> | null = null;
let hantPromise: Promise<Convert | null> | null = null;

const listeners = new Set<() => void>();

export function openccLoadState(): { hans: LoadState; hant: LoadState } {
  return { hans: hansState, hant: hantState };
}

export function subscribeOpencc(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  for (const listener of listeners) {
    try {
      listener();
    } catch {
      /* a subscriber must not break conversion */
    }
  }
  const host = globalThis.window;
  if (!host || typeof host.dispatchEvent !== "function") return;
  try {
    host.dispatchEvent(new Event(OPENCC_READY_EVENT));
  } catch {
    /* ignore */
  }
}

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

/** Mirrors opencc-js `tw2s`: Taiwan Traditional → Mainland Simplified. */
async function loadHansConverter(): Promise<Convert> {
  const [core, cjk, tsPhrases, tsChars, twVarPhrases, twVar] = await Promise.all([
    import(/* webpackChunkName: "opencc-core" */ "opencc-js/core"),
    import(
      /* webpackChunkName: "opencc-cjk" */ "opencc-js/dict/CJK_Compatibility_Ideographs"
    ),
    import(/* webpackChunkName: "opencc-tw2cn" */ "opencc-js/dict/TSPhrases"),
    import(/* webpackChunkName: "opencc-tw2cn" */ "opencc-js/dict/TSCharacters"),
    import(/* webpackChunkName: "opencc-tw2cn" */ "opencc-js/dict/TWVariantsRevPhrases"),
    import(/* webpackChunkName: "opencc-tw2cn" */ "opencc-js/dict/TWVariantsRev"),
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
}

/** Mirrors opencc-js `s2tw`: Mainland Simplified → Taiwan Traditional. */
async function loadHantConverter(): Promise<Convert> {
  const [core, cjk, stPhrases, stPhrasesGen, stChars, twVarPhrases, twVar] = await Promise.all([
    import(/* webpackChunkName: "opencc-core" */ "opencc-js/core"),
    import(
      /* webpackChunkName: "opencc-cjk" */ "opencc-js/dict/CJK_Compatibility_Ideographs"
    ),
    import(/* webpackChunkName: "opencc-cn2tw" */ "opencc-js/dict/STPhrases"),
    import(
      /* webpackChunkName: "opencc-cn2tw" */ "opencc-js/dict/STPhrases_GeneratedFromRegionalPhrases"
    ),
    import(/* webpackChunkName: "opencc-cn2tw" */ "opencc-js/dict/STCharacters"),
    import(/* webpackChunkName: "opencc-cn2tw" */ "opencc-js/dict/TWVariantsPhrases"),
    import(/* webpackChunkName: "opencc-cn2tw" */ "opencc-js/dict/TWVariants"),
  ]);
  const build = core.ConverterBuilder as Builder;
  const phrases = asDict(stPhrases);
  const phrasesGen = asDict(stPhrasesGen);
  const chars = asDict(stChars);
  const variantsPhrases = asDict(twVarPhrases);
  const variants = asDict(twVar);
  const compat = asDict(cjk);
  return build({
    from: { cn: [[phrases, chars]] },
    to: { tw: [[variantsPhrases, variants]] },
    configs: {
      s2tw: {
        normalizationChain: [[compat]],
        segmentation: [phrases, phrasesGen],
        conversionChain: [
          [phrases, phrasesGen, chars],
          [variantsPhrases, variants],
        ],
      },
    },
  })({ from: "cn", to: "tw" });
}

function canLoad(): boolean {
  return typeof window !== "undefined";
}

export function ensureHansConverter(): Promise<Convert | null> {
  if (hansConvert) return Promise.resolve(hansConvert);
  if (hansState === "failed") return Promise.resolve(null);
  if (!canLoad()) return Promise.resolve(null);
  if (!hansPromise) {
    hansState = "loading";
    hansPromise = loadHansConverter()
      .then((convert) => {
        hansConvert = convert;
        hansState = "ready";
        notify();
        return convert;
      })
      .catch(() => {
        hansState = "failed";
        return null;
      });
  }
  return hansPromise;
}

export function ensureHantConverter(): Promise<Convert | null> {
  if (hantConvert) return Promise.resolve(hantConvert);
  if (hantState === "failed") return Promise.resolve(null);
  if (!canLoad()) return Promise.resolve(null);
  if (!hantPromise) {
    hantState = "loading";
    hantPromise = loadHantConverter()
      .then((convert) => {
        hantConvert = convert;
        hantState = "ready";
        notify();
        return convert;
      })
      .catch(() => {
        hantState = "failed";
        return null;
      });
  }
  return hantPromise;
}

/** Sync Taiwan→Mainland. `null` means the dictionary is not ready (show the original). */
export function convertToHansSync(text: string): string | null {
  if (!hansConvert) return null;
  try {
    return hansConvert(text);
  } catch {
    return null;
  }
}

/** Sync Mainland→Taiwan. `null` means the dictionary is not ready. */
export function convertToHantSync(text: string): string | null {
  if (!hantConvert) return null;
  try {
    return hantConvert(text);
  } catch {
    return null;
  }
}
