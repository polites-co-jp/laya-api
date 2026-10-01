import type { AddressInfo } from "node:net";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LayaApiClient } from "../src/layaClient.js";
import { buildChatServer } from "../src/server.js";

const publicDir = fileURLToPath(new URL("../public", import.meta.url));
let close: (() => Promise<void>) | undefined;

afterEach(async () => {
  await close?.();
  close = undefined;
});

async function start(upstream: (url: string, init: RequestInit) => Response) {
  const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => upstream(String(url), init ?? {}));
  const server = buildChatServer(new LayaApiClient("http://api:8080", "s".repeat(32), fetchImpl as unknown as typeof fetch), publicDir);
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  close = () => new Promise((r) => server.close(() => r()));
  return { base: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, fetchImpl };
}

describe("chat server", () => {
  it("signs and forwards systemone requests", async () => {
    const { base, fetchImpl } = await start(
      () => new Response('{"answers":{}}', { status: 200, headers: { "content-type": "application/json", "x-laya-credits-used": "1" } })
    );
    const res = await fetch(`${base}/api/systemone`, { method: "POST", body: '{"state":"x"}' });
    expect(res.status).toBe(200);
    expect(res.headers.get("x-laya-credits-used")).toBe("1");
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe("http://api:8080/v1/systemone");
    const h = init!.headers as Record<string, string>;
    expect(h["x-auth-signature"]).toMatch(/^[0-9a-f]{64}$/);
    expect(init!.body).toBe('{"state":"x"}');
  });

  it("serves the UI and refuses path traversal", async () => {
    const { base } = await start(() => new Response("{}"));
    const index = await fetch(`${base}/`);
    expect(index.status).toBe(200);
    expect(await index.text()).toContain("Laya 判断チャット");
    expect((await fetch(`${base}/..%2fpackage.json`)).status).toBe(404);
    expect((await fetch(`${base}/missing.js`)).status).toBe(404);
  });

  it("returns 502 when the API is unreachable", async () => {
    const { base } = await start(() => {
      throw new TypeError("fetch failed");
    });
    expect((await fetch(`${base}/api/models`)).status).toBe(502);
  });
});
