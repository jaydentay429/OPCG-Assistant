import { API_BASE } from "./api";

export type BattleChar = {
  iid: string;
  card_id: string;
  rested: boolean;
  power_mod: number;
  cost_mod?: number;
  /** Live cost after continuous +cost auras (preferred over printed+cost_mod). */
  cost?: number;
  don_attached: number;
  summoning_sick: boolean;
  keywords: string[];
  power?: number;
  cannot_attack?: boolean;
  cannot_rest?: boolean;
  cannot_be_ko?: boolean;
  effects_negated?: boolean;
  taunt?: boolean;
};

export type BattleLifeFace = {
  face_up: boolean;
  card_id: string | null;
};

export type BattlePlayerView = {
  seat: number;
  user_id: string;
  username: string;
  elite_title?: string | null;
  elite_title_zh?: string | null;
  is_ai: boolean;
  leader_card_id: string;
  leader_rested: boolean;
  leader_don: number;
  leader_power: number;
  leader_keywords?: string[];
  leader_cannot_attack?: boolean;
  life: number;
  /** Per-card Life face state; face-up entries expose card_id to both players. */
  life_faces?: BattleLifeFace[];
  deck_count: number;
  hand_count: number;
  hand: string[];
  trash: string[];
  characters: BattleChar[];
  stages: BattleChar[];
  don_active: number;
  don_rested: number;
  don_given: number;
  don_deck_size?: number;
};

export type BattleAction = Record<string, unknown> & { type: string };

export type BattleLogEntry = {
  key: string;
  [param: string]: string | number | boolean | null | undefined;
};

export type BattleChatMessage = {
  id: string;
  user_id: string;
  username: string;
  text: string;
  ts: number;
  seat?: number | null;
};

export type BattleState = {
  room_code: string;
  status: string;
  phase: string;
  turn_seat: number;
  first_seat: number;
  turn_number: number;
  mulligan_seat?: number | null;
  winner_seat: number | null;
  viewer_seat: number | null;
  acting_seat?: number | null;
  log: Array<string | BattleLogEntry>;
  attack: {
    attacker_seat: number;
    attacker_iid: string;
    target_iid: string;
    declared_power: number;
    blocker_iid: string | null;
    counter_bonus: number;
    counter_buffs?: Record<string, number>;
    combat_entered?: boolean;
    combat_phase?: string;
  } | null;
  pending_effect: {
    effect_id: string;
    seat: number;
    card_id: string;
    source_iid?: string;
    summary: string;
    ops: Array<Record<string, unknown>>;
    uncertain: boolean;
    confirmations: Record<string, boolean>;
  } | null;
  pending_trigger?: {
    seat: number;
    card_id: string;
    summary: string;
    ops: Array<Record<string, unknown>>;
    remaining_hits: number;
  } | null;
  pending_search?: {
    seat: number;
    card_id: string;
    source_iid?: string;
    phase?: "pick" | "order" | "choose_dest" | string;
    revealed: Array<string | null>;
    eligible: number[];
    /** Indices currently toggled for multi-add searches (viewer only). */
    selected?: number[];
    bottom_order?: Array<string | null>;
    max_add: number;
    trait_contains?: string;
    name_contains?: string;
    card_type?: string;
    exclude_name?: string;
    summary?: string;
    order_bottom?: boolean;
    to_top_or_bottom?: boolean;
    order_dest?: "top" | "bottom" | string;
  } | null;
  pending_choice?: {
    seat: number;
    card_id: string;
    source_iid?: string;
    target_kind: string;
    options: string[];
    option_labels?: Record<string, string>;
    optional: boolean;
    multi_select?: boolean;
    summary?: string;
    purpose?: string;
  } | null;
  players: BattlePlayerView[];
  legal_actions: BattleAction[];
  vs_ai?: boolean;
  hotseat?: boolean;
  ranked?: boolean;
  replay_id?: string | null;
  replay_mode?: boolean;
  viewer_role?: "player" | "spectator";
  spectator_mode?: "ai" | "pvp" | "hotseat";
  spectator_show_hands?: boolean;
};

export type WaitingRoom = {
  type: "room";
  room_code: string;
  status: string;
  vs_ai: boolean;
  hotseat?: boolean;
  players: Array<{
    user_id: string;
    username: string;
    is_ai: boolean;
    ready?: boolean;
    has_deck?: boolean;
    deck_id?: string | null;
    deck_name?: string | null;
    leader_card_id?: string | null;
  } | null>;
};

export function battleWsUrl(token: string, room: string, role?: "player" | "spectator"): string {
  const http = API_BASE.replace(/\/$/, "");
  const wsBase = http.startsWith("https://") ? http.replace(/^https:/, "wss:") : http.replace(/^http:/, "ws:");
  const url = new URL(`${wsBase}/battle/ws`);
  url.searchParams.set("token", token);
  url.searchParams.set("room", room);
  if (role === "spectator") url.searchParams.set("role", "spectator");
  return url.toString();
}

export function connectBattleWs(opts: {
  token: string;
  room: string;
  role?: "player" | "spectator";
  onState: (state: BattleState) => void;
  onWaiting: (room: WaitingRoom) => void;
  onError: (message: string) => void;
  onClose: () => void;
  onChat?: (messages: BattleChatMessage[]) => void;
}): { sendAction: (action: BattleAction) => void; sendSync: () => void; sendChat: (text: string) => void; close: () => void } {
  const ws = new WebSocket(battleWsUrl(opts.token, opts.room, opts.role));
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let closedByClient = false;
  let openedOnce = false;

  ws.onopen = () => {
    openedOnce = true;
    // Match may already be running (AI rooms) — pull state immediately.
    ws.send(JSON.stringify({ type: "sync" }));
    pingTimer = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
    }, 20000);
  };
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(String(ev.data || "{}")) as Record<string, unknown>;
      if (data.type === "state" && data.state && typeof data.state === "object") {
        opts.onState(data.state as BattleState);
        return;
      }
      if (data.type === "room") {
        opts.onWaiting(data as WaitingRoom);
        return;
      }
      if (data.type === "chat" && Array.isArray(data.messages)) {
        opts.onChat?.(data.messages as BattleChatMessage[]);
        return;
      }
      if (data.type === "error") {
        opts.onError(String(data.error || "Battle error"));
      }
    } catch {
      opts.onError("Bad battle message");
    }
  };
  // Browser websocket `error` has no useful detail and can fire transiently
  // during reload/network jitter. Surface user-facing errors from close path.
  ws.onerror = () => undefined;
  ws.onclose = () => {
    if (pingTimer) clearInterval(pingTimer);
    if (!closedByClient && openedOnce) {
      opts.onError("WebSocket disconnected");
    }
    opts.onClose();
  };

  return {
    sendAction(action) {
      const payload = JSON.stringify({ type: "action", action });
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(payload);
        return;
      }
      if (ws.readyState === WebSocket.CONNECTING) {
        let sent = false;
        const flush = () => {
          if (sent) return;
          if (ws.readyState === WebSocket.OPEN) {
            sent = true;
            ws.send(payload);
          } else {
            opts.onError("WebSocket not connected");
          }
        };
        ws.addEventListener("open", flush, { once: true });
        window.setTimeout(flush, 1500);
        return;
      }
      opts.onError("WebSocket disconnected");
    },
    sendSync() {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "sync" }));
      }
    },
    sendChat(text) {
      const body = text.trim();
      if (!body) return;
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "chat", text: body }));
      }
    },
    close() {
      closedByClient = true;
      if (pingTimer) clearInterval(pingTimer);
      ws.close();
    },
  };
}
