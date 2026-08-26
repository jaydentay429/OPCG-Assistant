"use client";

import { API_BASE } from "@/lib/api";

const VISITOR_KEY = "opcg_analytics_vid_v1";
const SESSION_KEY = "opcg_analytics_sid_v1";

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `v_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function getOrCreate(storage: Storage, key: string): string {
  try {
    const existing = storage.getItem(key);
    if (existing && existing.length >= 8) return existing;
    const id = uuid();
    storage.setItem(key, id);
    return id;
  } catch {
    return uuid();
  }
}

export function getVisitorId(): string {
  return getOrCreate(window.localStorage, VISITOR_KEY);
}

export function getSessionId(): string {
  return getOrCreate(window.sessionStorage, SESSION_KEY);
}

type TrackPayload = {
  path: string;
  referrer?: string;
  visitor_id: string;
  session_id: string;
  language?: string;
  screen?: string;
};

export function trackPageview(path: string, token?: string | null): void {
  if (typeof window === "undefined") return;
  const payload: TrackPayload = {
    path: path || "/",
    referrer: document.referrer || undefined,
    visitor_id: getVisitorId(),
    session_id: getSessionId(),
    language: navigator.language || undefined,
    screen:
      typeof window.screen?.width === "number"
        ? `${window.screen.width}x${window.screen.height}`
        : undefined,
  };

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const url = `${API_BASE}/analytics/event`;
  try {
    void fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      keepalive: true,
      mode: "cors",
      credentials: "omit",
    }).catch(() => {
      /* ignore network errors */
    });
  } catch {
    /* ignore */
  }
}

/** Expose visitor id in console once so you can exclude yourself. */
export function logMyAnalyticsIds(): void {
  if (typeof window === "undefined") return;
  try {
    if (window.sessionStorage.getItem("opcg_analytics_vid_logged") === "1") return;
    window.sessionStorage.setItem("opcg_analytics_vid_logged", "1");
  } catch {
    /* ignore */
  }
  // eslint-disable-next-line no-console
  console.info(
    "[OPCG analytics] your visitor_id (add to ANALYTICS_EXCLUDE_VISITOR_IDS):",
    getVisitorId(),
  );
}
