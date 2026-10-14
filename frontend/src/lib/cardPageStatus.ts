import { AsyncLocalStorage } from "node:async_hooks";
import { Server, ServerResponse } from "node:http";

/**
 * App Router has no response object in a Server Component, and the card page
 * must not grow a second API call in middleware. The Node response for this
 * request is locked to 503 before the HTML is flushed, including when the
 * framework later assigns 200 or 500.
 */
const requestResponses = new AsyncLocalStorage<ServerResponse>();
const locked = new WeakMap<ServerResponse, number>();

let installed = false;

export function installCardPageStatusPatch(): void {
  if (installed) return;
  installed = true;

  const origEmit = Server.prototype.emit;
  Server.prototype.emit = function (this: Server, event: string | symbol, ...args: unknown[]): boolean {
    if (event === "request" && args[1] instanceof ServerResponse) {
      const res = args[1];
      return requestResponses.run(res, () => origEmit.apply(this, [event, ...args] as [string | symbol, ...unknown[]]));
    }
    return origEmit.apply(this, [event, ...args] as [string | symbol, ...unknown[]]);
  };

  const origWriteHead = ServerResponse.prototype.writeHead;
  ServerResponse.prototype.writeHead = function (
    this: ServerResponse,
    statusCode: number,
    reason?: string | { [key: string]: string | string[] | number | undefined },
    headers?: { [key: string]: string | string[] | number | undefined },
  ): ServerResponse {
    const retryAfter = locked.get(this);
    if (retryAfter != null) {
      if (!this.getHeader("Retry-After")) this.setHeader("Retry-After", String(retryAfter));
      if (!this.getHeader("Cache-Control")) this.setHeader("Cache-Control", "no-store");
      statusCode = 503;
      if (typeof reason === "string") reason = "Service Unavailable";
    }
    if (headers !== undefined) return origWriteHead.call(this, statusCode, reason as string, headers);
    if (reason !== undefined) return origWriteHead.call(this, statusCode, reason as never);
    return origWriteHead.call(this, statusCode);
  } as typeof ServerResponse.prototype.writeHead;
}

function lockResponse(res: ServerResponse, retryAfterSeconds: number): void {
  locked.set(res, retryAfterSeconds);
  if (!res.headersSent) {
    res.setHeader("Retry-After", String(retryAfterSeconds));
    res.setHeader("Cache-Control", "no-store");
  }
  let current = 503;
  Object.defineProperty(res, "statusCode", {
    configurable: true,
    enumerable: true,
    get() {
      return current;
    },
    set(value: number) {
      if (value === 503) current = value;
    },
  });
  res.statusMessage = "Service Unavailable";
}

/** Lock this request to 503 + Retry-After. No-op when the response is already gone. */
export function markCardPageUnavailable(retryAfterSeconds: number): boolean {
  installCardPageStatusPatch();
  const res = requestResponses.getStore();
  if (!res || res.headersSent) return false;
  lockResponse(res, retryAfterSeconds);
  return true;
}

installCardPageStatusPatch();
