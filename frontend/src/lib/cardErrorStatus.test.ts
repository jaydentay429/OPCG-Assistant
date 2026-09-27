import assert from "node:assert/strict";
import http from "node:http";
import { describe, it } from "node:test";
import {
  isCardDetailPath,
  rewriteCardServerErrorBody,
  stripServerErrorNoindex,
} from "./cardErrorStatus";
import { installCardServerErrorRewrite } from "./cardErrorStatusPatch";

describe("card error status helpers", () => {
  it("matches only the card detail path", () => {
    assert.equal(isCardDetailPath("/cards/OP13-001"), true);
    assert.equal(isCardDetailPath("/cards/OP13-001/"), true);
    assert.equal(isCardDetailPath("/cards/OP13-001?picked=OP13-001-P1"), true);
    assert.equal(isCardDetailPath("/en/cards/OP13-001"), false);
    assert.equal(isCardDetailPath("/zh-HK/cards/OP13-001"), false);
    assert.equal(isCardDetailPath("/search"), false);
    assert.equal(isCardDetailPath("/cards"), false);
  });

  it("removes a robots noindex tag and leaves other metas", () => {
    const html =
      '<meta name="viewport" content="width=device-width"/>' +
      '<meta name="robots" content="noindex"/>' +
      '<meta name="theme-color" content="#0b1220"/>';
    const next = stripServerErrorNoindex(html);
    assert.equal(next.includes("noindex"), false);
    assert.equal(next.includes("viewport"), true);
    assert.equal(next.includes("theme-color"), true);
  });

  it("keeps an index,follow robots meta", () => {
    const html = '<meta name="robots" content="index, follow"/>';
    assert.equal(stripServerErrorNoindex(html), html);
  });

  it("rewrites an HTML error body and ignores a non-HTML payload", () => {
    const html = Buffer.from('<!DOCTYPE html><meta name="robots" content="noindex"/><p>x</p>');
    assert.equal(rewriteCardServerErrorBody(html).toString("utf8").includes("noindex"), false);
    const bytes = Buffer.from([0, 1, 2, 3]);
    assert.equal(rewriteCardServerErrorBody(bytes).equals(bytes), true);
  });
});

function listen(server: http.Server): Promise<number> {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") throw new Error("no port");
      resolve(address.port);
    });
  });
}

function textRequest(port: number, path: string): Promise<{ status: number; retryAfter: string | null; body: string }> {
  return new Promise((resolve, reject) => {
    const req = http.get({ hostname: "127.0.0.1", port, path }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      res.on("end", () => {
        resolve({
          status: res.statusCode || 0,
          retryAfter: res.headers["retry-after"]?.toString() ?? null,
          body: Buffer.concat(chunks).toString("utf8"),
        });
      });
    });
    req.on("error", reject);
  });
}

describe("card server error rewrite", () => {
  it("turns a card-page 500 into 503 without noindex, and leaves 404 and other routes alone", async () => {
    installCardServerErrorRewrite();
    const server = http.createServer((req, res) => {
      const url = req.url || "";
      if (url.startsWith("/cards/ZZ")) {
        res.statusCode = 404;
        res.end('<!DOCTYPE html><meta name="robots" content="noindex"/><h1>missing</h1>');
        return;
      }
      if (url.startsWith("/cards/")) {
        res.statusCode = 500;
        res.write('<!DOCTYPE html><meta name="robots" content="noindex"/>');
        res.end("<h1>down</h1>");
        return;
      }
      res.statusCode = 500;
      res.end('<!DOCTYPE html><meta name="robots" content="noindex"/><h1>other</h1>');
    });
    const port = await listen(server);
    try {
      const down = await textRequest(port, "/cards/OP13-001");
      assert.equal(down.status, 503);
      assert.equal(down.retryAfter, "10");
      assert.equal(down.body.includes("noindex"), false);
      assert.equal(down.body.includes("down"), true);

      const missing = await textRequest(port, "/cards/ZZ99-999");
      assert.equal(missing.status, 404);
      assert.equal(missing.body.includes("noindex"), true);

      const other = await textRequest(port, "/search");
      assert.equal(other.status, 500);
      assert.equal(other.body.includes("noindex"), true);

      const prefixed = await textRequest(port, "/en/cards/OP13-001");
      assert.equal(prefixed.status, 500);
      assert.equal(prefixed.body.includes("noindex"), true);
    } finally {
      await new Promise<void>((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
    }
  });
});
