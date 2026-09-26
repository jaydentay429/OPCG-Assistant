import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ApiError } from "./api";
import { withTransientRetry } from "./transientRetry";

const noWait = async () => {};

describe("withTransientRetry", () => {
  it("retries a 5xx once and returns the second success", async () => {
    const calls: number[] = [];
    const result = await withTransientRetry(
      async () => {
        calls.push(calls.length + 1);
        if (calls.length === 1) throw new ApiError(503, "unavailable");
        return { ok: true };
      },
      { delayMs: 0, sleep: noWait },
    );
    assert.deepEqual(result, { ok: true });
    assert.deepEqual(calls, [1, 2]);
  });

  it("retries a timeout once and returns the second success", async () => {
    const calls: number[] = [];
    const result = await withTransientRetry(
      async () => {
        calls.push(calls.length + 1);
        if (calls.length === 1) throw new ApiError(408, "timeout");
        return "card";
      },
      { delayMs: 0, sleep: noWait },
    );
    assert.equal(result, "card");
    assert.deepEqual(calls, [1, 2]);
  });

  it("retries a network error once and returns the second success", async () => {
    const calls: number[] = [];
    const result = await withTransientRetry(
      async () => {
        calls.push(calls.length + 1);
        if (calls.length === 1) throw new TypeError("fetch failed");
        return "card";
      },
      { delayMs: 0, sleep: noWait },
    );
    assert.equal(result, "card");
    assert.deepEqual(calls, [1, 2]);
  });

  it("throws after two 5xx failures", async () => {
    let calls = 0;
    await assert.rejects(
      () =>
        withTransientRetry(
          async () => {
            calls += 1;
            throw new ApiError(500, "boom");
          },
          { delayMs: 0, sleep: noWait },
        ),
      (error: unknown) => error instanceof ApiError && error.status === 500,
    );
    assert.equal(calls, 2);
  });

  it("throws after two timeouts", async () => {
    let calls = 0;
    await assert.rejects(
      () =>
        withTransientRetry(
          async () => {
            calls += 1;
            throw new ApiError(408, "timeout");
          },
          { delayMs: 0, sleep: noWait },
        ),
      (error: unknown) => error instanceof ApiError && error.status === 408,
    );
    assert.equal(calls, 2);
  });

  it("does not retry 404", async () => {
    let calls = 0;
    const slept: number[] = [];
    await assert.rejects(
      () =>
        withTransientRetry(
          async () => {
            calls += 1;
            throw new ApiError(404, "missing");
          },
          {
            delayMs: 200,
            sleep: async (ms) => {
              slept.push(ms);
            },
          },
        ),
      (error: unknown) => error instanceof ApiError && error.status === 404,
    );
    assert.equal(calls, 1);
    assert.deepEqual(slept, []);
  });

  it("does not retry 422", async () => {
    let calls = 0;
    await assert.rejects(
      () =>
        withTransientRetry(
          async () => {
            calls += 1;
            throw new ApiError(422, "invalid");
          },
          { delayMs: 0, sleep: noWait },
        ),
      (error: unknown) => error instanceof ApiError && error.status === 422,
    );
    assert.equal(calls, 1);
  });
});
