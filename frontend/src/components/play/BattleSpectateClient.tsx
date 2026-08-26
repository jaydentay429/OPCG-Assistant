"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BattleBoard } from "@/components/play/BattleBoard";
import {
  fetchBattleGuestToken,
  fetchBattleRoom,
  fetchDeckStatsBatch,
  fetchLiveSpectatableRooms,
  prefetchCardImages,
  type BattleLiveRoomSummary,
  type DeckStatFields,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { collectCardIdsFromLogs } from "@/lib/battleLogCards";
import { connectBattleWs, type BattleChatMessage, type BattleState } from "@/lib/battleWs";
import { useI18n } from "@/lib/i18n";

const GUEST_TOKEN_KEY = "opcg_battle_guest_token";

type ModeFilter = "all" | "ai" | "pvp" | "hotseat";

export function BattleSpectateClient() {
  const { t } = useI18n();
  const router = useRouter();
  const { token, ready } = useAuth();
  const [guestToken, setGuestToken] = useState<string | null>(null);
  const [filter, setFilter] = useState<ModeFilter>("all");
  const [rooms, setRooms] = useState<BattleLiveRoomSummary[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<BattleState | null>(null);
  const [names, setNames] = useState<Record<string, DeckStatFields>>({});
  const [activeCode, setActiveCode] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<BattleChatMessage[]>([]);
  const wsRef = useRef<ReturnType<typeof connectBattleWs> | null>(null);

  const battleToken = token || guestToken;

  useEffect(() => {
    if (!ready) return;
    if (token) return;
    if (guestToken) return;
    fetchBattleGuestToken()
      .then((g) => {
        setGuestToken(g.guest_token);
        try {
          sessionStorage.setItem(GUEST_TOKEN_KEY, g.guest_token);
        } catch {
          /* ignore */
        }
      })
      .catch(() => undefined);
  }, [ready, token, guestToken]);

  useEffect(() => {
    document.body.classList.toggle("battle-active", Boolean(state));
    return () => document.body.classList.remove("battle-active");
  }, [state]);

  const loadList = useCallback(async () => {
    setListLoading(true);
    try {
      const list = await fetchLiveSpectatableRooms(filter);
      setRooms(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setListLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (!ready) return;
    void loadList();
    const timer = window.setInterval(() => void loadList(), 5000);
    return () => window.clearInterval(timer);
  }, [ready, loadList]);

  useEffect(() => {
    if (!state) return;
    const ids = new Set<string>();
    for (const p of state.players) {
      if (p.leader_card_id) ids.add(p.leader_card_id);
      for (const ch of p.characters) ids.add(ch.card_id);
      for (const st of p.stages) ids.add(st.card_id);
      for (const cid of p.hand || []) ids.add(cid);
    }
    prefetchCardImages(ids);
    for (const cid of collectCardIdsFromLogs(state.log)) ids.add(cid);
    const missing = [...ids].filter((id) => !names[id]);
    if (!missing.length) return;
    fetchDeckStatsBatch(missing)
      .then((res) => setNames((prev) => ({ ...prev, ...res })))
      .catch(() => undefined);
  }, [state, names]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setActiveCode(null);
    setState(null);
    setChatMessages([]);
  }, []);

  const connectSpectate = useCallback(
    (roomCode: string, authToken: string) => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setActiveCode(roomCode);
      setError(null);
      setChatMessages([]);
      const sock = connectBattleWs({
        token: authToken,
        room: roomCode,
        role: "spectator",
        onState: (next) => {
          setState({ ...next, viewer_role: "spectator" });
          setError(null);
        },
        onWaiting: () => {
          setError(t("play.spectate_not_live"));
          sock.close();
          setActiveCode(null);
          setState(null);
        },
        onError: (message) => setError(message),
        onClose: () => {
          if (wsRef.current === sock) wsRef.current = null;
          setActiveCode(null);
          setState(null);
          setChatMessages([]);
        },
        onChat: (messages) => setChatMessages(messages),
      });
      wsRef.current = sock;
      return sock;
    },
    [t],
  );

  useEffect(() => () => disconnect(), [disconnect]);

  async function enterByCode(roomCode: string) {
    const trimmed = roomCode.trim().toUpperCase();
    if (!trimmed) return;
    if (!battleToken) {
      setError(t("play.spectate_need_auth"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const info = await fetchBattleRoom(trimmed);
      if (!info.can_spectate) {
        setError(t("play.spectate_denied"));
        return;
      }
      connectSpectate(trimmed, battleToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const modeLabel = useMemo(
    () => ({
      ai: t("play.spectate_filter_ai"),
      pvp: t("play.spectate_filter_pvp"),
      hotseat: t("play.spectate_filter_hotseat"),
    }),
    [t],
  );

  if (state && activeCode) {
    return (
      <BattleBoard
        state={state}
        names={names}
        onAction={() => undefined}
        onLeave={() => {
          disconnect();
          router.push("/play/spectate");
        }}
        spectatorMode
        replayMode={Boolean(state.spectator_show_hands || state.replay_mode)}
        chatMessages={chatMessages}
      />
    );
  }

  return (
    <section className="play-lobby play-spectate-lobby">
      <div className="play-lobby-head">
        <h1 className="page-title">{t("play.spectate_title")}</h1>
        <Link href="/play" className="play-back-link-btn">{t("play.back")}</Link>
      </div>
      <p className="muted">{t("play.spectate_subtitle")}</p>
      {error ? <p className="error-text">{error}</p> : null}

      <div className="play-panel">
        <label className="play-field">
          <span>{t("play.spectate_code")}</span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABC123"
            maxLength={8}
            disabled={busy}
          />
        </label>
        <div className="play-actions">
          <button type="button" disabled={busy || code.trim().length < 4} onClick={() => void enterByCode(code)}>
            {t("play.spectate_enter")}
          </button>
        </div>
      </div>

      <div className="play-panel">
        <div className="play-spectate-filters">
          {(["all", "ai", "pvp", "hotseat"] as ModeFilter[]).map((m) => (
            <button
              key={m}
              type="button"
              className={filter === m ? "secondary" : "ghost"}
              onClick={() => setFilter(m)}
            >
              {m === "all" ? t("play.spectate_filter_all") : modeLabel[m]}
            </button>
          ))}
        </div>
        {listLoading ? <p className="muted">{t("play.spectate_loading")}</p> : null}
        {!listLoading && rooms.length === 0 ? <p className="muted">{t("play.spectate_empty")}</p> : null}
        <ul className="play-spectate-list">
          {rooms.map((room) => {
            const p0 = room.players[0];
            const p1 = room.players[1];
            const label = `${p0?.username || "?"} vs ${p1?.username || "?"}`;
            return (
              <li key={room.room_code} className="play-spectate-item">
                <button
                  type="button"
                  className="play-spectate-link"
                  disabled={busy}
                  onClick={() => void enterByCode(room.room_code)}
                >
                  <span className="play-spectate-mode">{modeLabel[room.mode]}</span>
                  <span className="play-spectate-names">{label}</span>
                  <span className="play-spectate-meta">
                    {t("play.spectate_turn", { n: room.turn_number })}
                    {room.show_hands ? ` · ${t("play.spectate_hands_open")}` : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
