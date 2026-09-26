import path from "node:path";
import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
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
