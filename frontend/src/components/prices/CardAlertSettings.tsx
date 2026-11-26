"use client";

import { useEffect, useState } from "react";
import {
  fetchCardAlertSettings,
  saveCardAlertSettings,
  syncCardAlertWatchlist,
  type CardAlertSettings as Settings,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

/**
 * Opt-in email alerts for logged-in users. Renders nothing when logged out or when
 * the server has CARD_ALERTS_ENABLED off, so the feature ships dark.
 */
export function CardAlertSettings({ watchlist }: { watchlist: string[] }) {
  const { t, lang } = useI18n();
  const { token, isLoggedIn } = useAuth();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isLoggedIn || !token) {
      setSettings(null);
      return;
    }
    let alive = true;
    fetchCardAlertSettings(token)
      .then((s) => {
        if (alive) setSettings(s);
      })
      .catch(() => {
        if (alive) setSettings(null);
      });
    return () => {
      alive = false;
    };
  }, [isLoggedIn, token]);

  const priceWatchOn = Boolean(settings?.feature_enabled && settings.price_watch);
  const watchKey = watchlist.join(",");

  // Server needs the watchlist (it lives in localStorage) to know what to watch.
  useEffect(() => {
    if (!priceWatchOn || !token) return;
    const timer = window.setTimeout(() => {
      syncCardAlertWatchlist(token, watchKey ? watchKey.split(",") : []).catch(() => undefined);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [priceWatchOn, token, watchKey]);

  if (!settings || !settings.feature_enabled || !token) return null;

  async function update(next: { new_cards: boolean; price_watch: boolean }) {
    if (!token) return;
    setBusy(true);
    setStatus("");
    try {
      setSettings(await saveCardAlertSettings(token, { ...next, lang }));
      setStatus(t("alerts.saved"));
    } catch {
      setStatus(t("alerts.save_failed"));
    } finally {
      setBusy(false);
    }
  }

  const locked = busy || !settings.email_verified;
  return (
    <div className="deck-panel card-alerts">
      <h3 className="deck-section-title">{t("alerts.title")}</h3>
      {!settings.email_verified ? <p className="muted">{t("alerts.verify_first")}</p> : null}
      <label className="card-alerts-row">
        <input
          type="checkbox"
          checked={settings.new_cards}
          disabled={locked}
          onChange={(e) => void update({ new_cards: e.target.checked, price_watch: settings.price_watch })}
        />
        <span>{t("alerts.new_cards")}</span>
      </label>
      <label className="card-alerts-row">
        <input
          type="checkbox"
          checked={settings.price_watch}
          disabled={locked}
          onChange={(e) => void update({ new_cards: settings.new_cards, price_watch: e.target.checked })}
        />
        <span>{t("alerts.price_watch", { pct: settings.threshold_pct })}</span>
      </label>
      {status ? (
        <p className="muted" role="status">
          {status}
        </p>
      ) : null}
    </div>
  );
}
