import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {
  CHUNK_NAV_CLICK_WINDOW_MS,
  CHUNK_RELOAD_STORAGE_KEY,
  CHUNK_RELOAD_WINDOW_MS,
  assignOnceForChunkNavigation,
  attachChunkLoadRecovery,
  clearPendingNavigation,
  handleChunkLoadFailure,
  internalNavigationHrefFromClick,
  isChunkLoadError,
  type ChunkLoadEventTarget,
} from "./chunkReload";

const ORIGIN = "http://127.0.0.1:3456";

type Listener = (event: Event) => void;

class FakeTarget implements ChunkLoadEventTarget {
  private listeners = new Map<string, Set<Listener>>();

  addEventListener(type: string, listener: Listener, capture = false) {
    const key = `${type}:${capture ? "capture" : "bubble"}`;
    const set = this.listeners.get(key) ?? new Set();
    set.add(listener);
    this.listeners.set(key, set);
  }

  removeEventListener(type: string, listener: Listener, capture = false) {
    this.listeners.get(`${type}:${capture ? "capture" : "bubble"}`)?.delete(listener);
  }

  dispatch(type: string, event: object, capture = false) {
    const key = `${type}:${capture ? "capture" : "bubble"}`;
    for (const listener of this.listeners.get(key) ?? []) listener(event as Event);
  }
}

function chunkError(message = "Loading chunk 927 failed."): Error {
  const error = new Error(message);
  error.name = "ChunkLoadError";
  return error;
}

function anchor(attrs: { href: string; target?: string; download?: boolean }, current = `${ORIGIN}/`) {
  const el = {
    href: new URL(attrs.href, current).href,
    target: attrs.target ?? "",
    getAttribute(name: string) {
      if (name === "href") return attrs.href;
      if (name === "target") return attrs.target ?? null;
      if (name === "download") return attrs.download ? "" : null;
      return null;
    },
    hasAttribute(name: string) {
      return name === "download" && Boolean(attrs.download);
    },
    closest(selector: string) {
      return selector === "a" ? el : null;
    },
  };
  return el;
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
      isChunkLoadError(
        new TypeError("Failed to fetch dynamically imported module: https://optcgassistant.com/_next/static/chunks/page.js"),
      ),
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

describe("internalNavigationHrefFromClick", () => {
  const current = `${ORIGIN}/builder`;

  it("resolves a same-origin link, including a click on a child of the anchor", () => {
    const link = anchor({ href: "/search?q=luffy" }, current);
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: link }, current),
      `${ORIGIN}/search?q=luffy`,
    );
    const child = { closest: (selector: string) => (selector === "a" ? link : null) };
    assert.equal(internalNavigationHrefFromClick({ button: 0, target: child }, current), `${ORIGIN}/search?q=luffy`);
  });

  it("ignores external links, new tabs, modifiers, downloads, and hash-only changes", () => {
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: anchor({ href: "https://example.com/deck" }, current) }, current),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: anchor({ href: "/search", target: "_blank" }, current) }, current),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick(
        { button: 0, metaKey: true, target: anchor({ href: "/search" }, current) },
        current,
      ),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick(
        { button: 0, ctrlKey: true, target: anchor({ href: "/search" }, current) },
        current,
      ),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick({ button: 1, target: anchor({ href: "/search" }, current) }, current),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: anchor({ href: "/deck.txt", download: true }, current) }, current),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: anchor({ href: "#leader" }, current) }, current),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: anchor({ href: "/builder?x=1#top" }, `${ORIGIN}/builder?x=1`) }, `${ORIGIN}/builder?x=1`),
      null,
    );
    assert.equal(
      internalNavigationHrefFromClick({ button: 0, target: anchor({ href: "mailto:jaydentay429@gmail.com" }, current) }, current),
      null,
    );
    assert.equal(internalNavigationHrefFromClick({ button: 0, target: { closest: () => null } }, current), null);
  });
});

describe("chunk recovery", () => {
  const originals = {
    window: Object.getOwnPropertyDescriptor(globalThis, "window"),
    sessionStorage: Object.getOwnPropertyDescriptor(globalThis, "sessionStorage"),
  };
  let assigned: string[] = [];
  let reloads = 0;
  let storage = new Map<string, string>();
  let storageThrows = false;
  let href = `${ORIGIN}/`;

  function installBrowser() {
    storage = new Map();
    storageThrows = false;
    assigned = [];
    reloads = 0;
    href = `${ORIGIN}/`;
    clearPendingNavigation();
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
          get href() {
            return href;
          },
          assign(url: string) {
            assigned.push(url);
            href = url;
          },
          reload() {
            reloads += 1;
          },
        },
      },
    });
  }

  afterEach(() => {
    clearPendingNavigation();
    for (const key of ["window", "sessionStorage"] as const) {
      const descriptor = originals[key];
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  });

  it("keeps the 10 second window and the opcg-chunk-reload-at key", () => {
    assert.equal(CHUNK_RELOAD_WINDOW_MS, 10_000);
    assert.equal(CHUNK_RELOAD_STORAGE_KEY, "opcg-chunk-reload-at");
    assert.equal(CHUNK_NAV_CLICK_WINDOW_MS, 5_000);
  });

  it("assigns the clicked page once and records the timestamp", () => {
    installBrowser();
    const now = 1_700_000_000_000;
    assert.equal(assignOnceForChunkNavigation(`${ORIGIN}/search`, now), true);
    assert.deepEqual(assigned, [`${ORIGIN}/search`]);
    assert.equal(reloads, 0);
    assert.equal(storage.get(CHUNK_RELOAD_STORAGE_KEY), String(now));
  });

  it("does not assign again until 10 seconds have passed", () => {
    installBrowser();
    const now = 1_700_000_000_000;
    assert.equal(assignOnceForChunkNavigation(`${ORIGIN}/search`, now), true);
    assert.equal(assignOnceForChunkNavigation(`${ORIGIN}/builder`, now + 1), false);
    assert.equal(assignOnceForChunkNavigation(`${ORIGIN}/builder`, now + CHUNK_RELOAD_WINDOW_MS - 1), false);
    assert.deepEqual(assigned, [`${ORIGIN}/search`]);
    assert.equal(storage.get(CHUNK_RELOAD_STORAGE_KEY), String(now));

    assert.equal(assignOnceForChunkNavigation(`${ORIGIN}/prices`, now + CHUNK_RELOAD_WINDOW_MS), true);
    assert.deepEqual(assigned, [`${ORIGIN}/search`, `${ORIGIN}/prices`]);
    assert.equal(reloads, 0);
  });

  it("does not assign when sessionStorage throws", () => {
    installBrowser();
    storageThrows = true;
    assert.equal(assignOnceForChunkNavigation(`${ORIGIN}/search`, 1_700_000_000_000), false);
    assert.deepEqual(assigned, []);
    assert.equal(storage.size, 0);
  });

  it("navigates only after an in-app link click, and prompts otherwise", () => {
    installBrowser();
    const windowTarget = new FakeTarget();
    const documentTarget = new FakeTarget();
    let prompts = 0;
    let clock = 1_700_000_000_000;
    const detach = attachChunkLoadRecovery({
      windowTarget,
      documentTarget,
      currentHref: () => href,
      now: () => clock,
      onPrompt: () => {
        prompts += 1;
      },
    });

    windowTarget.dispatch("error", { error: chunkError(), message: "Loading chunk 927 failed." });
    windowTarget.dispatch("unhandledrejection", {
      reason: new TypeError("Failed to fetch dynamically imported module: /_next/static/chunks/panel.js"),
    });
    assert.deepEqual(assigned, []);
    assert.equal(prompts, 2);
    assert.equal(storage.has(CHUNK_RELOAD_STORAGE_KEY), false);

    documentTarget.dispatch("click", { button: 0, target: { closest: () => null } }, true);
    windowTarget.dispatch("error", { error: chunkError("Loading chunk panel failed."), message: "Loading chunk panel failed." });
    assert.deepEqual(assigned, []);
    assert.equal(prompts, 3);

    documentTarget.dispatch("click", { button: 0, target: anchor({ href: "/search" }, href) }, true);
    windowTarget.dispatch("unhandledrejection", { reason: chunkError() });
    assert.deepEqual(assigned, [`${ORIGIN}/search`]);
    assert.equal(prompts, 3);
    assert.equal(storage.get(CHUNK_RELOAD_STORAGE_KEY), String(clock));
    assert.equal(reloads, 0);

    clock += 1_000;
    documentTarget.dispatch("click", { button: 0, target: anchor({ href: "/builder" }, href) }, true);
    windowTarget.dispatch("error", { error: null, message: "Importing a module script failed." });
    assert.deepEqual(assigned, [`${ORIGIN}/search`]);
    assert.equal(prompts, 4);

    clock += CHUNK_RELOAD_WINDOW_MS;
    documentTarget.dispatch("click", { button: 0, target: anchor({ href: "/prices" }, href) }, true);
    windowTarget.dispatch("error", { error: chunkError(), message: "Loading chunk 12 failed." });
    assert.deepEqual(assigned, [`${ORIGIN}/search`, `${ORIGIN}/prices`]);

    detach();
    clearPendingNavigation();
    storage.delete(CHUNK_RELOAD_STORAGE_KEY);
    documentTarget.dispatch("click", { button: 0, target: anchor({ href: "/play" }, href) }, true);
    windowTarget.dispatch("unhandledrejection", { reason: chunkError() });
    assert.deepEqual(assigned, [`${ORIGIN}/search`, `${ORIGIN}/prices`]);
  });

  it("does not treat external or new-tab clicks as navigation", () => {
    installBrowser();
    const windowTarget = new FakeTarget();
    const documentTarget = new FakeTarget();
    let prompts = 0;
    const clock = 1_700_000_000_000;
    attachChunkLoadRecovery({
      windowTarget,
      documentTarget,
      currentHref: () => href,
      now: () => clock,
      onPrompt: () => {
        prompts += 1;
      },
    });

    documentTarget.dispatch(
      "click",
      { button: 0, target: anchor({ href: "https://example.com/cards" }, href) },
      true,
    );
    documentTarget.dispatch("click", { button: 0, ctrlKey: true, target: anchor({ href: "/search" }, href) }, true);
    documentTarget.dispatch("click", { button: 0, target: anchor({ href: "/search", target: "_blank" }, href) }, true);
    windowTarget.dispatch("unhandledrejection", { reason: chunkError() });
    assert.deepEqual(assigned, []);
    assert.equal(prompts, 1);
    assert.equal(handleChunkLoadFailure(new Error("Failed to fetch"), clock), "ignored");
  });

  it("stops treating a click as the cause once a few seconds have passed", () => {
    installBrowser();
    const now = 1_700_000_000_000;
    const windowTarget = new FakeTarget();
    const documentTarget = new FakeTarget();
    let prompts = 0;
    let clock = now;
    attachChunkLoadRecovery({
      windowTarget,
      documentTarget,
      currentHref: () => href,
      now: () => clock,
      onPrompt: () => {
        prompts += 1;
      },
    });

    documentTarget.dispatch("click", { button: 0, target: anchor({ href: "/search" }, href) }, true);
    clock = now + CHUNK_NAV_CLICK_WINDOW_MS + 1;
    windowTarget.dispatch("error", { error: chunkError() });
    assert.deepEqual(assigned, []);
    assert.equal(prompts, 1);
  });
});
