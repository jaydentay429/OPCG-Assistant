"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BattleBoard } from "@/components/play/BattleBoard";
import { ReplayControls } from "@/components/play/ReplayControls";
import {
  fetchBattleReplay,
  fetchDeckStatsBatch,
  type BattleReplayPayload,
  type DeckStatFields,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { collectCardIdsFromLogs } from "@/lib/battleLogCards";
import type { BattleLogEntry, BattleState } from "@/lib/battleWs";
import { useI18n } from "@/lib/i18n";

type Props = {
  replayId: string;
};

function accumulateLog(frames: BattleReplayPayload["frames"], through: number): BattleLogEntry[] {
  const out: BattleLogEntry[] = [];
  for (let i = 0; i <= through; i++) {
    const delta = frames[i]?.log_delta;
    if (!Array.isArray(delta)) continue;
    for (const entry of delta) {
      if (entry && typeof entry === "object" && "key" in entry) {
        out.push(entry as BattleLogEntry);
      }
    }
  }
  return out.slice(-100);
}

function buildLogsByFrame(frames: BattleReplayPayload["frames"]): BattleLogEntry[][] {
  const out: BattleLogEntry[][] = [];
  const running: BattleLogEntry[] = [];
  let lastReplaySearchSig = "";

  const replaySearchReveal = (frame: BattleReplayPayload["frames"][number]): { sig: string; line: BattleLogEntry } | null => {
    const pending = (frame as { pending_search?: { phase?: string; revealed?: Array<string | null>; seat?: number } }).pending_search;
    if (!pending) return null;
    const ids = (pending.revealed || []).filter((id): id is string => Boolean(id && String(id).trim()));
    if (!ids.length) return null;
    const players = (frame as { players?: Array<{ seat?: number; username?: string }> }).players || [];
    const actorName =
      players.find((p) => Number(p.seat) === Number(pending.seat))?.username || `P${Number(pending.seat) + 1}`;
    const sig = `${pending.seat ?? "?"}:${pending.phase ?? "pick"}:${ids.join("|")}`;
    return {
      sig,
      line: {
        key: "play.log.replay_search_revealed",
        name: actorName,
        ids: ids.join(","),
      },
    };
  };

  for (const frame of frames) {
    const delta = frame?.log_delta;
    if (Array.isArray(delta)) {
      for (const entry of delta) {
        if (entry && typeof entry === "object" && "key" in entry) {
          running.push(entry as BattleLogEntry);
        }
      }
    }
    const replayReveal = replaySearchReveal(frame);
    if (replayReveal && replayReveal.sig !== lastReplaySearchSig) {
      running.push(replayReveal.line);
      lastReplaySearchSig = replayReveal.sig;
    }
    out.push(running.slice(-100));
  }
  return out;
}

function frameToState(
  payload: BattleReplayPayload,
  logsByFrame: BattleLogEntry[][],
  frameIndex: number,
  viewerSeat: 0 | 1,
): BattleState {
  const frame = payload.frames[frameIndex] || payload.frames[payload.frames.length - 1];
  const log = logsByFrame[frameIndex] || accumulateLog(payload.frames, frameIndex);
  const header = payload.header;
  return {
    ...(frame as unknown as BattleState),
    viewer_seat: viewerSeat,
    acting_seat: viewerSeat,
    log,
    legal_actions: [],
    replay_mode: true,
    vs_ai: header.mode === "ai",
    hotseat: header.mode === "hotseat",
    replay_id: header.id,
  };
}

function collectCardIdsFromFrame(
  payload: BattleReplayPayload,
  frameIndex: number,
  logs?: BattleLogEntry[],
): string[] {
  const ids = new Set<string>();
  const addPlayer = (p: {
    leader_card_id?: string;
    hand?: string[];
    trash?: string[];
    characters?: { card_id: string }[];
    stages?: { card_id: string }[];
  }) => {
    if (p.leader_card_id) ids.add(p.leader_card_id);
    for (const c of p.hand || []) ids.add(c);
    for (const c of p.trash || []) ids.add(c);
    for (const c of p.characters || []) ids.add(c.card_id);
    for (const c of p.stages || []) ids.add(c.card_id);
  };
  ids.add(payload.header.p0.leader_card_id);
  ids.add(payload.header.p1.leader_card_id);
  const frame = payload.frames[frameIndex] || payload.frames[payload.frames.length - 1];
  const players = (frame as { players?: Array<Record<string, unknown>> }).players;
  if (players) {
    for (const p of players) addPlayer(p as Parameters<typeof addPlayer>[0]);
  }
  const ps = (frame as { pending_search?: { revealed?: Array<string | null> } }).pending_search;
  for (const c of ps?.revealed || []) {
    if (c) ids.add(c);
  }
  for (const cid of collectCardIdsFromLogs(logs)) ids.add(cid);
  return [...ids];
}

export function BattleReplayClient({ replayId }: Props) {
  const { t } = useI18n();
  const router = useRouter();
  const { token, isLoggedIn, ready } = useAuth();
  const [payload, setPayload] = useState<BattleReplayPayload | null>(null);
  const [names, setNames] = useState<Record<string, DeckStatFields>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [perspective, setPerspective] = useState<0 | 1>(0);
  const [frameIndex, setFrameIndex] = useState(0);
  const [logsByFrame, setLogsByFrame] = useState<BattleLogEntry[][]>([]);

  const frameCount = payload?.frames.length || 0;
  const maxIndex = Math.max(0, frameCount - 1);

  useEffect(() => {
    if (!ready || !token || !isLoggedIn) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchBattleReplay(token, replayId);
        if (cancelled) return;
        setPayload(data);
        setLogsByFrame(buildLogsByFrame(data.frames || []));
        setFrameIndex(0);
        const logs0 = buildLogsByFrame(data.frames || [])[0];
        const ids = collectCardIdsFromFrame(data, 0, logs0);
        if (ids.length) {
          const stats = await fetchDeckStatsBatch(ids);
          if (!cancelled) setNames(stats);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, token, isLoggedIn, replayId]);

  useEffect(() => {
    if (!payload) return;
    const ids = collectCardIdsFromFrame(payload, frameIndex, logsByFrame[frameIndex]);
    const missing = ids.filter((id) => !names[id]);
    if (!missing.length) return;
    let cancelled = false;
    (async () => {
      try {
        const stats = await fetchDeckStatsBatch(missing);
        if (!cancelled) setNames((prev) => ({ ...stats, ...prev }));
      } catch {
        // Keep replay navigable even if card metadata fetch fails.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [payload, frameIndex, names, logsByFrame]);

  const state = useMemo(() => {
    if (!payload?.frames.length) return null;
    return frameToState(payload, logsByFrame, frameIndex, perspective);
  }, [payload, logsByFrame, frameIndex, perspective]);

  const winnerBanner = useMemo(() => {
    if (!payload || !state) return null;
    const ws = payload.header.winner_seat;
    if (ws == null) return null;
    const winner = ws === 0 ? payload.header.p0.username : payload.header.p1.username;
    const atEnd = frameIndex >= payload.frames.length - 1;
    if (!atEnd && state.status !== "finished") return null;
    return t("play.replay_winner", { name: winner });
  }, [payload, state, frameIndex, t]);

  const noop = useCallback(() => undefined, []);
  const leaveReplay = useCallback(() => {
    router.push("/play/history");
  }, [router]);
  const step = useCallback(
    (delta: number) => setFrameIndex((prev) => Math.max(0, Math.min(maxIndex, prev + delta))),
    [maxIndex],
  );
  const seek = useCallback((next: number) => setFrameIndex(Math.max(0, Math.min(maxIndex, next))), [maxIndex]);
  const jump = useCallback(
    (kind: "first" | "last") => setFrameIndex(kind === "first" ? 0 : maxIndex),
    [maxIndex],
  );

  if (!ready) return <p className="muted">…</p>;

  if (!isLoggedIn) {
    return (
      <section className="play-lobby">
        <h1 className="page-title">{t("play.replay_title")}</h1>
        <p className="muted">{t("play.history_login")}</p>
        <Link href="/play/history" className="secondary">
          {t("play.back")}
        </Link>
      </section>
    );
  }

  if (loading) return <p className="muted">{t("play.replay_loading")}</p>;
  if (error || !payload || !state) {
    return (
      <section className="play-lobby">
        <h1 className="page-title">{t("play.replay_title")}</h1>
        <p className="error-text">{error || t("play.replay_not_found")}</p>
        <Link href="/play/history" className="secondary">
          {t("play.back")}
        </Link>
      </section>
    );
  }

  return (
    <div className="replay-shell">
      <div className="replay-topbar">
        <Link href="/play/history" className="play-back-link-btn replay-back">
          {t("play.back")}
        </Link>
        <span className="replay-topbar-title">{t("play.replay_title")}</span>
        {winnerBanner ? <span className="replay-winner-badge">{winnerBanner}</span> : null}
      </div>
      <BattleBoard
        state={state}
        names={names}
        onAction={noop}
        onLeave={leaveReplay}
        replayMode
        replayControls={
          <ReplayControls
            frameIndex={frameIndex}
            frameCount={payload.frames.length}
            onJump={jump}
            onStep={step}
            onSeek={seek}
            perspective={perspective}
            onPerspectiveChange={setPerspective}
            p0Name={payload.header.p0.username}
            p1Name={payload.header.p1.username}
          />
        }
      />
    </div>
  );
}
