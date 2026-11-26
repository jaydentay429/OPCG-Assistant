import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  internalRewriteUrl,
  hreflangAlternates,
  isLocalizedRoute,
  langFromPathname,
  localizedPath,
  stripLangPrefix,
} from "./localeRouting";

describe("language URLs", () => {
  it("reads and strips the prefix", () => {
    assert.equal(langFromPathname("/en"), "en");
    assert.equal(langFromPathname("/en/cards/OP01-001"), "en");
    assert.equal(langFromPathname("/zh-hans/sets/OP18"), "zh-Hans");
    assert.equal(langFromPathname("/cards/OP01-001"), null);
    // "/english" or "/enx" are not the English prefix.
    assert.equal(langFromPathname("/english"), null);
    assert.equal(stripLangPrefix("/en"), "/");
    assert.equal(stripLangPrefix("/zh-hans/leaders/OP01-001"), "/leaders/OP01-001");
    assert.equal(stripLangPrefix("/prices"), "/prices");
  });

  it("only localizes pages with language copies", () => {
    for (const p of ["/", "/search", "/cards/OP01-001", "/sets", "/sets/OP18", "/leaders", "/leaders/OP01-001", "/tournaments", "/prices", "/builder"]) {
      assert.equal(isLocalizedRoute(p), true, p);
    }
    for (const p of ["/play", "/community", "/collector", "/legal/privacy", "/cards/", "/binder"]) {
      assert.equal(isLocalizedRoute(p), false, p);
    }
  });

  it("builds hrefs per language, keeping query and hash", () => {
    assert.equal(localizedPath("/cards/OP01-001?pickedVariant=OP01-001-P1", "en"), "/en/cards/OP01-001?pickedVariant=OP01-001-P1");
    assert.equal(localizedPath("/", "zh-Hans"), "/zh-hans");
    assert.equal(localizedPath("/en/search", "zh-Hant"), "/search");
    assert.equal(localizedPath("/zh-hans/search", "en"), "/en/search");
    assert.equal(localizedPath("/play", "en"), "/play");
    assert.equal(localizedPath("https://example.com/x", "en"), "https://example.com/x");
  });

  it("links the three copies with hreflang and an x-default", () => {
    const alt = hreflangAlternates("/cards/OP01-001", "https://optcgassistant.com");
    assert.equal(alt["zh-Hant"], "https://optcgassistant.com/cards/OP01-001");
    assert.equal(alt["zh-Hans"], "https://optcgassistant.com/zh-hans/cards/OP01-001");
    assert.equal(alt.en, "https://optcgassistant.com/en/cards/OP01-001");
    assert.equal(alt["x-default"], "https://optcgassistant.com/cards/OP01-001");
    assert.equal(hreflangAlternates("/", "https://optcgassistant.com/").en, "https://optcgassistant.com/en");
  });
});

describe("internalRewriteUrl", () => {
  it("restores a loopback listen address that NextURL turned into localhost", () => {
    assert.equal(internalRewriteUrl("https://localhost:3000/en?q=1", "/", "127.0.0.1").href, "https://127.0.0.1:3000/?q=1");
    assert.equal(internalRewriteUrl("http://localhost:3000/en/cards/X", "/cards/X", "::1").href, "http://[::1]:3000/cards/X");
  });
  it("leaves other hosts alone", () => {
    assert.equal(internalRewriteUrl("http://localhost:3000/en", "/", undefined).href, "http://localhost:3000/");
    assert.equal(internalRewriteUrl("http://localhost:3000/en", "/", "my-runner-host").href, "http://localhost:3000/");
    assert.equal(internalRewriteUrl("http://0.0.0.0:3000/en", "/", "0.0.0.0").href, "http://0.0.0.0:3000/");
  });
});
