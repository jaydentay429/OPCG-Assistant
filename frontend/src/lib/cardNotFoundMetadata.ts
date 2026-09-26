import type { Metadata } from "next";

/**
 * Missing-card metadata.
 *
 * `notFound()` already inserts a single `<meta name="robots" content="noindex">`.
 * Setting `robots: { index: false, follow: false }` renders a second tag,
 * `noindex, nofollow`. `robots: null` clears the layout's index,follow so the
 * automatic tag is the only robots meta.
 */
export const cardNotFoundMetadata: Metadata = {
  title: "找不到卡牌",
  description: "這個卡號不存在。請回到卡牌搜索查看有效卡牌。",
  robots: null,
};
