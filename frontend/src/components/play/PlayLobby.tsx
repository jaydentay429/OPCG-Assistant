"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchDeckStatsBatch, type AiBattleDeck, type BattleInlineDeck } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { isLeaderType } from "@/lib/deck";
import { displayCardId } from "@/lib/cardId";
import { parseDeckListText } from "@/lib/deckShare";
import { useI18n } from "@/lib/i18n";
import type { Deck } from "@/lib/types";
import { SpectatorPrefsToggles, useSpectatorPrefs } from "@/components/play/SpectatorPrefsToggles";
import { DeckImportBlock } from "@/components/play/DeckImportBlock";
import { RankEliteTier, eliteTitleClass } from "@/components/play/RankEliteBadge";

type Mode = "pick" | "match" | "ranked" | "room" | "ai" | "self";

export type PlayDeckPick =
  | { kind: "saved"; deckId: string }
  | { kind: "inline"; deck: BattleInlineDeck };

type Props = {
  decks: Deck[];
  aiDecks: AiBattleDeck[];
  busy: boolean;
  error: string | null;
  onCreateRoom: () => void;
  onJoinRoom: (code: string) => void;
  onFindMatch: (pick: PlayDeckPick) => void;
  onFindRanked?: (pick: PlayDeckPick) => void;
  rankProfile?: {
    rating: number;
    tier_label_zh: string;
    elite_title?: string | null;
    elite_title_zh?: string | null;
    wins: number;
    losses: number;
    elite_pending?: boolean;
  } | null;
  onStartAi: (pick: PlayDeckPick, aiDeckId: string) => void;
  onStartSelf: (pick: PlayDeckPick, opp: PlayDeckPick) => void;
};

const IMPORT_ID = "__imported__";
const IMPORT_OPP_ID = "__imported_opp__";

async function resolveImportedDeck(raw: string): Promise<BattleInlineDeck | null> {
  const initial = parseDeckListText(raw);
  if (!initial) return null;
  let leader = initial.leader;
  let cards = { ...initial.cards };
  if (!leader) {
    const ids = Object.keys(cards);
    if (!ids.length) return null;
    let stats: Record<string, { card_type?: string | null }> = {};
    try {
      stats = await fetchDeckStatsBatch(ids);
    } catch {
      return null;
    }
    const leaderId = ids.find((id) => isLeaderType(stats[id]?.card_type));
    if (!leaderId) return null;
    leader = leaderId;
    delete cards[leaderId];
  }
  const nonLeader = Object.values(cards).reduce((a, b) => a + Number(b || 0), 0);
  if (!leader || nonLeader !== 50) return null;
  return {
    leader_card_id: leader,
    cards,
    name: initial.name || "Imported",
  };
}

function PlaySetupCard({ children }: { children: ReactNode }) {
  return <div className="play-setup-card">{children}</div>;
}

function PlaySetupBlock({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="play-setup-block">
      {title ? <p className="play-setup-block-title">{title}</p> : null}
      {children}
    </div>
  );
}

export function PlayLobby({
  decks,
  aiDecks,
  busy,
  error,
  onCreateRoom,
  onJoinRoom,
  onFindMatch,
  onFindRanked,
  rankProfile,
  onStartAi,
  onStartSelf,
}: Props) {
  const { t } = useI18n();
  const { isLoggedIn, requestLogin } = useAuth();
  const { prefs, setPrefs } = useSpectatorPrefs();
  const ready = useMemo(() => decks.filter((d) => d.is_valid_ready && d.leader_card_id), [decks]);
  const [mode, setMode] = useState<Mode>("pick");
  const [roomSub, setRoomSub] = useState<"menu" | "join">("menu");
  const [deckId, setDeckId] = useState(ready[0]?.id || "");
  const [aiDeckId, setAiDeckId] = useState(aiDecks[0]?.id || "");
  const [oppDeckId, setOppDeckId] = useState(ready[1]?.id || ready[0]?.id || "");
  const [code, setCode] = useState("");
  const [importText, setImportText] = useState("");
  const [importOppText, setImportOppText] = useState("");
  const [imported, setImported] = useState<BattleInlineDeck | null>(null);
  const [importedOpp, setImportedOpp] = useState<BattleInlineDeck | null>(null);
  const [importing, setImporting] = useState(false);
  const [importingOpp, setImportingOpp] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);

  const selected = deckId || (imported ? IMPORT_ID : ready[0]?.id || "");
  const selectedAi = aiDeckId || aiDecks[0]?.id || "";
  const selectedOpp = oppDeckId || (importedOpp ? IMPORT_OPP_ID : ready[1]?.id || ready[0]?.id || "");

  useEffect(() => {
    if (!deckId && ready[0]?.id && !imported) setDeckId(ready[0].id);
  }, [ready, deckId, imported]);

  useEffect(() => {
    if (!aiDeckId && aiDecks[0]?.id) setAiDeckId(aiDecks[0].id);
  }, [aiDecks, aiDeckId]);

  useEffect(() => {
    if (!oppDeckId && ready.length && !importedOpp) {
      setOppDeckId(ready[1]?.id || ready[0]?.id || "");
    }
  }, [ready, oppDeckId, importedOpp]);

  async function applyImport(which: "p1" | "p2") {
    setImportError(null);
    const raw = which === "p1" ? importText : importOppText;
    if (which === "p1") setImporting(true);
    else setImportingOpp(true);
    try {
      const deck = await resolveImportedDeck(raw);
      if (!deck) {
        setImportError(t("play.import_invalid"));
        return;
      }
      const label = `${deck.name || t("play.imported_deck")} · ${displayCardId(deck.leader_card_id)} · 50/50`;
      if (which === "p1") {
        setImported(deck);
        setDeckId(IMPORT_ID);
      } else {
        setImportedOpp(deck);
        setOppDeckId(IMPORT_OPP_ID);
      }
      setImportError(null);
      void label;
    } finally {
      if (which === "p1") setImporting(false);
      else setImportingOpp(false);
    }
  }

  function pickFromSelect(id: string, which: "p1" | "p2"): PlayDeckPick | null {
    if (which === "p1") {
      if (id === IMPORT_ID) return imported ? { kind: "inline", deck: imported } : null;
      return id ? { kind: "saved", deckId: id } : null;
    }
    if (id === IMPORT_OPP_ID) return importedOpp ? { kind: "inline", deck: importedOpp } : null;
    return id ? { kind: "saved", deckId: id } : null;
  }

  const canStartMatch = Boolean(pickFromSelect(selected, "p1"));
  const canStartAi = Boolean(pickFromSelect(selected, "p1") && selectedAi);
  const canStartSelf = Boolean(pickFromSelect(selected, "p1") && pickFromSelect(selectedOpp, "p2"));
  const hasAnyDeckSource = ready.length > 0 || Boolean(imported);

  const heading =
    mode === "match"
      ? { title: t("play.mode_match"), sub: t("play.mode_match_hint") }
      : mode === "ranked"
        ? { title: t("play.mode_ranked"), sub: t("play.mode_ranked_hint") }
        : mode === "room"
        ? { title: t("play.mode_room"), sub: t("play.mode_room_hint") }
        : mode === "ai"
          ? { title: t("play.mode_ai"), sub: t("play.mode_ai_hint") }
          : mode === "self"
            ? { title: t("play.mode_self"), sub: t("play.mode_self_hint") }
            : { title: t("play.title"), sub: t("play.subtitle") };

  return (
    <section className="play-lobby">
      <div className="play-lobby-head">
        <div className="play-lobby-titles">
          <h1 className="page-title">{heading.title}</h1>
          <p className="muted play-lobby-sub">{heading.sub}</p>
        </div>
      </div>
      {isLoggedIn && mode === "pick" ? (
        <div className="play-lobby-quick-links">
          <Link href="/play/rank" className="play-history-link-btn">
            {t("play.rank_open")}
          </Link>
          <Link href="/play/history" className="play-history-link-btn">
            {t("play.history_open")}
          </Link>
        </div>
      ) : null}
      {error ? <p className="error-text">{error}</p> : null}
      {importError ? <p className="error-text">{importError}</p> : null}

      {mode === "pick" ? (
        <div className="play-mode-grid">
          <button type="button" className="play-mode-card is-featured" disabled={busy} onClick={() => setMode("match")}>
            <span className="play-mode-kicker">{t("play.mode_featured")}</span>
            <strong>{t("play.mode_match")}</strong>
            <span className="muted">{t("play.mode_match_hint")}</span>
          </button>
          <button
            type="button"
            className="play-mode-card is-featured is-ranked"
            disabled={busy}
            onClick={() => {
              if (!isLoggedIn) {
                requestLogin();
                return;
              }
              setMode("ranked");
            }}
          >
            <span className="play-mode-kicker">{t("play.rank_badge")}</span>
            <strong>{t("play.mode_ranked")}</strong>
            <span className="muted">
              {isLoggedIn ? t("play.mode_ranked_hint") : t("play.rank_need_login_hint")}
            </span>
          </button>
          <button type="button" className="play-mode-card" disabled={busy} onClick={() => setMode("room")}>
            <strong>{t("play.mode_room")}</strong>
            <span className="muted">{t("play.mode_room_hint")}</span>
          </button>
          <button type="button" className="play-mode-card" disabled={busy} onClick={() => setMode("ai")}>
            <strong>{t("play.mode_ai")}</strong>
            <span className="muted">{t("play.mode_ai_hint")}</span>
          </button>
          <button type="button" className="play-mode-card" disabled={busy} onClick={() => setMode("self")}>
            <strong>{t("play.mode_self")}</strong>
            <span className="muted">{t("play.mode_self_hint")}</span>
          </button>
          <Link href="/play/spectate" className="play-mode-card play-mode-card-link is-quiet">
            <strong>{t("play.mode_spectate")}</strong>
            <span className="muted">{t("play.mode_spectate_hint")}</span>
          </Link>
        </div>
      ) : null}

      {mode === "ranked" ? (
        <div className="play-panel">
          <button type="button" className="ghost play-back" disabled={busy} onClick={() => setMode("pick")}>
            {t("play.back")}
          </button>
          {!isLoggedIn ? (
            <p className="muted">{t("play.rank_need_login")}</p>
          ) : !hasAnyDeckSource ? (
            <p className="muted">{t("play.need_deck_or_import")}</p>
          ) : (
            <>
              {rankProfile ? (
                <p className={`play-rank-summary${rankProfile.elite_title ? ` ${eliteTitleClass(rankProfile.elite_title) || ""}` : ""}`}>
                  <RankEliteTier label={rankProfile.tier_label_zh} eliteTitle={rankProfile.elite_title} />
                  <span> · {rankProfile.rating} · {rankProfile.wins}W-{rankProfile.losses}L</span>
                  {rankProfile.elite_pending ? (
                    <span className="muted"> · {t("play.rank_elite_pending")}</span>
                  ) : null}
                </p>
              ) : null}
              <PlaySetupCard>
                <PlaySetupBlock>
                  {ready.length ? (
                    <label className="play-field">
                      <span>{t("play.choose_deck")}</span>
                      <select value={selected} onChange={(e) => setDeckId(e.target.value)} disabled={busy}>
                        {ready.map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                          </option>
                        ))}
                        {imported ? (
                          <option value={IMPORT_ID}>
                            {imported.name || t("play.imported_deck")} · {displayCardId(imported.leader_card_id)} · 50/50
                          </option>
                        ) : null}
                      </select>
                    </label>
                  ) : imported ? (
                    <p className="muted">
                      {t("play.imported_deck")}: {imported.name || displayCardId(imported.leader_card_id)} · 50/50
                    </p>
                  ) : null}
                  <DeckImportBlock
                    label={t("play.import_deck")}
                    value={importText}
                    onChange={setImportText}
                    onApply={() => void applyImport("p1")}
                    busy={busy}
                    importing={importing}
                    appliedLabel={
                      imported ? `${t("play.imported_ok")} · ${displayCardId(imported.leader_card_id)} · 50/50` : null
                    }
                  />
                </PlaySetupBlock>
                <PlaySetupBlock title={t("play.spectator_section")}>
                  <SpectatorPrefsToggles prefs={prefs} onChange={setPrefs} disabled={busy} />
                </PlaySetupBlock>
              </PlaySetupCard>
              <div className="play-actions play-actions-primary">
                <button
                  type="button"
                  className="success"
                  disabled={busy || !canStartMatch || !onFindRanked}
                  onClick={() => {
                    const pick = pickFromSelect(selected, "p1");
                    if (pick && onFindRanked) onFindRanked(pick);
                  }}
                >
                  {t("play.find_ranked")}
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}

      {mode === "match" ? (
        <div className="play-panel">
          <button type="button" className="ghost play-back" disabled={busy} onClick={() => setMode("pick")}>
            {t("play.back")}
          </button>
          {!hasAnyDeckSource ? (
            <p className="muted">{t("play.need_deck_or_import")}</p>
          ) : null}
          <>
            <PlaySetupCard>
              <PlaySetupBlock>
                {ready.length ? (
                  <label className="play-field">
                    <span>{t("play.choose_deck")}</span>
                    <select value={selected} onChange={(e) => setDeckId(e.target.value)} disabled={busy}>
                      {ready.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                        </option>
                      ))}
                      {imported ? (
                        <option value={IMPORT_ID}>
                          {imported.name || t("play.imported_deck")} · {displayCardId(imported.leader_card_id)} · 50/50
                        </option>
                      ) : null}
                    </select>
                  </label>
                ) : imported ? (
                  <p className="muted">
                    {t("play.imported_deck")}: {imported.name || displayCardId(imported.leader_card_id)} · 50/50
                  </p>
                ) : null}
                <DeckImportBlock
                  label={t("play.import_deck")}
                  value={importText}
                  onChange={setImportText}
                  onApply={() => void applyImport("p1")}
                  busy={busy}
                  importing={importing}
                  appliedLabel={
                    imported ? `${t("play.imported_ok")} · ${displayCardId(imported.leader_card_id)} · 50/50` : null
                  }
                />
              </PlaySetupBlock>
              <PlaySetupBlock title={t("play.spectator_section")}>
                <SpectatorPrefsToggles prefs={prefs} onChange={setPrefs} disabled={busy} />
              </PlaySetupBlock>
            </PlaySetupCard>
            <div className="play-actions play-actions-primary">
              <button
                type="button"
                className="success"
                disabled={busy || !canStartMatch}
                onClick={() => {
                  const pick = pickFromSelect(selected, "p1");
                  if (pick) onFindMatch(pick);
                }}
              >
                {t("play.find_match")}
              </button>
            </div>
          </>
        </div>
      ) : null}

      {mode === "room" ? (
        <div className="play-panel">
          <button type="button" className="ghost play-back" disabled={busy} onClick={() => { setMode("pick"); setRoomSub("menu"); }}>
            {t("play.back")}
          </button>
          {roomSub === "menu" ? (
            <PlaySetupCard>
              <PlaySetupBlock title={t("play.spectator_section")}>
                <SpectatorPrefsToggles prefs={prefs} onChange={setPrefs} disabled={busy} />
              </PlaySetupBlock>
              <div className="play-actions play-actions-stack">
                <button type="button" disabled={busy} onClick={onCreateRoom}>
                  {t("play.create_room")}
                </button>
                <button type="button" className="secondary" disabled={busy} onClick={() => setRoomSub("join")}>
                  {t("play.enter_code")}
                </button>
              </div>
            </PlaySetupCard>
          ) : (
            <>
              <label className="play-field">
                <span>{t("play.join_code")}</span>
                <input
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="ABC123"
                  maxLength={8}
                  disabled={busy}
                />
              </label>
              <div className="play-actions">
                <button type="button" className="ghost" disabled={busy} onClick={() => setRoomSub("menu")}>
                  {t("play.back")}
                </button>
                <button
                  type="button"
                  disabled={busy || code.trim().length < 4}
                  onClick={() => onJoinRoom(code.trim())}
                >
                  {t("play.join_room")}
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}

      {mode === "ai" ? (
        <div className="play-panel">
          <button type="button" className="ghost play-back" disabled={busy} onClick={() => setMode("pick")}>
            {t("play.back")}
          </button>
          {!hasAnyDeckSource ? (
            <p className="muted">{t("play.need_deck_or_import")}</p>
          ) : null}
          <>
            <PlaySetupCard>
              <PlaySetupBlock>
                {ready.length ? (
                  <label className="play-field">
                    <span>{t("play.choose_deck")}</span>
                    <select
                      value={selected}
                      onChange={(e) => {
                        setDeckId(e.target.value);
                        if (e.target.value !== IMPORT_ID) {
                          /* keep imported as option */
                        }
                      }}
                      disabled={busy}
                    >
                      {ready.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                        </option>
                      ))}
                      {imported ? (
                        <option value={IMPORT_ID}>
                          {imported.name || t("play.imported_deck")} · {displayCardId(imported.leader_card_id)} · 50/50
                        </option>
                      ) : null}
                    </select>
                  </label>
                ) : imported ? (
                  <p className="muted">
                    {t("play.imported_deck")}: {imported.name || displayCardId(imported.leader_card_id)} · 50/50
                  </p>
                ) : null}
                <DeckImportBlock
                  label={t("play.import_deck")}
                  value={importText}
                  onChange={setImportText}
                  onApply={() => void applyImport("p1")}
                  busy={busy}
                  importing={importing}
                  appliedLabel={
                    imported
                      ? `${t("play.imported_ok")} · ${displayCardId(imported.leader_card_id)} · 50/50`
                      : null
                  }
                />
                <label className="play-field">
                  <span>{t("play.choose_ai_deck")}</span>
                  <select
                    value={selectedAi}
                    onChange={(e) => setAiDeckId(e.target.value)}
                    disabled={busy || !aiDecks.length}
                  >
                    {!aiDecks.length ? (
                      <option value="">{t("play.ai_deck_empty")}</option>
                    ) : (
                      aiDecks.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                        </option>
                      ))
                    )}
                  </select>
                </label>
              </PlaySetupBlock>
              <PlaySetupBlock title={t("play.spectator_section")}>
                <SpectatorPrefsToggles prefs={prefs} onChange={setPrefs} disabled={busy} />
              </PlaySetupBlock>
            </PlaySetupCard>
            <div className="play-actions play-actions-primary">
              <button
                type="button"
                className="success"
                disabled={busy || !canStartAi}
                onClick={() => {
                  const pick = pickFromSelect(selected, "p1");
                  if (pick && selectedAi) onStartAi(pick, selectedAi);
                }}
              >
                {t("play.start_ai")}
              </button>
            </div>
          </>
        </div>
      ) : null}

      {mode === "self" ? (
        <div className="play-panel">
          <button type="button" className="ghost play-back" disabled={busy} onClick={() => setMode("pick")}>
            {t("play.back")}
          </button>
          {!hasAnyDeckSource && !importedOpp ? (
            <p className="muted">{t("play.need_deck_or_import")}</p>
          ) : null}
          <>
            <PlaySetupCard>
              <PlaySetupBlock>
                {ready.length ? (
                  <label className="play-field">
                    <span>{t("play.choose_deck_p1")}</span>
                    <select value={selected} onChange={(e) => setDeckId(e.target.value)} disabled={busy}>
                      {ready.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                        </option>
                      ))}
                      {imported ? (
                        <option value={IMPORT_ID}>
                          {imported.name || t("play.imported_deck")} · {displayCardId(imported.leader_card_id)} · 50/50
                        </option>
                      ) : null}
                    </select>
                  </label>
                ) : imported ? (
                  <p className="muted">
                    {t("play.choose_deck_p1")}: {imported.name || displayCardId(imported.leader_card_id)} · 50/50
                  </p>
                ) : null}
                <DeckImportBlock
                  label={t("play.import_deck_p1")}
                  value={importText}
                  onChange={setImportText}
                  onApply={() => void applyImport("p1")}
                  busy={busy}
                  importing={importing}
                  appliedLabel={
                    imported ? `${t("play.imported_ok")} · ${displayCardId(imported.leader_card_id)} · 50/50` : null
                  }
                />
              </PlaySetupBlock>
              <PlaySetupBlock>
                {ready.length ? (
                  <label className="play-field">
                    <span>{t("play.choose_deck_p2")}</span>
                    <select value={selectedOpp} onChange={(e) => setOppDeckId(e.target.value)} disabled={busy}>
                      {ready.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                        </option>
                      ))}
                      {importedOpp ? (
                        <option value={IMPORT_OPP_ID}>
                          {importedOpp.name || t("play.imported_deck")} · {displayCardId(importedOpp.leader_card_id)} · 50/50
                        </option>
                      ) : null}
                    </select>
                  </label>
                ) : importedOpp ? (
                  <p className="muted">
                    {t("play.choose_deck_p2")}: {importedOpp.name || displayCardId(importedOpp.leader_card_id)} · 50/50
                  </p>
                ) : null}
                <DeckImportBlock
                  label={t("play.import_deck_p2")}
                  value={importOppText}
                  onChange={setImportOppText}
                  onApply={() => void applyImport("p2")}
                  busy={busy}
                  importing={importingOpp}
                  appliedLabel={
                    importedOpp ? `${t("play.imported_ok")} · ${displayCardId(importedOpp.leader_card_id)} · 50/50` : null
                  }
                />
              </PlaySetupBlock>
              <p className="muted play-setup-note">{t("play.mode_self_note")}</p>
              <PlaySetupBlock title={t("play.spectator_section")}>
                <SpectatorPrefsToggles prefs={prefs} onChange={setPrefs} disabled={busy} />
              </PlaySetupBlock>
            </PlaySetupCard>
            <div className="play-actions play-actions-primary">
              <button
                type="button"
                className="success"
                disabled={busy || !canStartSelf}
                onClick={() => {
                  const a = pickFromSelect(selected, "p1");
                  const b = pickFromSelect(selectedOpp, "p2");
                  if (a && b) onStartSelf(a, b);
                }}
              >
                {t("play.start_self")}
              </button>
            </div>
          </>
        </div>
      ) : null}
    </section>
  );
}
