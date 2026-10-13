"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { markTabNavScrollReset } from "@/lib/scrollRestore";

const PRIMARY = [
  { href: "/search", key: "nav.search", icon: IconSearch },
  { href: "/builder", key: "nav.builder", icon: IconDeck },
  { href: "/tournaments", key: "nav.tournaments", icon: IconTrophy },
  { href: "/collector", key: "nav.collector", icon: IconCollect },
  { href: "/prices", key: "nav.prices", icon: IconPrice },
] as const;

const MORE = [
  { href: "/binder", key: "nav.binder", icon: IconBinder },
  { href: "/community", key: "nav.community", icon: IconCommunity },
  { href: "/play", key: "nav.play", icon: IconPlay },
] as const;

function tabRoot(pathname: string): string {
  if (pathname.startsWith("/builder")) return "/builder";
  if (pathname.startsWith("/tournaments")) return "/tournaments";
  if (pathname.startsWith("/play")) return "/play";
  if (pathname.startsWith("/community")) return "/community";
  if (pathname.startsWith("/collector")) return "/collector";
  if (pathname.startsWith("/binder")) return "/binder";
  if (pathname.startsWith("/prices")) return "/prices";
  if (pathname === "/search" || pathname.startsWith("/cards") || pathname.startsWith("/photo")) {
    return "/search";
  }
  return pathname;
}

function IconSearch() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16.2 16.2L20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconDeck() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <rect x="5" y="4" width="11" height="15" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M9 4.5V19.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16 7h3a1.5 1.5 0 0 1 1.5 1.5v11A1.5 1.5 0 0 1 19 21h-8" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function IconTrophy() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        d="M8 4h8v3a4 4 0 0 1-8 0V4z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M8 5H5.5A2.5 2.5 0 0 0 5.5 10H8" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16 5h2.5A2.5 2.5 0 0 1 18.5 10H16" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M10 14h4v2.5l-2 2.5-2-2.5V14z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M8 21h8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function IconCollect() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        d="M12 19.5l-6.2-5.4A4.2 4.2 0 0 1 12 7.4a4.2 4.2 0 0 1 6.2 6.7L12 19.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconBinder() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <rect x="5" y="4" width="14" height="16" rx="1.5" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M9 4v16M15 4v16" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function IconPlay() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path d="M8 6.5v11l9-5.5-9-5.5z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function IconCommunity() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        d="M5 6.5h14a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 19 16.5H12l-4 3v-3H5A1.5 1.5 0 0 1 3.5 15V8A1.5 1.5 0 0 1 5 6.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconPrice() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path d="M5 18V9l4 3 3-5 3 4 4-6v13" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

function IconMore() {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <circle cx="6" cy="12" r="1.6" fill="currentColor" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
      <circle cx="18" cy="12" r="1.6" fill="currentColor" />
    </svg>
  );
}

export function BottomNav() {
  const pathname = usePathname();
  const { t } = useI18n();
  const current = tabRoot(pathname);
  const [moreOpen, setMoreOpen] = useState(false);
  const moreActive = MORE.some((tab) => tab.href === current);

  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  return (
    <>
      {moreOpen ? (
        <button type="button" className="nav-more-backdrop" aria-label={t("nav.more_close")} onClick={() => setMoreOpen(false)} />
      ) : null}
      {moreOpen ? (
        <div className="nav-more-sheet" role="menu">
          {MORE.map((tab) => {
            const Icon = tab.icon;
            const active = current === tab.href;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                role="menuitem"
                className={active ? "active" : undefined}
                onClick={() => {
                  if (tab.href !== current) markTabNavScrollReset();
                  setMoreOpen(false);
                }}
              >
                <Icon />
                <span>{t(tab.key)}</span>
              </Link>
            );
          })}
        </div>
      ) : null}
      <nav className="bottom-nav" aria-label={t("nav.main")}>
        {PRIMARY.map((tab) => {
          const active = current === tab.href;
          const Icon = tab.icon;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              scroll
              className={active ? "active" : undefined}
              onClick={() => {
                if (tab.href !== current) markTabNavScrollReset();
              }}
            >
              <Icon />
              <span>{t(tab.key)}</span>
            </Link>
          );
        })}
        <button
          type="button"
          className={moreOpen || moreActive ? "active" : undefined}
          aria-expanded={moreOpen}
          aria-haspopup="true"
          onClick={() => setMoreOpen((v) => !v)}
        >
          <IconMore />
          <span>{t("nav.more")}</span>
        </button>
      </nav>
    </>
  );
}
