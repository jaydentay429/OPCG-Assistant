"use client";

import { RouteErrorFallback } from "@/components/RouteErrorFallback";
import "./globals.css";

/**
 * Catches errors in the root layout itself. The segment `error.tsx` stays
 * mounted inside the layout, so the update banner survives a page failure.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-HK">
      <body>
        <RouteErrorFallback error={error} reset={reset} />
      </body>
    </html>
  );
}
