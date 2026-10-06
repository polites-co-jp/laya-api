// laya-api を外部アプリから呼ぶサンプルクライアント（Node.js 18 以上、依存なし）。
// 署名方式は docs/ja/auth.md（英語版 docs/en/auth.md）を参照。
//
// 使い方:
//   API_AUTH_SECRET=... node laya_client.mjs "判断させたい文章"
//   LAYA_API_URL を指定しなければ http://127.0.0.1:22300 を呼ぶ。
//
// 自分のアプリでは LayaClient をそのまま import して使える。
import { createHash, createHmac, randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";

export class LayaClient {
  /**
   * @param {string} baseUrl 例 "http://127.0.0.1:22300"
   * @param {string} secret  API と共有する API_AUTH_SECRET
   */
  constructor(baseUrl, secret) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.secret = secret;
  }

  /** 署名ヘッダを作る。body は送るバイト列そのもの（文字列なら UTF-8） */
  signHeaders(method, path, body) {
    const timestamp = String(Date.now());
    const nonce = randomBytes(18).toString("base64url");
    const bodyHash = createHash("sha256").update(body).digest("hex");
    const canonical = ["v1", timestamp, nonce, method.toUpperCase(), path, bodyHash].join("\n");
    return {
      "x-auth-timestamp": timestamp,
      "x-auth-nonce": nonce,
      "x-auth-signature": createHmac("sha256", this.secret).update(canonical).digest("hex")
    };
  }

  /**
   * 署名付きで呼ぶ。payload はオブジェクトなら JSON にして送る。
   * @returns {Promise<{ status: number, inferenceMs: number | null, retryAfter: string | null, data: any }>}
   */
  async request(method, path, payload) {
    // 署名した文字列をそのまま送る。署名後に JSON を作り直すと本文のハッシュが変わり 401 になる
    const body = payload === undefined ? "" : JSON.stringify(payload);
    const headers = this.signHeaders(method, path, body);
    if (method === "POST") headers["content-type"] = "application/json";
    const res = await fetch(this.baseUrl + path, { method, headers, body: method === "POST" ? body : undefined });
    const text = await res.text();
    let data;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
    const inference = res.headers.get("x-inference-time-ms");
    return {
      status: res.status,
      inferenceMs: inference === null ? null : Number(inference),
      retryAfter: res.headers.get("retry-after"),
      data
    };
  }

  /** Laya の状態（ロード済みチェックポイント、計算デバイス） */
  health() {
    return this.request("GET", "/health");
  }

  /** 1件の state を判断する。payload は { state, questions, model?, session_id?, user? } */
  decide(payload) {
    return this.request("POST", "/v1/systemone", payload);
  }

  /** 複数の states に同じ questions をまとめて判断する。payload は { states, questions, model? } */
  decideBatch(payload) {
    return this.request("POST", "/v1/systemone/batch", payload);
  }
}

async function main() {
  const secret = process.env.API_AUTH_SECRET;
  if (!secret) {
    console.error("API_AUTH_SECRET を環境変数に設定してください / Set API_AUTH_SECRET in the environment");
    process.exit(1);
  }
  const client = new LayaClient(process.env.LAYA_API_URL ?? "http://127.0.0.1:22300", secret);

  const health = await client.health();
  console.log("GET /health", health.status, JSON.stringify(health.data));

  const state = process.argv[2] ?? "注文した商品が壊れて届きました。今日中に交換してほしいです。";
  const res = await client.decide({
    state,
    questions: {
      urgent: { type: "noul", instructions: "今日中の対応が必要か？" },
      queue: {
        type: "choice",
        instructions: "どの窓口が担当すべきか？",
        criteria: { returns: "返品・破損", delivery: "配送状況", other: "その他" }
      },
      intensity: { type: "score", instructions: "どのくらい急ぎか？", criteria: ["Routine", "Soon", "Today", "Immediate"] }
    }
  });
  console.log("POST /v1/systemone", res.status, `inference ${res.inferenceMs} ms`);
  console.log(JSON.stringify(res.data, null, 2));
  if (res.status !== 200) process.exit(1);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  await main();
}
