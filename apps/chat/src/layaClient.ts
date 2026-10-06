import { createHash, createHmac, randomBytes } from "node:crypto";

/**
 * laya-api を呼ぶための署名付きクライアント。
 * 本API を呼ぶ他サービスはこのファイルをそのまま持ち込むか、docs/ja/auth.md の手順で同じ署名を実装する。
 */
export class LayaApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly secret: string,
    private readonly fetchImpl: typeof fetch = fetch
  ) {}

  signHeaders(method: string, pathWithQuery: string, body: string, now = Date.now()): Record<string, string> {
    const timestamp = String(now);
    const nonce = randomBytes(18).toString("base64url");
    const bodyHash = createHash("sha256").update(body).digest("hex");
    const canonical = ["v1", timestamp, nonce, method.toUpperCase(), pathWithQuery, bodyHash].join("\n");
    return {
      "x-auth-timestamp": timestamp,
      "x-auth-nonce": nonce,
      "x-auth-signature": createHmac("sha256", this.secret).update(canonical).digest("hex")
    };
  }

  async request(method: "GET" | "POST", pathWithQuery: string, body?: string): Promise<Response> {
    const payload = body ?? "";
    const headers = this.signHeaders(method, pathWithQuery, payload);
    if (method === "POST") headers["content-type"] = "application/json";
    return this.fetchImpl(`${this.baseUrl.replace(/\/+$/, "")}${pathWithQuery}`, {
      method,
      headers,
      body: method === "POST" ? payload : undefined
    });
  }
}
