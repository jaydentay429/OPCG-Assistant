import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { ApiError } from "./api";
import {
  AUTH_STORAGE_KEY,
  refreshAuthSession,
  restoreAuthSession,
  type AuthStorage,
} from "./authSession";

const noWait = async () => {};
const fast = { delayMs: 0, sleep: noWait };

const originalFetch = globalThis.fetch;

function memoryStorage(): AuthStorage {
  const map = new Map<string, string>();
  return {
    getItem: (key) => (map.has(key) ? map.get(key)! : null),
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

function seedLogin(storage: AuthStorage, username = "luffy") {
  storage.setItem(
    AUTH_STORAGE_KEY,
    JSON.stringify({
      t: "tok-1",
      u: username,
      e: `${username}@example.com`,
      v: "1",
      a: "0",
    }),
  );
}

function stored(storage: AuthStorage): { t?: string; u?: string; e?: string; v?: string; a?: string } | null {
  const raw = storage.getItem(AUTH_STORAGE_KEY);
  return raw ? (JSON.parse(raw) as { t?: string; u?: string; e?: string; v?: string; a?: string }) : null;
}

function httpResponse(status: number, body: unknown, statusText = ""): Response {
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  return new Response(payload, {
    status,
    statusText,
    headers: { "Content-Type": typeof body === "string" ? "text/plain" : "application/json" },
  });
}

const meBody = {
  username: "zoro",
  email: "zoro@example.com",
  email_verified: true,
  is_admin: true,
};

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("restoreAuthSession", () => {
  it("clears the stored login when /auth/me returns 401", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      return httpResponse(401, { detail: "invalid token" }, "Unauthorized");
    };

    const session = await restoreAuthSession(storage, fast);

    assert.equal(calls, 1);
    assert.equal(session.token, null);
    assert.equal(session.username, null);
    assert.equal(storage.getItem(AUTH_STORAGE_KEY), null);
  });

  it("clears the stored login when /auth/me returns 403", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      return httpResponse(403, { detail: "revoked" }, "Forbidden");
    };

    const session = await restoreAuthSession(storage, fast);

    assert.equal(calls, 1);
    assert.equal(session.token, null);
    assert.equal(storage.getItem(AUTH_STORAGE_KEY), null);
  });

  it("keeps the token and username when /auth/me returns 502", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      return httpResponse(502, "bad gateway", "Bad Gateway");
    };

    const session = await restoreAuthSession(storage, fast);

    assert.equal(calls, 4);
    assert.equal(session.token, "tok-1");
    assert.equal(session.username, "luffy");
    assert.equal(session.email, "luffy@example.com");
    const saved = stored(storage);
    assert.equal(saved?.t, "tok-1");
    assert.equal(saved?.u, "luffy");
  });

  it("keeps the stored login when /auth/me fails with a network error", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      throw new TypeError("Failed to fetch");
    };

    const session = await restoreAuthSession(storage, fast);

    assert.equal(calls, 4);
    assert.equal(session.token, "tok-1");
    assert.equal(session.username, "luffy");
    assert.equal(stored(storage)?.t, "tok-1");
    assert.equal(stored(storage)?.u, "luffy");
  });

  it("keeps the stored login on 429 and on timeout", async () => {
    const storage = memoryStorage();
    seedLogin(storage, "nami");
    globalThis.fetch = async () => httpResponse(429, { detail: "slow down" }, "Too Many Requests");

    const limited = await restoreAuthSession(storage, fast);
    assert.equal(limited.token, "tok-1");
    assert.equal(limited.username, "nami");
    assert.equal(stored(storage)?.u, "nami");

    globalThis.fetch = async () => {
      throw Object.assign(new Error("aborted"), { name: "AbortError" });
    };
    const timedOut = await restoreAuthSession(storage, { ...fast, retries: 0 });
    assert.equal(timedOut.token, "tok-1");
    assert.equal(timedOut.username, "nami");
    assert.equal(stored(storage)?.t, "tok-1");
  });

  it("refreshes the stored profile after a 502 retry succeeds", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let calls = 0;
    globalThis.fetch = async (input, init) => {
      calls += 1;
      const url = String(input);
      assert.match(url, /\/auth\/me$/);
      const headers = new Headers(init?.headers);
      assert.equal(headers.get("authorization"), "Bearer tok-1");
      if (calls === 1) return httpResponse(502, "bad gateway", "Bad Gateway");
      return httpResponse(200, meBody);
    };

    const session = await restoreAuthSession(storage, fast);

    assert.equal(calls, 2);
    assert.equal(session.token, "tok-1");
    assert.equal(session.username, "zoro");
    assert.equal(session.email, "zoro@example.com");
    assert.equal(session.verified, true);
    assert.equal(session.isAdmin, true);
    const saved = stored(storage);
    assert.equal(saved?.t, "tok-1");
    assert.equal(saved?.u, "zoro");
    assert.equal(saved?.e, "zoro@example.com");
    assert.equal(saved?.v, "1");
    assert.equal(saved?.a, "1");
  });
});

describe("restoreAuthSession abort", () => {
  it("does not clear the stored login if the session changed before a 401 arrives", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let abort = false;
    globalThis.fetch = async () => {
      abort = true;
      return httpResponse(401, { detail: "invalid token" }, "Unauthorized");
    };

    const session = await restoreAuthSession(storage, {
      ...fast,
      shouldAbort: () => abort,
    });

    assert.equal(session.token, "tok-1");
    assert.equal(session.username, "luffy");
    assert.equal(stored(storage)?.t, "tok-1");
  });
});

describe("refreshAuthSession", () => {
  it("clears the stored login when /auth/me returns 401 or 403", async () => {
    for (const status of [401, 403]) {
      const storage = memoryStorage();
      seedLogin(storage);
      globalThis.fetch = async () => httpResponse(status, { detail: "nope" });
      const result = await refreshAuthSession(storage, "tok-1", fast);
      assert.equal(result.status, "rejected");
      assert.ok(result.status === "rejected" && result.error instanceof ApiError);
      assert.equal(result.status === "rejected" && result.error instanceof ApiError && result.error.status, status);
      assert.equal(storage.getItem(AUTH_STORAGE_KEY), null);
    }
  });

  it("keeps the stored login when /auth/me returns 502 or the network fails", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    globalThis.fetch = async () => httpResponse(502, "bad gateway", "Bad Gateway");
    const down = await refreshAuthSession(storage, "tok-1", fast);
    assert.equal(down.status, "kept");
    assert.equal(stored(storage)?.t, "tok-1");
    assert.equal(stored(storage)?.u, "luffy");

    globalThis.fetch = async () => {
      throw new TypeError("Failed to fetch");
    };
    const offline = await refreshAuthSession(storage, "tok-1", { ...fast, retries: 0 });
    assert.equal(offline.status, "kept");
    assert.equal(stored(storage)?.u, "luffy");
  });

  it("refreshes the stored profile after a retry succeeds", async () => {
    const storage = memoryStorage();
    seedLogin(storage);
    let calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      if (calls === 1) return httpResponse(502, "bad gateway", "Bad Gateway");
      return httpResponse(200, meBody);
    };

    const result = await refreshAuthSession(storage, "tok-1", fast);

    assert.equal(calls, 2);
    assert.equal(result.status, "updated");
    if (result.status === "updated") {
      assert.equal(result.session.username, "zoro");
      assert.equal(result.session.isAdmin, true);
    }
    assert.equal(stored(storage)?.u, "zoro");
    assert.equal(stored(storage)?.t, "tok-1");
  });
});
