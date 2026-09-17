"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createBattleRoom,
  fetchAiBattleDecks,
  fetchBattleMatchmakingStatus,
  fetchBattleRankAppealStatus,
  fetchBattleRankMe,
  fetchBattleRankedStatus,
  fetchBattleRoom,
  fetchDeckStatsBatch,
  fetchDecks,
  joinBattleMatchmaking,
  joinBattleRanked,
  joinBattleRoom,
  leaveBattleMatchmaking,
  leaveBattleRanked,
  prefetchCardImages,
  setBattleRoomDeck,
  setBattleRoomReady,
  submitBattleRankAppeal,
  submitBattleBugReport,
  ApiError,
  type AiBattleDeck,
  type BattleInlineDeck,
  type BattleRankProfile,
  type BattleRankAppealStatus,
  type DeckStatFields,
} from "@/lib/api";
import { readBattleSpectatorPrefs } from "@/lib/battleSpectatorPrefs";
import { collectCardIdsFromLogs } from "@/lib/battleLogCards";
import { useAuth } from "@/lib/auth";
import { displayCardId } from "@/lib/cardId";
import { isLeaderType } from "@/lib/deck";
import { parseDeckListText } from "@/lib/deckShare";
import { connectBattleWs, type BattleAction, type BattleChatMessage, type BattleState, type WaitingRoom } from "@/lib/battleWs";
import { useI18n } from "@/lib/i18n";
import type { Deck } from "@/lib/types";
import { BattleBoard } from "./BattleBoard";
import { DeckImportBlock } from "./DeckImportBlock";
import { PlayLobby, type PlayDeckPick } from "./PlayLobby";

const ROOM_KEY = "opcg_battle_room";
const GUEST_TOKEN_KEY = "opcg_battle_guest_token";
const GUEST_USER_KEY = "opcg_battle_guest_user";
const BETA_NOTICE_KEY = "opcg_battle_beta_notice_v2";

type RematchAi = { pick: PlayDeckPick; aiDeckId: string };
type RematchSelf = { pick: PlayDeckPick; opp: PlayDeckPick };
type RematchMatch = { pick: PlayDeckPick; ranked?: boolean };

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

function pickToCreateOpts(pick: PlayDeckPick): { deckId?: string; deck?: BattleInlineDeck } {
  return pick.kind === "saved" ? { deckId: pick.deckId } : { deck: pick.deck };
}

export function PlayPageClient() {
  const { t } = useI18n();
  const router = useRouter();
  const { token, username, isLoggedIn, ready } = useAuth();
  const [guestToken, setGuestToken] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return sessionStorage.getItem(GUEST_TOKEN_KEY);
    } catch {
      return null;
    }
  });
  const [guestUserId, setGuestUserId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const raw = sessionStorage.getItem(GUEST_USER_KEY);
      if (!raw) return null;
      return (JSON.parse(raw) as { id?: string }).id || null;
    } catch {
      return null;
    }
  });
  const [guestUsername, setGuestUsername] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const raw = sessionStorage.getItem(GUEST_USER_KEY);
      if (!raw) return null;
      return (JSON.parse(raw) as { name?: string }).name || null;
    } catch {
      return null;
    }
  });
  const [decks, setDecks] = useState<Deck[]>([]);
  const [aiDecks, setAiDecks] = useState<AiBattleDeck[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actionBusyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [roomCode, setRoomCode] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<WaitingRoom | null>(null);
  const [state, setState] = useState<BattleState | null>(null);
  const [names, setNames] = useState<Record<string, DeckStatFields>>({});
  const [lobbyDeckId, setLobbyDeckId] = useState("");
  const [lobbyInline, setLobbyInline] = useState<BattleInlineDeck | null>(null);
  const [lobbyImportText, setLobbyImportText] = useState("");
  const [lobbyImporting, setLobbyImporting] = useState(false);
  const [roomMeta, setRoomMeta] = useState<{ vs_ai: boolean; hotseat?: boolean; ranked?: boolean; status: string } | null>(null);
  const [matching, setMatching] = useState(false);
  const [rankedMatching, setRankedMatching] = useState(false);
  const [matchWaitSec, setMatchWaitSec] = useState(0);
  const [matchWindow, setMatchWindow] = useState<number | null>(null);
  const [rankProfile, setRankProfile] = useState<BattleRankProfile | null>(null);
  const [rankAppealStatus, setRankAppealStatus] = useState<BattleRankAppealStatus["status"]>("none");
  const [showBetaNotice, setShowBetaNotice] = useState(false);
  const [chatMessages, setChatMessages] = useState<BattleChatMessage[]>([]);
  const lastAiRef = useRef<RematchAi | null>(null);
  const lastSelfRef = useRef<RematchSelf | null>(null);
  const lastMatchRef = useRef<RematchMatch | null>(null);
  const socketRef = useRef<ReturnType<typeof connectBattleWs> | null>(null);
  const roomMetaRef = useRef(roomMeta);
  roomMetaRef.current = roomMeta;

  const battleToken = token || guestToken;
  const displayName = username || guestUsername || (guestToken ? t("auth.guest") : null);

  const validDecks = useMemo(() => decks.filter((d) => d.is_valid_ready && d.leader_card_id), [decks]);

  useEffect(() => {
    document.body.classList.toggle("play-active", Boolean(roomCode || matching || rankedMatching));
    document.body.classList.toggle("battle-active", Boolean(state));
    return () => {
      document.body.classList.remove("play-active");
      document.body.classList.remove("battle-active");
    };
  }, [roomCode, matching, rankedMatching, state]);

  useEffect(() => {
    if (!lobbyDeckId && validDecks[0]?.id) setLobbyDeckId(validDecks[0].id);
  }, [validDecks, lobbyDeckId]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!sessionStorage.getItem(BETA_NOTICE_KEY)) setShowBetaNotice(true);
    const savedGuest = sessionStorage.getItem(GUEST_TOKEN_KEY);
    if (savedGuest) setGuestToken(savedGuest);
    try {
      const raw = sessionStorage.getItem(GUEST_USER_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { id?: string; name?: string };
        if (parsed.id) setGuestUserId(parsed.id);
        if (parsed.name) setGuestUsername(parsed.name);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const rememberGuestToken = useCallback((info: {
    guest_token?: string | null;
    guest_user_id?: string | null;
    guest_username?: string | null;
  } | null | undefined) => {
    if (!info) return;
    if (info.guest_token) {
      setGuestToken(info.guest_token);
      try {
        sessionStorage.setItem(GUEST_TOKEN_KEY, info.guest_token);
      } catch {
        /* ignore */
      }
    }
    if (info.guest_user_id || info.guest_username) {
      if (info.guest_user_id) setGuestUserId(info.guest_user_id);
      if (info.guest_username) setGuestUsername(info.guest_username);
      try {
        sessionStorage.setItem(
          GUEST_USER_KEY,
          JSON.stringify({
            id: info.guest_user_id || guestUserId || "",
            name: info.guest_username || guestUsername || "",
          }),
        );
      } catch {
        /* ignore */
      }
    }
  }, [guestUserId, guestUsername]);

  const disconnect = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
  }, []);

  const connect = useCallback(
    (code: string, authToken?: string | null) => {
      const tok = authToken || battleToken;
      if (!tok) return;
      disconnect();
      setRoomCode(code);
      sessionStorage.setItem(ROOM_KEY, code);
      setChatMessages([]);
      socketRef.current = connectBattleWs({
        token: tok,
        room: code,
        onState: (next) => {
          setWaiting(null);
          const hotseat = Boolean(next.hotseat || roomMetaRef.current?.hotseat);
          const rawActing = next.acting_seat;
          const rawViewer = next.viewer_seat;
          let viewer: number | null = null;
          if (rawActing != null && Number.isFinite(Number(rawActing))) {
            viewer = Number(rawActing);
          } else if (rawViewer != null && Number.isFinite(Number(rawViewer))) {
            viewer = Number(rawViewer);
          }
          setState({
            ...next,
            hotseat,
            viewer_seat: viewer,
            acting_seat: viewer,
          });
          if (next.ranked) {
            setRoomMeta((prev) => ({
              vs_ai: prev?.vs_ai ?? false,
              hotseat: prev?.hotseat ?? false,
              ranked: true,
              status: prev?.status ?? "playing",
            }));
          }
          setError(null);
          setActionBusy(false);
          if (actionBusyTimer.current) {
            clearTimeout(actionBusyTimer.current);
            actionBusyTimer.current = null;
          }
        },
        onWaiting: (room) => {
          setState(null);
          setWaiting(room);
          setError(null);
          setActionBusy(false);
        },
        onError: (message) => {
          setError(message);
          setActionBusy(false);
        },
        onClose: () => {
          socketRef.current = null;
          setActionBusy(false);
        },
        onChat: (messages) => setChatMessages(messages),
      });
    },
    [disconnect, battleToken],
  );

  useEffect(() => {
    if (!ready) return;
    if (token) {
      fetchDecks(token)
        .then((res) => setDecks(res.decks || []))
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    } else {
      setDecks([]);
    }
    fetchAiBattleDecks()
      .then((list) => setAiDecks(list))
      .catch(() => setAiDecks([]));
    const saved = sessionStorage.getItem(ROOM_KEY);
    const tok = token || guestToken || sessionStorage.getItem(GUEST_TOKEN_KEY);
    if (saved && tok) connect(saved, tok);
    return () => disconnect();
    // Only re-run when auth readiness / identity changes — not every guestToken write mid-match.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, token]);

  useEffect(() => {
    if (!roomCode || !battleToken) return;
    if (state && !socketRef.current) connect(roomCode);
  }, [roomCode, battleToken, state, connect]);

  useEffect(() => {
    if (!roomCode) return;
    const timer = window.setInterval(() => {
      fetchBattleRoom(roomCode)
        .then((info) => {
          setRoomMeta({
            vs_ai: Boolean(info.vs_ai),
            hotseat: Boolean(info.hotseat),
            ranked: Boolean(info.ranked),
            status: info.status,
          });
          if (info.status === "playing") {
            setWaiting(null);
            if (battleToken) {
              if (!socketRef.current) connect(roomCode);
              else socketRef.current.sendSync?.();
            }
            return;
          }
          if (!state) {
            setWaiting({
              type: "room",
              room_code: info.room_code,
              status: info.status,
              vs_ai: Boolean(info.vs_ai),
              hotseat: Boolean(info.hotseat),
              players: info.players || [null, null],
            });
          }
        })
        .catch((e) => {
          if (e instanceof ApiError && e.status === 404) {
            disconnect();
            sessionStorage.removeItem(ROOM_KEY);
            setRoomCode(null);
            setState(null);
            setWaiting(null);
            setActionBusy(false);
            setError(t("play.room_expired"));
          }
        });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [roomCode, state, battleToken, connect, disconnect, t]);

  useEffect(() => {
    if (!state) return;
    const ids = new Set<string>();
    for (const p of state.players) {
      if (p.leader_card_id) ids.add(p.leader_card_id);
      for (const ch of p.characters) ids.add(ch.card_id);
      for (const st of p.stages) ids.add(st.card_id);
      for (const cid of p.hand || []) ids.add(cid);
      for (const face of p.life_faces || []) {
        if (face?.face_up && face.card_id) ids.add(face.card_id);
      }
    }
    if (state.pending_effect?.card_id) ids.add(state.pending_effect.card_id);
    if (state.pending_trigger?.card_id) ids.add(state.pending_trigger.card_id);
    for (const cid of state.pending_search?.revealed || []) {
      if (cid) ids.add(cid);
    }
    for (const cid of state.pending_search?.bottom_order || []) {
      if (cid) ids.add(cid);
    }
    for (const cid of collectCardIdsFromLogs(state.log)) ids.add(cid);
    prefetchCardImages(ids);
    const missing = [...ids].filter((id) => !names[id]);
    if (!missing.length) return;
    fetchDeckStatsBatch(missing)
      .then((res) => setNames((prev) => ({ ...prev, ...res })))
      .catch(() => undefined);
  }, [state, names]);

  function enterMatchedRoom(code: string, authToken?: string | null) {
    setMatching(false);
    setRankedMatching(false);
    setMatchWaitSec(0);
    setMatchWindow(null);
    setRoomMeta({ vs_ai: false, hotseat: false, ranked: Boolean(lastMatchRef.current?.ranked), status: "playing" });
    setWaiting(null);
    connect(code, authToken);
  }

  useEffect(() => {
    if (!token) {
      setRankProfile(null);
      return;
    }
    fetchBattleRankMe(token)
      .then((profile) => setRankProfile(profile))
      .catch(() => setRankProfile(null));
  }, [token, state]);

  useEffect(() => {
    if (!rankedMatching || !token) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const result = await fetchBattleRankedStatus(token);
        if (cancelled) return;
        if (result.status === "matched" && result.room_code) {
          enterMatchedRoom(result.room_code, token);
        } else if (result.status === "idle") {
          setRankedMatching(false);
          setError(t("play.match_expired"));
        } else {
          setMatchWaitSec(Number(result.waited_sec || 0));
          setMatchWindow(typeof result.match_window === "number" ? result.match_window : null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [rankedMatching, token, t]);

  useEffect(() => {
    if (!matching || !battleToken) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const result = await fetchBattleMatchmakingStatus(battleToken);
        if (cancelled) return;
        rememberGuestToken(result);
        if (result.status === "matched" && result.room_code) {
          enterMatchedRoom(result.room_code, result.guest_token || battleToken);
        } else if (result.status === "idle") {
          setMatching(false);
          setError(t("play.match_expired"));
        } else {
          setMatchWaitSec(Number(result.waited_sec || 0));
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    void tick();
    const timer = window.setInterval(() => void tick(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matching, battleToken, t]);

  function acknowledgeBeta() {
    sessionStorage.setItem(BETA_NOTICE_KEY, "1");
    setShowBetaNotice(false);
  }

  async function handleCreateRoom() {
    setBusy(true);
    setError(null);
    try {
      const sp = readBattleSpectatorPrefs();
      const room = await createBattleRoom(battleToken, {
        vsAi: false,
        allowSpectators: sp.allowSpectators,
        spectatorShowHands: sp.showHands,
      });
      rememberGuestToken(room);
      connect(room.room_code, room.guest_token || battleToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleJoinRoom(code: string) {
    setBusy(true);
    setError(null);
    try {
      const room = await joinBattleRoom(battleToken, code);
      rememberGuestToken(room);
      connect(room.room_code, room.guest_token || battleToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleFindRankedMatch(pick: PlayDeckPick) {
    if (!token) {
      setError(t("play.rank_need_login"));
      return;
    }
    setBusy(true);
    setError(null);
    lastMatchRef.current = { pick, ranked: true };
    lastAiRef.current = null;
    lastSelfRef.current = null;
    try {
      disconnect();
      sessionStorage.removeItem(ROOM_KEY);
      setRoomCode(null);
      setState(null);
      setWaiting(null);
      const sp = readBattleSpectatorPrefs();
      const result = await joinBattleRanked(token, {
        ...pickToCreateOpts(pick),
        allowSpectators: sp.allowSpectators,
        spectatorShowHands: sp.showHands,
      });
      if (result.status === "matched" && result.room_code) {
        enterMatchedRoom(result.room_code, token);
      } else {
        setRankedMatching(true);
        setRoomMeta({ vs_ai: false, hotseat: false, ranked: true, status: "playing" });
        setMatchWaitSec(Number(result.waited_sec || 0));
        setMatchWindow(typeof result.match_window === "number" ? result.match_window : null);
      }
    } catch (e) {
      setRankedMatching(false);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleFindMatch(pick: PlayDeckPick) {
    setBusy(true);
    setError(null);
    lastMatchRef.current = { pick, ranked: false };
    lastAiRef.current = null;
    lastSelfRef.current = null;
    try {
      disconnect();
      sessionStorage.removeItem(ROOM_KEY);
      setRoomCode(null);
      setState(null);
      setWaiting(null);
      const sp = readBattleSpectatorPrefs();
      const result = await joinBattleMatchmaking(battleToken, {
        ...pickToCreateOpts(pick),
        allowSpectators: sp.allowSpectators,
        spectatorShowHands: sp.showHands,
      });
      rememberGuestToken(result);
      if (result.status === "matched" && result.room_code) {
        enterMatchedRoom(result.room_code, result.guest_token || battleToken);
      } else {
        setMatching(true);
        setMatchWaitSec(Number(result.waited_sec || 0));
      }
    } catch (e) {
      setMatching(false);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleStartAi(pick: PlayDeckPick, aiDeckId: string) {
    setBusy(true);
    setError(null);
    try {
      lastAiRef.current = { pick, aiDeckId };
      lastSelfRef.current = null;
      lastMatchRef.current = null;
      const sp = readBattleSpectatorPrefs();
      const room = await createBattleRoom(battleToken, {
        ...pickToCreateOpts(pick),
        vsAi: true,
        aiDeckId,
        allowSpectators: sp.allowSpectators,
        spectatorShowHands: sp.showHands,
      });
      rememberGuestToken(room);
      setRoomMeta({ vs_ai: true, hotseat: false, status: room.status });
      if (room.status === "playing") setWaiting(null);
      connect(room.room_code, room.guest_token || battleToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleStartSelf(pick: PlayDeckPick, opp: PlayDeckPick) {
    setBusy(true);
    setError(null);
    try {
      lastSelfRef.current = { pick, opp };
      lastAiRef.current = null;
      lastMatchRef.current = null;
      const sp = readBattleSpectatorPrefs();
      const room = await createBattleRoom(battleToken, {
        ...pickToCreateOpts(pick),
        hotseat: true,
        ...(opp.kind === "saved" ? { oppDeckId: opp.deckId } : { oppDeck: opp.deck }),
        allowSpectators: sp.allowSpectators,
        spectatorShowHands: sp.showHands,
      });
      rememberGuestToken(room);
      setRoomMeta({ vs_ai: false, hotseat: true, status: room.status });
      if (room.status === "playing") setWaiting(null);
      connect(room.room_code, room.guest_token || battleToken);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleSelectDeck(deckId: string) {
    if (!battleToken || !roomCode) return;
    setLobbyDeckId(deckId);
    setLobbyInline(null);
    setBusy(true);
    setError(null);
    try {
      const info = await setBattleRoomDeck(battleToken, roomCode, { deckId });
      rememberGuestToken(info);
      setWaiting({
        type: "room",
        room_code: info.room_code,
        status: info.status,
        vs_ai: Boolean(info.vs_ai),
        players: info.players || [null, null],
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleLobbyImport() {
    if (!battleToken || !roomCode) return;
    setLobbyImporting(true);
    setError(null);
    try {
      const deck = await resolveImportedDeck(lobbyImportText);
      if (!deck) {
        setError(t("play.import_invalid"));
        return;
      }
      setLobbyInline(deck);
      setLobbyDeckId("");
      const info = await setBattleRoomDeck(battleToken, roomCode, { deck });
      rememberGuestToken(info);
      setWaiting({
        type: "room",
        room_code: info.room_code,
        status: info.status,
        vs_ai: Boolean(info.vs_ai),
        players: info.players || [null, null],
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLobbyImporting(false);
    }
  }

  async function handleReady(nextReady: boolean) {
    if (!battleToken || !roomCode) return;
    setBusy(true);
    setError(null);
    try {
      if (nextReady) {
        if (lobbyInline) {
          await setBattleRoomDeck(battleToken, roomCode, { deck: lobbyInline });
        } else if (lobbyDeckId) {
          await setBattleRoomDeck(battleToken, roomCode, { deckId: lobbyDeckId });
        }
      }
      const info = await setBattleRoomReady(battleToken, roomCode, nextReady);
      rememberGuestToken(info);
      if (info.status === "playing") {
        if (!socketRef.current) connect(roomCode);
      } else {
        setWaiting({
          type: "room",
          room_code: info.room_code,
          status: info.status,
          vs_ai: Boolean(info.vs_ai),
          players: info.players || [null, null],
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelRankedMatchmaking() {
    setRankedMatching(false);
    setMatchWaitSec(0);
    setMatchWindow(null);
    if (token) {
      try {
        await leaveBattleRanked(token);
      } catch {
        /* ignore */
      }
    }
  }

  async function cancelMatchmaking() {
    setMatching(false);
    setMatchWaitSec(0);
    if (battleToken) {
      try {
        await leaveBattleMatchmaking(battleToken);
      } catch {
        /* ignore */
      }
    }
  }

  function leave() {
    if (matching) void cancelMatchmaking();
    if (rankedMatching) void cancelRankedMatchmaking();
    disconnect();
    sessionStorage.removeItem(ROOM_KEY);
    setRoomCode(null);
    setState(null);
    setWaiting(null);
    setRoomMeta(null);
    setChatMessages([]);
  }

  async function rematch() {
    const ai = lastAiRef.current;
    const self = lastSelfRef.current;
    const queued = lastMatchRef.current;
    const wasAi = Boolean(state?.vs_ai || state?.players.some((p) => p.is_ai));
    const wasSelf = Boolean(state?.hotseat || roomMeta?.hotseat);
    leave();
    if (wasSelf && self?.pick && self?.opp) {
      await handleStartSelf(self.pick, self.opp);
      return;
    }
    if (wasAi && ai?.pick && ai?.aiDeckId) {
      await handleStartAi(ai.pick, ai.aiDeckId);
      return;
    }
    if (queued?.pick) {
      if (queued.ranked) await handleFindRankedMatch(queued.pick);
      else await handleFindMatch(queued.pick);
    }
  }

  useEffect(() => {
    if (!token || !state?.room_code) return;
    const isRanked = Boolean(state.ranked || roomMeta?.ranked || lastMatchRef.current?.ranked);
    if (!isRanked || state.status !== "finished") return;
    fetchBattleRankAppealStatus(token, state.room_code)
      .then((res) => {
        if (res.status === "approved") setRankAppealStatus("reverted");
        else setRankAppealStatus(res.status);
      })
      .catch(() => setRankAppealStatus("none"));
  }, [token, state?.room_code, state?.status, state?.ranked, roomMeta?.ranked]);

  async function handleRankAppeal(message: string) {
    if (!token || !state?.room_code) throw new Error(t("play.rank_need_login"));
    await submitBattleRankAppeal(token, {
      room_code: state.room_code,
      message,
      replay_id: state.replay_id || null,
    });
    setRankAppealStatus("pending");
  }

  async function handleBugReport(message: string) {
    if (!token) throw new Error(t("play.bug_need_login"));
    await submitBattleBugReport(token, {
      message,
      room_code: state?.room_code || roomCode,
      phase: state?.phase,
      turn_number: state?.turn_number,
      page_url: typeof window !== "undefined" ? window.location.href : null,
    });
  }

  function sendAction(action: BattleAction) {
    setError(null);
    const sock = socketRef.current;
    if (!sock) {
      setError(t("play.ws_disconnected"));
      setActionBusy(false);
      if (roomCode && battleToken) connect(roomCode);
      return;
    }
    setActionBusy(true);
    if (actionBusyTimer.current) clearTimeout(actionBusyTimer.current);
    actionBusyTimer.current = setTimeout(() => {
      setActionBusy(false);
      setError((prev) => prev || t("play.action_timeout"));
      try {
        socketRef.current?.sendSync?.();
      } catch {
        /* ignore */
      }
      if (roomCode && battleToken && !socketRef.current) connect(roomCode);
    }, 30000);
    try {
      sock.sendAction(action);
    } catch (e) {
      setActionBusy(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const meSlot = useMemo(() => {
    if (!waiting) return null;
    if (guestUserId) {
      const byId = waiting.players.find((p) => p && p.user_id === guestUserId);
      if (byId) return byId;
    }
    if (displayName || username) {
      const byName = waiting.players.find(
        (p) => p && (p.username === displayName || p.username === username || p.username === guestUsername),
      );
      if (byName) return byName;
    }
    return waiting.players.find((p) => p && !p.is_ai) || null;
  }, [waiting, displayName, username, guestUserId, guestUsername]);

  if (!ready) return <p className="muted">…</p>;

  const betaModal = showBetaNotice ? (
    <div className="play-beta-layer" role="dialog" aria-modal="true">
      <div className="play-beta-card">
        <h2>{t("play.beta_title")}</h2>
        <p>{t("play.beta_body")}</p>
        {!isLoggedIn ? <p className="muted">{t("play.guest_hint")}</p> : null}
        <button type="button" className="success" onClick={acknowledgeBeta}>
          {t("play.beta_ack")}
        </button>
      </div>
    </div>
  ) : null;

  if (state) {
    return (
      <>
        {betaModal}
        <BattleBoard
          state={state}
          names={names}
          onAction={sendAction}
          onLeave={leave}
          onRematch={() => void rematch()}
          onWatchReplay={
            state.replay_id
              ? () => router.push(`/play/history/${encodeURIComponent(state.replay_id!)}`)
              : undefined
          }
          onBugReport={handleBugReport}
          ranked={Boolean(state.ranked || roomMeta?.ranked || lastMatchRef.current?.ranked)}
          onRankAppeal={token && isLoggedIn ? handleRankAppeal : undefined}
          rankAppealStatus={rankAppealStatus}
          actionBusy={actionBusy}
          error={error}
          onDismissError={() => setError(null)}
          chatMessages={chatMessages}
          chatSelfUserId={guestUserId || null}
          onSendChat={(text) => socketRef.current?.sendChat(text)}
        />
      </>
    );
  }

  if ((matching || rankedMatching) && !state) {
    return (
      <>
        {betaModal}
        <section className="play-lobby">
          <h1 className="page-title">{rankedMatching ? t("play.ranked_matching") : t("play.matching")}</h1>
          <p className="muted">{rankedMatching ? t("play.ranked_matching_hint") : t("play.matching_hint")}</p>
          <p className="play-matching-wait">{t("play.matching_wait", { n: matchWaitSec })}</p>
          {rankedMatching && matchWindow != null ? (
            <p className="muted">{t("play.ranked_match_window", { n: matchWindow })}</p>
          ) : null}
          <div className="play-actions">
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void (rankedMatching ? cancelRankedMatchmaking() : cancelMatchmaking())}
            >
              {t("play.match_cancel")}
            </button>
          </div>
          {error ? <p className="error-text">{error}</p> : null}
        </section>
      </>
    );
  }

  if (roomCode && !state) {
    const code = waiting?.room_code || roomCode;
    const players = waiting?.players || [null, null];
    const vsAi = Boolean(waiting?.vs_ai || roomMeta?.vs_ai);
    const isHotseat = Boolean(waiting?.hotseat || roomMeta?.hotseat);
    const isStarting = vsAi || isHotseat || roomMeta?.status === "playing";

    if (isStarting) {
      const title = isHotseat
        ? t("play.starting_self")
        : vsAi
          ? t("play.starting_ai")
          : t("play.starting_pvp");
      const hint = isHotseat
        ? t("play.starting_self_hint")
        : vsAi
          ? t("play.starting_ai_hint")
          : t("play.starting_pvp_hint");
      return (
        <>
          {betaModal}
          <section className="play-lobby">
            <h1 className="page-title">{title}</h1>
            <p className="muted">{hint}</p>
            <div className="play-actions">
              <button type="button" className="secondary" onClick={leave}>
                {t("play.leave")}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  if (battleToken) {
                    if (!socketRef.current) connect(roomCode);
                    else socketRef.current.sendSync?.();
                  }
                }}
              >
                {t("play.retry_connect")}
              </button>
            </div>
            {error ? <p className="error-text">{error}</p> : null}
          </section>
        </>
      );
    }

    const myReady = Boolean(meSlot?.ready);
    const myHasDeck = Boolean(meSlot?.has_deck);
    const selectedDeck = lobbyDeckId || meSlot?.deck_id || validDecks[0]?.id || "";
    const canReady = Boolean(lobbyInline || selectedDeck);

    return (
      <>
        {betaModal}
        <section className="play-lobby">
          <h1 className="page-title">{t("play.waiting")}</h1>
          <p className="play-code">{code}</p>
          <p className="muted">{t("play.waiting_ready_hint")}</p>
          <div className="play-actions">
            <button
              type="button"
              className="ghost"
              onClick={() => navigator.clipboard.writeText(code).catch(() => undefined)}
            >
              {t("play.copy")}
            </button>
            <button type="button" className="secondary" onClick={leave}>
              {t("play.leave")}
            </button>
          </div>
          <div className="play-seats">
            {players.map((p, i) => (
              <div key={i} className="play-seat">
                {p ? (
                  <>
                    <strong>{p.username}</strong>
                    <span className="muted">
                      {p.has_deck ? t("play.deck_selected") : t("play.deck_pending")}
                      {" · "}
                      {p.ready ? t("play.ready_yes") : t("play.ready_no")}
                    </span>
                  </>
                ) : (
                  <span className="muted">{t("play.seat_empty")}</span>
                )}
              </div>
            ))}
          </div>
          {!vsAi ? (
            <>
              {validDecks.length ? (
                <label className="play-field">
                  <span>{t("play.choose_deck")}</span>
                  <select
                    value={lobbyInline ? "" : selectedDeck}
                    disabled={busy || myReady || !validDecks.length}
                    onChange={(e) => void handleSelectDeck(e.target.value)}
                  >
                    {validDecks.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} · {displayCardId(d.leader_card_id)} · {d.non_leader_count}/50
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="muted">{t("play.need_deck_or_import")}</p>
              )}
              <DeckImportBlock
                label={t("play.import_deck")}
                value={lobbyImportText}
                onChange={setLobbyImportText}
                onApply={() => void handleLobbyImport()}
                busy={busy || myReady}
                importing={lobbyImporting}
                appliedLabel={
                  lobbyInline ? `${t("play.imported_ok")} · ${displayCardId(lobbyInline.leader_card_id)} · 50/50` : null
                }
              />
              <div className="play-actions">
                {!myReady ? (
                  <button type="button" disabled={busy || !canReady} onClick={() => handleReady(true)}>
                    {t("play.ready")}
                  </button>
                ) : (
                  <button type="button" className="secondary" disabled={busy} onClick={() => handleReady(false)}>
                    {t("play.cancel_ready")}
                  </button>
                )}
              </div>
              {myReady && !myHasDeck ? <p className="muted">{t("play.ready_need_deck")}</p> : null}
            </>
          ) : null}
          {error ? <p className="error-text">{error}</p> : null}
        </section>
      </>
    );
  }

  return (
    <>
      {betaModal}
      <PlayLobby
        decks={decks}
        aiDecks={aiDecks}
        busy={busy}
        error={error}
        onCreateRoom={handleCreateRoom}
        onJoinRoom={handleJoinRoom}
        onFindMatch={handleFindMatch}
        onFindRanked={handleFindRankedMatch}
        rankProfile={rankProfile}
        onStartAi={handleStartAi}
        onStartSelf={handleStartSelf}
      />
    </>
  );
}
