import { randomBytes } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import { canonicalString, sign } from "../src/auth.js";
import type { Config } from "../src/config.js";
import { buildServer } from "../src/server.js";

const SECRET = "k".repeat(64);
const NOW = 1_790_000_000_000;

const config: Config = {
  port: 0,
  host: "127.0.0.1",
  authSecret: SECRET,
  authMaxSkewMs: 1000,
  layaBaseUrl: "http://laya:8000",
  upstreamTimeoutMs: 1000,
  bodyLimit: 2 * 1024 * 1024
};

function auth(method: string, path: string, body = "", ts = NOW) {
  const timestamp = String(ts);
  const nonce = randomBytes(16).toString("base64url");
  return {
    "x-auth-timestamp": timestamp,
    "x-auth-nonce": nonce,
    "x-auth-signature": sign(SECRET, canonicalString({ timestamp, nonce, method, pathWithQuery: path, body }))
  };
}

function setup(upstream: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => upstream(String(url), init ?? {}));
  const app = buildServer({ config, now: () => NOW, fetchImpl: fetchImpl as unknown as typeof fetch, logger: false });
  return { app, fetchImpl };
}

let current: ReturnType<typeof setup> | undefined;
afterEach(async () => {
  await current?.app.close();
  current = undefined;
});

describe("server", () => {
  it("proxies systemone to laya-serve and passes inference headers through", async () => {
    current = setup(
      () =>
        new Response(JSON.stringify({ model: "multilingual", answers: {} }), {
          status: 200,
          headers: { "content-type": "application/json", "x-inference-time-ms": "31.20", "x-internal": "no" }
        })
    );
    const body = JSON.stringify({ state: "hello", questions: { q: { type: "noul", instructions: "Is it a greeting?" } } });
    const res = await current.app.inject({
      method: "POST",
      url: "/v1/systemone",
      headers: { "content-type": "application/json", ...auth("POST", "/v1/systemone", body) },
      payload: body
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ model: "multilingual", answers: {} });
    expect(res.headers["x-inference-time-ms"]).toBe("31.20");
    expect(res.headers["x-internal"]).toBeUndefined();

    const [url, init] = current.fetchImpl.mock.calls[0]!;
    expect(url).toBe("http://laya:8000/v1/systemone");
    expect((init!.headers as Record<string, string>).authorization).toBeUndefined();
    expect(Buffer.from(init!.body as Uint8Array).toString()).toBe(body);
  });

  it.each([
    ["POST", "/v1/systemone/batch"],
    ["GET", "/health"]
  ])("proxies %s %s", async (method, path) => {
    current = setup(() => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    const body = method === "POST" ? "{}" : "";
    const res = await current.app.inject({
      method: method as "GET" | "POST",
      url: path,
      headers: { ...(body ? { "content-type": "application/json" } : {}), ...auth(method, path, body) },
      payload: body || undefined
    });
    expect(res.statusCode).toBe(200);
    expect(current.fetchImpl.mock.calls[0]![0]).toBe(`http://laya:8000${path}`);
  });

  it("does not forward the caller's query string", async () => {
    current = setup(() => new Response("{}", { status: 200 }));
    const res = await current.app.inject({ method: "GET", url: "/health?x=1", headers: auth("GET", "/health?x=1") });
    expect(res.statusCode).toBe(200);
    expect(current.fetchImpl.mock.calls[0]![0]).toBe("http://laya:8000/health");
  });

  it("rejects unsigned requests without calling Laya", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/health" });
    expect(res.statusCode).toBe(401);
    expect(res.json()).toEqual({ error: "unauthorized" });
    expect(current.fetchImpl).not.toHaveBeenCalled();
  });

  it("rejects a replayed request", async () => {
    current = setup(() => new Response("{}", { status: 200 }));
    const headers = auth("GET", "/health");
    expect((await current.app.inject({ method: "GET", url: "/health", headers })).statusCode).toBe(200);
    expect((await current.app.inject({ method: "GET", url: "/health", headers })).statusCode).toBe(401);
    expect(current.fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("rejects an expired request", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/health", headers: auth("GET", "/health", "", NOW - 2000) });
    expect(res.statusCode).toBe(401);
  });

  it("passes upstream errors and Retry-After through", async () => {
    current = setup(
      () =>
        new Response(JSON.stringify({ detail: "server busy, try again later" }), {
          status: 503,
          headers: { "retry-after": "1", "content-type": "application/json" }
        })
    );
    const body = "{}";
    const res = await current.app.inject({
      method: "POST",
      url: "/v1/systemone",
      headers: { "content-type": "application/json", ...auth("POST", "/v1/systemone", body) },
      payload: body
    });
    expect(res.statusCode).toBe(503);
    expect(res.headers["retry-after"]).toBe("1");
  });

  it("returns 502 when Laya is unreachable", async () => {
    current = setup(() => {
      throw new TypeError("fetch failed");
    });
    const res = await current.app.inject({ method: "GET", url: "/health", headers: auth("GET", "/health") });
    expect(res.statusCode).toBe(502);
  });

  it("serves healthz without auth", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/healthz" });
    expect(res.statusCode).toBe(200);
  });

  it("returns 401 for unknown paths before revealing they do not exist", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/v1/models" });
    expect(res.statusCode).toBe(401);
  });
});
