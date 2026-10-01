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
  layaBaseUrl: "https://laya.example/api",
  layaApiKey: "laya-secret-key",
  upstreamTimeoutMs: 1000,
  bodyLimit: 256_000
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
  it("proxies systemone with the Laya key and passes billing headers through", async () => {
    current = setup(
      () =>
        new Response(JSON.stringify({ model: "laya-english", answers: {} }), {
          status: 200,
          headers: { "content-type": "application/json", "x-laya-tokens-remaining": "42", "x-internal": "no" }
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
    expect(res.json()).toEqual({ model: "laya-english", answers: {} });
    expect(res.headers["x-laya-tokens-remaining"]).toBe("42");
    expect(res.headers["x-internal"]).toBeUndefined();

    const [url, init] = current.fetchImpl.mock.calls[0]!;
    expect(url).toBe("https://laya.example/api/v1/systemone");
    expect((init!.headers as Record<string, string>).authorization).toBe("Bearer laya-secret-key");
    expect(Buffer.from(init!.body as Buffer).toString()).toBe(body);
  });

  it.each([
    ["GET", "/v1/models"],
    ["GET", "/laya/status"],
    ["POST", "/alpha/decisions"]
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
    expect(current.fetchImpl.mock.calls[0]![0]).toBe(`https://laya.example/api${path}`);
  });

  it("rejects unsigned requests without calling Laya", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/v1/models" });
    expect(res.statusCode).toBe(401);
    expect(res.json()).toEqual({ error: "unauthorized" });
    expect(current.fetchImpl).not.toHaveBeenCalled();
  });

  it("rejects a replayed request", async () => {
    current = setup(() => new Response("{}", { status: 200 }));
    const headers = auth("GET", "/v1/models");
    expect((await current.app.inject({ method: "GET", url: "/v1/models", headers })).statusCode).toBe(200);
    expect((await current.app.inject({ method: "GET", url: "/v1/models", headers })).statusCode).toBe(401);
    expect(current.fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("rejects an expired request", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/v1/models", headers: auth("GET", "/v1/models", "", NOW - 2000) });
    expect(res.statusCode).toBe(401);
  });

  it("passes upstream errors and Retry-After through", async () => {
    current = setup(
      () => new Response(JSON.stringify({ error: "rate" }), { status: 429, headers: { "retry-after": "3", "content-type": "application/json" } })
    );
    const res = await current.app.inject({ method: "GET", url: "/v1/models", headers: auth("GET", "/v1/models") });
    expect(res.statusCode).toBe(429);
    expect(res.headers["retry-after"]).toBe("3");
  });

  it("returns 502 when Laya is unreachable", async () => {
    current = setup(() => {
      throw new TypeError("fetch failed");
    });
    const res = await current.app.inject({ method: "GET", url: "/v1/models", headers: auth("GET", "/v1/models") });
    expect(res.statusCode).toBe(502);
  });

  it("serves healthz without auth", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/healthz" });
    expect(res.statusCode).toBe(200);
  });

  it("returns 401 for unknown paths before revealing they do not exist", async () => {
    current = setup(() => new Response("{}"));
    const res = await current.app.inject({ method: "GET", url: "/nope" });
    expect(res.statusCode).toBe(401);
  });
});
