"use client";

import { useAuth } from "@/lib/auth";
import { logMyAnalyticsIds, trackPageview } from "@/lib/analytics";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

function AnalyticsBeaconInner() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { token, ready } = useAuth();
  const lastKey = useRef("");

  useEffect(() => {
    logMyAnalyticsIds();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const qs = searchParams?.toString() ? `?${searchParams.toString()}` : "";
    const full = `${pathname || "/"}${qs}`;
    const key = `${full}|${token || ""}`;
    if (key === lastKey.current) return;
    lastKey.current = key;
    trackPageview(full, token);
  }, [pathname, searchParams, ready, token]);

  return null;
}

export function AnalyticsBeacon() {
  return (
    <Suspense fallback={null}>
      <AnalyticsBeaconInner />
    </Suspense>
  );
}
