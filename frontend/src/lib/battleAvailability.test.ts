import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BATTLE_PAUSED_DETAIL,
  isBattleDisabledError,
  probeBattleService,
  reduceBattleService,
  shouldPollBattle,
  shouldReconnectBattleSocket,
} from "./battleAvailability.ts";

class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

describe("battle unavailable state", () => {
  it("recognizes the paused API detail and ignores a missing room", () => {
    assert.equal(isBattleDisabledError(new ApiError(404, BATTLE_PAUSED_DETAIL)), true);
    assert.equal(isBattleDisabledError(new ApiError(404, "Room not found.")), false);
    assert.equal(isBattleDisabledError(new ApiError(400, "Deck needs a Leader.")), false);
  });

  it("resolves one probe to ready or unavailable and does not poll while down", async () => {
    assert.equal(await probeBattleService(async () => ["deck"]), "ready");
    assert.equal(
      await probeBattleService(async () => {
        throw new ApiError(404, BATTLE_PAUSED_DETAIL);
      }),
      "unavailable",
    );
    assert.equal(
      await probeBattleService(async () => {
        throw new TypeError("Failed to fetch");
      }),
      "unavailable",
    );
    assert.equal(shouldPollBattle("loading"), false);
    assert.equal(shouldPollBattle("unavailable"), false);
    assert.equal(shouldPollBattle("ready"), true);
  });

  it("stops after a failed socket handshake instead of reconnecting", () => {
    let status = reduceBattleService("loading", "probe-ready");
    assert.equal(status, "ready");
    status = reduceBattleService(status, "handshake-failed");
    assert.equal(status, "unavailable");
    status = reduceBattleService(status, "probe-ready");
    assert.equal(status, "unavailable");
    assert.equal(shouldReconnectBattleSocket({ handshakeFailed: true, serviceDown: true, hasSocket: false }), false);
    assert.equal(shouldReconnectBattleSocket({ handshakeFailed: false, serviceDown: false, hasSocket: false }), true);
    assert.equal(
      shouldReconnectBattleSocket({ handshakeFailed: false, serviceDown: false, hasSocket: false, leaving: true }),
      false,
    );
    assert.equal(reduceBattleService("unavailable", "retry"), "loading");
    assert.equal(reduceBattleService("loading", "disabled-response"), "unavailable");
  });
});
