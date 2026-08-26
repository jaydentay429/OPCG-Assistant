"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { loadWatchlist } from "@/lib/priceWatchlist";
import { readTabPref, saveTabPref, type PricesTab } from "@/lib/pricesPrefs";
import { AssetsPanel } from "./prices/AssetsPanel";
import { CalcPanel } from "./prices/CalcPanel";
import { MarketPanel } from "./prices/MarketPanel";
import { WatchlistPanel } from "./prices/WatchlistPanel";

type TabId = PricesTab;

export function PricesPageClient() {
  const { t } = useI18n();
  const { isLoggedIn, ready } = useAuth();
  const [tab, setTab] = useState<TabId | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);

  useEffect(() => {
    setWatchlist(loadWatchlist());
  }, []);

  useEffect(() => {
    if (tab != null) return;
    const saved = readTabPref();
    if (saved) {
      setTab(saved);
      return;
    }
    if (!ready) return;
    setTab(isLoggedIn ? "assets" : "market");
  }, [ready, isLoggedIn, tab]);

  function selectTab(next: TabId) {
    setTab(next);
    saveTabPref(next);
  }

  const active = tab;

  const tabs: { id: TabId; label: string }[] = [
    { id: "assets", label: t("prices.tab_assets") },
    { id: "calc", label: t("prices.tab_calc") },
    { id: "market", label: t("prices.tab_market") },
    { id: "watch", label: t("prices.tab_watch") },
  ];

  return (
    <div className="stack">
      <h1 className="page-title">{t("prices.title")}</h1>
      <p className="muted">{t("prices.subtitle")}</p>

      <div className="prices-tabs" role="tablist">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active === item.id}
            className={`secondary${active === item.id ? " prices-tab-active" : ""}`}
            onClick={() => selectTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {active === "assets" ? <AssetsPanel /> : null}
      {active === "calc" ? <CalcPanel /> : null}
      {active === "market" ? (
        <MarketPanel watchlist={watchlist} onWatchlistChange={setWatchlist} />
      ) : null}
      {active === "watch" ? (
        <WatchlistPanel watchlist={watchlist} onWatchlistChange={setWatchlist} />
      ) : null}
    </div>
  );
}
