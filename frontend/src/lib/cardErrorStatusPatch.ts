import http from "node:http";
import {
  CARD_UNAVAILABLE_RETRY_AFTER,
  isCardDetailPath,
  isServerErrorStatus,
  rewriteCardServerErrorBody,
} from "./cardErrorStatus";

type RewriteState = {
  mode: "rewrite" | "passthrough";
  chunks: Buffer[];
};

const states = new WeakMap<http.ServerResponse, RewriteState>();
const installed = Symbol.for("opcg.cardServerErrorRewrite");

function requestUrl(res: http.ServerResponse): string {
  const req = res.req;
  return typeof req?.url === "string" ? req.url : "";
}

function asBuffer(chunk: unknown, encoding: BufferEncoding): Buffer {
  if (Buffer.isBuffer(chunk)) return chunk;
  if (chunk instanceof Uint8Array) return Buffer.from(chunk);
  return Buffer.from(String(chunk ?? ""), encoding);
}

function writeCallback(encoding: unknown, cb: unknown): { encoding: BufferEncoding; cb?: () => void } {
  let enc: BufferEncoding = "utf8";
  let callback: (() => void) | undefined;
  if (typeof encoding === "function") callback = encoding as () => void;
  else if (typeof encoding === "string") enc = encoding as BufferEncoding;
  if (typeof cb === "function") callback = cb as () => void;
  return { encoding: enc, cb: callback };
}

function stateFor(res: http.ServerResponse): RewriteState {
  const existing = states.get(res);
  if (existing) return existing;
  const rewrite =
    isCardDetailPath(requestUrl(res)) && isServerErrorStatus(res.statusCode);
  const state: RewriteState = { mode: rewrite ? "rewrite" : "passthrough", chunks: [] };
  states.set(res, state);
  if (rewrite && !res.headersSent) {
    res.statusCode = 503;
    res.setHeader("Retry-After", CARD_UNAVAILABLE_RETRY_AFTER);
    if (res.hasHeader("content-length")) res.removeHeader("content-length");
  }
  return state;
}

/**
 * Next.js 15.5 cannot set 503 from a Server Component, and its error document
 * adds `noindex` for every status above 400. This rewrites only `/cards/:id`
 * responses that Next already marked 5xx: status becomes 503, and the
 * injected robots noindex tag is removed. 200 and 404 are passed through.
 */
export function installCardServerErrorRewrite(): void {
  const proto = http.ServerResponse.prototype as http.ServerResponse & {
    [installed]?: boolean;
  };
  if (proto[installed]) return;
  proto[installed] = true;

  const origWrite = proto.write;
  const origEnd = proto.end;
  const origWriteHead = proto.writeHead;
  const origFlushHeaders = proto.flushHeaders;

  proto.flushHeaders = function flushHeaders(this: http.ServerResponse) {
    stateFor(this);
    return origFlushHeaders.apply(this, arguments as unknown as Parameters<http.ServerResponse["flushHeaders"]>);
  };

  proto.writeHead = function writeHead(this: http.ServerResponse, ...args: unknown[]) {
    if (typeof args[0] === "number") this.statusCode = args[0];
    const state = stateFor(this);
    if (state.mode === "rewrite" && typeof args[0] === "number") args[0] = 503;
    return origWriteHead.apply(this, args as Parameters<http.ServerResponse["writeHead"]>);
  };

  proto.write = function write(this: http.ServerResponse, chunk: unknown, encoding?: unknown, cb?: unknown) {
    const state = stateFor(this);
    if (state.mode !== "rewrite") {
      return origWrite.apply(this, arguments as unknown as Parameters<http.ServerResponse["write"]>);
    }
    const parsed = writeCallback(encoding, cb);
    if (chunk != null && chunk !== "") state.chunks.push(asBuffer(chunk, parsed.encoding));
    parsed.cb?.();
    return true;
  };

  proto.end = function end(this: http.ServerResponse, chunk?: unknown, encoding?: unknown, cb?: unknown) {
    const state = stateFor(this);
    if (state.mode !== "rewrite") {
      return origEnd.apply(this, arguments as unknown as Parameters<http.ServerResponse["end"]>);
    }
    let payload = chunk;
    let enc: unknown = encoding;
    let done: unknown = cb;
    if (typeof payload === "function") {
      done = payload;
      payload = undefined;
      enc = undefined;
    }
    const parsed = writeCallback(enc, done);
    if (payload != null && payload !== "") {
      state.chunks.push(asBuffer(payload, parsed.encoding));
    }
    const body = rewriteCardServerErrorBody(Buffer.concat(state.chunks));
    if (!this.headersSent) this.statusCode = 503;
    return origEnd.call(this, body, "utf8", parsed.cb);
  };
}
