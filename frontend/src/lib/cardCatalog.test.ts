import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { cardNotFoundMetadata } from "./cardNotFoundMetadata";
import { catalogHasCard, missingCardShould404, normalizeCatalogCardId } from "./cardCatalog";

describe("missingCardShould404", () => {
  it("404s only a definitive miss that is absent from the catalog", () => {
    assert.equal(missingCardShould404(404, false), true);
    assert.equal(missingCardShould404(422, false), true);
    assert.equal(missingCardShould404(null, false), true);
  });

  it("does not 404 catalogued ids or transient failures", () => {
    assert.equal(missingCardShould404(404, true), false);
    assert.equal(missingCardShould404(422, true), false);
    assert.equal(missingCardShould404(null, true), false);
    assert.equal(missingCardShould404(408, false), false);
    assert.equal(missingCardShould404(500, false), false);
    assert.equal(missingCardShould404(503, true), false);
  });
});

describe("normalizeCatalogCardId", () => {
  it("matches stored keys for standard, parallel, and promo ids", () => {
    assert.equal(normalizeCatalogCardId("op01-065"), "OP01-065");
    assert.equal(normalizeCatalogCardId("st18-005-p2"), "ST18-005-P2");
    assert.equal(normalizeCatalogCardId("p-001"), "P-001");
    assert.equal(normalizeCatalogCardId("OP-01-065"), "OP01-065");
  });
});

describe("catalogHasCard", () => {
  it("knows real cards and rejects an unknown number", () => {
    assert.equal(catalogHasCard("OP01-065"), true);
    assert.equal(catalogHasCard("ST18-005-P2"), true);
    assert.equal(catalogHasCard("P-001"), true);
    assert.equal(catalogHasCard("op01-065"), true);
    assert.equal(catalogHasCard("OP99-999"), false);
  });
});

describe("card not-found metadata", () => {
  it("does not declare a second robots meta", () => {
    assert.equal(cardNotFoundMetadata.robots, null);
    assert.equal(JSON.stringify(cardNotFoundMetadata).includes("nofollow"), false);
  });
});
