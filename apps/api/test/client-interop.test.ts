import { afterEach, describe, expect, it, vi } from "vitest";
import { LayaApiClient } from "../../chat/src/layaClient.js";
import { MemoryNonceStore, verifyRequest } from "../src/auth.js";

interface ExampleClient {
  decide(payload: unknown): Promise<{ status: number; data: unknown }>;
}

// 外部アプリ向けサンプル（apps/examples/node）は型定義を持たない .mjs なので、URL で読み込む
const { LayaClient } = (await import(new URL("../../examples/node/laya_client.mjs", import.meta.url).href)) as {
  LayaClient: new (baseUrl: string, secret: string) => ExampleClient;
};

// 呼び出し側の参照実装（apps/chat/src/layaClient.ts）が API の検証を通ることを保証する
describe("LayaApiClient interop", () => {
  it("produces headers that the API accepts", () => {
    const secret = "z".repeat(48);
    const client = new LayaApiClient("http://api:8080", secret);
    const body = JSON.stringify({ state: "日本語の本文", questions: {} });
    const now = Date.now();
    const headers = client.signHeaders("POST", "/v1/systemone", body, now);
    const result = verifyRequest({
      secret,
      maxSkewMs: 1000,
      now,
      method: "POST",
      pathWithQuery: "/v1/systemone",
      body: Buffer.from(body, "utf8"),
      headers,
      nonces: new MemoryNonceStore()
    });
    expect(result).toEqual({ ok: true });
  });
});

// 外部アプリ向けサンプル（apps/examples/node/laya_client.mjs）が送るリクエストが API の検証を通ることを保証する
describe("example Node.js client interop", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends exactly the body it signed", async () => {
    const secret = "y".repeat(48);
    let sent: { url: string; init: RequestInit } | undefined;
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      sent = { url, init };
      return new Response('{"answers":{}}', { status: 200, headers: { "x-inference-time-ms": "12.5" } });
    });
    const client = new LayaClient("http://127.0.0.1:22300/", secret);
    const res = await client.decide({ state: "日本語の本文", questions: { q: { type: "noul", instructions: "急ぎか？" } } });
    expect(res).toMatchObject({ status: 200, inferenceMs: 12.5, data: { answers: {} } });
    expect(sent!.url).toBe("http://127.0.0.1:22300/v1/systemone");
    const headers = sent!.init.headers as Record<string, string>;
    const result = verifyRequest({
      secret,
      maxSkewMs: 1000,
      now: Number(headers["x-auth-timestamp"]),
      method: "POST",
      pathWithQuery: "/v1/systemone",
      body: Buffer.from(sent!.init.body as string, "utf8"),
      headers,
      nonces: new MemoryNonceStore()
    });
    expect(result).toEqual({ ok: true });
  });
});
