import type { Metadata } from "next";
import { buildPageMetadata } from "@/lib/seo";

/** Every /play URL stays out of the index and still passes equity to linked pages. */
export function playPageMetadata(input: { title: string; description: string; path: string }): Metadata {
  const meta = buildPageMetadata({
    title: input.title,
    description: input.description,
    path: input.path,
    absoluteTitle: true,
    noIndex: true,
  });
  return {
    ...meta,
    robots: {
      index: false,
      follow: true,
      googleBot: { index: false, follow: true },
    },
  };
}
