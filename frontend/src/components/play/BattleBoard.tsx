"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type DragEvent, type MouseEvent, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { CardImg } from "@/components/CardImg";
import { fetchCardBrief } from "@/lib/api";
import type { BattleAction, BattleChar, BattleChatMessage, BattleLogEntry, BattlePlayerView, BattleState } from "@/lib/battleWs";
import { BATTLE_CARD_ID_ONE, BATTLE_CARD_ID_RE } from "@/lib/battleLogCards";
import { hasCjk, localizeCardName, localizeCardText, preferLangText } from "@/lib/cardLocale";
import { localizeFilterToken } from "@/lib/filterLabels";
import { formatEffectLines } from "@/lib/formatEffect";
import { useI18n } from "@/lib/i18n";
import type { DeckStatFields } from "@/lib/api";
import type { Card } from "@/lib/types";
import { BattleChat } from "./BattleChat";
import { RankEliteName, eliteLabelForTitle } from "./RankEliteBadge";

type Props = {
  state: BattleState;
  names: Record<string, DeckStatFields>;
  onAction: (action: BattleAction) => void;
  onLeave: () => void;
  onRematch?: () => void;
  onWatchReplay?: () => void;
  onBugReport?: (message: string) => Promise<void>;
  ranked?: boolean;
  onRankAppeal?: (message: string) => Promise<void>;
  rankAppealStatus?: "none" | "pending" | "approved" | "rejected" | "reverted";
  actionBusy?: boolean;
  error?: string | null;
  onDismissError?: () => void;
  replayMode?: boolean;
  spectatorMode?: boolean;
  replayControls?: ReactNode;
  chatMessages?: BattleChatMessage[];
  chatSelfUserId?: string | null;
  onSendChat?: (text: string) => void;
};

type Lang = "zh-Hant" | "zh-Hans" | "en";

const DON_DRAG_MIME = "application/x-opcg-don";

/** Field reminder tags — order is display priority (restrictions first). */
const STATUS_TAG_ORDER = [
  "cannot_attack",
  "cannot_rest",
  "summoning_sick",
  "effects_negated",
  "cannot_be_ko",
  "taunt",
  "blocker",
  "double_attack",
  "banish",
  "blockerless",
  "rush",
  "rush_character",
] as const;

type StatusTagId = (typeof STATUS_TAG_ORDER)[number];

/** Debuffs / locks that need a loud banner on the card. */
const STATUS_RESTRICTION_IDS = new Set<StatusTagId>([
  "cannot_attack",
  "cannot_rest",
  "summoning_sick",
  "effects_negated",
]);

function collectStatusTags(opts: {
  keywords?: string[] | null;
  cannot_attack?: boolean;
  cannot_rest?: boolean;
  cannot_be_ko?: boolean;
  effects_negated?: boolean;
  taunt?: boolean;
  summoning_sick?: boolean;
}): StatusTagId[] {
  const set = new Set<string>((opts.keywords || []).map(String));
  const sick = Boolean(opts.summoning_sick);
  // First-turn Characters (no Rush) cannot attack — surface both reason and restriction.
  if (opts.cannot_attack || sick) set.add("cannot_attack");
  if (sick) set.add("summoning_sick");
  if (opts.cannot_rest) set.add("cannot_rest");
  if (opts.cannot_be_ko) set.add("cannot_be_ko");
  if (opts.effects_negated) set.add("effects_negated");
  if (opts.taunt) set.add("taunt");
  // Rush already means can attack this turn.
  if (set.has("rush") || set.has("rush_character")) {
    set.delete("summoning_sick");
    if (!opts.cannot_attack) set.delete("cannot_attack");
  }
  // 「剛登場」已說明本回合不能攻擊，勿再疊一層「不能攻擊」佔位。
  if (set.has("summoning_sick")) set.delete("cannot_attack");
  return STATUS_TAG_ORDER.filter((id) => set.has(id));
}

function statusTagLabel(id: StatusTagId, t: (key: string) => string): string {
  return t(`play.status.${id}`);
}

function actionMatch(actions: BattleAction[], type: string, extra: Record<string, unknown> = {}) {
  return actions.some((a) => {
    if (a.type !== type) return false;
    return Object.entries(extra).every(([k, v]) => a[k] === v || (v == null && (a[k] == null || a[k] === "")));
  });
}

/** Optional 「可以發動」window: activate via the source card menu, not a modal. */
function canActivatePendingEffect(actions: BattleAction[], sourceIid: string) {
  return actionMatch(actions, "confirm_effect", { accept: true, source_iid: sourceIid });
}

function canPlayPlain(actions: BattleAction[], handIndex: number) {
  return actions.some(
    (a) =>
      a.type === "play_card" &&
      a.hand_index === handIndex &&
      (a.replace_iid == null || a.replace_iid === ""),
  );
}

function needsReplacePlay(actions: BattleAction[], handIndex: number) {
  return actions.some((a) => a.type === "play_card" && a.hand_index === handIndex && a.replace_iid);
}

function phaseLabel(phase: string, t: (k: string) => string) {
  if (phase === "main") return t("play.phase_main");
  if (phase === "block") return t("play.phase_block");
  if (phase === "counter") return t("play.phase_counter");
  if (phase === "trigger") return t("play.phase_trigger");
  if (phase === "mulligan") return t("play.phase_mulligan");
  if (phase === "gameover") return t("play.phase_end");
  return phase;
}

type DecisionChromeSpec = {
  label: string;
  run: () => void;
  secondary?: { label: string; run: () => void };
};

function choicePurposeKey(purpose: string | undefined | null): string {
  const p = String(purpose || "general").trim().toLowerCase();
  const allowed = new Set([
    "ko",
    "trash",
    "buff",
    "rest",
    "return_hand",
    "bottom",
    "play",
    "attach_don",
    "return_don",
    "choose_effect",
    "life",
    "grant_keyword",
    "grant_cost",
    "reduce_cost",
    "set_active",
    "skip_untap",
    "replace_leave",
    "general",
  ]);
  return allowed.has(p) ? p : "general";
}

function localizeEffectOptionLabel(
  label: string,
  lang: Lang,
  t: (key: string, vars?: Record<string, string | number>) => string,
  optionId?: string,
): string {
  const iid = String(optionId || "").trim();
  if (iid === "life:top") return t("play.life_top");
  if (iid === "life:bottom") return t("play.life_bottom");
  if (iid === "don:active") {
    const m = /^don_active:(\d+)$/.exec(String(label || ""));
    return t("play.choice_don_active", { n: m ? Number(m[1]) : 1 });
  }
  if (iid === "don:rested") {
    const m = /^don_rested:(\d+)$/.exec(String(label || ""));
    return t("play.choice_don_rested", { n: m ? Number(m[1]) : 1 });
  }
  if (iid === "don:leader") {
    const m = /^don_leader:(\d+)$/.exec(String(label || ""));
    return t("play.choice_don_leader", { n: m ? Number(m[1]) : 1 });
  }
  if (iid.startsWith("don:char:")) {
    const m = /^don_char:(\d+):(.+)$/.exec(String(label || ""));
    const n = m ? Number(m[1]) : 1;
    const cid = m?.[2] || "";
    return t("play.choice_don_character", { n, id: cid });
  }

  const raw = String(label || "").trim();
  if (!raw) return raw;

  const key = raw.toLowerCase();
  const map: Record<string, string> = {
    "draw 2": t("play.opt_draw_n", { n: 2 }),
    "draw 1": t("play.opt_draw_n", { n: 1 }),
    "life top": t("play.life_top"),
    "life bottom": t("play.life_bottom"),
    "生命組上方": t("play.life_top"),
    "生命组上方": t("play.life_top"),
    "生命組下方": t("play.life_bottom"),
    "生命组下方": t("play.life_bottom"),
    "draw 2, trash 1, play dressrosa cost≤4": t("play.opt_op15_054_a"),
    "draw 2, trash 1, play dressrosa cost<=4": t("play.opt_op15_054_a"),
    "return up to 1 stage to owner's hand": t("play.opt_op15_054_b"),
    "dressrosa character gains blocker until opp end": t("play.opt_op15_055_blocker"),
    "dressrosa gains blocker": t("play.opt_op15_055_blocker"),
  };
  if (map[key] || map[raw]) return map[key] || map[raw];

  if (lang === "en") {
    const en = preferLangText(raw, "en");
    if (en) return en;
    return iid || t("play.choice_purpose_choose_effect");
  }
  if (hasCjk(raw)) return localizeCardText(raw, lang) || raw;
  return raw;
}

function displayEffectSummary(
  summary: string | null | undefined,
  lang: Lang,
): string {
  return localizeCardText(summary, lang) || "";
}

function skipEffectLabel(
  state: BattleState,
  sourceIid: string,
  cardId: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
): string {
  const src = String(sourceIid || "");
  const cid = String(cardId || "");
  const me = state.players.find((p) => p.seat === state.viewer_seat);
  if (src === "leader" || src.startsWith("leader")) return t("play.effect_skip_leader");
  if (me?.stages?.some((s) => s.iid === src)) return t("play.effect_skip_stage");
  if (me?.characters?.some((c) => c.iid === src)) return t("play.effect_skip_character");
  if (cid) {
    const nm = localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid;
    return t("play.effect_skip_named", { name: nm });
  }
  return t("play.effect_skip");
}

function resolveDecisionChrome(
  state: BattleState,
  onAction: (action: BattleAction) => void,
  t: (key: string, vars?: Record<string, string | number>) => string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
): DecisionChromeSpec | null {
  if (state.pending_choice || state.pending_search || state.pending_trigger) return null;
  if (state.viewer_seat == null) return null;
  const viewer = Number(state.viewer_seat);
  const legal = state.legal_actions;
  const accept = legal.find((a) => a.type === "confirm_effect" && a.accept === true);
  const skip = legal.find((a) => a.type === "confirm_effect" && a.accept === false);
  if (accept && state.pending_effect != null && Number(state.pending_effect.seat) === viewer) {
    const src = String(accept.source_iid || state.pending_effect.source_iid || "leader");
    return {
      label: t("play.menu_activate"),
      run: () => onAction({ type: "confirm_effect", accept: true, source_iid: src }),
      secondary:
        skip != null
          ? {
              label: skipEffectLabel(
                state,
                String(skip.source_iid || src),
                String(state.pending_effect.card_id || ""),
                t,
                names,
                lang,
              ),
              run: () =>
                onAction({
                  type: "confirm_effect",
                  accept: false,
                  source_iid: String(skip.source_iid || src),
                }),
            }
          : undefined,
    };
  }
  if (state.phase === "block" && actionMatch(legal, "block", { blocker_iid: null })) {
    return { label: t("play.no_block"), run: () => onAction({ type: "block", blocker_iid: null }) };
  }
  if (state.phase === "counter" && actionMatch(legal, "pass_counter")) {
    return { label: t("play.pass_counter"), run: () => onAction({ type: "pass_counter" }) };
  }
  return null;
}

function localizeLogCardId(
  raw: string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
): string {
  const cid = String(raw || "").trim();
  if (BATTLE_CARD_ID_ONE.test(cid)) {
    return localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid;
  }
  return cid;
}

function LogCardChip({
  cardId,
  label,
  onOpenDetail,
}: {
  cardId: string;
  label: string;
  onOpenDetail: (cardId: string) => void;
}) {
  const [hover, setHover] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [previewPos, setPreviewPos] = useState<{ left: number; top: number } | null>(null);
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  const show = hover || pinned;

  const updatePreviewPos = useCallback(() => {
    const el = wrapRef.current;
    if (!el || typeof window === "undefined") return;
    const rect = el.getBoundingClientRect();
    const previewW = 112;
    const previewH = 168;
    const gap = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = rect.left + rect.width / 2 - previewW / 2;
    left = Math.max(8, Math.min(left, vw - previewW - 8));
    // Prefer below the name; flip above if it would hit the bottom chrome / chat.
    let top = rect.bottom + gap;
    if (top + previewH > vh - 12) {
      top = Math.max(8, rect.top - gap - previewH);
    }
    setPreviewPos({ left, top });
  }, []);

  useLayoutEffect(() => {
    if (!show) {
      setPreviewPos(null);
      return;
    }
    updatePreviewPos();
  }, [show, updatePreviewPos, label, cardId]);

  useEffect(() => {
    if (!show) return;
    const onMove = () => updatePreviewPos();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [show, updatePreviewPos]);

  useEffect(() => {
    if (!pinned) return;
    const onDoc = (ev: Event) => {
      const el = wrapRef.current;
      if (el && ev.target instanceof Node && !el.contains(ev.target)) {
        setPinned(false);
      }
    };
    document.addEventListener("pointerdown", onDoc, true);
    return () => document.removeEventListener("pointerdown", onDoc, true);
  }, [pinned]);

  const preview =
    show && previewPos && typeof document !== "undefined"
      ? createPortal(
          <span
            className="ux-log-card-preview is-portal"
            role="tooltip"
            style={{ left: previewPos.left, top: previewPos.top }}
          >
            <CardImg cardId={cardId} className="ux-log-card-preview-img" loading="eager" alt={label} />
            <span className="ux-log-card-preview-meta">{cardId}</span>
          </span>,
          document.body,
        )
      : null;

  return (
    <span
      ref={wrapRef}
      className={`ux-log-card-wrap ${show ? "is-open" : ""}`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        className="ux-log-card"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          const fineHover =
            typeof window !== "undefined" && window.matchMedia("(hover: hover) and (pointer: fine)").matches;
          if (fineHover) {
            onOpenDetail(cardId);
            return;
          }
          setPinned((v) => !v);
        }}
      >
        {label}
      </button>
      {preview}
    </span>
  );
}

function cardChipOrText(
  raw: string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
  onOpenDetail: (cardId: string) => void,
): ReactNode {
  const cid = String(raw || "").trim();
  if (!BATTLE_CARD_ID_ONE.test(cid)) return cid;
  return (
    <LogCardChip
      cardId={cid}
      label={localizeLogCardId(cid, names, lang)}
      onOpenDetail={onOpenDetail}
    />
  );
}

function renderIdsChips(
  raw: string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
  onOpenDetail: (cardId: string) => void,
): ReactNode {
  const parts = String(raw)
    .split(/[,，、]/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (!parts.length) return null;
  const sep = lang === "en" ? ", " : "、";
  return parts.map((part, i) => (
    <span key={`${part}-${i}`}>
      {i > 0 ? sep : null}
      {cardChipOrText(part, names, lang, onOpenDetail)}
    </span>
  ));
}

function renderBattleLog(
  entry: string | BattleLogEntry,
  t: (key: string, vars?: Record<string, string | number>) => string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
  onOpenDetail: (cardId: string) => void,
): ReactNode {
  if (typeof entry === "string") {
    return renderLegacyLogRich(entry, t, names, lang, onOpenDetail);
  }
  const { key, ...rest } = entry;
  let logKey = key;
  if (key === "play.log.trashes" && typeof rest.n === "number") {
    logKey = "play.log.trashes_many";
  }
  const stringVars: Record<string, string | number> = {};
  let idRaw: string | null = null;
  let idsRaw: string | null = null;
  for (const [k, v] of Object.entries(rest)) {
    if (v == null) continue;
    let value: string | number = typeof v === "boolean" ? (v ? "1" : "0") : (v as string | number);
    if ((k === "target" || k === "attacker") && value === "leader") {
      value = t("play.zone_leader");
    } else if (k === "id") {
      idRaw = String(value);
      value = localizeLogCardId(idRaw, names, lang);
    } else if (k === "ids") {
      idsRaw = String(value);
      value = idsRaw
        .split(/[,，、]/)
        .map((part) => localizeLogCardId(part.trim(), names, lang))
        .filter(Boolean)
        .join(lang === "en" ? ", " : "、");
    } else if (k === "summary") {
      const s = String(value);
      value = displayEffectSummary(s, lang) || (lang === "en" ? "" : s);
    }
    stringVars[k] = value;
  }
  const MARK_ID = "⟦CARD_ID⟧";
  const MARK_IDS = "⟦CARD_IDS⟧";
  const renderVars = { ...stringVars };
  if (idRaw && BATTLE_CARD_ID_ONE.test(idRaw)) renderVars.id = MARK_ID;
  if (idsRaw) renderVars.ids = MARK_IDS;
  const localized = t(logKey, renderVars);
  if (localized === logKey) {
    if (typeof rest.text === "string") return renderLegacyLogRich(rest.text, t, names, lang, onOpenDetail);
    return logKey;
  }
  if (!idRaw && !idsRaw) return localized;
  if (!localized.includes(MARK_ID) && !localized.includes(MARK_IDS)) {
    // Fallback: plain localized names (no interactive chips)
    return t(logKey, stringVars);
  }
  const nodes: ReactNode[] = [];
  let remaining = localized;
  let keyIdx = 0;
  while (remaining.length) {
    const iId = remaining.indexOf(MARK_ID);
    const iIds = remaining.indexOf(MARK_IDS);
    let next = -1;
    let which: "id" | "ids" | null = null;
    if (iId >= 0 && (iIds < 0 || iId <= iIds)) {
      next = iId;
      which = "id";
    } else if (iIds >= 0) {
      next = iIds;
      which = "ids";
    }
    if (next < 0 || !which) {
      nodes.push(remaining);
      break;
    }
    if (next > 0) nodes.push(remaining.slice(0, next));
    if (which === "id" && idRaw) {
      nodes.push(
        <span key={`id-${keyIdx++}`}>{cardChipOrText(idRaw, names, lang, onOpenDetail)}</span>,
      );
      remaining = remaining.slice(next + MARK_ID.length);
    } else if (which === "ids" && idsRaw) {
      nodes.push(
        <span key={`ids-${keyIdx++}`}>{renderIdsChips(idsRaw, names, lang, onOpenDetail)}</span>,
      );
      remaining = remaining.slice(next + MARK_IDS.length);
    } else {
      nodes.push(remaining.slice(next, next + 1));
      remaining = remaining.slice(next + 1);
    }
  }
  return <>{nodes}</>;
}

function renderLegacyLogRich(
  line: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
  onOpenDetail: (cardId: string) => void,
): ReactNode {
  const plain = localizeLegacyLog(line, t, names, lang);
  const matches = [...plain.matchAll(BATTLE_CARD_ID_RE)];
  if (!matches.length) return plain;
  const nodes: ReactNode[] = [];
  let last = 0;
  matches.forEach((m, i) => {
    const start = m.index ?? 0;
    if (start > last) nodes.push(plain.slice(last, start));
    const cid = m[0];
    nodes.push(
      <LogCardChip
        key={`${cid}-${i}-${start}`}
        cardId={cid}
        label={localizeLogCardId(cid, names, lang)}
        onOpenDetail={onOpenDetail}
      />,
    );
    last = start + cid.length;
  });
  if (last < plain.length) nodes.push(plain.slice(last));
  return <>{nodes}</>;
}

/** Translate older English plain-text battle logs (pre structured i18n). */
function localizeLegacyLog(
  line: string,
  t: (key: string, vars?: Record<string, string | number>) => string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
) {
  const s = line.trim();
  let m: RegExpMatchArray | null;
  if ((m = s.match(/^(.+?) will go first — mulligan starting/))) {
    return t("play.log.first_mulligan", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) sets (\d+) Life\.?$/))) {
    return t("play.log.sets_life", { name: m[1], n: m[2] });
  }
  if ((m = s.match(/^(.+?) starts turn 1\.?$/))) {
    return t("play.log.starts_turn1", { name: m[1] });
  }
  if ((m = s.match(/^(.+?)'s first turn — no attacks/))) {
    return t("play.log.first_turn_no_attack", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) mulligans\.?$/))) {
    return t("play.log.mulligans", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) keeps opening hand\.?$/))) {
    return t("play.log.keeps_hand", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) plays event ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.plays_event", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) plays Counter event ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.counter_event", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) plays ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.plays", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) sets stage ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.sets_stage", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) attaches 1 DON!!\.?$/))) {
    return t("play.log.attach_don", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) attacks with (.+?) → (.+?) \((\d+) power\) \[Blockerless\]\.?$/))) {
    return t("play.log.attack_blockerless", {
      name: m[1],
      attacker: m[2] === "leader" ? t("play.zone_leader") : m[2],
      target: m[3] === "leader" ? t("play.zone_leader") : m[3],
      power: m[4],
    });
  }
  if ((m = s.match(/^(.+?) attacks with (.+?) → (.+?) \((\d+) power\)\.?$/))) {
    return t("play.log.attack", {
      name: m[1],
      attacker: m[2] === "leader" ? t("play.zone_leader") : m[2],
      target: m[3] === "leader" ? t("play.zone_leader") : m[3],
      power: m[4],
    });
  }
  if ((m = s.match(/^(.+?) blocks with ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.blocks", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) does not block\.?$/))) {
    return t("play.log.no_block", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) counters with ([A-Z0-9-]+) \(\+(\d+) on (.+?)\)\.?$/))) {
    return t("play.log.counters", {
      name: m[1],
      id: localizeLogCardId(m[2], names, lang),
      bonus: m[3],
      target: m[4] === "leader" ? t("play.zone_leader") : m[4],
    });
  }
  if ((m = s.match(/^(.+?) takes 1 life \(Banish\) \((\d+) left\)\.?$/))) {
    return t("play.log.life_banish", { name: m[1], left: m[2] });
  }
  if ((m = s.match(/^(.+?) takes 1 life \((\d+) left\)\.?$/))) {
    return t("play.log.life_taken", { name: m[1], left: m[2] });
  }
  if ((m = s.match(/^(.+?) may activate Trigger on ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.trigger_offer", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) activates Trigger on ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.trigger_yes", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) declines Trigger \(([A-Z0-9-]+) to hand\)\.?$/))) {
    return t("play.log.trigger_no", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^Turn passes to (.+?)\.?$/))) {
    return t("play.log.turn_passes", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) wins!?$/))) {
    return t("play.log.wins", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) decks out\.?$/))) {
    return t("play.log.decks_out", { name: m[1] });
  }
  if ((m = s.match(/^(.+?) draws (\d+)\.?$/))) {
    return t("play.log.draws", { name: m[1], n: m[2] });
  }
  if ((m = s.match(/^(.+?) gains (\d+) DON!!\.?$/))) {
    return t("play.log.gains_don", { name: m[1], n: m[2] });
  }
  if ((m = s.match(/^([A-Z0-9-]+) is K\.O\.'d\.?$/))) {
    return t("play.log.ko", { id: localizeLogCardId(m[1], names, lang) });
  }
  if (s === "Attack on leader fails." || s === "Attack on leader fails") {
    return t("play.log.attack_leader_fails");
  }
  if (s === "Attack fails." || s === "Attack fails") {
    return t("play.log.attack_fails");
  }
  if (s === "Effect skipped by player." || s === "Effect skipped by player") {
    return t("play.log.effect_skipped");
  }
  if ((m = s.match(/^(.+?) activates Main on ([A-Z0-9-]+)\.?$/))) {
    return t("play.log.activate_main", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  if ((m = s.match(/^(.+?) trashes ([A-Z0-9-]+) for space/))) {
    return t("play.log.trash_for_space", { name: m[1], id: localizeLogCardId(m[2], names, lang) });
  }
  return line;
}

function BattleModal({
  children,
  layerClassName = "",
  modalClassName = "",
}: {
  children: ReactNode;
  layerClassName?: string;
  modalClassName?: string;
}) {
  return (
    <div className={`battle-modal-layer ${layerClassName}`.trim()} role="presentation" onMouseDown={(e) => e.stopPropagation()}>
      <div
        className={`battle-modal ${modalClassName}`.trim()}
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function formatPower(power?: number | string | null) {
  if (power == null || power === "") return null;
  const n = typeof power === "number" ? power : Number(String(power).replace(/[^\d.-]/g, ""));
  if (!Number.isFinite(n)) return String(power);
  if (Math.abs(n) >= 1000 && n % 1000 === 0) return `${n / 1000}k`;
  return String(n);
}

function formatCounter(counter?: number | string | null) {
  if (counter == null || counter === "") return null;
  const n = typeof counter === "number" ? counter : Number(String(counter).replace(/[^\d.-]/g, ""));
  if (!Number.isFinite(n) || n <= 0) return null;
  if (n >= 1000 && n % 1000 === 0) return `+${n / 1000}k`;
  return `+${n}`;
}

function battleToken(seat: number, iid: string) {
  return `${seat}:${iid}`;
}

function unitLabel(
  player: BattlePlayerView | undefined,
  iid: string,
  names: Record<string, DeckStatFields>,
  lang: Lang,
  t: (k: string) => string,
) {
  if (!player) return iid;
  if (iid === "leader") {
    const id = player.leader_card_id;
    return localizeCardName(names[id]?.name, names[id]?.name_en, lang) || t("play.zone_leader");
  }
  const ch = player.characters.find((c) => c.iid === iid) || player.stages.find((c) => c.iid === iid);
  if (!ch) return iid;
  return localizeCardName(names[ch.card_id]?.name, names[ch.card_id]?.name_en, lang) || ch.card_id;
}

type AttackLine = { x1: number; y1: number; x2: number; y2: number; w: number; h: number };

function AttackArrowOverlay({
  playmatRef,
  fromToken,
  toToken,
  revision,
}: {
  playmatRef: RefObject<HTMLDivElement | null>;
  fromToken: string | null;
  toToken: string | null;
  revision: string;
}) {
  const [line, setLine] = useState<AttackLine | null>(null);

  useLayoutEffect(() => {
    const root = playmatRef.current;
    if (!root || !fromToken || !toToken) {
      setLine(null);
      return;
    }

    const measure = () => {
      const fromEl = root.querySelector(`[data-ux-token="${fromToken}"]`) as HTMLElement | null;
      const toEl = root.querySelector(`[data-ux-token="${toToken}"]`) as HTMLElement | null;
      if (!fromEl || !toEl) {
        setLine(null);
        return;
      }
      const rootBox = root.getBoundingClientRect();
      const a = fromEl.getBoundingClientRect();
      const b = toEl.getBoundingClientRect();
      setLine({
        w: rootBox.width,
        h: rootBox.height,
        x1: a.left + a.width / 2 - rootBox.left,
        y1: a.top + a.height / 2 - rootBox.top,
        x2: b.left + b.width / 2 - rootBox.left,
        y2: b.top + b.height / 2 - rootBox.top,
      });
    };

    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(root);
    window.addEventListener("resize", measure);
    const t = window.setTimeout(measure, 40);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", measure);
      window.clearTimeout(t);
    };
  }, [playmatRef, fromToken, toToken, revision]);

  if (!line || !fromToken || !toToken) return null;

  const dx = line.x2 - line.x1;
  const dy = line.y2 - line.y1;
  const len = Math.hypot(dx, dy) || 1;
  // Shorten so arrowheads don't cover card centers
  const inset = Math.min(36, len * 0.22);
  const ux = dx / len;
  const uy = dy / len;
  const x1 = line.x1 + ux * inset;
  const y1 = line.y1 + uy * inset;
  const x2 = line.x2 - ux * inset;
  const y2 = line.y2 - uy * inset;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2 - Math.min(28, len * 0.12);
  const path = `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`;

  return (
    <svg className="ux-attack-arrow" width={line.w} height={line.h} viewBox={`0 0 ${line.w} ${line.h}`} aria-hidden>
      <defs>
        <marker id="ux-attack-head" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L8,3 L0,6 Z" className="ux-attack-arrow-head" />
        </marker>
        <filter id="ux-attack-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="2.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path className="ux-attack-arrow-trail" d={path} />
      <path className="ux-attack-arrow-line" d={path} markerEnd="url(#ux-attack-head)" filter="url(#ux-attack-glow)" />
    </svg>
  );
}

function formatEffectForPanel(text: string): string {
  return formatEffectLines(text);
}

function MatCard({
  cardId,
  label,
  rested,
  power,
  cost,
  counter,
  selected,
  legal,
  size = "md",
  statuses,
  onClick,
}: {
  cardId: string;
  label?: string;
  rested?: boolean;
  power?: number | string | null;
  cost?: number | string | null;
  counter?: number | string | null;
  selected?: boolean;
  legal?: boolean;
  size?: "sm" | "md" | "lg" | "hand";
  statuses?: StatusTagId[];
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void;
}) {
  const { t } = useI18n();
  const powerText = formatPower(power);
  const counterText = formatCounter(counter);
  const allTags = statuses || [];
  const restrictionTags = allTags.filter((id) => STATUS_RESTRICTION_IDS.has(id));
  const keywordTags = allTags.filter((id) => !STATUS_RESTRICTION_IDS.has(id));
  const chipTags = [...restrictionTags, ...keywordTags].slice(0, 4);
  const chipExtra = Math.max(0, restrictionTags.length + keywordTags.length - chipTags.length);
  const statusClass = restrictionTags.map((id) => `has-restriction-${id}`).join(" ");
  return (
    <button
      type="button"
      className={`ux-card size-${size} ${rested ? "is-rested" : ""} ${selected ? "is-selected" : ""} ${legal ? "is-legal" : ""} ${onClick ? "is-clickable" : ""} ${allTags.length ? "has-status" : ""} ${restrictionTags.length ? "has-restriction" : ""} ${statusClass}`}
      onClick={onClick}
      disabled={!onClick}
      title={[label, ...allTags.map((id) => statusTagLabel(id, t))].filter(Boolean).join(" · ")}
    >
      <CardImg cardId={cardId} className="ux-card-img" />
      {cost != null && cost !== "" ? <span className="ux-badge cost">{cost}</span> : null}
      {powerText != null ? <span className="ux-badge power">{powerText}</span> : null}
      {counterText != null ? <span className="ux-badge counter">{counterText}</span> : null}
      {chipTags.length ? (
        <span className="ux-status-tags" aria-hidden>
          {chipTags.map((id) => (
            <span
              key={id}
              className={`ux-status-tag is-${id}${STATUS_RESTRICTION_IDS.has(id) ? " is-restriction" : ""}`}
            >
              {statusTagLabel(id, t)}
            </span>
          ))}
          {chipExtra > 0 ? <span className="ux-status-tag is-more">+{chipExtra}</span> : null}
        </span>
      ) : null}
    </button>
  );
}

function ZoneSlot({
  label,
  tone,
  children,
  className = "",
}: {
  label: string;
  tone?: "life" | "deck" | "trash" | "don" | "stage" | "char" | "leader";
  count?: number | string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`ux-zone tone-${tone || "default"} ${className}`} aria-label={label}>
      <div className="ux-zone-body">{children}</div>
    </div>
  );
}

function CardBack({
  label,
  kind = "deck",
}: {
  label?: string;
  kind?: "deck" | "life" | "hand" | "don" | "leader";
}) {
  const src =
    kind === "don"
      ? "/battle/don-back.png"
      : kind === "leader"
        ? "/battle/leader-back.png"
        : "/battle/card-back.png";
  return (
    <div className={`ux-card-back kind-${kind}`} aria-hidden>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt="" className="ux-card-back-img" />
      {label != null && label !== "" ? <span className="ux-card-back-count">{label}</span> : null}
    </div>
  );
}

function DonToken({
  rested,
  clickable,
  draggable: canDrag,
  onClick,
  compact,
}: {
  rested?: boolean;
  clickable?: boolean;
  draggable?: boolean;
  onClick?: () => void;
  compact?: boolean;
}) {
  const onDragStart = (event: DragEvent) => {
    if (!canDrag) return;
    event.dataTransfer.setData(DON_DRAG_MIME, "1");
    event.dataTransfer.setData("text/plain", "don");
    event.dataTransfer.effectAllowed = "move";
    document.body.classList.add("is-dragging-don");
  };
  const onDragEnd = () => {
    document.body.classList.remove("is-dragging-don");
  };
  const inner = (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/battle/don-front.png" alt="DON!!" className="ux-don-card-img" draggable={false} />
  );
  const dragProps = canDrag
    ? {
        draggable: true as const,
        onDragStart,
        onDragEnd,
      }
    : {};
  return (
    <span
      className={`ux-don-wrap ${rested ? "is-rested" : ""} ${canDrag ? "is-draggable" : ""} ${compact ? "is-compact" : ""}`}
    >
      {clickable || canDrag ? (
        <button
          type="button"
          className="ux-don-card is-active"
          onClick={onClick}
          title={canDrag ? "Tap a character / leader, or drag" : "+DON"}
          {...dragProps}
        >
          {inner}
        </button>
      ) : (
        <span className="ux-don-card">{inner}</span>
      )}
    </span>
  );
}

/** One full-size DON!! under Leader / Character; count badge for how many are attached. */
function AttachedDonStack({ count }: { count: number }) {
  const n = Math.max(0, Number(count) || 0);
  if (n <= 0) return null;
  return (
    <div className="ux-don-attached" aria-label={`DON!! ×${n}`}>
      <span className="ux-don-on">×{n}</span>
      <DonToken />
    </div>
  );
}

/** Face-down / face-up Life card — same rested footprint / stack geometry as DON. */
function LifeToken({
  faceUp = false,
  cardId = null,
}: {
  faceUp?: boolean;
  cardId?: string | null;
}) {
  return (
    <span className={`ux-life-wrap ${faceUp && cardId ? "is-face-up" : ""}`}>
      <span className={`ux-life-card ${faceUp && cardId ? "is-face-up" : ""}`} aria-hidden>
        {faceUp && cardId ? (
          <CardImg cardId={cardId} className="ux-life-card-img" loading="eager" />
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/battle/card-back.png" alt="" className="ux-life-card-img" draggable={false} />
          </>
        )}
      </span>
    </span>
  );
}

function SideBoard({
  player,
  mine,
  names,
  lang,
  state,
  attacker,
  replaceHandIndex,
  selectedHandIndex,
  attackMark,
  onSelectAttacker,
  onTarget,
  onAttach,
  donArmed = false,
  onArmDon,
  onDisarmDon,
  onPlayHand,
  onReplaceChar,
  onCardMenu,
  onOpenTrash,
  choiceHoverIid = null,
  decisionChrome = null,
  actionBusy = false,
  replayMode = false,
}: {
  player: BattlePlayerView;
  mine: boolean;
  names: Record<string, DeckStatFields>;
  lang: Lang;
  state: BattleState;
  attacker: string | null;
  replaceHandIndex: number | null;
  selectedHandIndex?: number | null;
  attackMark?: Record<string, "attacker" | "target" | "blocker">;
  onSelectAttacker: (iid: string) => void;
  onTarget: (iid: string) => void;
  onAttach: (iid: string) => void;
  donArmed?: boolean;
  onArmDon?: () => void;
  onDisarmDon?: () => void;
  onPlayHand: (index: number, anchor?: { x: number; y: number }, cardId?: string) => void;
  onReplaceChar: (iid: string) => void;
  onCardMenu: (
    target: { iid: string; cardId: string; donAttached: number; mine: boolean },
    anchor?: { x: number; y: number },
  ) => void;
  onOpenTrash?: () => void;
  choiceHoverIid?: string | null;
  decisionChrome?: DecisionChromeSpec | null;
  actionBusy?: boolean;
  replayMode?: boolean;
}) {
  const { t } = useI18n();
  const legal = state.legal_actions;
  const [donDropIid, setDonDropIid] = useState<string | null>(null);
  const nameOf = (id: string) => localizeCardName(names[id]?.name, names[id]?.name_en, lang) || id;
  const costOf = (id: string, inst?: { cost_mod?: number; cost?: number }) => {
    if (typeof inst?.cost === "number") return inst.cost;
    const base = names[id]?.cost;
    if (base == null) return null;
    return base + (inst?.cost_mod ?? 0);
  };
  const counterOf = (id: string, idx: number) => {
    const fromLegal = legal.find((a) => a.type === "counter" && a.hand_index === idx);
    if (typeof fromLegal?.counter === "number") return fromLegal.counter;
    return names[id]?.counter ?? null;
  };
  const showHandCounters =
    mine && (state.phase === "counter" || state.phase === "block");
  const handChoiceOptions =
    mine && state.pending_choice?.target_kind === "hand_card" ? state.pending_choice.options || [] : [];
  const handChoiceLegal = (idx: number, cid: string) =>
    handChoiceOptions.some((o) => o === `hand:${idx}:${cid}` || o.endsWith(`:${cid}`));
  const markClass = (iid: string) => {
    const role = attackMark?.[iid];
    if (role === "attacker") return "is-attack-source";
    if (role === "blocker") return "is-attack-blocker";
    if (role === "target") return "is-attack-target";
    return "";
  };
  const replacing = mine && replaceHandIndex != null;
  const canBlockWith = (iid: string) =>
    mine && state.phase === "block" && actionMatch(legal, "block", { blocker_iid: iid });
  const stage = player.stages[0];
  const slots: Array<BattleChar | null> = Array.from({ length: 5 }, (_, i) => player.characters[i] || null);
  const canAttachLeader = mine && actionMatch(legal, "attach_don", { target_iid: "leader" });
  const canDragActiveDon = mine && legal.some((a) => a.type === "attach_don");
  const canAttachTo = (iid: string) => mine && actionMatch(legal, "attach_don", { target_iid: iid });
  const attachIfArmed = (iid: string) => {
    if (!donArmed || !canAttachTo(iid)) return false;
    onAttach(iid);
    onDisarmDon?.();
    return true;
  };
  const onDonTokenClick = () => {
    if (!mine || !canDragActiveDon) return;
    if (donArmed) {
      onDisarmDon?.();
      return;
    }
    // Mobile / coarse pointers: arm then tap a card. Fine pointer: keep one-tap → leader.
    const coarse =
      typeof window !== "undefined" &&
      (window.matchMedia("(pointer: coarse)").matches || window.matchMedia("(max-width: 900px)").matches);
    if (coarse) {
      onArmDon?.();
      return;
    }
    if (canAttachLeader) onAttach("leader");
  };
  const isDonDrag = (event: DragEvent) =>
    Array.from(event.dataTransfer.types || []).some((t) => t === DON_DRAG_MIME || t === "text/plain");
  const onDonDragOver = (iid: string) => (event: DragEvent) => {
    if (!canAttachTo(iid) || !isDonDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    if (donDropIid !== iid) setDonDropIid(iid);
  };
  const onDonDragLeave = (iid: string) => (event: DragEvent) => {
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    if (donDropIid === iid) setDonDropIid(null);
  };
  const onDonDrop = (iid: string) => (event: DragEvent) => {
    event.preventDefault();
    setDonDropIid(null);
    document.body.classList.remove("is-dragging-don");
    if (!canAttachTo(iid)) return;
    onAttach(iid);
  };
  const donLeft = Math.max(0, (player.don_deck_size ?? 10) - player.don_given);

  const lifeCount = Math.max(0, Math.min(20, Number(player.life) || 0));
  const lifeFaces = player.life_faces || [];
  const lifeZone = (
    <ZoneSlot label={t("play.life")} tone="life" className="is-board">
      {lifeCount > 0 ? (
        <div className={`ux-life-rail ${mine ? "is-mine" : "is-foe"}`} title={`${lifeCount}`}>
          <div className="ux-life-stack" aria-label={`${t("play.life")} ${lifeCount}`}>
            {Array.from({ length: lifeCount }).map((_, i) => {
              const face = lifeFaces[i];
              return (
                <LifeToken
                  key={`life-${i}-${face?.card_id || "back"}`}
                  faceUp={Boolean(face?.face_up && face?.card_id)}
                  cardId={face?.card_id || null}
                />
              );
            })}
          </div>
          {lifeCount > 5 ? <span className="ux-life-count">{lifeCount}</span> : null}
        </div>
      ) : (
        <div className="ux-slot-empty" />
      )}
    </ZoneSlot>
  );

  const deckZone = (
    <ZoneSlot label={t("play.deck")} tone="deck" className="is-board">
      {player.deck_count > 0 ? <CardBack kind="deck" label={String(player.deck_count)} /> : <div className="ux-slot-empty" />}
    </ZoneSlot>
  );

  const openFieldMenu = (
    iid: string,
    cardId: string,
    donAttached: number,
    isMine: boolean,
    event: MouseEvent<HTMLButtonElement>,
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    onCardMenu(
      { iid, cardId, donAttached, mine: isMine },
      { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
    );
  };

  const chars = (
    <div className={`ux-chars ${mine && decisionChrome ? "has-decision-chrome" : ""}`} aria-label={t("play.zone_character")}>
      {slots.map((ch, i) =>
        ch ? (
          <div
            key={ch.iid}
            className={`ux-char ${markClass(ch.iid)} ${canBlockWith(ch.iid) ? "is-blockable" : ""} ${donDropIid === ch.iid ? "is-don-drop" : ""} ${canAttachTo(ch.iid) ? "is-don-droppable" : ""} ${choiceHoverIid === ch.iid ? "is-choice-focus" : ""}`}
            data-ux-token={battleToken(player.seat, ch.iid)}
            onDragOver={onDonDragOver(ch.iid)}
            onDragLeave={onDonDragLeave(ch.iid)}
            onDrop={onDonDrop(ch.iid)}
          >
            {ch.don_attached > 0 ? <AttachedDonStack count={ch.don_attached} /> : null}
            <MatCard
              cardId={ch.card_id}
              label={nameOf(ch.card_id)}
              rested={ch.rested}
              power={ch.power}
              cost={costOf(ch.card_id, ch)}
              size="md"
              statuses={collectStatusTags({
                keywords: ch.keywords,
                cannot_attack: ch.cannot_attack,
                cannot_rest: ch.cannot_rest,
                cannot_be_ko: ch.cannot_be_ko,
                effects_negated: ch.effects_negated,
                taunt: ch.taunt,
                summoning_sick: ch.summoning_sick,
              })}
              selected={attacker === ch.iid || choiceHoverIid === ch.iid}
              legal={
                replacing
                  ? actionMatch(legal, "play_card", { hand_index: replaceHandIndex, replace_iid: ch.iid })
                  : actionMatch(legal, "select_choice", { target_iid: ch.iid })
                    ? true
                    : canBlockWith(ch.iid)
                      ? true
                      : mine
                        ? actionMatch(legal, "attack", { attacker_iid: ch.iid }) ||
                          actionMatch(legal, "attach_don", { target_iid: ch.iid }) ||
                          actionMatch(legal, "remove_don", { target_iid: ch.iid }) ||
                          actionMatch(legal, "activate_main", { source_iid: ch.iid }) ||
                          canActivatePendingEffect(legal, ch.iid)
                        : Boolean(attacker && actionMatch(legal, "attack", { attacker_iid: attacker, target_iid: ch.iid }))
              }
              onClick={
                actionMatch(legal, "select_choice", { target_iid: ch.iid })
                  ? (event) => openFieldMenu(ch.iid, ch.card_id, ch.don_attached, mine, event)
                  : donArmed && canAttachTo(ch.iid)
                  ? () => attachIfArmed(ch.iid)
                  : replacing
                  ? () => onReplaceChar(ch.iid)
                  : mine
                    ? (event) => {
                        if (attachIfArmed(ch.iid)) return;
                        openFieldMenu(ch.iid, ch.card_id, ch.don_attached, true, event);
                      }
                    : attacker
                      ? () => onTarget(ch.iid)
                      : (event) => openFieldMenu(ch.iid, ch.card_id, ch.don_attached, false, event)
              }
            />
            {attackMark?.[ch.iid] === "attacker" ? <span className="ux-attack-tag is-source">{t("play.attack_tag_source")}</span> : null}
            {attackMark?.[ch.iid] === "target" ? <span className="ux-attack-tag is-target">{t("play.attack_tag_target")}</span> : null}
            {attackMark?.[ch.iid] === "blocker" ? <span className="ux-attack-tag is-blocker">{t("play.attack_tag_blocker")}</span> : null}
          </div>
        ) : (
          <div key={`e${i}`} className="ux-char is-empty">
            <div className="ux-slot-empty dim">{i + 1}</div>
          </div>
        ),
      )}
      {mine && decisionChrome ? (
        <div className="ux-decision-chrome" role="group" aria-label={t("play.hint_title")}>
          <button
            type="button"
            className="ux-decision-chrome-btn"
            disabled={actionBusy}
            onClick={() => decisionChrome.run()}
          >
            {decisionChrome.label}
          </button>
          {decisionChrome.secondary ? (
            <button
              type="button"
              className="ux-decision-chrome-btn is-secondary"
              disabled={actionBusy}
              onClick={() => decisionChrome.secondary?.run()}
            >
              {decisionChrome.secondary.label}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );

  const donActiveCount = Math.max(0, player.don_active);
  const donRestedCount = Math.max(0, player.don_rested);
  const donTokens = (
    <div className="ux-don-open">
      <div className="ux-don-cost-row">
        {donActiveCount > 0 ? (
          <div className="ux-don-stack is-active" aria-label={`DON!! ×${donActiveCount}`}>
            {Array.from({ length: donActiveCount }).map((_, i) => (
              <DonToken
                key={`a${i}`}
                clickable={mine && canDragActiveDon}
                draggable={canDragActiveDon}
                onClick={mine && canDragActiveDon ? onDonTokenClick : undefined}
              />
            ))}
          </div>
        ) : null}
        {donRestedCount > 0 ? (
          <div className="ux-don-stack is-rested" aria-label={`DON!! rested ×${donRestedCount}`}>
            {Array.from({ length: donRestedCount }).map((_, i) => (
              <DonToken key={`r${i}`} rested />
            ))}
          </div>
        ) : null}
        {donActiveCount + donRestedCount === 0 ? <span className="ux-don-slot" /> : null}
      </div>
    </div>
  );

  const donBlock = (
    <div className={`ux-row-2-don ${mine ? "is-mine" : "is-foe"}`}>
      {mine ? (
        <>
          <ZoneSlot label="DON!!" tone="don" className="is-board">
            {donLeft > 0 ? <CardBack kind="don" label={String(donLeft)} /> : <div className="ux-slot-empty" />}
          </ZoneSlot>
          {donTokens}
        </>
      ) : (
        <>
          {donTokens}
          <ZoneSlot label="DON!!" tone="don" className="is-board">
            {donLeft > 0 ? <CardBack kind="don" label={String(donLeft)} /> : <div className="ux-slot-empty" />}
          </ZoneSlot>
        </>
      )}
    </div>
  );

  const leaderZone = (
    <ZoneSlot label={t("play.zone_leader")} tone="leader" className="is-field">
      <div
        className={`ux-card-stack ${markClass("leader")} ${donDropIid === "leader" ? "is-don-drop" : ""} ${canAttachLeader ? "is-don-droppable" : ""} ${choiceHoverIid === "leader" ? "is-choice-focus" : ""}`}
        data-ux-token={battleToken(player.seat, "leader")}
        onDragOver={onDonDragOver("leader")}
        onDragLeave={onDonDragLeave("leader")}
        onDrop={onDonDrop("leader")}
      >
        {player.leader_don > 0 ? <AttachedDonStack count={player.leader_don} /> : null}
        <MatCard
          cardId={player.leader_card_id}
          label={nameOf(player.leader_card_id)}
          rested={player.leader_rested}
          power={player.leader_power}
          cost={costOf(player.leader_card_id)}
          size="lg"
          statuses={collectStatusTags({
            keywords: player.leader_keywords,
            cannot_attack: player.leader_cannot_attack,
          })}
          selected={attacker === "leader" || choiceHoverIid === "leader"}
          legal={
            actionMatch(legal, "select_choice", { target_iid: "leader" })
              ? true
              : mine
                ? actionMatch(legal, "attack", { attacker_iid: "leader" }) ||
                  canAttachLeader ||
                  actionMatch(legal, "remove_don", { target_iid: "leader" }) ||
                  actionMatch(legal, "activate_main", { source_iid: "leader" }) ||
                  canActivatePendingEffect(legal, "leader")
                : Boolean(attacker && actionMatch(legal, "attack", { attacker_iid: attacker, target_iid: "leader" }))
          }
          onClick={
            actionMatch(legal, "select_choice", { target_iid: "leader" })
              ? (event) => openFieldMenu("leader", player.leader_card_id, player.leader_don, mine, event)
              : donArmed && canAttachLeader
              ? () => attachIfArmed("leader")
              : mine
              ? (event) => {
                  if (attachIfArmed("leader")) return;
                  openFieldMenu("leader", player.leader_card_id, player.leader_don, true, event);
                }
              : attacker
                ? () => onTarget("leader")
                : (event) => openFieldMenu("leader", player.leader_card_id, player.leader_don, false, event)
          }
        />
        {attackMark?.leader === "attacker" ? <span className="ux-attack-tag is-source">{t("play.attack_tag_source")}</span> : null}
        {attackMark?.leader === "target" ? <span className="ux-attack-tag is-target">{t("play.attack_tag_target")}</span> : null}
        {attackMark?.leader === "blocker" ? <span className="ux-attack-tag is-blocker">{t("play.attack_tag_blocker")}</span> : null}
      </div>
    </ZoneSlot>
  );

  const stageZone = (
    <ZoneSlot label={t("play.zone_stage")} tone="stage" className="is-field">
      {stage ? (
        <MatCard
          cardId={stage.card_id}
          label={nameOf(stage.card_id)}
          rested={stage.rested}
          power={stage.power}
          cost={costOf(stage.card_id)}
          size="md"
          statuses={collectStatusTags({
            keywords: stage.keywords,
          })}
          legal={
            actionMatch(legal, "select_choice", { target_iid: stage.iid }) ||
            actionMatch(legal, "activate_main", { source_iid: stage.iid }) ||
            canActivatePendingEffect(legal, stage.iid)
          }
          onClick={(event) => {
            if (actionMatch(legal, "select_choice", { target_iid: stage.iid })) {
              openFieldMenu(stage.iid, stage.card_id, stage.don_attached || 0, mine, event);
              return;
            }
            openFieldMenu(stage.iid, stage.card_id, stage.don_attached || 0, mine, event);
          }}
        />
      ) : (
        <div className="ux-slot-empty" />
      )}
    </ZoneSlot>
  );

  const trashZone = (
    <ZoneSlot label={t("play.zone_trash")} tone="trash" className="is-board">
      {player.trash.length ? (
        <button
          type="button"
          className="ux-trash-wrap is-clickable"
          onClick={() => onOpenTrash?.()}
          title={t("play.trash_title")}
          aria-label={`${t("play.zone_trash")} (${player.trash.length})`}
        >
          <CardImg cardId={player.trash[player.trash.length - 1]} className="ux-zone-card-img" />
          <span className="ux-card-back-count">{player.trash.length}</span>
        </button>
      ) : (
        <button
          type="button"
          className="ux-slot-empty is-clickable"
          onClick={() => onOpenTrash?.()}
          title={t("play.trash_title")}
          aria-label={t("play.zone_trash")}
        />
      )}
    </ZoneSlot>
  );

  /* 己方：生命|角色|卡组 + DON|领袖|舞台|废弃
     对手镜像（卡面仍正向）：卡组|角色|生命 + 废弃|舞台|领袖|DON */
  const rowChars = (
    <div className="ux-row ux-row-1">
      {mine ? (
        <>
          {lifeZone}
          {chars}
          {deckZone}
        </>
      ) : (
        <>
          {deckZone}
          {chars}
          {lifeZone}
        </>
      )}
    </div>
  );

  const rowBoard = (
    <div className="ux-row ux-row-2">
      {mine ? (
        <>
          {donBlock}
          <div className="ux-row-2-board">
            {leaderZone}
            {stageZone}
            {trashZone}
          </div>
        </>
      ) : (
        <>
          <div className="ux-row-2-board">
            {trashZone}
            {stageZone}
            {leaderZone}
          </div>
          {donBlock}
        </>
      )}
    </div>
  );

  const hand = mine || (replayMode && player.hand.length > 0) ? (
    <div
      className={`ux-hand is-peek ${showHandCounters ? "is-counter-phase" : ""} ${replayMode && !mine ? "is-replay-foe" : ""}`}
      aria-label={t("play.hand")}
    >
      {player.hand.map((cid, idx) => (
        <MatCard
          key={`${cid}-${idx}`}
          cardId={cid}
          label={nameOf(cid)}
          size="hand"
          cost={costOf(cid)}
          power={names[cid]?.power}
          counter={showHandCounters ? counterOf(cid, idx) : null}
          selected={replaceHandIndex === idx || selectedHandIndex === idx}
          legal={
            !replayMode &&
            (handChoiceLegal(idx, cid) ||
              actionMatch(legal, "counter", { hand_index: idx }) ||
              canPlayPlain(legal, idx) ||
              needsReplacePlay(legal, idx))
          }
          onClick={
            replayMode
              ? undefined
              : (event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  onPlayHand(idx, { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }, cid);
                }
          }
        />
      ))}
    </div>
  ) : (
    <div className="ux-hand-foe is-peek" aria-label={t("play.hand")}>
      {Array.from({ length: Math.min(player.hand_count, 12) }).map((_, i) => (
        <span key={i} className="ux-back">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/battle/card-back.png" alt="" />
        </span>
      ))}
      {player.hand_count > 12 ? <span className="ux-more">+{player.hand_count - 12}</span> : null}
    </div>
  );

  return (
    <section className={`ux-side ${mine ? "is-mine" : "is-foe"}`}>
      {/* 手牌锚在顶/底；场面紧贴手牌，行间距收紧，剩余高度留在中线一侧 */}
      {mine ? (
        <>
          <div className="ux-field-block">
            {rowChars}
            {rowBoard}
          </div>
          {hand}
        </>
      ) : (
        <>
          {hand}
          <div className="ux-field-block">
            {rowBoard}
            {rowChars}
          </div>
        </>
      )}
    </section>
  );
}

export function BattleBoard({
  state,
  names,
  onAction,
  onLeave,
  onRematch,
  onWatchReplay,
  onBugReport,
  ranked = false,
  onRankAppeal,
  rankAppealStatus = "none",
  actionBusy = false,
  error = null,
  onDismissError,
  replayMode = false,
  spectatorMode = false,
  replayControls = null,
  chatMessages = [],
  chatSelfUserId = null,
  onSendChat,
}: Props) {
  const readOnly = replayMode || spectatorMode;
  const effectiveReplayMode =
    replayMode || (spectatorMode && Boolean(state.spectator_show_hands || state.replay_mode));
  const { t, lang } = useI18n();
  const playerEliteLabel = useCallback(
    (player: BattlePlayerView) => eliteLabelForTitle(player.elite_title, t, player.elite_title_zh),
    [t],
  );
  const [attacker, setAttacker] = useState<string | null>(null);
  const [replaceHandIndex, setReplaceHandIndex] = useState<number | null>(null);
  const [bugOpen, setBugOpen] = useState(false);
  const [bugText, setBugText] = useState("");
  const [bugBusy, setBugBusy] = useState(false);
  const [bugStatus, setBugStatus] = useState<string | null>(null);
  const [appealOpen, setAppealOpen] = useState(false);
  const [appealText, setAppealText] = useState("");
  const [appealBusy, setAppealBusy] = useState(false);
  const [appealStatus, setAppealStatus] = useState<string | null>(null);
  /** Phone / short landscape: keep battle log drawer closed by default. */
  const [hudMoreOpen, setHudMoreOpen] = useState(false);
  const [compactBattle, setCompactBattle] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(
      "(max-width: 900px), (max-height: 560px), ((pointer: coarse) and (orientation: landscape)), ((pointer: coarse) and (max-height: 700px))",
    ).matches;
  });
  const [donArmed, setDonArmed] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenHint, setFullscreenHint] = useState<string | null>(null);
  const boardRef = useRef<HTMLElement | null>(null);
  const [cardMenu, setCardMenu] = useState<{
    iid: string;
    cardId: string;
    donAttached: number;
    mine: boolean;
    anchorX: number;
    anchorY: number;
  } | null>(null);
  const [cardDetail, setCardDetail] = useState<{
    cardId: string;
    loading: boolean;
    error: string | null;
    card: Card | null;
    /** When opened from a legal blocker during block phase */
    blockIid?: string | null;
  } | null>(null);
  const [mulliganViewBoard, setMulliganViewBoard] = useState(false);
  const [mulliganCardMenu, setMulliganCardMenu] = useState<string | null>(null);
  const [searchViewBoard, setSearchViewBoard] = useState(false);
  const [searchCardMenu, setSearchCardMenu] = useState<number | null>(null);
  const [triggerViewBoard, setTriggerViewBoard] = useState(false);
  const [choiceViewBoard, setChoiceViewBoard] = useState(false);
  const [choiceCardMenu, setChoiceCardMenu] = useState<string | null>(null);
  const [trashViewer, setTrashViewer] = useState<{
    seat: number;
    username: string;
  } | null>(null);
  const [handMenu, setHandMenu] = useState<{
    index: number;
    cardId: string;
    anchorX: number;
    anchorY: number;
  } | null>(null);
  const blockSubmitRef = useRef(false);
  const [choiceHoverIid, setChoiceHoverIid] = useState<string | null>(null);
  const viewerSeat = state.viewer_seat == null ? null : Number(state.viewer_seat);
  const me = state.players.find((p) => p.seat === viewerSeat) || state.players[0];
  const foe = state.players.find((p) => p.seat !== me?.seat) || state.players[1];
  const isHotseat = Boolean(state.hotseat);
  const trashViewerCards = trashViewer
    ? state.players.find((p) => p.seat === trashViewer.seat)?.trash || []
    : [];
  const playmatRef = useRef<HTMLDivElement | null>(null);
  const attack = state.attack;
  const attackFromToken = attack && me && foe
    ? battleToken(attack.attacker_seat, attack.attacker_iid)
    : null;
  const attackToToken = attack && me && foe
    ? battleToken(
        state.players.find((p) => p.seat !== attack.attacker_seat)?.seat ?? (attack.attacker_seat === 0 ? 1 : 0),
        attack.blocker_iid || attack.target_iid,
      )
    : null;
  const attackRevision = attack
    ? `${attack.attacker_seat}:${attack.attacker_iid}>${attack.blocker_iid || attack.target_iid}:${state.phase}:${me?.characters.length}:${foe?.characters.length}`
    : "";

  const foeAttackMark = useMemo(() => {
    const marks: Record<string, "attacker" | "target" | "blocker"> = {};
    if (!attack || !foe) return marks;
    if (attack.attacker_seat === foe.seat) marks[attack.attacker_iid] = "attacker";
    else {
      marks[attack.target_iid] = "target";
      if (attack.blocker_iid) marks[attack.blocker_iid] = "blocker";
    }
    return marks;
  }, [attack, foe]);

  const meAttackMark = useMemo(() => {
    const marks: Record<string, "attacker" | "target" | "blocker"> = {};
    if (!attack || !me) return marks;
    if (attack.attacker_seat === me.seat) marks[attack.attacker_iid] = "attacker";
    else {
      marks[attack.target_iid] = "target";
      if (attack.blocker_iid) marks[attack.blocker_iid] = "blocker";
    }
    return marks;
  }, [attack, me]);

  const attackBanner = useMemo(() => {
    if (!attack || !me || !foe) return null;
    const atkPlayer = state.players.find((p) => p.seat === attack.attacker_seat);
    const defPlayer = state.players.find((p) => p.seat !== attack.attacker_seat);
    const fromName = unitLabel(atkPlayer, attack.attacker_iid, names, lang, t);
    const toIid = attack.blocker_iid || attack.target_iid;
    const toName = unitLabel(defPlayer, toIid, names, lang, t);
    const atkPower =
      formatPower(attack.declared_power) ||
      formatPower(
        attack.attacker_iid === "leader"
          ? atkPlayer?.leader_power
          : atkPlayer?.characters.find((c) => c.iid === attack.attacker_iid)?.power,
      ) ||
      String(attack.declared_power);
    const defRaw =
      toIid === "leader"
        ? defPlayer?.leader_power
        : defPlayer?.characters.find((c) => c.iid === toIid)?.power;
    const defPower = formatPower(defRaw) || (defRaw != null ? String(defRaw) : "—");
    const blocked = Boolean(attack.blocker_iid);
    return {
      fromName,
      toName,
      atkPower,
      defPower,
      blocked,
      originalTarget: unitLabel(defPlayer, attack.target_iid, names, lang, t),
    };
  }, [attack, me, foe, names, lang, t, state.players]);

  const canActNow = state.legal_actions.some((a) => a.type !== "concede");
  const myTurn = isHotseat
    ? canActNow
    : (state.turn_seat === viewerSeat && state.phase === "main") ||
      (state.phase === "mulligan" && state.mulligan_seat === viewerSeat) ||
      (state.phase === "trigger" && state.pending_trigger?.seat === viewerSeat) ||
      (state.pending_search != null && state.pending_search.seat === viewerSeat) ||
      (state.pending_choice != null && state.pending_choice.seat === viewerSeat) ||
      (state.pending_effect != null &&
        Number(state.pending_effect.seat) === viewerSeat &&
        state.legal_actions.some((a) => a.type === "confirm_effect")) ||
      (state.phase === "block" &&
        Boolean(state.attack) &&
        state.attack!.attacker_seat !== viewerSeat &&
        state.legal_actions.some((a) => a.type === "block")) ||
      (state.phase === "counter" &&
        Boolean(state.attack) &&
        state.attack!.attacker_seat !== viewerSeat &&
        state.legal_actions.some((a) => a.type === "pass_counter" || a.type === "counter"));
  // Self-battle never waits on another browser — overlay would freeze combat handoffs.
  const waitingOpponent =
    !isHotseat &&
    !myTurn &&
    state.status === "playing" &&
    (state.phase === "main" ||
      state.phase === "block" ||
      state.phase === "counter" ||
      state.phase === "trigger" ||
      state.phase === "mulligan" ||
      Boolean(state.pending_choice) ||
      Boolean(state.pending_search) ||
      Boolean(state.pending_effect));
  const foeActing = waitingOpponent && Boolean(foe?.is_ai);
  const winner = state.winner_seat == null ? null : state.players[state.winner_seat];
  const iWon = state.winner_seat != null && state.winner_seat === viewerSeat;
  const matchOver = !readOnly && (state.status === "finished" || state.winner_seat != null);
  const showHotseatHandoff =
    isHotseat &&
    Boolean(me) &&
    (viewerSeat !== state.turn_seat ||
      state.phase === "block" ||
      state.phase === "counter" ||
      Boolean(state.attack && state.attack.combat_entered === false) ||
      Boolean(state.pending_effect) ||
      Boolean(state.pending_choice) ||
      Boolean(state.pending_search) ||
      Boolean(state.pending_trigger));

  const decisionChrome = useMemo(
    () => resolveDecisionChrome(state, onAction, t, names, lang),
    [state, onAction, t, names, lang],
  );

  const showMulligan = state.phase === "mulligan" && state.legal_actions.some((a) => a.type === "mulligan");

  useEffect(() => {
    if (!showMulligan) setMulliganViewBoard(false);
    if (!showMulligan) setMulliganCardMenu(null);
  }, [showMulligan]);

  useLayoutEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia(
      "(max-width: 900px), (max-height: 560px), ((pointer: coarse) and (orientation: landscape)), ((pointer: coarse) and (max-height: 700px))",
    );
    const apply = () => {
      const next = mq.matches;
      setCompactBattle(next);
      if (!next) setHudMoreOpen(false);
    };
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    if (!state.pending_choice || state.pending_choice.seat !== state.viewer_seat) {
      setChoiceHoverIid(null);
      setChoiceViewBoard(false);
      setChoiceCardMenu(null);
    }
  }, [state.pending_choice, state.viewer_seat]);

  useEffect(() => {
    if (cardDetail) setChoiceCardMenu(null);
  }, [cardDetail]);

  const resolveFieldChoice = useCallback(
    (iid: string) => {
      if (iid === "leader") {
        const owner =
          state.players.find((p) => p.seat === state.pending_choice?.seat) ||
          state.players.find((p) => p.seat === state.viewer_seat) ||
          me;
        if (!owner?.leader_card_id) return null;
        return {
          iid: "leader",
          cardId: owner.leader_card_id,
          rested: owner.leader_rested,
          power: owner.leader_power,
          don: owner.leader_don,
          slot: 0,
          mine: owner.seat === state.viewer_seat,
          ownerName: owner.username,
          keywords: owner.leader_keywords || [],
        };
      }
      for (const p of state.players) {
        const slot = p.characters.findIndex((c) => c.iid === iid);
        if (slot >= 0) {
          const ch = p.characters[slot];
          return {
            iid: ch.iid,
            cardId: ch.card_id,
            rested: ch.rested,
            power: ch.power,
            don: ch.don_attached,
            slot: slot + 1,
            mine: p.seat === state.viewer_seat,
            ownerName: p.username,
            keywords: ch.keywords || [],
          };
        }
        const stage = p.stages.find((c) => c.iid === iid);
        if (stage) {
          return {
            iid: stage.iid,
            cardId: stage.card_id,
            rested: stage.rested,
            power: stage.power,
            don: stage.don_attached,
            slot: 0,
            mine: p.seat === state.viewer_seat,
            ownerName: p.username,
            keywords: stage.keywords || [],
            isStage: true,
          };
        }
      }
      return null;
    },
    [state.players, state.pending_choice?.seat, state.viewer_seat, me],
  );

  const showSearchPrompt =
    !readOnly &&
    Boolean(state.pending_search && state.pending_search.seat === state.viewer_seat) &&
    !searchViewBoard &&
    !cardDetail;
  const showSearchBoardToggle =
    !readOnly &&
    searchViewBoard &&
    Boolean(state.pending_search && state.pending_search.seat === state.viewer_seat);

  useEffect(() => {
    if (!(state.pending_search && state.pending_search.seat === state.viewer_seat)) {
      setSearchViewBoard(false);
      setSearchCardMenu(null);
    }
  }, [state.pending_search]);

  useEffect(() => {
    if (!(state.phase === "trigger" && state.pending_trigger?.seat === state.viewer_seat)) {
      setTriggerViewBoard(false);
    }
  }, [state.phase, state.pending_trigger]);

  useEffect(() => {
    setSearchCardMenu(null);
  }, [state.pending_search?.phase, state.pending_search?.bottom_order?.length]);

  useEffect(() => {
    if (cardDetail) setSearchCardMenu(null);
  }, [cardDetail]);

  useEffect(() => {
    if (cardDetail) setHandMenu(null);
  }, [cardDetail]);

  useEffect(() => {
    if (!actionMatch(state.legal_actions, "attach_don")) setDonArmed(false);
  }, [state.legal_actions]);

  // Hotseat seat flips must drop attack-target selection / menus from the previous seat.
  useEffect(() => {
    setAttacker(null);
    setCardMenu(null);
    setHandMenu(null);
    setReplaceHandIndex(null);
    setDonArmed(false);
    setChoiceHoverIid(null);
    blockSubmitRef.current = false;
  }, [viewerSeat, state.phase]);

  useEffect(() => {
    document.body.classList.toggle("is-don-armed", donArmed);
    return () => document.body.classList.remove("is-don-armed");
  }, [donArmed]);

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    const prevOverflow = root.style.overflow;
    const prevBodyOverflow = body.style.overflow;
    const prevBodyPosition = body.style.position;
    const prevBodyWidth = body.style.width;
    const prevBodyTop = body.style.top;
    const prevBodyLeft = body.style.left;
    const prevBodyTouch = body.style.touchAction;
    const scrollY = window.scrollY;

    root.style.overflow = "hidden";
    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.width = "100%";
    body.style.top = "0";
    body.style.left = "0";
    body.style.touchAction = "manipulation";
    window.scrollTo(0, 0);

    const isCompactDevice = () =>
      window.matchMedia("(max-width: 900px)").matches ||
      window.matchMedia("(pointer: coarse)").matches ||
      window.matchMedia("(max-height: 560px)").matches;

    let lastH = -1;
    let lastW = -1;
    const syncVisualViewport = () => {
      const vv = window.visualViewport;
      const height = Math.round(vv?.height ?? window.innerHeight);
      const width = Math.round(vv?.width ?? window.innerWidth);
      // Pin to layout viewport (0,0). Binding top/left to visualViewport.offset*
      // makes iOS/Android jump the whole board on every tap (address-bar / focus scroll).
      if (Math.abs(height - lastH) > 1) {
        lastH = height;
        root.style.setProperty("--battle-vvh", `${height}px`);
      }
      if (Math.abs(width - lastW) > 1) {
        lastW = width;
        root.style.setProperty("--battle-vvw", `${width}px`);
      }
      root.style.setProperty("--battle-vvt", "0px");
      root.style.setProperty("--battle-vvl", "0px");
      const short = height > 0 && height < 430;
      body.classList.toggle("battle-short-vv", short);
    };

    const tryLockLandscape = async () => {
      if (!isCompactDevice()) return;
      const landscape = window.matchMedia("(orientation: landscape)").matches;
      if (!landscape) return;
      // Fullscreen needs a user tap — see the HUD "全屏" button. Only lock orientation here.
      try {
        const orient = screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> };
        if (orient?.lock) await orient.lock("landscape").catch(() => undefined);
      } catch {
        /* ignore */
      }
    };

    let orientTimer: number | null = null;
    let resizeTimer: number | null = null;
    const onViewportResize = () => {
      if (resizeTimer != null) window.clearTimeout(resizeTimer);
      // Debounce chrome show/hide so mid-tap viewport wobble doesn't relayout the board.
      resizeTimer = window.setTimeout(() => {
        syncVisualViewport();
      }, 120);
    };
    const onOrientationChange = () => {
      if (orientTimer != null) window.clearTimeout(orientTimer);
      // Safari needs a beat after rotate before visualViewport settles / chrome animates.
      orientTimer = window.setTimeout(() => {
        window.scrollTo(0, 0);
        syncVisualViewport();
        void tryLockLandscape();
        orientTimer = window.setTimeout(() => {
          window.scrollTo(0, 0);
          syncVisualViewport();
        }, 280);
      }, 80);
    };

    syncVisualViewport();
    void tryLockLandscape();

    window.addEventListener("resize", onViewportResize);
    window.addEventListener("orientationchange", onOrientationChange);
    window.visualViewport?.addEventListener("resize", onViewportResize);
    document.addEventListener("fullscreenchange", onOrientationChange);

    // Stop mobile browsers from scrolling focused controls into view (causes whole-page jump).
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (!boardRef.current?.contains(target)) return;
      try {
        target.focus({ preventScroll: true });
      } catch {
        /* ignore */
      }
      window.scrollTo(0, 0);
    };
    document.addEventListener("focusin", onFocusIn);

    return () => {
      if (orientTimer != null) window.clearTimeout(orientTimer);
      if (resizeTimer != null) window.clearTimeout(resizeTimer);
      window.removeEventListener("resize", onViewportResize);
      window.removeEventListener("orientationchange", onOrientationChange);
      window.visualViewport?.removeEventListener("resize", onViewportResize);
      document.removeEventListener("fullscreenchange", onOrientationChange);
      document.removeEventListener("focusin", onFocusIn);

      root.style.overflow = prevOverflow;
      body.style.overflow = prevBodyOverflow;
      body.style.position = prevBodyPosition;
      body.style.width = prevBodyWidth;
      body.style.top = prevBodyTop;
      body.style.left = prevBodyLeft;
      body.style.touchAction = prevBodyTouch;
      root.style.removeProperty("--battle-vvh");
      root.style.removeProperty("--battle-vvw");
      root.style.removeProperty("--battle-vvt");
      root.style.removeProperty("--battle-vvl");
      body.classList.remove("battle-short-vv");
      window.scrollTo(0, scrollY);

      try {
        if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
      } catch {
        /* ignore */
      }
      try {
        const orient = screen.orientation as ScreenOrientation & { unlock?: () => void };
        orient.unlock?.();
      } catch {
        /* ignore */
      }
    };
  }, []);

  useEffect(() => {
    const syncFs = () => {
      const fsEl =
        document.fullscreenElement ||
        (document as Document & { webkitFullscreenElement?: Element | null }).webkitFullscreenElement ||
        null;
      setIsFullscreen(Boolean(fsEl));
    };
    syncFs();
    document.addEventListener("fullscreenchange", syncFs);
    document.addEventListener("webkitfullscreenchange", syncFs as EventListener);
    return () => {
      document.removeEventListener("fullscreenchange", syncFs);
      document.removeEventListener("webkitfullscreenchange", syncFs as EventListener);
    };
  }, []);

  useEffect(() => {
    if (!fullscreenHint) return;
    const id = window.setTimeout(() => setFullscreenHint(null), 4200);
    return () => window.clearTimeout(id);
  }, [fullscreenHint]);

  async function toggleFullscreen() {
    setHudMoreOpen(false);
    const doc = document as Document & {
      webkitFullscreenElement?: Element | null;
      webkitExitFullscreen?: () => Promise<void> | void;
    };
    const active =
      document.fullscreenElement || doc.webkitFullscreenElement || null;

    try {
      if (active) {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (doc.webkitExitFullscreen) await doc.webkitExitFullscreen();
        setIsFullscreen(false);
        return;
      }

      const target = (boardRef.current || document.documentElement) as HTMLElement & {
        requestFullscreen?: (opts?: FullscreenOptions) => Promise<void>;
        webkitRequestFullscreen?: () => Promise<void> | void;
      };

      if (target.requestFullscreen) {
        await target.requestFullscreen({ navigationUI: "hide" });
      } else if (target.webkitRequestFullscreen) {
        await target.webkitRequestFullscreen();
      } else {
        setFullscreenHint(t("play.fullscreen_unsupported"));
        return;
      }

      try {
        const orient = screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> };
        if (orient?.lock) await orient.lock("landscape").catch(() => undefined);
      } catch {
        /* ignore */
      }
      setIsFullscreen(true);
      window.setTimeout(() => {
        window.scrollTo(0, 0);
        const vv = window.visualViewport;
        const root = document.documentElement;
        root.style.setProperty("--battle-vvh", `${Math.round(vv?.height ?? window.innerHeight)}px`);
        root.style.setProperty("--battle-vvw", `${Math.round(vv?.width ?? window.innerWidth)}px`);
        root.style.setProperty("--battle-vvt", "0px");
        root.style.setProperty("--battle-vvl", "0px");
      }, 60);
    } catch {
      setFullscreenHint(t("play.fullscreen_unsupported"));
      setIsFullscreen(false);
    }
  }

  if (!me || !foe) return <p className="muted">{t("play.waiting")}</p>;

  async function submitBug() {
    if (!onBugReport || bugBusy) return;
    const msg = bugText.trim();
    if (msg.length < 4) {
      setBugStatus(t("play.bug_too_short"));
      return;
    }
    setBugBusy(true);
    setBugStatus(null);
    try {
      await onBugReport(msg);
      setBugText("");
      setBugStatus(t("play.bug_sent"));
      window.setTimeout(() => {
        setBugOpen(false);
        setBugStatus(null);
      }, 1200);
    } catch (e) {
      setBugStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setBugBusy(false);
    }
  }

  async function submitAppeal() {
    if (!onRankAppeal || appealBusy) return;
    const msg = appealText.trim();
    if (msg.length < 8) {
      setAppealStatus(t("play.rank_appeal_too_short"));
      return;
    }
    setAppealBusy(true);
    setAppealStatus(null);
    try {
      await onRankAppeal(msg);
      setAppealText("");
      setAppealStatus(t("play.rank_appeal_sent"));
      window.setTimeout(() => {
        setAppealOpen(false);
        setAppealStatus(null);
      }, 1400);
    } catch (e) {
      setAppealStatus(e instanceof Error ? e.message : String(e));
    } finally {
      setAppealBusy(false);
    }
  }

  const canShowRankAppeal =
    ranked &&
    Boolean(onRankAppeal) &&
    (rankAppealStatus === "none" || rankAppealStatus === "rejected");
  const rankAppealLabel =
    rankAppealStatus === "pending"
      ? t("play.rank_appeal_pending")
      : rankAppealStatus === "approved" || rankAppealStatus === "reverted"
        ? t("play.rank_appeal_done")
        : t("play.rank_appeal_btn");

  function playHand(idx: number) {
    const playActs = state.legal_actions.filter((a) => a.type === "play_card" && a.hand_index === idx);
    const counterActs = state.legal_actions.filter((a) => a.type === "counter" && a.hand_index === idx);
    if (counterActs.length) {
      const defended = state.attack?.blocker_iid || state.attack?.target_iid || "leader";
      const preferred =
        counterActs.find((a) => a.buff_target === defended) ||
        counterActs.find((a) => a.buff_target === "leader") ||
        counterActs[0];
      onAction({ type: "counter", hand_index: idx, buff_target: preferred.buff_target ?? defended });
      return;
    }
    if (playActs.length && needsReplacePlay(state.legal_actions, idx) && !canPlayPlain(state.legal_actions, idx)) {
      setReplaceHandIndex(idx);
      setAttacker(null);
      return;
    }
    if (playActs.length && canPlayPlain(state.legal_actions, idx)) {
      onAction({ type: "play_card", hand_index: idx });
      setReplaceHandIndex(null);
    }
  }

  function playHandCard(idx: number) {
    if (needsReplacePlay(state.legal_actions, idx) && !canPlayPlain(state.legal_actions, idx)) {
      setReplaceHandIndex(idx);
      setAttacker(null);
      return;
    }
    if (canPlayPlain(state.legal_actions, idx)) {
      onAction({ type: "play_card", hand_index: idx });
      setReplaceHandIndex(null);
    }
  }

  function playHandCounter(idx: number) {
    const counterActs = state.legal_actions.filter((a) => a.type === "counter" && a.hand_index === idx);
    if (!counterActs.length) return;
    const defended = state.attack?.blocker_iid || state.attack?.target_iid || "leader";
    const preferred =
      counterActs.find((a) => a.buff_target === defended) ||
      counterActs.find((a) => a.buff_target === "leader") ||
      counterActs[0];
    onAction({ type: "counter", hand_index: idx, buff_target: preferred.buff_target ?? defended });
  }

  function confirmBlock(blockerIid: string | null | undefined) {
    const iid = String(blockerIid || "").trim();
    if (!iid || state.phase !== "block") return;
    if (blockSubmitRef.current || actionBusy) return;
    blockSubmitRef.current = true;
    setCardMenu(null);
    setCardDetail(null);
    onAction({ type: "block", blocker_iid: iid });
    window.setTimeout(() => {
      blockSubmitRef.current = false;
    }, 1500);
  }

  async function openCardDetail(cardId: string, blockIid?: string | null) {
    const cached = names[cardId];
    setCardDetail({
      cardId,
      loading: true,
      error: null,
      card: cached
        ? { id: cardId, name: cached.name, name_en: cached.name_en, effect: null, effect_en: null }
        : null,
      blockIid: blockIid ?? null,
    });
    try {
      const card = await fetchCardBrief(cardId);
      setCardDetail((prev) => ({
        cardId,
        loading: false,
        error: null,
        card: {
          id: cardId,
          name: card.name ?? cached?.name ?? null,
          name_en: card.name_en ?? cached?.name_en ?? null,
          effect: card.effect ?? null,
          effect_en: card.effect_en ?? null,
        },
        blockIid: prev?.blockIid ?? blockIid ?? null,
      }));
    } catch (e) {
      setCardDetail((prev) => ({
        cardId,
        loading: false,
        error: e instanceof Error ? e.message : String(e),
        card: prev?.card ?? null,
        blockIid: prev?.blockIid ?? blockIid ?? null,
      }));
    }
  }

  const viewportW = typeof window === "undefined" ? 1280 : window.innerWidth;
  const viewportH = typeof window === "undefined" ? 720 : window.innerHeight;


  const boardClass = [
    "battle-board",
    "ux-board",
    compactBattle ? "is-compact" : "",
    replayMode ? "is-replay" : "",
    spectatorMode ? "is-spectator" : "",
    donArmed ? "is-don-armed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section ref={boardRef} className={boardClass}>
      <div className="battle-portrait-gate" role="status">
        <p>{t("play.rotate_landscape")}</p>
        <p className="battle-portrait-hint">{t("play.rotate_landscape_hint")}</p>
      </div>

      <header className={`ux-hud ${attackBanner ? "has-attack" : ""}`}>
        <div className="ux-hud-left">
          {!compactBattle ? (
            <button type="button" className="ghost ux-bug-btn" onClick={() => setBugOpen(true)}>
              {t("play.bug_report")}
            </button>
          ) : null}
          <button
            type="button"
            className={`ghost ux-fullscreen-btn ${isFullscreen ? "is-active" : ""}`}
            aria-pressed={isFullscreen}
            onClick={() => void toggleFullscreen()}
          >
            {isFullscreen ? t("play.fullscreen_exit") : t("play.fullscreen")}
          </button>
          {compactBattle ? (
            <button type="button" className="ghost ux-bug-btn" onClick={() => setBugOpen(true)}>
              {t("play.bug_report")}
            </button>
          ) : null}
          {!compactBattle ? (
            <>
              <strong className="ux-room">{state.room_code}</strong>
              <button type="button" className="ghost" onClick={() => navigator.clipboard.writeText(state.room_code).catch(() => undefined)}>
                {t("play.copy")}
              </button>
            </>
          ) : null}
          {spectatorMode ? <span className="ux-you">{t("play.spectating")}</span> : null}
          <span className="ux-phase-pill">
            {t("play.turn")} {state.turn_number} · {phaseLabel(state.phase, t)}
          </span>
          {myTurn ? <span className="ux-you">{t("play.your_turn")}</span> : null}
          <span
            className={`ux-busy ${actionBusy || waitingOpponent ? "is-on" : ""}`}
            aria-hidden={!(actionBusy || waitingOpponent)}
          >
            {actionBusy
              ? t("play.action_busy")
              : foeActing
                ? t("play.ai_thinking")
                : waitingOpponent
                  ? t("play.waiting_opponent")
                  : "\u00a0"}
          </span>
          {donArmed ? (
            <button type="button" className="ghost ux-don-arm-chip" onClick={() => setDonArmed(false)}>
              {t("play.don_arm_hint")}
            </button>
          ) : null}
        </div>

        {attackBanner ? (
          <div className="ux-attack-banner is-hud-center" role="status">
            <span className="ux-attack-banner-side is-atk">
              <span className="ux-attack-banner-from">{attackBanner.fromName}</span>
              <span className="ux-attack-banner-power">{t("play.attack_power", { power: attackBanner.atkPower })}</span>
            </span>
            <span className="ux-attack-banner-arrow" aria-hidden>
              →
            </span>
            <span className="ux-attack-banner-side is-def">
              <span className="ux-attack-banner-to">{attackBanner.toName}</span>
              <span className="ux-attack-banner-power">{t("play.attack_power", { power: attackBanner.defPower })}</span>
            </span>
            {attackBanner.blocked ? (
              <span className="ux-attack-banner-note">{t("play.attack_blocked_note", { target: attackBanner.originalTarget })}</span>
            ) : null}
          </div>
        ) : null}
        {showHotseatHandoff ? (
          <div className="ux-hotseat-handoff" role="status">
            {t("play.hotseat_handoff", { name: me.username })}
          </div>
        ) : null}

        <div className="ux-hud-right">
          {!compactBattle
            ? state.legal_actions
                .filter((a) => a.type === "activate_main")
                .map((a) => {
                  const cid = String(a.card_id || "");
                  const label =
                    localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) ||
                    cid ||
                    String(a.source_iid);
                  return (
                    <button
                      key={String(a.source_iid)}
                      type="button"
                      className="secondary"
                      disabled={actionBusy}
                      onClick={() => onAction({ type: "activate_main", source_iid: a.source_iid })}
                    >
                      {t("play.activate_main_named", { name: label })}
                    </button>
                  );
                })
            : null}
          {!readOnly ? (
          <button
            type="button"
            className="ux-end"
            disabled={actionBusy || !actionMatch(state.legal_actions, "end_turn")}
            onClick={() => onAction({ type: "end_turn" })}
          >
            {actionBusy ? t("play.action_busy") : t("play.end_turn")}
          </button>
          ) : null}
          {!compactBattle ? (
            <>
              {!readOnly ? (
              <button
                type="button"
                className="ghost"
                disabled={actionBusy || !actionMatch(state.legal_actions, "concede")}
                onClick={() => {
                  if (typeof window !== "undefined" && !window.confirm(t("play.concede_confirm"))) return;
                  onAction({ type: "concede" });
                }}
              >
                {t("play.concede")}
              </button>
              ) : null}
              <button type="button" className="secondary" onClick={onLeave}>
                {t("play.leave")}
              </button>
            </>
          ) : (
            <div className="ux-hud-more">
              <button
                type="button"
                className="ghost ux-hud-more-btn"
                aria-expanded={hudMoreOpen}
                onClick={() => setHudMoreOpen((v) => !v)}
              >
                {t("play.more")}
              </button>
              {hudMoreOpen ? (
                <>
                  <button type="button" className="ux-hud-more-scrim" aria-label={t("play.menu_close")} onClick={() => setHudMoreOpen(false)} />
                  <div className="ux-hud-more-menu" role="menu">
                    <div className="ux-hud-more-room">
                      <span>{t("play.room")}</span>
                      <strong className="ux-room">{state.room_code}</strong>
                    </div>
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => {
                        navigator.clipboard.writeText(state.room_code).catch(() => undefined);
                        setHudMoreOpen(false);
                      }}
                    >
                      {t("play.copy_room")}
                    </button>
                    {!readOnly ? (
                    <button
                      type="button"
                      className="ghost"
                      disabled={actionBusy || !actionMatch(state.legal_actions, "concede")}
                      onClick={() => {
                        setHudMoreOpen(false);
                        if (typeof window !== "undefined" && !window.confirm(t("play.concede_confirm"))) return;
                        onAction({ type: "concede" });
                      }}
                    >
                      {t("play.concede")}
                    </button>
                    ) : null}
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setHudMoreOpen(false);
                        onLeave();
                      }}
                    >
                      {t("play.leave")}
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          )}
        </div>
      </header>

      {fullscreenHint ? (
        <div className="ux-fullscreen-hint" role="status">
          <span>{fullscreenHint}</span>
          <button type="button" className="ghost" onClick={() => setFullscreenHint(null)}>
            {t("play.menu_close")}
          </button>
        </div>
      ) : null}

      {error ? (
        <div className="battle-action-error" role="alert">
          <span>{error}</span>
          {onDismissError ? (
            <button type="button" className="ghost" onClick={onDismissError}>
              {t("play.menu_close")}
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="ux-shell">
        <aside className="ux-rail">
          <div className="ux-roster">
            <div className="ux-roster-row is-foe">
              <strong className="ux-roster-name">
                <RankEliteName
                  name={foe.username}
                  eliteTitle={foe.elite_title}
                  eliteLabel={playerEliteLabel(foe)}
                  size="sm"
                />
              </strong>
              {foe.is_ai ? <em className="ux-roster-ai">AI</em> : null}
              {state.turn_seat === foe.seat || (isHotseat && viewerSeat === foe.seat) ? (
                <span className="ux-turn-tag">{t("play.acting")}</span>
              ) : null}
            </div>
            <div className="ux-roster-row is-me">
              <strong className="ux-roster-name">
                <RankEliteName
                  name={me.username}
                  eliteTitle={me.elite_title}
                  eliteLabel={playerEliteLabel(me)}
                  size="sm"
                />
              </strong>
              {me.is_ai ? <em className="ux-roster-ai">AI</em> : null}
              {isHotseat ? <em className="ux-roster-ai">{t("play.hotseat_controlling")}</em> : null}
              {state.turn_seat === me.seat || (isHotseat && viewerSeat === me.seat) ? (
                <span className="ux-turn-tag">{t("play.acting")}</span>
              ) : null}
            </div>
          </div>
          <div className={`ux-log ${replayMode && replayControls ? "is-replay-split" : "is-chat-split"}`}>
            <div className="ux-replay-log-slot">
              <div className="ux-rail-title">{t("play.log_title")}</div>
              <div className="ux-log-list">
                {state.log.length ? (
                  state.log
                    .slice(-16)
                    .slice()
                    .reverse()
                    .map((line, i) => (
                      <div key={`${typeof line === "string" ? line : line.key}-${i}`} className="ux-log-line">
                        {renderBattleLog(line, t, names, lang, (cardId) => void openCardDetail(cardId))}
                      </div>
                    ))
                ) : (
                  <div className="ux-log-line muted">—</div>
                )}
              </div>
            </div>
            {replayMode && replayControls ? (
              <div className="ux-replay-controls-slot">{replayControls}</div>
            ) : (
              <div className="ux-chat-slot">
                <BattleChat
                  messages={chatMessages}
                  selfUserId={chatSelfUserId || me.user_id}
                  readOnly={spectatorMode || !onSendChat}
                  onSend={onSendChat}
                />
              </div>
            )}
          </div>
        </aside>

        <div className="ux-mat-wrap">
          <div className={`ux-playmat ${attack ? "has-attack" : ""}`} ref={playmatRef}>
            <AttackArrowOverlay
              playmatRef={playmatRef}
              fromToken={attackFromToken}
              toToken={attackToToken}
              revision={attackRevision}
            />
            <SideBoard
              player={foe}
              mine={false}
              names={names}
              lang={lang}
              state={state}
              attacker={attacker}
              replaceHandIndex={null}
              attackMark={foeAttackMark}
              onSelectAttacker={() => undefined}
              onTarget={(iid) => {
                if (!attacker) return;
                if (actionMatch(state.legal_actions, "attack", { attacker_iid: attacker, target_iid: iid })) {
                  onAction({ type: "attack", attacker_iid: attacker, target_iid: iid });
                  setAttacker(null);
                }
              }}
              onAttach={() => undefined}
              donArmed={false}
              onPlayHand={() => undefined}
              onReplaceChar={() => undefined}
              onCardMenu={(target, anchor) => {
                setAttacker(null);
                setCardMenu({
                  ...target,
                  anchorX: anchor?.x ?? viewportW * 0.5,
                  anchorY: anchor?.y ?? viewportH * 0.28,
                });
              }}
              onOpenTrash={() =>
                setTrashViewer({
                  seat: foe.seat,
                  username: foe.username,
                })
              }
              choiceHoverIid={choiceHoverIid}
              replayMode={effectiveReplayMode}
            />

            <SideBoard
              player={me}
              mine
              names={names}
              lang={lang}
              state={state}
              attacker={attacker}
              replaceHandIndex={replaceHandIndex}
              selectedHandIndex={handMenu?.index ?? null}
              attackMark={meAttackMark}
              onSelectAttacker={(iid) => {
                if (actionMatch(state.legal_actions, "attack", { attacker_iid: iid })) setAttacker(iid);
              }}
              onTarget={() => undefined}
              onAttach={(iid) => {
                onAction({ type: "attach_don", target_iid: iid, amount: 1 });
                setDonArmed(false);
              }}
              donArmed={donArmed}
              onArmDon={() => {
                setCardMenu(null);
                setHandMenu(null);
                setDonArmed(true);
              }}
              onDisarmDon={() => setDonArmed(false)}
              onReplaceChar={(iid) => {
                if (replaceHandIndex == null) return;
                if (actionMatch(state.legal_actions, "play_card", { hand_index: replaceHandIndex, replace_iid: iid })) {
                  onAction({ type: "play_card", hand_index: replaceHandIndex, replace_iid: iid });
                  setReplaceHandIndex(null);
                }
              }}
              onPlayHand={(index, anchor, cardId) => {
                setAttacker(null);
                setReplaceHandIndex(null);
                const handTok =
                  cardId != null ? `hand:${index}:${cardId}` : `hand:${index}:`;
                if (
                  state.pending_choice?.seat === state.viewer_seat &&
                  state.pending_choice.target_kind === "hand_card" &&
                  state.pending_choice.options.some(
                    (o) => o === handTok || (cardId != null && o.endsWith(`:${cardId}`)),
                  )
                ) {
                  const match =
                    state.pending_choice.options.find((o) => o === handTok) ||
                    state.pending_choice.options.find((o) => cardId != null && o.endsWith(`:${cardId}`));
                  if (match) {
                    setChoiceViewBoard(false);
                    if (state.pending_choice.multi_select) {
                      onAction({ type: "select_choice", target_iid: match });
                      return;
                    }
                    setChoiceCardMenu(match);
                    return;
                  }
                }
                if (!cardId) {
                  playHand(index);
                  return;
                }
                // Counter phase: open menu; user must press「使用反击」to confirm.
                setHandMenu({
                  index,
                  cardId,
                  anchorX: anchor?.x ?? viewportW * 0.5,
                  anchorY: anchor?.y ?? viewportH * 0.85,
                });
              }}
              onCardMenu={(target, anchor) => {
                setAttacker(null);
                setCardMenu({
                  ...target,
                  anchorX: anchor?.x ?? viewportW * 0.68,
                  anchorY: anchor?.y ?? viewportH * 0.62,
                });
              }}
              onOpenTrash={() =>
                setTrashViewer({
                  seat: me.seat,
                  username: me.username,
                })
              }
              choiceHoverIid={choiceHoverIid}
              decisionChrome={!matchOver ? decisionChrome : null}
              actionBusy={actionBusy}
              replayMode={effectiveReplayMode}
            />
          </div>
        </div>
      </div>

      {cardMenu ? (
        <>
          <button
            type="button"
            className="ux-card-quick-dismiss"
            onPointerDown={() => setCardMenu(null)}
            aria-label={t("play.menu_close")}
          />
          <div
            className={`ux-card-quick-menu ${state.phase === "block" && actionMatch(state.legal_actions, "block", { blocker_iid: cardMenu.iid }) ? "is-block-menu" : ""}`}
            style={{
              left: Math.max(88, Math.min(viewportW - 88, cardMenu.anchorX)),
              top: Math.max(90, Math.min(viewportH - 90, cardMenu.anchorY)),
            }}
            onPointerDown={(e) => e.stopPropagation()}
          >
            {state.phase === "block" && actionMatch(state.legal_actions, "block", { blocker_iid: cardMenu.iid }) ? (
              <>
                <button
                  type="button"
                  className="success"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    confirmBlock(cardMenu.iid);
                  }}
                >
                  {t("play.confirm_block")}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const { cardId, iid } = cardMenu;
                    setCardMenu(null);
                    void openCardDetail(cardId, iid);
                  }}
                >
                  {t("play.card_detail")}
                </button>
              </>
            ) : actionMatch(state.legal_actions, "select_choice", { target_iid: cardMenu.iid }) ? (
              <>
                <button
                  type="button"
                  className="success"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onAction({ type: "select_choice", target_iid: cardMenu.iid });
                    setCardMenu(null);
                    setChoiceHoverIid(null);
                  }}
                >
                  {t("play.choice_select")}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const { cardId } = cardMenu;
                    setCardMenu(null);
                    void openCardDetail(cardId);
                  }}
                >
                  {t("play.card_detail")}
                </button>
              </>
            ) : (
              <>
            {canActivatePendingEffect(state.legal_actions, cardMenu.iid) ? (
              <button
                type="button"
                className="success"
                onClick={() => {
                  onAction({ type: "confirm_effect", accept: true, source_iid: cardMenu.iid });
                  setCardMenu(null);
                }}
              >
                {t("play.menu_activate")}
              </button>
            ) : null}
            {actionMatch(state.legal_actions, "confirm_effect", {
              accept: false,
              source_iid: cardMenu.iid,
            }) ? (
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  onAction({
                    type: "confirm_effect",
                    accept: false,
                    source_iid: cardMenu.iid,
                  });
                  setCardMenu(null);
                }}
              >
                {skipEffectLabel(
                  state,
                  cardMenu.iid,
                  cardMenu.cardId || String(state.pending_effect?.card_id || ""),
                  t,
                  names,
                  lang,
                )}
              </button>
            ) : null}
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setCardMenu(null);
                void openCardDetail(cardMenu.cardId);
              }}
            >
              {t("play.card_detail")}
            </button>
            <button
              type="button"
              className="success"
              disabled={!cardMenu.mine || !actionMatch(state.legal_actions, "attack", { attacker_iid: cardMenu.iid })}
              onClick={() => {
                setAttacker(cardMenu.iid);
                setCardMenu(null);
              }}
            >
              {t("play.menu_attack")}
            </button>
            {!canActivatePendingEffect(state.legal_actions, cardMenu.iid) ? (
            <button
              type="button"
              className={
                actionMatch(state.legal_actions, "activate_main", { source_iid: cardMenu.iid })
                  ? "success"
                  : undefined
              }
              disabled={
                !cardMenu.mine ||
                !actionMatch(state.legal_actions, "activate_main", { source_iid: cardMenu.iid })
              }
              onClick={() => {
                onAction({ type: "activate_main", source_iid: cardMenu.iid });
                setCardMenu(null);
              }}
            >
              {t("play.menu_activate")}
            </button>
            ) : null}
            <button
              type="button"
              disabled={!cardMenu.mine || !actionMatch(state.legal_actions, "attach_don", { target_iid: cardMenu.iid })}
              onClick={() => {
                onAction({ type: "attach_don", target_iid: cardMenu.iid, amount: 1 });
              }}
            >
              {t("play.attach_don_one_btn")}
            </button>
            <button
              type="button"
              disabled={!cardMenu.mine || !actionMatch(state.legal_actions, "remove_don", { target_iid: cardMenu.iid })}
              onClick={() => {
                onAction({ type: "remove_don", target_iid: cardMenu.iid, amount: 1 });
                setCardMenu(null);
              }}
            >
              {t("play.detach_don_one_btn")}
            </button>
              </>
            )}
          </div>
        </>
      ) : null}

      {handMenu ? (
        <>
          <button
            type="button"
            className="ux-card-quick-dismiss"
            onClick={() => setHandMenu(null)}
            aria-label={t("play.menu_close")}
          />
          <div
            className={`ux-hand-quick-menu ${state.phase === "counter" ? "is-counter-menu" : ""}`}
            style={{
              left: Math.max(88, Math.min(viewportW - 88, handMenu.anchorX)),
              top: Math.max(90, Math.min(viewportH - 90, handMenu.anchorY)),
            }}
          >
            {state.phase === "counter" ? (
              <button
                type="button"
                className="success"
                disabled={!actionMatch(state.legal_actions, "counter", { hand_index: handMenu.index })}
                onClick={() => {
                  const idx = handMenu.index;
                  setHandMenu(null);
                  playHandCounter(idx);
                }}
              >
                {t("play.use_counter")}
              </button>
            ) : null}
            <button
              type="button"
              className="secondary"
              onClick={() => {
                const id = handMenu.cardId;
                setHandMenu(null);
                void openCardDetail(id);
              }}
            >
              {t("play.card_detail")}
            </button>
            {state.phase !== "counter" ? (
              <>
                <button
                  type="button"
                  disabled={
                    !state.legal_actions.some(
                      (a) => a.type === "play_card" && a.hand_index === handMenu.index && a.card_type !== "event",
                    )
                  }
                  onClick={() => {
                    const idx = handMenu.index;
                    setHandMenu(null);
                    playHandCard(idx);
                  }}
                >
                  {t("play.menu_play")}
                </button>
                <button
                  type="button"
                  disabled={
                    !state.legal_actions.some(
                      (a) => a.type === "play_card" && a.hand_index === handMenu.index && a.card_type === "event",
                    )
                  }
                  onClick={() => {
                    const idx = handMenu.index;
                    setHandMenu(null);
                    playHandCard(idx);
                  }}
                >
                  {t("play.menu_activate")}
                </button>
                <button
                  type="button"
                  disabled={!actionMatch(state.legal_actions, "counter", { hand_index: handMenu.index })}
                  onClick={() => {
                    const idx = handMenu.index;
                    setHandMenu(null);
                    playHandCounter(idx);
                  }}
                >
                  {t("play.menu_counter")}
                </button>
              </>
            ) : null}
          </div>
        </>
      ) : null}

      {cardDetail ? (
        <BattleModal layerClassName="is-topmost" modalClassName="is-card-detail">
          <div className="ux-card-detail-split">
            {cardDetail.loading ? <p className="muted">…</p> : null}
            {cardDetail.error ? <p className="battle-error-text">{cardDetail.error}</p> : null}
            {cardDetail.card ? (
              <>
                <div className="ux-card-detail-left">
                  <CardImg cardId={cardDetail.cardId} className="ux-card-detail-img" loading="eager" />
                </div>
                <div className="ux-card-detail-right">
                  <div className="ux-card-detail-meta">
                    <strong>
                      {localizeCardName(cardDetail.card.name, cardDetail.card.name_en, lang) ||
                        cardDetail.cardId}
                    </strong>
                    <span className="muted">{cardDetail.cardId}</span>
                  </div>
                  <div className="ux-card-detail-body">
                    <h3>{t("detail.effect")}</h3>
                    <p>
                      {formatEffectForPanel(
                        localizeCardText(cardDetail.card.effect, lang, cardDetail.card.effect_en) ||
                          t("play.no_effect"),
                      )}
                    </p>
                  </div>
                  <div className="ux-card-detail-actions">
                    {cardDetail.blockIid && state.phase === "block" ? (
                      <button
                        type="button"
                        className="success"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          confirmBlock(cardDetail.blockIid);
                        }}
                      >
                        {t("play.confirm_block")}
                      </button>
                    ) : null}
                    <button type="button" className="ghost" onClick={() => setCardDetail(null)}>
                      {t("play.menu_close")}
                    </button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </BattleModal>
      ) : null}

      {trashViewer && !cardDetail ? (
        <BattleModal layerClassName="is-topmost" modalClassName="is-mulligan is-trash-viewer">
          <div className="ux-mulligan-head">
            <h3>
              {t("play.trash_title")}
              {trashViewer.username ? ` · ${trashViewer.username}` : ""}
            </h3>
          </div>
          <p className="muted">{t("play.trash_count", { n: trashViewerCards.length })}</p>
          {trashViewerCards.length === 0 ? (
            <p className="muted">{t("play.trash_empty")}</p>
          ) : (
            <div className="ux-search-reveal ux-trash-reveal">
              {[...trashViewerCards].reverse().map((cid, i) => (
                <button
                  key={`trash-${cid}-${i}`}
                  type="button"
                  className="ux-search-card is-eligible"
                  onClick={() => void openCardDetail(cid)}
                  title={localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid}
                >
                  <CardImg cardId={cid} className="ux-search-card-img" loading="eager" />
                </button>
              ))}
            </div>
          )}
          <div className="play-actions">
            <button type="button" className="ghost" onClick={() => setTrashViewer(null)}>
              {t("play.menu_close")}
            </button>
          </div>
        </BattleModal>
      ) : null}

      {showMulligan && !mulliganViewBoard && !cardDetail ? (
        <BattleModal modalClassName="is-mulligan">
          <div className="ux-mulligan-head">
            <h3>{t("play.mulligan_preview_title")}</h3>
            <span
              className={`ux-turn-order-badge ${state.viewer_seat === state.first_seat ? "is-first" : "is-second"}`}
            >
              {state.viewer_seat === state.first_seat ? t("play.going_first") : t("play.going_second")}
            </span>
          </div>
          <div className="ux-mulligan-hand">
            {(me.hand || []).slice(0, 5).map((cid, i) => (
              <button
                key={`${cid}-${i}`}
                type="button"
                className="ux-mulligan-card-btn"
                onClick={() => setMulliganCardMenu((prev) => (prev === cid ? null : cid))}
                title={t("play.card_detail")}
              >
                <CardImg cardId={cid} className="ux-mulligan-card" loading="eager" />
                {mulliganCardMenu === cid ? (
                  <span className="ux-mulligan-card-overlay">
                    <span
                      role="button"
                      tabIndex={0}
                      className="ux-mulligan-card-overlay-btn"
                      onClick={(event) => {
                        event.stopPropagation();
                        setMulliganCardMenu(null);
                        void openCardDetail(cid);
                      }}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter" && event.key !== " ") return;
                        event.preventDefault();
                        event.stopPropagation();
                        setMulliganCardMenu(null);
                        void openCardDetail(cid);
                      }}
                    >
                      {t("play.card_detail")}
                    </span>
                  </span>
                ) : null}
              </button>
            ))}
          </div>
          <p className="muted">{t("play.mulligan_hint")}</p>
          <div className="play-actions">
            <button type="button" className="success" onClick={() => onAction({ type: "mulligan", redraw: false })}>
              {t("play.mulligan_keep")}
            </button>
            <button type="button" className="secondary" onClick={() => onAction({ type: "mulligan", redraw: true })}>
              {t("play.mulligan_redraw")}
            </button>
            <button type="button" className="ghost" onClick={() => setMulliganViewBoard(true)}>
              {t("play.mulligan_view_board")}
            </button>
          </div>
        </BattleModal>
      ) : null}

      {showMulligan && mulliganViewBoard ? (
        <div className="ux-mulligan-board-toggle">
          <button type="button" className="secondary" onClick={() => setMulliganViewBoard(false)}>
            {t("play.mulligan_back_hand")}
          </button>
        </div>
      ) : null}

      {state.phase === "trigger" &&
      state.pending_trigger &&
      state.legal_actions.some((a) => a.type === "trigger") &&
      !triggerViewBoard ? (
        <BattleModal modalClassName="is-decision-prompt">
          <h3>{t("play.trigger_title")}</h3>
          <div className="ux-choice-cards">
            <button
              type="button"
              className="ux-choice-card"
              onClick={() => void openCardDetail(state.pending_trigger!.card_id)}
              title={
                localizeCardName(
                  names[state.pending_trigger.card_id]?.name,
                  names[state.pending_trigger.card_id]?.name_en,
                  lang,
                ) || state.pending_trigger.card_id
              }
            >
              <CardImg cardId={state.pending_trigger.card_id} className="ux-choice-card-img" loading="eager" />
            </button>
          </div>
          <p className="muted">
            {(() => {
              const summary = displayEffectSummary(state.pending_trigger.summary, lang);
              if (summary) return formatEffectForPanel(summary);
              return t("play.trigger_hint", { id: state.pending_trigger.card_id });
            })()}
          </p>
          <div className="play-actions">
            <button type="button" className="ghost" onClick={() => setTriggerViewBoard(true)}>
              {t("play.view_board")}
            </button>
            <button type="button" className="success" onClick={() => onAction({ type: "trigger", accept: true })}>
              {t("play.trigger_yes")}
            </button>
            <button type="button" className="secondary" onClick={() => onAction({ type: "trigger", accept: false })}>
              {t("play.trigger_no")}
            </button>
          </div>
        </BattleModal>
      ) : null}

      {state.phase === "trigger" &&
      state.pending_trigger &&
      state.legal_actions.some((a) => a.type === "trigger") &&
      triggerViewBoard ? (
        <div className="ux-mulligan-board-toggle">
            <button type="button" className="secondary" onClick={() => setTriggerViewBoard(false)}>
              {t("play.back_to_prompt")}
            </button>
        </div>
      ) : null}

      {replaceHandIndex != null ? (
        <div className="ux-replace-banner" role="status">
          <p>{t("play.select_replace")}</p>
          <button type="button" className="ghost" onClick={() => setReplaceHandIndex(null)}>
            {t("play.cancel_replace")}
          </button>
        </div>
      ) : null}

      {appealOpen ? (
        <BattleModal layerClassName="is-topmost">
          <h3>{t("play.rank_appeal_title")}</h3>
          <p className="muted">{t("play.rank_appeal_hint")}</p>
          <textarea
            className="ux-bug-textarea"
            rows={5}
            value={appealText}
            onChange={(e) => setAppealText(e.target.value)}
            placeholder={t("play.rank_appeal_placeholder")}
            disabled={appealBusy}
          />
          {appealStatus ? (
            <p className={appealStatus === t("play.rank_appeal_sent") ? "muted" : "error-text"}>{appealStatus}</p>
          ) : null}
          <div className="play-actions">
            <button type="button" className="ghost" disabled={appealBusy} onClick={() => setAppealOpen(false)}>
              {t("play.menu_close")}
            </button>
            <button type="button" className="success" disabled={appealBusy || !onRankAppeal} onClick={() => void submitAppeal()}>
              {appealBusy ? t("play.action_busy") : t("play.rank_appeal_submit")}
            </button>
          </div>
        </BattleModal>
      ) : null}

      {bugOpen ? (
        <BattleModal layerClassName="is-topmost">
          <h3>{t("play.bug_title")}</h3>
          <p className="muted">{t("play.bug_hint")}</p>
          <textarea
            className="ux-bug-textarea"
            rows={5}
            value={bugText}
            onChange={(e) => setBugText(e.target.value)}
            placeholder={t("play.bug_placeholder")}
            disabled={bugBusy}
          />
          {bugStatus ? <p className={bugStatus === t("play.bug_sent") ? "muted" : "error-text"}>{bugStatus}</p> : null}
          <div className="play-actions">
            <button type="button" className="ghost" disabled={bugBusy} onClick={() => setBugOpen(false)}>
              {t("play.menu_close")}
            </button>
            <button type="button" className="success" disabled={bugBusy || !onBugReport} onClick={() => void submitBug()}>
              {bugBusy ? t("play.action_busy") : t("play.bug_submit")}
            </button>
          </div>
        </BattleModal>
      ) : null}

      {matchOver && winner ? (
        <div className="ux-match-over-layer" role="dialog" aria-modal="true">
          <div className={`ux-match-over-card ${iWon ? "is-win" : "is-lose"}`}>
            <p className="ux-match-over-eyebrow">{iWon ? t("play.result_win") : t("play.result_lose")}</p>
            <h2 className="ux-match-over-winner">
              <RankEliteName
                name={winner.username}
                eliteTitle={winner.elite_title}
                eliteLabel={playerEliteLabel(winner)}
                size="lg"
              />
              <span>{t("play.winner_suffix")}</span>
            </h2>
            {ranked && rankAppealStatus === "pending" ? (
              <p className="muted ux-match-over-note">{t("play.rank_appeal_pending_note")}</p>
            ) : null}
            {ranked && (rankAppealStatus === "approved" || rankAppealStatus === "reverted") ? (
              <p className="muted ux-match-over-note">{t("play.rank_appeal_done_note")}</p>
            ) : null}
            <div className="play-actions">
              {canShowRankAppeal ? (
                <button type="button" className="ghost" onClick={() => setAppealOpen(true)}>
                  {rankAppealLabel}
                </button>
              ) : ranked && rankAppealStatus === "pending" ? (
                <button type="button" className="ghost" disabled>
                  {rankAppealLabel}
                </button>
              ) : null}
              {onWatchReplay ? (
                <button type="button" className="success" onClick={onWatchReplay}>
                  {t("play.watch_replay")}
                </button>
              ) : null}
              {onRematch ? (
                <button type="button" className={onWatchReplay ? "secondary" : "success"} onClick={onRematch}>
                  {t("play.rematch")}
                </button>
              ) : null}
              <button type="button" className="secondary" onClick={onLeave}>
                {t("play.leave")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {showSearchBoardToggle ? (
        <div className="ux-mulligan-board-toggle">
          <button type="button" className="secondary" onClick={() => setSearchViewBoard(false)}>
            {t("play.back_to_prompt")}
          </button>
        </div>
      ) : null}

      {showSearchPrompt ? (
        <BattleModal layerClassName="is-topmost" modalClassName="is-mulligan is-search-prompt">
          {state.pending_search!.phase === "order" ? (
            <>
              <h3>{t("play.search_order_title")}</h3>
              <p className="muted">{t("play.search_order_hint")}</p>
              {(state.pending_search!.bottom_order || []).length > 0 ? (
                <div className="ux-search-order-row" aria-label={t("play.search_order_chosen")}>
                  {(state.pending_search!.bottom_order || []).map((cid, i) =>
                    cid ? (
                      <div key={`ord-${cid}-${i}`} className="ux-search-card is-ordered" title={`${i + 1}`}>
                        <span className="ux-search-order-num">{i + 1}</span>
                        <CardImg cardId={cid} className="ux-search-card-img" loading="eager" />
                      </div>
                    ) : (
                      <div key={`ord-hid-${i}`} className="ux-search-card is-hidden" />
                    ),
                  )}
                </div>
              ) : null}
              <div className="ux-search-reveal">
                {(state.pending_search!.revealed || []).map((cid, i) => {
                  if (!cid) {
                    return <div key={`hid-${i}`} className="ux-search-card is-hidden" />;
                  }
                  return (
                    <button
                      key={`${cid}-${i}`}
                      type="button"
                      className="ux-search-card is-eligible"
                      onClick={() => onAction({ type: "order_search_bottom", index: i })}
                      title={`${localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid} · ${t("play.search_order_pick")}`}
                    >
                      <CardImg cardId={cid} className="ux-search-card-img" loading="eager" />
                    </button>
                  );
                })}
              </div>
              <div className="play-actions">
                {(state.pending_search!.bottom_order || []).length > 0 ? (
                  <button type="button" className="ghost" onClick={() => onAction({ type: "undo_search_order" })}>
                    {t("play.search_order_undo")}
                  </button>
                ) : null}
                <button type="button" className="ghost" onClick={() => setSearchViewBoard(true)}>
                  {t("play.view_board")}
                </button>
              </div>
            </>
          ) : (
            <>
              <h3>{t("play.search_title")}</h3>
              <p className="muted">
                {(() => {
                  const traitRaw =
                    state.pending_search!.trait_contains || state.pending_search!.name_contains || "";
                  const baseTrait =
                    (lang === "en"
                      ? traitRaw
                      : traitRaw === "Impel Down"
                        ? "推進城"
                        : traitRaw) || "—";
                  const typeHintRaw = String(state.pending_search!.card_type || "").trim();
                  const typeHint = typeHintRaw
                    ? ` ${localizeFilterToken("type", typeHintRaw, lang) || typeHintRaw}`
                    : "";
                  const trait = `${baseTrait}${typeHint}`;
                  const exclude = state.pending_search!.exclude_name || "";
                  const params = { n: state.pending_search!.max_add, trait, exclude };
                  return exclude
                    ? t("play.search_hint_exclude", params)
                    : t("play.search_hint", params);
                })()}
              </p>
              {(state.pending_search!.max_add || 1) > 1 ? (
                <p className="muted">
                  {t("play.search_selected", {
                    n: (state.pending_search!.selected || []).length,
                    max: state.pending_search!.max_add,
                  })}
                </p>
              ) : null}
              <div className="ux-search-reveal">
                {(state.pending_search!.revealed || []).map((cid, i) => {
                  const eligible = (state.pending_search?.eligible || []).some((x) => Number(x) === i);
                  const picked = (state.pending_search?.selected || []).some((x) => Number(x) === i);
                  if (!cid) {
                    return <div key={`hid-${i}`} className="ux-search-card is-hidden" />;
                  }
                  const menuOpen = searchCardMenu === i;
                  return (
                    <button
                      key={`${cid}-${i}`}
                      type="button"
                      className={`ux-search-card ${eligible ? "is-eligible" : "is-blocked"} ${picked ? "is-picked" : ""} ${menuOpen ? "is-menu-open" : ""}`}
                      onClick={() => {
                        if (!eligible) {
                          void openCardDetail(cid);
                          return;
                        }
                        setSearchCardMenu((prev) => (prev === i ? null : i));
                      }}
                      title={
                        eligible
                          ? `${localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid} · ${t("play.search_detail_hint")}`
                          : t("play.search_ineligible")
                      }
                    >
                      <CardImg cardId={cid} className="ux-search-card-img" loading="eager" />
                      {menuOpen && eligible ? (
                        <span className="ux-search-card-overlay">
                          <span
                            role="button"
                            tabIndex={0}
                            className="ux-search-card-overlay-btn"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSearchCardMenu(null);
                              void openCardDetail(cid);
                            }}
                            onKeyDown={(event) => {
                              if (event.key !== "Enter" && event.key !== " ") return;
                              event.preventDefault();
                              event.stopPropagation();
                              setSearchCardMenu(null);
                              void openCardDetail(cid);
                            }}
                          >
                            {t("play.card_detail")}
                          </span>
                          <span
                            role="button"
                            tabIndex={0}
                            className="ux-search-card-overlay-btn is-primary"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSearchCardMenu(null);
                              onAction({ type: "select_search", index: i });
                            }}
                            onKeyDown={(event) => {
                              if (event.key !== "Enter" && event.key !== " ") return;
                              event.preventDefault();
                              event.stopPropagation();
                              setSearchCardMenu(null);
                              onAction({ type: "select_search", index: i });
                            }}
                          >
                            {picked ? t("play.search_unpick") : t("play.choice_select")}
                          </span>
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
              <div className="play-actions">
                <button type="button" className="ghost" onClick={() => setSearchViewBoard(true)}>
                  {t("play.view_board")}
                </button>
                {actionMatch(state.legal_actions, "confirm_search") ? (
                  <button type="button" className="primary" onClick={() => onAction({ type: "confirm_search" })}>
                    {t("play.search_confirm")}
                  </button>
                ) : null}
                {actionMatch(state.legal_actions, "skip_search") ? (
                  <button type="button" className="secondary" onClick={() => onAction({ type: "skip_search" })}>
                    {t("play.search_skip")}
                  </button>
                ) : null}
              </div>
            </>
          )}
        </BattleModal>
      ) : null}

      {state.pending_choice && !replayMode && state.pending_choice.seat !== state.viewer_seat ? (
        <div className="ux-choice-waiting" role="status">
          {t("play.choice_waiting")}
        </div>
      ) : null}

      {choiceViewBoard &&
      state.pending_choice &&
      state.pending_choice.seat === state.viewer_seat ? (
        <div className="ux-mulligan-board-toggle">
          <button type="button" className="secondary" onClick={() => setChoiceViewBoard(false)}>
            {t("play.back_to_prompt")}
          </button>
        </div>
      ) : null}

      {!readOnly &&
      state.pending_choice &&
      state.pending_choice.seat === state.viewer_seat &&
      !choiceViewBoard &&
      !cardDetail ? (
        <BattleModal
          layerClassName="is-passthrough"
          modalClassName={`is-decision-prompt is-counter-prompt is-choice-cards`}
        >
          <h3>
            {state.pending_choice.target_kind === "effect_option"
              ? t("play.choice_effect_title")
              : (() => {
                  const purpose = choicePurposeKey(state.pending_choice.purpose);
                  const summary = displayEffectSummary(state.pending_choice.summary, lang);
                  // Prefer effect summary as the title when choosing grant/cost targets.
                  if (
                    summary &&
                    (purpose === "grant_keyword" ||
                      purpose === "grant_cost" ||
                      purpose === "reduce_cost" ||
                      purpose === "general")
                  ) {
                    return summary;
                  }
                  return t(`play.choice_purpose_${purpose}`);
                })()}
          </h3>
          <p className="muted">
            {state.pending_choice.target_kind === "hand_card"
              ? `${t(`play.choice_purpose_hint_${choicePurposeKey(state.pending_choice.purpose)}`)} ${
                  state.pending_choice.multi_select
                    ? t("play.choice_hand_hint")
                    : t("play.choice_hand_hint_single")
                }`
              : state.pending_choice.target_kind === "effect_option" ||
                  state.pending_choice.target_kind === "life_position" ||
                  state.pending_choice.target_kind === "life_owner"
                ? displayEffectSummary(state.pending_choice.summary, lang) || t("play.choice_hint")
                : (() => {
                    const purpose = choicePurposeKey(state.pending_choice.purpose);
                    const summary = displayEffectSummary(state.pending_choice.summary, lang);
                    const hint = t(`play.choice_purpose_hint_${purpose}`);
                    // When summary is already the title, don't repeat it in parentheses.
                    if (
                      summary &&
                      (purpose === "grant_keyword" ||
                        purpose === "grant_cost" ||
                        purpose === "reduce_cost" ||
                        purpose === "general")
                    ) {
                      return hint;
                    }
                    if (!summary) return hint;
                    return lang === "en" ? `${hint} (${summary})` : `${hint}（${summary}）`;
                  })()}
          </p>
          {state.pending_choice.target_kind === "hand_card" ? (
            <div className="ux-choice-cards">
              {(state.pending_choice.options || []).map((iid) => {
                const zoneMatch = /^(hand|trash):(\d+):(.+)$/.exec(iid);
                const zone = zoneMatch?.[1] || "";
                const zoneIndex = zoneMatch ? Number(zoneMatch[2]) + 1 : null;
                const cid = zoneMatch?.[3] || "";
                if (!cid) return null;
                const multi = Boolean(state.pending_choice?.multi_select);
                const menuOpen = !multi && choiceCardMenu === iid;
                return (
                  <button
                    key={iid}
                    type="button"
                    className={`ux-choice-card has-meta ${menuOpen ? "is-menu-open" : ""}`}
                    onClick={() => {
                      if (multi) {
                        onAction({ type: "select_choice", target_iid: iid });
                        return;
                      }
                      setChoiceCardMenu((prev) => (prev === iid ? null : iid));
                    }}
                    title={localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid}
                  >
                    <CardImg cardId={cid} className="ux-choice-card-img" loading="eager" />
                    <span className="ux-choice-meta">
                      {zone === "trash" ? (
                        <span className="ux-choice-chip is-trash">{t("play.choice_from_trash")}</span>
                      ) : zoneIndex != null ? (
                        <span className="ux-choice-chip">{t("play.choice_hand_slot", { n: zoneIndex })}</span>
                      ) : null}
                      {names[cid]?.cost != null ? (
                        <span className="ux-choice-chip is-cost">{t("play.choice_cost", { n: names[cid].cost })}</span>
                      ) : null}
                      {multi ? (
                        <span
                          role="button"
                          tabIndex={0}
                          className="ux-choice-chip"
                          onClick={(event) => {
                            event.stopPropagation();
                            void openCardDetail(cid);
                          }}
                          onKeyDown={(event) => {
                            if (event.key !== "Enter" && event.key !== " ") return;
                            event.preventDefault();
                            event.stopPropagation();
                            void openCardDetail(cid);
                          }}
                        >
                          {t("play.card_detail")}
                        </span>
                      ) : null}
                    </span>
                    {menuOpen ? (
                      <span className="ux-search-card-overlay">
                        <span
                          role="button"
                          tabIndex={0}
                          className="ux-search-card-overlay-btn"
                          onClick={(event) => {
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            void openCardDetail(cid);
                          }}
                          onKeyDown={(event) => {
                            if (event.key !== "Enter" && event.key !== " ") return;
                            event.preventDefault();
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            void openCardDetail(cid);
                          }}
                        >
                          {t("play.card_detail")}
                        </span>
                        <span
                          role="button"
                          tabIndex={0}
                          className="ux-search-card-overlay-btn is-primary"
                          onClick={(event) => {
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            onAction({ type: "select_choice", target_iid: iid });
                          }}
                          onKeyDown={(event) => {
                            if (event.key !== "Enter" && event.key !== " ") return;
                            event.preventDefault();
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            onAction({ type: "select_choice", target_iid: iid });
                          }}
                        >
                          {t("play.choice_select")}
                        </span>
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          ) : state.pending_choice.target_kind === "effect_option" ||
            state.pending_choice.target_kind === "life_position" ||
            state.pending_choice.target_kind === "life_owner" ||
            state.pending_choice.target_kind === "return_don" ? (
            <div className="ux-choice-options">
              {(state.pending_choice.options || []).map((iid) => {
                let label = localizeEffectOptionLabel(
                  state.pending_choice?.option_labels?.[iid] || iid,
                  lang,
                  t,
                  iid,
                );
                if (iid.startsWith("don:char:")) {
                  const meta = state.pending_choice?.option_labels?.[iid] || "";
                  const m = /^don_char:(\d+):(.+)$/.exec(meta);
                  const n = m ? Number(m[1]) : 1;
                  const cid = m?.[2] || "";
                  const nm =
                    localizeCardName(names[cid]?.name, names[cid]?.name_en, lang) || cid || t("play.zone_character");
                  label = t("play.choice_don_character_named", { n, name: nm });
                }
                return (
                  <button
                    key={iid}
                    type="button"
                    className="secondary ux-choice-option-btn"
                    onClick={() => onAction({ type: "select_choice", target_iid: iid })}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="ux-choice-cards is-field">
              {(state.pending_choice.options || []).map((iid) => {
                const target = resolveFieldChoice(iid);
                if (!target) {
                  return (
                    <button key={iid} type="button" onClick={() => onAction({ type: "select_choice", target_iid: iid })}>
                      {iid === "leader" ? t("play.zone_leader") : iid === "don" ? "DON!!" : iid}
                    </button>
                  );
                }
                const powerText = formatPower(target.power);
                const name =
                  iid === "leader"
                    ? t("play.zone_leader")
                    : localizeCardName(names[target.cardId]?.name, names[target.cardId]?.name_en, lang) ||
                      target.cardId;
                const menuOpen = choiceCardMenu === iid;
                return (
                  <button
                    key={iid}
                    type="button"
                    className={`ux-choice-card has-meta ${choiceHoverIid === iid ? "is-focused" : ""} ${menuOpen ? "is-menu-open" : ""}`}
                    onClick={() => {
                      setChoiceHoverIid(iid);
                      setChoiceCardMenu((prev) => (prev === iid ? null : iid));
                    }}
                    onMouseEnter={() => setChoiceHoverIid(iid)}
                    onMouseLeave={() => setChoiceHoverIid((cur) => (cur === iid ? null : cur))}
                    onFocus={() => setChoiceHoverIid(iid)}
                    onBlur={() => setChoiceHoverIid((cur) => (cur === iid ? null : cur))}
                    title={[
                      name,
                      target.mine ? t("play.choice_mine") : t("play.choice_foe"),
                      target.rested ? t("play.rested") : t("play.choice_active"),
                      target.slot > 0 ? t("play.choice_slot", { n: target.slot }) : null,
                      target.don > 0 ? `DON×${target.don}` : null,
                      powerText != null ? `${powerText}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  >
                    <span className="ux-choice-card-face">
                      <CardImg cardId={target.cardId} className="ux-choice-card-img" loading="eager" />
                      {target.rested ? <span className="ux-choice-rested-mark">{t("play.rested")}</span> : null}
                    </span>
                    <span className="ux-choice-meta">
                      <span className={`ux-choice-chip ${target.mine ? "is-mine" : "is-foe"}`}>
                        {target.mine ? t("play.choice_mine") : t("play.choice_foe")}
                      </span>
                      {iid === "leader" ? (
                        <span className="ux-choice-chip">{t("play.zone_leader")}</span>
                      ) : target.slot > 0 ? (
                        <span className="ux-choice-chip">{t("play.choice_slot", { n: target.slot })}</span>
                      ) : (
                        <span className="ux-choice-chip">{t("play.zone_stage")}</span>
                      )}
                      <span className={`ux-choice-chip ${target.rested ? "is-rested" : "is-active"}`}>
                        {target.rested ? t("play.rested") : t("play.choice_active")}
                      </span>
                      {target.don > 0 ? <span className="ux-choice-chip is-don">DON×{target.don}</span> : null}
                      {powerText != null ? <span className="ux-choice-chip is-power">{powerText}</span> : null}
                    </span>
                    {menuOpen ? (
                      <span className="ux-search-card-overlay">
                        <span
                          role="button"
                          tabIndex={0}
                          className="ux-search-card-overlay-btn"
                          onClick={(event) => {
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            void openCardDetail(target.cardId);
                          }}
                          onKeyDown={(event) => {
                            if (event.key !== "Enter" && event.key !== " ") return;
                            event.preventDefault();
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            void openCardDetail(target.cardId);
                          }}
                        >
                          {t("play.card_detail")}
                        </span>
                        <span
                          role="button"
                          tabIndex={0}
                          className="ux-search-card-overlay-btn is-primary"
                          onClick={(event) => {
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            setChoiceHoverIid(null);
                            onAction({ type: "select_choice", target_iid: iid });
                          }}
                          onKeyDown={(event) => {
                            if (event.key !== "Enter" && event.key !== " ") return;
                            event.preventDefault();
                            event.stopPropagation();
                            setChoiceCardMenu(null);
                            setChoiceHoverIid(null);
                            onAction({ type: "select_choice", target_iid: iid });
                          }}
                        >
                          {t("play.choice_select")}
                        </span>
                      </span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}
          <div className="play-actions">
            {state.pending_choice.optional ? (
              <button type="button" className="ghost" onClick={() => onAction({ type: "skip_choice" })}>
                {state.pending_choice.multi_select ? t("play.choice_done") : t("play.choice_skip")}
              </button>
            ) : null}
            <button type="button" className="ghost" onClick={() => setChoiceViewBoard(true)}>
              {t("play.view_board")}
            </button>
          </div>
        </BattleModal>
      ) : null}
    </section>
  );
}
