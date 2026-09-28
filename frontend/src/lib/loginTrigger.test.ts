import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createLoginTrigger, settleCapturedLogin, type LoginListenTarget } from "./loginTrigger.ts";

function harness() {
  let listener: ((event: { target: EventTarget | null }) => void) | null = null;
  let capture: boolean | undefined;
  const target: LoginListenTarget = {
    addEventListener(_type, fn, cap) {
      listener = fn;
      capture = cap;
    },
    removeEventListener() {
      listener = null;
    },
  };
  const trigger = createLoginTrigger(target);
  const login = {
    closest(selector: string) {
      return selector === "[data-login-trigger]" ? this : null;
    },
  };
  const other = {
    closest() {
      return null;
    },
  };
  return {
    trigger,
    capture,
    click(node: EventTarget | null) {
      listener?.({ target: node });
    },
    login: login as unknown as EventTarget,
    other: other as unknown as EventTarget,
  };
}

describe("login trigger during hydration", () => {
  it("remembers a click that happens before the opener is bound, and ignores other targets", () => {
    const { trigger, capture, click, login, other } = harness();
    assert.equal(capture, true);

    const opened: string[] = [];
    click(other);
    assert.equal(trigger.hasIntent(), false);

    click(login);
    assert.equal(trigger.hasIntent(), true);
    assert.deepEqual(opened, []);

    const unbind = trigger.bind(() => opened.push("open"));
    assert.deepEqual(opened, ["open"]);

    click(login);
    assert.deepEqual(opened, ["open", "open"]);

    unbind();
    click(login);
    assert.deepEqual(opened, ["open", "open"]);
    assert.equal(trigger.hasIntent(), true);

    trigger.clearIntent();
    const unbindAgain = trigger.bind(() => opened.push("again"));
    assert.deepEqual(opened, ["open", "open"]);
    unbindAgain();
    trigger.dispose();
  });

  it("opens a captured click only after auth is ready and there is no session", () => {
    assert.deepEqual(settleCapturedLogin(true, { ready: false, token: null }), { pending: true, open: false });
    assert.deepEqual(settleCapturedLogin(true, { ready: true, token: null }), { pending: false, open: true });
    assert.deepEqual(settleCapturedLogin(false, { ready: true, token: null }), { pending: false, open: false });
  });

  it("drops the click when a token is already stored, including while /auth/me is in flight or kept after a 5xx", () => {
    // Mirror loaded, /auth/me not finished yet.
    assert.deepEqual(settleCapturedLogin(true, { ready: true, token: "tok" }), { pending: false, open: false });
    // 5xx/network failure keeps the same token (#20). Still not a logged-out user.
    assert.deepEqual(settleCapturedLogin(true, { ready: true, token: "tok" }), { pending: false, open: false });

    // Seen a session first, so a later 401 that clears the token must not revive this click.
    const dropped = settleCapturedLogin(true, { ready: true, token: "tok" });
    assert.deepEqual(dropped, { pending: false, open: false });
    assert.deepEqual(settleCapturedLogin(dropped.pending, { ready: true, token: null }), {
      pending: false,
      open: false,
    });
  });
});
