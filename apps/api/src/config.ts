export interface Config {
  port: number;
  host: string;
  authSecret: string;
  authMaxSkewMs: number;
  layaBaseUrl: string;
  layaApiKey: string;
  upstreamTimeoutMs: number;
  bodyLimit: number;
}

function int(env: NodeJS.ProcessEnv, name: string, fallback: number): number {
  const raw = env[name];
  if (raw === undefined || raw === "") return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) throw new Error(`${name} must be a positive integer`);
  return n;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const authSecret = env.API_AUTH_SECRET ?? "";
  if (authSecret.length < 32) {
    throw new Error("API_AUTH_SECRET must be set and at least 32 characters");
  }
  const layaApiKey = env.LAYA_AI_API_KEY ?? "";
  if (layaApiKey === "") throw new Error("LAYA_AI_API_KEY must be set");
  return {
    port: int(env, "PORT", 8080),
    host: env.HOST ?? "0.0.0.0",
    authSecret,
    authMaxSkewMs: int(env, "AUTH_MAX_SKEW_MS", 1000),
    layaBaseUrl: (env.LAYA_BASE_URL ?? "https://laya-ai.pro/api").replace(/\/+$/, ""),
    layaApiKey,
    upstreamTimeoutMs: int(env, "UPSTREAM_TIMEOUT_MS", 30000),
    // Laya の JSON 本文上限に合わせる
    bodyLimit: 256_000
  };
}
