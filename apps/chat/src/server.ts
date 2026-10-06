import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { extname, join, normalize } from "node:path";
import type { LayaApiClient } from "./layaClient.js";

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8"
};

/** UI の /api/* と laya-api の対応。ブラウザは署名を持たず、ここで署名して中継する */
const PROXY: Record<string, { method: "GET" | "POST"; path: string }> = {
  "GET /api/health": { method: "GET", path: "/health" },
  "POST /api/systemone": { method: "POST", path: "/v1/systemone" },
  "POST /api/systemone/batch": { method: "POST", path: "/v1/systemone/batch" }
};

/** API から UI へ渡すヘッダ */
const PASSTHROUGH = new Set(["retry-after", "server-timing", "x-inference-time-ms"]);

const MAX_BODY = 2 * 1024 * 1024;

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    size += (chunk as Buffer).length;
    if (size > MAX_BODY) throw new Error("body too large");
    chunks.push(chunk as Buffer);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function send(res: ServerResponse, status: number, body: string | Buffer, headers: Record<string, string> = {}) {
  res.writeHead(status, headers);
  res.end(body);
}

export function buildChatServer(client: LayaApiClient, publicDir: string): Server {
  return createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    try {
      const route = PROXY[`${req.method} ${url.pathname}`];
      if (route) {
        const body = route.method === "POST" ? await readBody(req) : undefined;
        const upstream = await client.request(route.method, route.path, body);
        const headers: Record<string, string> = {
          "content-type": upstream.headers.get("content-type") ?? "application/json"
        };
        upstream.headers.forEach((v, k) => {
          if (PASSTHROUGH.has(k)) headers[k] = v;
        });
        return send(res, upstream.status, Buffer.from(await upstream.arrayBuffer()), headers);
      }

      if (req.method === "GET" && url.pathname === "/healthz") {
        return send(res, 200, '{"ok":true}', { "content-type": "application/json" });
      }

      if (req.method === "GET") {
        const rel = normalize(url.pathname === "/" ? "/index.html" : url.pathname).replace(/^([/\\])+/, "");
        if (rel.startsWith("..")) return send(res, 404, "not found");
        const type = MIME[extname(rel)];
        if (!type) return send(res, 404, "not found");
        const file = await readFile(join(publicDir, rel)).catch(() => undefined);
        if (!file) return send(res, 404, "not found");
        return send(res, 200, file, { "content-type": type, "cache-control": "no-store" });
      }
      return send(res, 404, "not found");
    } catch (err) {
      console.error(err);
      return send(res, 502, JSON.stringify({ error: "api_unreachable" }), { "content-type": "application/json" });
    }
  });
}
