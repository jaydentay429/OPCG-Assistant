import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  EXCLUDE_COOKIE_MAX_AGE_SECONDS,
  buildExcludeCookie,
  cookieDomainForHost,
  decideExcludeMe,
  publicHost,
} from "./excludeMe";

describe("exclude-me cookie", () => {
  it("covers the public site and subdomains for about 400 days", () => {
    const cookie = buildExcludeCookie({
      revoke: false,
      host: "optcgassistant.com",
      proto: "https",
    });
    assert.match(cookie, /^opcg_exclude_me=1;/);
    assert.match(cookie, new RegExp(`Max-Age=${EXCLUDE_COOKIE_MAX_AGE_SECONDS}`));
    assert.match(cookie, /HttpOnly/);
    assert.match(cookie, /Secure/);
    assert.match(cookie, /SameSite=Lax/);
    assert.match(cookie, /Path=\//);
    assert.equal(cookieDomainForHost("api.optcgassistant.com"), ".optcgassistant.com");
    assert.match(cookie, /Domain=\.optcgassistant\.com/);
  });

  it("clears the same cookie on revoke", () => {
    const cookie = buildExcludeCookie({
      revoke: true,
      host: "www.optcgassistant.com",
      proto: "https",
    });
    assert.match(cookie, /^opcg_exclude_me=;/);
    assert.match(cookie, /Max-Age=0/);
    assert.match(cookie, /Domain=\.optcgassistant\.com/);
    assert.match(cookie, /Secure/);
  });

  it("does not force Secure on plain http localhost", () => {
    const cookie = buildExcludeCookie({ revoke: false, host: "localhost:3000", proto: "http" });
    assert.equal(cookie.includes("Secure"), false);
    assert.equal(cookie.includes("Domain="), false);
  });

  it("uses the forwarded host only when the app itself sees localhost", () => {
    assert.equal(publicHost("optcgassistant.com", "evil.example"), "optcgassistant.com");
    assert.equal(publicHost("127.0.0.1:3000", "optcgassistant.com"), "optcgassistant.com");
  });
});

describe("exclude-me response", () => {
  it("returns 404 for a missing or wrong token and does not set a cookie", () => {
    for (const provided of ["", "nope"]) {
      const decision = decideExcludeMe({
        providedToken: provided,
        revoke: false,
        expectedToken: "secret-token",
        host: "optcgassistant.com",
        proto: "https",
      });
      assert.equal(decision.status, 404);
      assert.equal(decision.headers["Set-Cookie"], undefined);
      assert.match(decision.headers["X-Robots-Tag"], /noindex/);
    }
  });

  it("returns 404 when the server token is unset", () => {
    const decision = decideExcludeMe({
      providedToken: "secret-token",
      revoke: false,
      expectedToken: "",
      host: "optcgassistant.com",
      proto: "https",
    });
    assert.equal(decision.status, 404);
  });

  it("confirms the device is excluded and offers revoke", () => {
    const decision = decideExcludeMe({
      providedToken: "secret-token",
      revoke: false,
      expectedToken: "secret-token",
      host: "optcgassistant.com",
      proto: "https",
    });
    assert.equal(decision.status, 200);
    assert.match(decision.body, /此设备已不计入统计/);
    assert.match(decision.body, /noindex, nofollow/);
    assert.match(decision.body, /revoke=1/);
    assert.match(decision.headers["Set-Cookie"] || "", /opcg_exclude_me=1/);
    assert.match(decision.headers["X-Robots-Tag"], /noindex/);
    assert.equal(decision.body.includes("https://"), false);
  });

  it("revokes and says counting is restored", () => {
    const decision = decideExcludeMe({
      providedToken: "secret-token",
      revoke: true,
      expectedToken: "secret-token",
      host: "optcgassistant.com",
      proto: "https",
    });
    assert.match(decision.body, /此设备已恢复计入统计/);
    assert.match(decision.headers["Set-Cookie"] || "", /Max-Age=0/);
  });
});
