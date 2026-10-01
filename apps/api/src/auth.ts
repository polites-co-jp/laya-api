import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const HEADER_TIMESTAMP = "x-auth-timestamp";
export const HEADER_NONCE = "x-auth-nonce";
export const HEADER_SIGNATURE = "x-auth-signature";

const NONCE_PATTERN = /^[A-Za-z0-9_-]{16,64}$/;

/**
 * 署名対象の正規化文字列。本文・メソッド・パス・時刻・nonce を全て含めることで、
 * 傍受者による本文の差し替えや別エンドポイントへの流用を防ぐ。
 */
export function canonicalString(p: {
  timestamp: string;
  nonce: string;
  method: string;
  pathWithQuery: string;
  body: Buffer | string;
}): string {
  const bodyHash = createHash("sha256").update(p.body).digest("hex");
  return ["v1", p.timestamp, p.nonce, p.method.toUpperCase(), p.pathWithQuery, bodyHash].join("\n");
}

export function sign(secret: string, canonical: string): string {
  return createHmac("sha256", secret).update(canonical).digest("hex");
}

export type AuthFailure =
  | "missing_headers"
  | "bad_timestamp"
  | "expired"
  | "bad_nonce"
  | "bad_signature"
  | "replay";

export type AuthResult = { ok: true } | { ok: false; reason: AuthFailure };

export interface NonceStore {
  /** 初見なら登録して true、既出なら false。 */
  claim(nonce: string, ttlMs: number, now: number): boolean;
}

export class MemoryNonceStore implements NonceStore {
  private readonly seen = new Map<string, number>();

  claim(nonce: string, ttlMs: number, now: number): boolean {
    // Map は挿入順で、ttl は固定なので先頭から期限切れを掃除できる
    for (const [k, exp] of this.seen) {
      if (exp > now) break;
      this.seen.delete(k);
    }
    if (this.seen.has(nonce)) return false;
    this.seen.set(nonce, now + ttlMs);
    return true;
  }
}

export interface VerifyInput {
  secret: string;
  maxSkewMs: number;
  now: number;
  method: string;
  pathWithQuery: string;
  body: Buffer | string;
  headers: Record<string, string | string[] | undefined>;
  nonces: NonceStore;
}

function one(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v;
}

export function verifyRequest(i: VerifyInput): AuthResult {
  const timestamp = one(i.headers[HEADER_TIMESTAMP]);
  const nonce = one(i.headers[HEADER_NONCE]);
  const signature = one(i.headers[HEADER_SIGNATURE]);
  if (!timestamp || !nonce || !signature) return { ok: false, reason: "missing_headers" };

  if (!/^\d{10,16}$/.test(timestamp)) return { ok: false, reason: "bad_timestamp" };
  if (!NONCE_PATTERN.test(nonce)) return { ok: false, reason: "bad_nonce" };

  // 署名を先に検証し、正しい署名でない限り nonce を消費させない
  const expected = Buffer.from(
    sign(
      i.secret,
      canonicalString({ timestamp, nonce, method: i.method, pathWithQuery: i.pathWithQuery, body: i.body })
    ),
    "hex"
  );
  const given = Buffer.from(signature, "hex");
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) {
    return { ok: false, reason: "bad_signature" };
  }

  if (Math.abs(i.now - Number(timestamp)) > i.maxSkewMs) return { ok: false, reason: "expired" };

  // 時刻は前後両側に許容幅があるので、nonce は幅の2倍保持すれば再送を確実に弾ける
  if (!i.nonces.claim(nonce, i.maxSkewMs * 2 + 1, i.now)) return { ok: false, reason: "replay" };
  return { ok: true };
}
