import Fastify, { type FastifyInstance } from "fastify";
import type { Config } from "./config.js";
import { MemoryNonceStore, verifyRequest, type NonceStore } from "./auth.js";

/** laya-serve から呼び出し元へそのまま返すヘッダ（推論時間・混雑時のリトライ目安） */
const PASSTHROUGH_RESPONSE_HEADERS = ["content-type", "retry-after", "server-timing", "x-inference-time-ms"];

interface Route {
  method: "GET" | "POST";
  path: string;
}

/** laya-serve が公開している全エンドポイント */
export const LAYA_ROUTES: Route[] = [
  { method: "POST", path: "/v1/systemone" },
  { method: "POST", path: "/v1/systemone/batch" },
  { method: "GET", path: "/health" }
];

export interface BuildOptions {
  config: Config;
  nonces?: NonceStore;
  now?: () => number;
  fetchImpl?: typeof fetch;
  logger?: boolean;
}

export function buildServer(opts: BuildOptions): FastifyInstance {
  const { config } = opts;
  const nonces = opts.nonces ?? new MemoryNonceStore();
  const now = opts.now ?? Date.now;
  const doFetch = opts.fetchImpl ?? fetch;

  const app = Fastify({
    bodyLimit: config.bodyLimit,
    logger: opts.logger === false ? false : { level: process.env.LOG_LEVEL ?? "info" }
  });

  // 署名は生の本文バイト列に対して計算するため、本文はパースせず Buffer のまま受ける
  app.removeAllContentTypeParsers();
  app.addContentTypeParser("*", { parseAs: "buffer" }, (_req, body, done) => done(null, body));

  // コンテナのヘルスチェック専用。情報は返さない
  app.get("/healthz", async () => ({ ok: true }));

  app.addHook("preHandler", async (req, reply) => {
    if (req.url === "/healthz") return;
    const result = verifyRequest({
      secret: config.authSecret,
      maxSkewMs: config.authMaxSkewMs,
      now: now(),
      method: req.method,
      pathWithQuery: req.url,
      body: Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0),
      headers: req.headers,
      nonces
    });
    if (!result.ok) {
      req.log.warn({ reason: result.reason, ip: req.ip }, "auth rejected");
      // 失敗理由は外へ出さない
      return reply.code(401).send({ error: "unauthorized" });
    }
  });

  for (const route of LAYA_ROUTES) {
    app.route({
      method: route.method,
      url: route.path,
      handler: async (req, reply) => {
        const headers: Record<string, string> = {};
        let body: Uint8Array<ArrayBuffer> | undefined;
        if (route.method === "POST") {
          headers["content-type"] = "application/json";
          body = Uint8Array.from(Buffer.isBuffer(req.body) ? req.body : []);
        }
        let upstream: Response;
        try {
          // 中継先のパスは固定し、呼び出し側のクエリ文字列は渡さない
          upstream = await doFetch(`${config.layaBaseUrl}${route.path}`, {
            method: route.method,
            headers,
            body,
            signal: AbortSignal.timeout(config.upstreamTimeoutMs)
          });
        } catch (err) {
          req.log.error({ err }, "upstream request failed");
          return reply.code(502).send({ error: "upstream_unreachable" });
        }
        for (const name of PASSTHROUGH_RESPONSE_HEADERS) {
          const v = upstream.headers.get(name);
          if (v !== null) reply.header(name, v);
        }
        return reply.code(upstream.status).send(Buffer.from(await upstream.arrayBuffer()));
      }
    });
  }

  app.setNotFoundHandler((_req, reply) => reply.code(404).send({ error: "not_found" }));
  return app;
}
