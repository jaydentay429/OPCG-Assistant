"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { displayCardId } from "@/lib/cardId";
import { useDeck } from "@/lib/deck";
import { parseDeckListText } from "@/lib/deckShare";
import { useI18n } from "@/lib/i18n";
import { formatYen, loadUnitPrices, sumPricedCopies, unitPriceOf } from "@/lib/priceCalc";
import { readCalcPrefs, saveCalcPrefs } from "@/lib/pricesPrefs";

export function CalcPanel() {
  const { t } = useI18n();
  const draft = useDeck();
  const saved = useMemo(() => readCalcPrefs(), []);
  const [text, setText] = useState(saved.text);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [leader, setLeader] = useState<string | null>(saved.leader);
  const [cards, setCards] = useState<Record<string, number>>(saved.cards);
  const [prices, setPrices] = useState<Record<string, { current_price?: number | null }>>({});
  const [importMsg, setImportMsg] = useState("");

  useEffect(() => {
    saveCalcPrefs({ text, leader, cards });
  }, [text, leader, cards]);

  // Re-quote the restored list so totals show without pressing calculate again.
  useEffect(() => {
    const ids = new Set<string>(Object.keys(saved.cards));
    if (saved.leader) ids.add(saved.leader);
    if (!ids.size) return;
    let cancelled = false;
    setLoading(true);
    loadUnitPrices([...ids])
      .then((map) => {
        if (!cancelled) setPrices(map);
      })
      .catch(() => {
        if (!cancelled) setPrices({});
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [saved]);

  const rows = useMemo(() => {
    const out: { id: string; qty: number; unit: number | null; line: number | null }[] = [];
    for (const [id, rawQty] of Object.entries(cards)) {
      const qty = Math.max(0, Math.floor(Number(rawQty) || 0));
      if (!qty) continue;
      const unit = unitPriceOf(prices, id);
      out.push({ id, qty, unit, line: unit == null ? null : unit * qty });
    }
    out.sort((a, b) => (b.line ?? -1) - (a.line ?? -1));
    return out;
  }, [cards, prices]);

  const sum = useMemo(() => sumPricedCopies(cards, prices), [cards, prices]);
  const leaderUnit = leader ? unitPriceOf(prices, leader) : null;
  const grandTotal = sum.total + (leaderUnit ?? 0);
  const missingIds = useMemo(() => {
    const miss: string[] = [];
    if (leader && unitPriceOf(prices, leader) == null) miss.push(leader);
    for (const row of rows) {
      if (row.unit == null) miss.push(row.id);
    }
    return miss;
  }, [leader, prices, rows]);

  async function runCalc() {
    setError("");
    setImportMsg("");
    const parsed = parseDeckListText(text);
    if (!parsed) {
      setError(t("prices.calc_parse_fail"));
      setLeader(null);
      setCards({});
      setPrices({});
      return;
    }
    setLoading(true);
    try {
      const qtyMap = { ...parsed.cards };
      const ids = new Set<string>(Object.keys(qtyMap));
      if (parsed.leader) ids.add(parsed.leader);
      const map = await loadUnitPrices([...ids]);
      setLeader(parsed.leader);
      setCards(qtyMap);
      setPrices(map);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function importDraft(mode: "merge" | "replace") {
    if (!leader && !Object.keys(cards).length) return;
    if (mode === "replace") {
      draft.importDeck({ name: "", leader, cards });
      setImportMsg(t("prices.calc_imported_replace"));
    } else {
      const { added, skipped } = draft.mergeIntoDeck({ leader, cards });
      setImportMsg(t("prices.calc_imported_merge", { added, skipped }));
    }
  }

  return (
    <div className="stack">
      <div className="deck-panel">
        <h2 className="deck-section-title">{t("prices.calc_title")}</h2>
        <p className="deck-section-sub muted">{t("prices.calc_hint")}</p>
        <textarea
          className="prices-calc-textarea"
          rows={10}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"Leader: OP09-001\nOP01-016 x4\nOP01-025 x4"}
        />
        <div className="prices-toolbar" style={{ marginTop: "0.65rem" }}>
          <button type="button" className="btn-price" disabled={loading || !text.trim()} onClick={() => void runCalc()}>
            {loading ? t("prices.loading") : t("prices.calc_run")}
          </button>
        </div>
        {error ? (
          <p className="error" style={{ color: "#fca5a5", marginTop: "0.5rem" }}>
            {error}
          </p>
        ) : null}
      </div>

      {leader || rows.length ? (
        <div className="deck-panel">
          <p className="prices-calc-total">
            {t("prices.calc_total", { total: formatYen(grandTotal) })}
            {sum.missingCopies || (leader && leaderUnit == null) ? (
              <span className="muted"> · {t("price.missing_note", { missing: missingIds.length })}</span>
            ) : null}
          </p>
          {leader ? (
            <p>
              {t("prices.calc_leader")}: <strong>{displayCardId(leader)}</strong>{" "}
              <span className={leaderUnit == null ? "muted" : "price-tile-yen"}>
                {leaderUnit == null ? t("prices.na") : formatYen(leaderUnit)}
              </span>
            </p>
          ) : null}
          <ul className="prices-asset-list">
            {rows.map((row) => (
              <li key={row.id}>
                <span>
                  {displayCardId(row.id)} ×{row.qty}
                </span>
                <span className={row.unit == null ? "muted" : "price-tile-yen"}>
                  {row.unit == null
                    ? t("prices.na")
                    : `${formatYen(row.unit)} → ${formatYen(row.line)}`}
                </span>
              </li>
            ))}
          </ul>
          {missingIds.length ? (
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              {t("prices.calc_missing")}: {missingIds.map(displayCardId).join(", ")}
            </p>
          ) : null}
          <div className="prices-calc-actions">
            <button type="button" className="btn-add" onClick={() => importDraft("merge")}>
              {t("prices.calc_import_merge")}
            </button>
            <button type="button" className="secondary" onClick={() => importDraft("replace")}>
              {t("prices.calc_import_replace")}
            </button>
            <Link href="/builder" className="secondary" style={{ textDecoration: "none" }}>
              {t("prices.calc_go_builder")}
            </Link>
          </div>
          {importMsg ? <p className="muted">{importMsg}</p> : null}
        </div>
      ) : null}
    </div>
  );
}
