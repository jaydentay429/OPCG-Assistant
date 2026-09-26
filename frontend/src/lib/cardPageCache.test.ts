import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiError } from "./api";
import {
  CardTemporarilyUnavailableError,
  createMapStore,
  fetchCardDetailUncached,
  fetchSecondaryUncached,
  loadRenderableCard,
  readThroughSuccessCache,
} from "./cardPageCache";
import type { CardDetailResponse } from "./types";

const noWait = async () => {};
const retryNow = { delayMs: 0, sleep: noWait };

function cardPayload(id: string, name: string): CardDetailResponse {
  return { card: { id, name, effect: `${name} effect`, rarity: "SR", card_type: "Character" } };
}

describe("readThroughSuccessCache", () => {
  it("does not store a throw or a resolved null", async () => {
    const store = createMapStore<CardDetailResponse>();
    await assert.rejects(
      () => readThroughSuccessCache(store, "OP05-093", async () => {
        throw new ApiError(502, "bad gateway");
      }),
      (error: unknown) => error instanceof ApiError && error.status === 502,
    );
    await assert.rejects(
      () => readThroughSuccessCache(store, "OP05-093", async () => null),
      (error: unknown) => error instanceof CardTemporarilyUnavailableError,
    );
    assert.equal(store.size(), 0);
    assert.equal(store.has("OP05-093"), false);
  });

  it("stores a success and then serves it without calling load again", async () => {
    const store = createMapStore<CardDetailResponse>();
    let calls = 0;
    const first = await readThroughSuccessCache(store, "OP05-093", async () => {
      calls += 1;
      return cardPayload("OP05-093", "Nami");
    });
    const second = await readThroughSuccessCache(store, "OP05-093", async () => {
      calls += 1;
      return cardPayload("OP05-093", "should-not-run");
    });
    assert.equal(first.card.name, "Nami");
    assert.equal(second.card.name, "Nami");
    assert.equal(calls, 1);
    assert.equal(store.size(), 1);
  });
});

describe("card detail cache policy", () => {
  it("does not cache a 502 after retries, then stores the recovered card", async () => {
    const store = createMapStore<CardDetailResponse>();
    let mode: "down" | "up" = "down";
    const calls: string[] = [];
    const fetchCard = async (id: string) => {
      calls.push(id);
      if (mode === "down") throw new ApiError(502, "bad gateway");
      return cardPayload(id, "Nami");
    };

    await assert.rejects(
      () =>
        readThroughSuccessCache(store, "OP05-093", () =>
          fetchCardDetailUncached("OP05-093", fetchCard, retryNow),
        ),
      (error: unknown) => error instanceof CardTemporarilyUnavailableError,
    );
    assert.deepEqual(calls, ["OP05-093", "OP05-093"]);
    assert.equal(store.size(), 0);

    mode = "up";
    const loaded = await loadRenderableCard(
      "OP05-093",
      () =>
        readThroughSuccessCache(store, "OP05-093", () =>
          fetchCardDetailUncached("OP05-093", fetchCard, retryNow),
        ),
      true,
    );
    assert.equal(loaded?.name, "Nami");
    assert.equal(store.size(), 1);
    assert.equal(calls.length, 3);

    calls.length = 0;
    const hit = await loadRenderableCard(
      "OP05-093",
      () =>
        readThroughSuccessCache(store, "OP05-093", () =>
          fetchCardDetailUncached("OP05-093", fetchCard, retryNow),
        ),
      true,
    );
    assert.equal(hit?.id, "OP05-093");
    assert.deepEqual(calls, []);
  });

  it("does not cache a connection failure, then reads fresh data after recovery", async () => {
    const store = createMapStore<CardDetailResponse>();
    let fail = true;
    const fetchCard = async (id: string) => {
      if (fail) throw new TypeError("fetch failed");
      return cardPayload(id, "Parallel");
    };
    await assert.rejects(
      () => fetchCardDetailUncached("OP05-093-P1", fetchCard, retryNow),
      (error: unknown) => error instanceof CardTemporarilyUnavailableError,
    );
    assert.equal(store.size(), 0);
    fail = false;
    const data = await readThroughSuccessCache(store, "OP05-093-P1", () =>
      fetchCardDetailUncached("OP05-093-P1", fetchCard, retryNow),
    );
    assert.equal(data.card.name, "Parallel");
    assert.equal(store.size(), 1);
  });

  it("treats HTTP 404 as a miss and does not cache it or retry it", async () => {
    const store = createMapStore<CardDetailResponse>();
    let calls = 0;
    const fetchCard = async () => {
      calls += 1;
      throw new ApiError(404, "missing");
    };
    await assert.rejects(
      () =>
        readThroughSuccessCache(store, "ZZ99-999", () =>
          fetchCardDetailUncached("ZZ99-999", fetchCard, retryNow),
        ),
      (error: unknown) => error instanceof ApiError && error.status === 404,
    );
    assert.equal(calls, 1);
    assert.equal(store.size(), 0);

    const missing = await loadRenderableCard(
      "ZZ99-999",
      () =>
        readThroughSuccessCache(store, "ZZ99-999", () =>
          fetchCardDetailUncached("ZZ99-999", fetchCard, retryNow),
        ),
      false,
    );
    assert.equal(missing, null);
    assert.equal(store.size(), 0);
    assert.equal(calls, 2);
  });

  it("does not turn a 5xx or a timeout into a 404, including for an unknown id", async () => {
    for (const status of [408, 500, 502, 503, 504]) {
      const store = createMapStore<CardDetailResponse>();
      const fetchCard = async () => {
        throw new ApiError(status, "unavailable");
      };
      await assert.rejects(
        () =>
          loadRenderableCard(
            "ZZ99-999",
            () =>
              readThroughSuccessCache(store, "ZZ99-999", () =>
                fetchCardDetailUncached("ZZ99-999", fetchCard, retryNow),
              ),
            false,
          ),
        (error: unknown) => error instanceof CardTemporarilyUnavailableError,
      );
      assert.equal(store.size(), 0);
    }
  });

  it("does not 404 a catalogued id when the API returns 404", async () => {
    const store = createMapStore<CardDetailResponse>();
    const fetchCard = async () => {
      throw new ApiError(404, "missing");
    };
    await assert.rejects(
      () =>
        loadRenderableCard(
          "OP05-093",
          () =>
            readThroughSuccessCache(store, "OP05-093", () =>
              fetchCardDetailUncached("OP05-093", fetchCard, retryNow),
            ),
          true,
        ),
      (error: unknown) => error instanceof ApiError && error.status === 404,
    );
    assert.equal(store.size(), 0);
  });

  it("does not cache a 200 body with no card", async () => {
    const store = createMapStore<CardDetailResponse>();
    const fetchCard = async () => ({ card: null }) as unknown as CardDetailResponse;
    await assert.rejects(
      () =>
        readThroughSuccessCache(store, "ZZ99-999", () =>
          fetchCardDetailUncached("ZZ99-999", fetchCard, retryNow),
        ),
      (error: unknown) => error instanceof ApiError && error.status === 404,
    );
    assert.equal(store.size(), 0);
  });
});

describe("secondary tournament cache policy", () => {
  it("does not cache a 502, then stores the recovered list", async () => {
    const store = createMapStore<{ items: Array<{ id: string }> }>();
    let mode: "down" | "up" = "down";
    let calls = 0;
    const load = async () => {
      calls += 1;
      if (mode === "down") throw new ApiError(502, "bad gateway");
      return { items: [{ id: "deck-1" }] };
    };

    await assert.rejects(
      () =>
        readThroughSuccessCache(store, "OP05-093", () => fetchSecondaryUncached(load, retryNow)),
      (error: unknown) => error instanceof CardTemporarilyUnavailableError,
    );
    assert.equal(store.size(), 0);
    assert.equal(calls, 2);

    mode = "up";
    const data = await readThroughSuccessCache(store, "OP05-093", () =>
      fetchSecondaryUncached(load, retryNow),
    );
    assert.deepEqual(data.items, [{ id: "deck-1" }]);
    assert.equal(store.size(), 1);
    assert.equal(calls, 3);

    const hitCalls = calls;
    const again = await readThroughSuccessCache(store, "OP05-093", () =>
      fetchSecondaryUncached(load, retryNow),
    );
    assert.equal(again.items[0]?.id, "deck-1");
    assert.equal(calls, hitCalls);
  });

  it("caches a successful empty list and does not cache a null failure", async () => {
    const store = createMapStore<{ items: unknown[] }>();
    const empty = await readThroughSuccessCache(store, "empty", () =>
      fetchSecondaryUncached(async () => ({ items: [] }), retryNow),
    );
    assert.deepEqual(empty.items, []);
    assert.equal(store.size(), 1);

    await assert.rejects(
      () =>
        readThroughSuccessCache(store, "null", () =>
          fetchSecondaryUncached(async () => null, retryNow),
        ),
      (error: unknown) => error instanceof CardTemporarilyUnavailableError,
    );
    assert.equal(store.has("null"), false);
  });
});
