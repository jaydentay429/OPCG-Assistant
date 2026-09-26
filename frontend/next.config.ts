import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: frontendRoot,
  // Default trailingSlash is false, but Next 308-strips the slash before
  // middleware. Skipping that lets middleware 301 a card URL (wrong case
  // and/or trailing slash) straight to /cards/ID in one hop.
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
