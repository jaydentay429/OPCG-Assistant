/**
 * Card art is 5:7. The attributes reserve that ratio on every `<img>`.
 * CSS still sets the displayed size (width 100% inside an aspect-ratio box).
 */
export const CARD_ART_WIDTH = 500;
export const CARD_ART_HEIGHT = 700;

/**
 * First row of the search card wall and the price wall.
 * Desktop is 7 columns, phones 5, so seven images cover the first row
 * on both, plus the two phone tiles that start the second row.
 */
export const CARD_WALL_EAGER_COUNT = 7;

export function cardWallImageLoading(index: number): "eager" | "lazy" {
  return index >= 0 && index < CARD_WALL_EAGER_COUNT ? "eager" : "lazy";
}

/** Only the eager first row is high priority. Later tiles stay at the browser default. */
export function cardWallImageFetchPriority(index: number): "high" | undefined {
  return index >= 0 && index < CARD_WALL_EAGER_COUNT ? "high" : undefined;
}
