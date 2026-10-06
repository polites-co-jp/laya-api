export interface Config {
  port: number;
  host: string;
  authSecret: string;
  authMaxSkewMs: number;
  layaBaseUrl: string;
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
  return {
    port: int(env, "PORT", 8080),
    host: env.HOST ?? "0.0.0.0",
    authSecret,
    authMaxSkewMs: int(env, "AUTH_MAX_SKEW_MS", 1000),
    layaBaseUrl: (env.LAYA_BASE_URL ?? "http://laya:8000").replace(/\/+$/, ""),
    upstreamTimeoutMs: int(env, "UPSTREAM_TIMEOUT_MS", 60000),
    // laya-serve の本文上限（MAX_BODY_BYTES = 2 MiB）に合わせる
    bodyLimit: 2 * 1024 * 1024
  };
}
