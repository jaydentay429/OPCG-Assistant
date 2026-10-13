import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiError } from "./api";
import { catalogCard, catalogHasCard } from "./cardCatalog";
import {
  CARD_PAGE_RETRY_AFTER_SECONDS,
  cardUnavailableMetadata,
  resolveCardPageLoad,
} from "./cardPageFallback";
import type { Card, CardDetailResponse } from "./types";

function card(id: string, name: string): Card {
  return { id, name, effect: `${name} effect`, rarity: "SR", card_type: "Character" };
}

function payload(id: string, name: string): CardDetailResponse {
  return { card: card(id, name) };
}

describe("resolveCardPageLoad", () => {
  it("returns the API card and does not read bundled data", async () => {
    const memory = new Map<string, Card>();
    let staticReads = 0;
    const loaded = await resolveCardPageLoad("OP03-040", async () => payload("OP03-040", "娜美"), {
      knownInCatalog: () => {
        throw new Error("catalog should not be consulted");
      },
      readStatic: () => {
        staticReads += 1;
        return card("OP03-040", "bundled");
      },
      memory,
    });
    assert.equal(loaded.kind, "card");
    if (loaded.kind === "card") {
      assert.equal(loaded.source, "api");
      assert.equal(loaded.card.name, "娜美");
    }
    assert.equal(staticReads, 0);
    assert.equal(memory.get("OP03-040")?.name, "娜美");
  });

  it("uses the last successful card when the API is down, without another fetch", async () => {
    const memory = new Map<string, Card>([["OP06-086", card("OP06-086", "cached")]]);
    let calls = 0;
    let staticReads = 0;
    const loaded = await resolveCardPageLoad(
      "OP06-086",
      async () => {
        calls += 1;
        throw new ApiError(502, "bad gateway");
      },
      {
        knownInCatalog: () => true,
        readStatic: () => {
          staticReads += 1;
          return card("OP06-086", "bundled");
        },
        memory,
      },
    );
    assert.equal(calls, 1);
    assert.equal(staticReads, 0);
    assert.equal(loaded.kind, "card");
    if (loaded.kind === "card") {
      assert.equal(loaded.source, "memory");
      assert.equal(loaded.card.name, "cached");
    }
  });

  it("falls back to bundled rows for a timeout or 5xx and does not retry", async () => {
    for (const status of [408, 500, 502, 503, 504]) {
      let calls = 0;
      const loaded = await resolveCardPageLoad(
        "ST10-001",
        async () => {
          calls += 1;
          throw new ApiError(status, "unavailable");
        },
        {
          knownInCatalog: () => true,
          readStatic: () => card("ST10-001", "bundled"),
          memory: new Map(),
        },
      );
      assert.equal(calls, 1);
      assert.equal(loaded.kind, "card");
      if (loaded.kind === "card") {
        assert.equal(loaded.source, "static");
        assert.equal(loaded.card.name, "bundled");
      }
    }
  });

  it("uses bundled data after a connection error", async () => {
    let calls = 0;
    const loaded = await resolveCardPageLoad(
      "OP03-040",
      async () => {
        calls += 1;
        throw new TypeError("fetch failed");
      },
      {
        knownInCatalog: () => true,
        readStatic: (id) => catalogCard(id),
        memory: new Map(),
      },
    );
    assert.equal(calls, 1);
    assert.equal(loaded.kind, "card");
    if (loaded.kind === "card") {
      assert.equal(loaded.source, "static");
      assert.equal(loaded.card.id, "OP03-040");
      assert.ok(loaded.card.name);
      assert.ok(loaded.card.effect);
    }
  });

  it("reads the real bundled rows for the cards that 500'd during an outage", async () => {
    for (const id of ["OP03-040", "OP06-086", "ST10-001"]) {
      let calls = 0;
      const loaded = await resolveCardPageLoad(
        id,
        async () => {
          calls += 1;
          throw new ApiError(502, "down");
        },
        {
          knownInCatalog: () => catalogHasCard(id),
          readStatic: (cardId) => catalogCard(cardId),
          memory: new Map(),
        },
      );
      assert.equal(calls, 1);
      assert.equal(catalogHasCard(id), true);
      assert.equal(loaded.kind, "card");
      if (loaded.kind === "card") {
        assert.equal(loaded.card.id, id);
        assert.equal(loaded.source, "static");
        assert.ok(String(loaded.card.name || "").trim());
      }
    }
  });

  it("404s an unknown id and does not turn a 5xx into a 404", async () => {
    let staticReads = 0;
    const missing = await resolveCardPageLoad("ZZ99-999", async () => {
      throw new ApiError(404, "missing");
    }, {
      knownInCatalog: () => false,
      readStatic: () => {
        staticReads += 1;
        return null;
      },
      memory: new Map(),
    });
    assert.equal(missing.kind, "missing");
    assert.equal(staticReads, 0);

    const down = await resolveCardPageLoad("ZZ99-999", async () => {
      throw new ApiError(503, "down");
    }, {
      knownInCatalog: () => false,
      readStatic: () => null,
      memory: new Map(),
    });
    assert.equal(down.kind, "unavailable");
    if (down.kind === "unavailable") {
      assert.equal(down.retryAfterSeconds, CARD_PAGE_RETRY_AFTER_SECONDS);
    }
  });

  it("does not 404 a catalogued id when the API 404s and the row is bundled", async () => {
    const loaded = await resolveCardPageLoad("OP03-040", async () => {
      throw new ApiError(404, "missing");
    }, {
      knownInCatalog: () => true,
      readStatic: () => card("OP03-040", "娜美"),
      memory: new Map(),
    });
    assert.equal(loaded.kind, "card");
    if (loaded.kind === "card") assert.equal(loaded.source, "static");
  });

  it("asks for a retry when nothing is stored", async () => {
    const loaded = await resolveCardPageLoad("OP03-040", async () => {
      throw new ApiError(502, "down");
    }, {
      knownInCatalog: () => true,
      readStatic: () => null,
      memory: new Map(),
    });
    assert.deepEqual(loaded, {
      kind: "unavailable",
      retryAfterSeconds: CARD_PAGE_RETRY_AFTER_SECONDS,
    });
  });
});

describe("card unavailable metadata", () => {
  it("does not add noindex", () => {
    assert.equal("robots" in cardUnavailableMetadata, false);
    assert.equal(JSON.stringify(cardUnavailableMetadata).includes("noindex"), false);
    assert.equal(JSON.stringify(cardUnavailableMetadata).includes("nofollow"), false);
  });
});
