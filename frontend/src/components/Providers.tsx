"use client";

import { AuthProvider, useAuth } from "@/lib/auth";
import { DeckProvider } from "@/lib/deck";
import { I18nProvider, type Lang } from "@/lib/i18n";
import { applyTabNavScrollTopIfNeeded, enableManualScrollRestoration } from "@/lib/scrollRestore";
import { usePathname } from "next/navigation";
import { useEffect, useLayoutEffect, type ReactNode } from "react";
import { AnalyticsBeacon } from "./AnalyticsBeacon";
import { AuthModal } from "./AuthModal";

function ScrollRestorationSetup() {
  const pathname = usePathname();

  useEffect(() => {
    enableManualScrollRestoration();
  }, []);

  // After bottom-nav switches, pin to top once the new route mounts
  // (beats App Router re-applying the previous page's scroll offset).
  useLayoutEffect(() => {
    applyTabNavScrollTopIfNeeded();
  }, [pathname]);

  useEffect(() => {
    if (!applyTabNavScrollTopIfNeeded()) return;
    const t1 = window.setTimeout(() => applyTabNavScrollTopIfNeeded(), 50);
    const t2 = window.setTimeout(() => applyTabNavScrollTopIfNeeded(), 200);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [pathname]);

  return null;
}

function AuthModalHost() {
  const { authOpen, closeAuth } = useAuth();
  if (!authOpen) return null;
  return <AuthModal onClose={closeAuth} />;
}

export function Providers({ children, initialLang }: { children: ReactNode; initialLang?: Lang }) {
  return (
    <I18nProvider initialLang={initialLang}>
      <AuthProvider>
        <DeckProvider>
          <ScrollRestorationSetup />
          <AnalyticsBeacon />
          {children}
          <AuthModalHost />
        </DeckProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
