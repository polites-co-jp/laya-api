import { describe, expect, it } from "vitest";
import { MemoryNonceStore, canonicalString, sign, verifyRequest } from "../src/auth.js";

const SECRET = "s".repeat(64);
const NOW = 1_790_000_000_000;

function signedHeaders(opts: { body: string; ts?: number; nonce?: string; path?: string; method?: string; secret?: string }) {
  const timestamp = String(opts.ts ?? NOW);
  const nonce = opts.nonce ?? "nonce-abcdefghijklmnop";
  const canonical = canonicalString({
    timestamp,
    nonce,
    method: opts.method ?? "POST",
    pathWithQuery: opts.path ?? "/v1/systemone",
    body: opts.body
  });
  return {
    "x-auth-timestamp": timestamp,
    "x-auth-nonce": nonce,
    "x-auth-signature": sign(opts.secret ?? SECRET, canonical)
  };
}

function verify(headers: Record<string, string>, over: Partial<{ body: string; now: number; path: string; nonces: MemoryNonceStore }> = {}) {
  return verifyRequest({
    secret: SECRET,
    maxSkewMs: 1000,
    now: over.now ?? NOW,
    method: "POST",
    pathWithQuery: over.path ?? "/v1/systemone",
    body: over.body ?? "{}",
    headers,
    nonces: over.nonces ?? new MemoryNonceStore()
  });
}

describe("verifyRequest", () => {
  it("accepts a correctly signed request", () => {
    expect(verify(signedHeaders({ body: "{}" }))).toEqual({ ok: true });
  });

  it("rejects missing headers", () => {
    expect(verify({})).toEqual({ ok: false, reason: "missing_headers" });
  });

  it("rejects a tampered body", () => {
    expect(verify(signedHeaders({ body: "{}" }), { body: '{"x":1}' })).toEqual({ ok: false, reason: "bad_signature" });
  });

  it("rejects reuse of the signature on another path", () => {
    expect(verify(signedHeaders({ body: "{}" }), { path: "/v1/systemone/batch" })).toEqual({
      ok: false,
      reason: "bad_signature"
    });
  });

  it("rejects a wrong secret", () => {
    expect(verify(signedHeaders({ body: "{}", secret: "x".repeat(64) }))).toEqual({ ok: false, reason: "bad_signature" });
  });

  it("accepts within the window on both sides and rejects outside", () => {
    expect(verify(signedHeaders({ body: "{}", ts: NOW - 1000 })).ok).toBe(true);
    expect(verify(signedHeaders({ body: "{}", ts: NOW + 1000 })).ok).toBe(true);
    expect(verify(signedHeaders({ body: "{}", ts: NOW - 1001 }))).toEqual({ ok: false, reason: "expired" });
    expect(verify(signedHeaders({ body: "{}", ts: NOW + 1001 }))).toEqual({ ok: false, reason: "expired" });
  });

  it("rejects a replay within the window", () => {
    const nonces = new MemoryNonceStore();
    const h = signedHeaders({ body: "{}" });
    expect(verify(h, { nonces }).ok).toBe(true);
    expect(verify(h, { nonces, now: NOW + 500 })).toEqual({ ok: false, reason: "replay" });
  });

  it("does not consume a nonce on a bad signature", () => {
    const nonces = new MemoryNonceStore();
    const good = signedHeaders({ body: "{}" });
    expect(verify({ ...good, "x-auth-signature": "00".repeat(32) }, { nonces }).ok).toBe(false);
    expect(verify(good, { nonces }).ok).toBe(true);
  });

  it("rejects malformed timestamp and nonce", () => {
    expect(verify({ ...signedHeaders({ body: "{}" }), "x-auth-timestamp": "12:00:00" })).toEqual({
      ok: false,
      reason: "bad_timestamp"
    });
    expect(verify(signedHeaders({ body: "{}", nonce: "short" }))).toEqual({ ok: false, reason: "bad_nonce" });
  });
});

describe("MemoryNonceStore", () => {
  it("forgets nonces after their ttl", () => {
    const store = new MemoryNonceStore();
    expect(store.claim("a", 100, 0)).toBe(true);
    expect(store.claim("a", 100, 50)).toBe(false);
    expect(store.claim("a", 100, 101)).toBe(true);
  });
});
