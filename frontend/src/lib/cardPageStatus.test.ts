import assert from "node:assert/strict";
import { once } from "node:events";
import http from "node:http";
import { describe, it } from "node:test";
import { markCardPageUnavailable } from "./cardPageStatus";

async function withServer(
  handler: http.RequestListener,
  run: (port: number) => Promise<void>,
) {
  const server = http.createServer(handler);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("no port");
  try {
    await run(address.port);
  } finally {
    server.close();
    await once(server, "close");
  }
}

async function read(port: number, path: string) {
  const res = await fetch(`http://127.0.0.1:${port}${path}`);
  return {
    status: res.status,
    retryAfter: res.headers.get("retry-after"),
    cacheControl: res.headers.get("cache-control"),
    robots: res.headers.get("x-robots-tag"),
    body: await res.text(),
  };
}

describe("card page unavailable status", () => {
  it("sends 503 and Retry-After even if the framework later sets 200 or 500", async () => {
    await withServer((req, res) => {
      const url = req.url || "/";
      if (url.startsWith("/cards/")) {
        const marked = markCardPageUnavailable(10);
        assert.equal(marked, true);
        res.statusCode = 200;
        res.statusCode = 500;
        res.end("卡牌暫時無法載入");
        return;
      }
      res.statusCode = 200;
      res.end("ok");
    }, async (port) => {
      const down = await read(port, "/cards/ZZ99-999");
      assert.equal(down.status, 503);
      assert.equal(down.retryAfter, "10");
      assert.equal(down.cacheControl, "no-store");
      assert.equal(down.robots, null);
      assert.match(down.body, /卡牌暫時無法載入/);
      assert.equal(down.body.includes("noindex"), false);

      const ok = await read(port, "/health");
      assert.equal(ok.status, 200);
      assert.equal(ok.retryAfter, null);
      assert.equal(ok.body, "ok");
    });
  });
});
