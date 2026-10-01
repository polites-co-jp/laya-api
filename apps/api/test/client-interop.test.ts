import { describe, expect, it } from "vitest";
import { LayaApiClient } from "../../chat/src/layaClient.js";
import { MemoryNonceStore, verifyRequest } from "../src/auth.js";

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
