import { ApiError, fetchMe } from "./api";
import type { MeResponse } from "./types";

/** localStorage mirror of the logged-in user. Backend sessions live in SQLite and survive API restarts. */
export const AUTH_STORAGE_KEY = "opcg_auth_mirror_v1";

/**
 * Extra /auth/me attempts after the first failure.
 * A deploy restarts opcg-api for a few seconds and Caddy answers 502; three
 * retries a few seconds apart cover that window without logging the user out.
 */
export const AUTH_ME_MAX_RETRIES = 3;

/** Pause before each silent retry. */
export const AUTH_ME_RETRY_DELAY_MS = 3000;

export type AuthSnapshot = {
  token: string | null;
  username: string | null;
  email: string | null;
  verified: boolean;
  isAdmin: boolean;
};

export type AuthStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function emptyAuth(): AuthSnapshot {
  return { token: null, username: null, email: null, verified: false, isAdmin: false };
}

/**
 * fetchMe (via apiGet) throws ApiError with the HTTP status for any non-OK
 * response, including 401, 403, 429, and 5xx. Timeouts are ApiError 408.
 * Transport failures reject with the original error and have no status.
 * Only an explicit 401 or 403 means the token is invalid, expired, or revoked.
 */
export function isAuthRejected(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403);
}

/** Network errors, timeouts, 429, and 5xx are worth another /auth/me try. Other 4xx are not. */
export function isRetryableMeFailure(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 408 || error.status === 429 || (error.status >= 500 && error.status <= 599);
  }
  return true;
}

export function loadStoredAuth(storage: AuthStorage): AuthSnapshot {
  try {
    const raw = storage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return emptyAuth();
    const data = JSON.parse(raw) as { t?: string; u?: string; e?: string; v?: string; a?: string };
    if (!data?.t) return emptyAuth();
    return {
      token: data.t,
      username: data.u || null,
      email: data.e || null,
      verified: data.v === "1",
      isAdmin: data.a === "1",
    };
  } catch {
    return emptyAuth();
  }
}

export function persistAuth(storage: AuthStorage, session: AuthSnapshot): void {
  try {
    if (!session.token) {
      storage.removeItem(AUTH_STORAGE_KEY);
      return;
    }
    storage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({
        t: session.token,
        u: session.username || "",
        e: session.email || "",
        v: session.verified ? "1" : "0",
        a: session.isAdmin ? "1" : "0",
      }),
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function sessionFromMe(token: string, me: MeResponse): AuthSnapshot {
  return {
    token,
    username: me.username,
    email: me.email,
    verified: me.email_verified,
    isAdmin: Boolean(me.is_admin),
  };
}

export type SyncAuthResult =
  | { status: "updated"; session: AuthSnapshot }
  | { status: "rejected"; error: unknown }
  | { status: "kept"; error: unknown }
  | { status: "aborted" };

export type SyncAuthOptions = {
  retries?: number;
  delayMs?: number;
  sleep?: (ms: number) => Promise<void>;
  shouldAbort?: () => boolean;
};

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Confirm a token with /auth/me.
 * 401/403 → rejected (caller clears the mirror).
 * Transient failures retry, then return kept so the mirror stays put.
 */
export async function syncSessionWithMe(token: string, opts?: SyncAuthOptions): Promise<SyncAuthResult> {
  const retries = opts?.retries ?? AUTH_ME_MAX_RETRIES;
  const delayMs = opts?.delayMs ?? AUTH_ME_RETRY_DELAY_MS;
  const sleep = opts?.sleep ?? defaultSleep;
  let attempt = 0;
  for (;;) {
    if (opts?.shouldAbort?.()) return { status: "aborted" };
    try {
      const me = await fetchMe(token);
      if (opts?.shouldAbort?.()) return { status: "aborted" };
      return { status: "updated", session: sessionFromMe(token, me) };
    } catch (error) {
      if (opts?.shouldAbort?.()) return { status: "aborted" };
      if (isAuthRejected(error)) return { status: "rejected", error };
      if (!isRetryableMeFailure(error) || attempt >= retries) return { status: "kept", error };
      attempt += 1;
      if (delayMs > 0) await sleep(delayMs);
    }
  }
}

/** Page-load path: read the mirror, refresh it, and clear it only on 401/403. */
export async function restoreAuthSession(storage: AuthStorage, opts?: SyncAuthOptions): Promise<AuthSnapshot> {
  const stored = loadStoredAuth(storage);
  if (!stored.token) return stored;
  const result = await syncSessionWithMe(stored.token, opts);
  if (result.status === "aborted" || opts?.shouldAbort?.()) return loadStoredAuth(storage);
  if (result.status === "updated") {
    persistAuth(storage, result.session);
    return result.session;
  }
  if (result.status === "rejected") {
    const session = emptyAuth();
    persistAuth(storage, session);
    return session;
  }
  return loadStoredAuth(storage);
}

/** Explicit refresh. Same clear rules as restore: non-401/403 leaves the mirror alone. */
export async function refreshAuthSession(
  storage: AuthStorage,
  token: string | null,
  opts?: SyncAuthOptions,
): Promise<SyncAuthResult> {
  if (!token) return { status: "kept", error: undefined };
  const result = await syncSessionWithMe(token, opts);
  if (result.status === "aborted" || opts?.shouldAbort?.()) return { status: "aborted" };
  if (result.status === "updated") {
    persistAuth(storage, result.session);
    return result;
  }
  if (result.status === "rejected") {
    persistAuth(storage, emptyAuth());
    return result;
  }
  return { status: "kept", error: result.error };
}
