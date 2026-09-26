import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {
  CHUNK_RELOAD_STORAGE_KEY,
  CHUNK_RELOAD_WINDOW_MS,
  attachChunkLoadRecovery,
  isChunkLoadError,
  recoverFromChunkLoadError,
  reloadOnceForChunkError,
  type ChunkLoadEventTarget,
} from "./chunkReload";

type Listener = (event: Event) => void;

class FakeTarget implements ChunkLoadEventTarget {
  private listeners = new Map<string, Set<Listener>>();

  addEventListener(type: string, listener: Listener) {
    const set = this.listeners.get(type) ?? new Set();
    set.add(listener);
    this.listeners.set(type, set);
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type: string, event: object) {
    for (const listener of this.listeners.get(type) ?? []) listener(event as Event);
  }
}

function chunkError(message = "Loading chunk 927 failed."): Error {
  const error = new Error(message);
  error.name = "ChunkLoadError";
  return error;
}

describe("isChunkLoadError", () => {
  it("matches ChunkLoadError by name even when the message is unrelated", () => {
    const error = new Error("network down");
    error.name = "ChunkLoadError";
    assert.equal(isChunkLoadError(error), true);
  });

  it("matches the webpack, Chrome, and Safari chunk messages", () => {
    assert.equal(isChunkLoadError(new Error("Loading chunk 927 failed.")), true);
    assert.equal(
      isChunkLoadError(new Error("Loading chunk app/page failed.\n(missing: /_next/static/chunks/app/page.js)")),
      true,
    );
    assert.equal(
      isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: https://optcgassistant.com/_next/static/chunks/page.js")),
      true,
    );
    assert.equal(isChunkLoadError(new TypeError("Importing a module script failed.")), true);
    assert.equal(isChunkLoadError("Loading chunk 12 failed"), true);
    assert.equal(isChunkLoadError("Uncaught ChunkLoadError: Loading chunk 12 failed."), true);
  });

  it("ignores ordinary failures, including a generic fetch error", () => {
    assert.equal(isChunkLoadError(new TypeError("Failed to fetch")), false);
    assert.equal(isChunkLoadError(new Error("Loading chunk metadata from the API failed")), false);
    assert.equal(isChunkLoadError("Importing a module script"), false);
    assert.equal(isChunkLoadError(null), false);
    assert.equal(isChunkLoadError(undefined), false);
    assert.equal(isChunkLoadError(404), false);
    assert.equal(isChunkLoadError({}), false);
  });
});

describe("reloadOnceForChunkError", () => {
  const originals = {
    window: Object.getOwnPropertyDescriptor(globalThis, "window"),
    sessionStorage: Object.getOwnPropertyDescriptor(globalThis, "sessionStorage"),
  };
  let reloads = 0;
  let storage = new Map<string, string>();
  let storageThrows = false;

  function installBrowser() {
    storage = new Map();
    storageThrows = false;
    reloads = 0;
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      value: {
        getItem(key: string) {
          if (storageThrows) throw new Error("sessionStorage blocked");
          return storage.has(key) ? storage.get(key)! : null;
        },
        setItem(key: string, value: string) {
          if (storageThrows) throw new Error("sessionStorage blocked");
          storage.set(key, value);
        },
      },
    });
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: {
        location: {
          reload() {
            reloads += 1;
          },
        },
      },
    });
  }

  afterEach(() => {
    for (const key of ["window", "sessionStorage"] as const) {
      const descriptor = originals[key];
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  });

  it("uses a 10 second window and the opcg-chunk-reload-at key", () => {
    assert.equal(CHUNK_RELOAD_WINDOW_MS, 10_000);
    assert.equal(CHUNK_RELOAD_STORAGE_KEY, "opcg-chunk-reload-at");
  });

  it("reloads once and records the timestamp", () => {
    installBrowser();
    const now = 1_700_000_000_000;
    assert.equal(reloadOnceForChunkError(now), true);
    assert.equal(reloads, 1);
    assert.equal(storage.get(CHUNK_RELOAD_STORAGE_KEY), String(now));
  });

  it("does not reload again until 10 seconds have passed", () => {
    installBrowser();
    const now = 1_700_000_000_000;
    assert.equal(reloadOnceForChunkError(now), true);

    assert.equal(reloadOnceForChunkError(now + 1), false);
    assert.equal(reloadOnceForChunkError(now + CHUNK_RELOAD_WINDOW_MS - 1), false);
    assert.equal(reloads, 1);
    assert.equal(storage.get(CHUNK_RELOAD_STORAGE_KEY), String(now));

    assert.equal(reloadOnceForChunkError(now + CHUNK_RELOAD_WINDOW_MS), true);
    assert.equal(reloads, 2);
    assert.equal(storage.get(CHUNK_RELOAD_STORAGE_KEY), String(now + CHUNK_RELOAD_WINDOW_MS));
  });

  it("does not reload when sessionStorage throws", () => {
    installBrowser();
    storageThrows = true;
    assert.equal(reloadOnceForChunkError(1_700_000_000_000), false);
    assert.equal(reloads, 0);
    assert.equal(storage.size, 0);
  });

  it("does not reload for an unrelated error", () => {
    installBrowser();
    assert.equal(recoverFromChunkLoadError(new Error("Failed to fetch"), 1_700_000_000_000), false);
    assert.equal(reloads, 0);
    assert.equal(storage.has(CHUNK_RELOAD_STORAGE_KEY), false);
  });

  it("reloads from error and unhandledrejection, and only once inside the window", () => {
    installBrowser();
    const target = new FakeTarget();
    const detach = attachChunkLoadRecovery(target);
    const nowStart = Date.now();

    target.dispatch("error", { error: chunkError(), message: "Loading chunk 927 failed." });
    assert.equal(reloads, 1);
    const stamped = Number(storage.get(CHUNK_RELOAD_STORAGE_KEY));
    assert.ok(stamped >= nowStart);

    target.dispatch("unhandledrejection", { reason: new TypeError("Failed to fetch dynamically imported module: /chunk.js") });
    target.dispatch("error", { error: null, message: "Importing a module script failed." });
    target.dispatch("error", { error: new Error("Failed to fetch"), message: "Failed to fetch" });
    assert.equal(reloads, 1);

    detach();
    storage.delete(CHUNK_RELOAD_STORAGE_KEY);
    target.dispatch("unhandledrejection", { reason: chunkError() });
    assert.equal(reloads, 1);
  });
});
