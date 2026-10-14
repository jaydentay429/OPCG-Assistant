export const BATTLE_PAUSED_DETAIL = "对战功能已暂停。";

export type BattleServiceStatus = "loading" | "ready" | "unavailable";

export function isBattleDisabledError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const status = "status" in error ? Number((error as { status: unknown }).status) : Number.NaN;
  const detail = "detail" in error ? (error as { detail: unknown }).detail : "";
  const message = error instanceof Error ? error.message : "";
  const text = `${typeof detail === "string" ? detail : ""} ${message}`;
  return status === 404 && text.includes(BATTLE_PAUSED_DETAIL);
}

/** One probe. Any failure means battle cannot be played yet; success means the API is on. */
export async function probeBattleService(load: () => Promise<unknown>): Promise<"ready" | "unavailable"> {
  try {
    await load();
    return "ready";
  } catch {
    return "unavailable";
  }
}

export function reduceBattleService(
  status: BattleServiceStatus,
  event: "probe-ready" | "probe-unavailable" | "handshake-failed" | "disabled-response" | "retry",
): BattleServiceStatus {
  if (event === "retry") return "loading";
  if (event === "probe-ready") return status === "loading" ? "ready" : status;
  if (event === "probe-unavailable" || event === "handshake-failed" || event === "disabled-response") {
    return "unavailable";
  }
  return status;
}

/** A failed handshake must not be retried by the room poll. */
export function shouldReconnectBattleSocket(opts: {
  handshakeFailed: boolean;
  serviceDown: boolean;
  hasSocket: boolean;
  leaving?: boolean;
}): boolean {
  return !opts.leaving && !opts.handshakeFailed && !opts.serviceDown && !opts.hasSocket;
}

export function shouldPollBattle(status: BattleServiceStatus): boolean {
  return status === "ready";
}
