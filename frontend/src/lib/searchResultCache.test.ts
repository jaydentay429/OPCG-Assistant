import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import {
  clearSearchResultMemory,
  recallSearchResults,
  rememberSearchResults,
  searchResultsCacheKey,
} from "./searchResultCache";

const store = new Map<string, string>();

afterEach(() => {
  store.clear();
  clearSearchResultMemory();
  delete (globalThis as { sessionStorage?: Storage }).sessionStorage;
});

function installSessionStorage(): void {
  (globalThis as { sessionStorage?: Storage }).sessionStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => store.clear(),
    key: () => null,
    get length() {
      return store.size;
    },
  };
}

describe("searchResultCache", () => {
  it("returns the last page only when the query key matches", () => {
    installSessionStorage();
    const key = searchResultsCacheKey("opcg_search_state_v1", { q: "魯夫", offset: 0, limit: 70 });
    rememberSearchResults("opcg_search_state_v1", {
      key,
      cards: [{ id: "ST01-001", name: "蒙其·D·魯夫" }],
      total: 244,
    });
    clearSearchResultMemory();
    const hit = recallSearchResults("opcg_search_state_v1", key);
    assert.equal(hit?.cards[0]?.id, "ST01-001");
    assert.equal(hit?.total, 244);
    const other = searchResultsCacheKey("opcg_search_state_v1", { q: "OP18", offset: 0, limit: 70 });
    assert.equal(recallSearchResults("opcg_search_state_v1", other), null);
  });

  it("keeps an in-memory copy when sessionStorage rejects the write", () => {
    (globalThis as { sessionStorage?: Storage }).sessionStorage = {
      getItem: () => null,
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => undefined,
      clear: () => undefined,
      key: () => null,
      get length() {
        return 0;
      },
    };
    const key = searchResultsCacheKey("opcg_search_state_v1", { q: "CP9" });
    rememberSearchResults("opcg_search_state_v1", {
      key,
      cards: [{ id: "OP03-076" }],
      total: 44,
    });
    assert.equal(recallSearchResults("opcg_search_state_v1", key)?.cards[0]?.id, "OP03-076");
  });
});
