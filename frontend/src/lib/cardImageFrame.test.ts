import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CARD_ART_HEIGHT,
  CARD_ART_WIDTH,
  CARD_WALL_EAGER_COUNT,
  cardWallImageFetchPriority,
  cardWallImageLoading,
} from "./cardImageFrame";

describe("card image frame", () => {
  it("reserves a 5:7 box", () => {
    assert.equal(CARD_ART_WIDTH * 7, CARD_ART_HEIGHT * 5);
  });

  it("marks only the first wall row eager and high priority", () => {
    assert.equal(CARD_WALL_EAGER_COUNT, 7);
    for (let index = 0; index < CARD_WALL_EAGER_COUNT; index += 1) {
      assert.equal(cardWallImageLoading(index), "eager");
      assert.equal(cardWallImageFetchPriority(index), "high");
    }
    assert.equal(cardWallImageLoading(CARD_WALL_EAGER_COUNT), "lazy");
    assert.equal(cardWallImageFetchPriority(CARD_WALL_EAGER_COUNT), undefined);
    assert.equal(cardWallImageLoading(69), "lazy");
    assert.equal(cardWallImageFetchPriority(-1), undefined);
  });
});
