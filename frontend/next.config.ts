import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

/**
 * User agents that get blocking metadata (`<title>` and the other tags inside
 * `<head>` in the raw HTML).
 *
 * Assigning `htmlLimitedBots` replaces Next.js's built-in list. It does not
 * merge. The pattern is `HTML_LIMITED_BOT_UA_RE` from Next 15.5.22
 * (`next/dist/shared/lib/router/utils/html-bots.js`) with `Googlebot` added.
 *
 * The default matches `*-Google` and `Google-*` (so Google-InspectionTool,
 * AdsBot-Google, and the rest of that family) and, because Next recompiles
 * this source with the `i` flag, bingbot, Baiduspider, YandexBot,
 * DuckDuckBot, and Applebot. It does not match `Googlebot`. Next treats
 * Googlebot as a JavaScript crawler and streams metadata into the body, so
 * the raw HTML has `<title>` after `</head>`.
 */
export const htmlLimitedBots =
  /Googlebot|[\w-]+-Google|Google-[\w-]+|Chrome-Lighthouse|Slurp|DuckDuckBot|baiduspider|yandex|sogou|bitlybot|tumblr|vkShare|quora link preview|redditbot|ia_archiver|Bingbot|BingPreview|applebot|facebookexternalhit|facebookcatalog|Twitterbot|LinkedInBot|Slackbot|Discordbot|WhatsApp|SkypeUriPreview|Yeti|googleweblight/i;

const nextConfig: NextConfig = {
  htmlLimitedBots,
  output: "standalone",
  outputFileTracingRoot: frontendRoot,
  // Next 308-strips a trailing slash before middleware, and that redirect's
  // Location is taken from the internal request host (localhost:3000 behind
  // Caddy). Skipping it lets middleware emit one public-origin redirect:
  // card case + slash collapse to a single 301, and /search/ /sets/ 308
  // without ever reading Host / request.url.
  skipTrailingSlashRedirect: true,
  images: {
    unoptimized: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
