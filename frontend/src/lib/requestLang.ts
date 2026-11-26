import { headers } from "next/headers";
import { LANG_HEADER, isUrlLang, type UrlLang } from "./localeRouting";

/**
 * UI language of the current request. Middleware sets the header only for
 * /en and /zh-hans URLs (and strips a client-sent one elsewhere), so an
 * unprefixed URL is always Traditional Chinese on the server.
 */
export async function getRequestLang(): Promise<UrlLang> {
  try {
    const value = (await headers()).get(LANG_HEADER);
    return isUrlLang(value) ? value : "zh-Hant";
  } catch {
    return "zh-Hant";
  }
}
