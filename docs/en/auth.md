# Authentication Spec (HMAC Signature + Nonce)

[日本語](../ja/auth.md) | **English** ・ [← README](../../README.en.md)

Requests to the API (`http://127.0.0.1:22300` by default) are signed with a secret key, `API_AUTH_SECRET`, shared by the caller and the API.
The key itself never goes over the wire, so intercepting traffic does not reveal it.

If you would rather not implement signing yourself, use the sample clients (Node.js / Python) in [Using the API](api.md) as they are.

## What it protects against

| What an eavesdropper wants to do | What stops it |
|---|---|
| Steal the key | Only the signature (HMAC-SHA256) is sent, never the key |
| Replay a captured request later | Requests whose timestamp is outside the allowed skew (±1 s by default) are rejected |
| Replay a captured request within 1 second | Each nonce is single-use; a used nonce is rejected |
| Keep the signature but swap the body (the questions) | The SHA-256 of the body is part of the signature |
| Reuse a signature on another endpoint | The method and path are part of the signature |

What it does not protect against: reading the body. To keep the body confidential, put TLS (HTTPS) in front.
Always terminate TLS when calling from outside the LAN or from another host.

## Request headers

| Header | Value |
|---|---|
| `X-Auth-Timestamp` | Send time as UNIX epoch milliseconds (e.g. `1790000000123`) |
| `X-Auth-Nonce` | A fresh random string for every request: 16–64 characters of `[A-Za-z0-9_-]` |
| `X-Auth-Signature` | HMAC-SHA256 of the canonical string below, as 64 lowercase hex characters |

## Canonical string

Join these six lines with `\n` (no trailing newline).

```
v1
<value of X-Auth-Timestamp>
<value of X-Auth-Nonce>
<HTTP method, uppercase>
<path + query string, e.g. /v1/systemone>
<SHA-256 of the body bytes, lowercase hex; for no body, the hash of the empty string>
```

Hash exactly the bytes you send. Do not reformat or re-serialize the JSON after signing.
Hash text containing non-ASCII characters as UTF-8 bytes, and send those same bytes.

## Verification order (API side)

1. All three headers are present and well-formed
2. The signature matches (constant-time comparison)
3. The timestamp is within ±`AUTH_MAX_SKEW_MS` (default 1000) of the API's current time
4. The nonce has not been used (nonces are remembered for twice the allowed skew)

On any failure the API returns `401 {"error":"unauthorized"}` regardless of the reason. The reason appears only in the API's log (see [Troubleshooting in the API guide](api.md#troubleshooting)).
A request with an invalid signature does not consume its nonce.

## Operational notes

- With a 1-second allowance, keep the caller and API hosts in sync with NTP. Where clocks drift, widen `AUTH_MAX_SKEW_MS`.
- Used nonces are kept in the API process's memory. To run several API instances, move them to a shared store (Redis or similar).
- To rotate the key, change `API_AUTH_SECRET` on the API and all callers at the same time.
- Never embed the key in browser JavaScript. Sign on the server side.

## Implementations

| Language | File |
|---|---|
| Node.js (no dependencies) | [apps/examples/node/laya_client.mjs](../../apps/examples/node/laya_client.mjs) |
| Python (standard library only) | [apps/examples/python/laya_client.py](../../apps/examples/python/laya_client.py) |
| TypeScript (reference implementation used by the chat) | [apps/chat/src/layaClient.ts](../../apps/chat/src/layaClient.ts) |

### curl + openssl

Write the body to a file, hash that file, and send it with `--data-binary @file`.
With `--data "$BODY"`, Windows Git Bash passes non-ASCII text to curl in a different encoding, so the body no longer matches the signature and you get 401.

```sh
SECRET='(API_AUTH_SECRET from .env)'
printf '%s' '{"state":"hello","questions":{"q":{"type":"noul","instructions":"Is this a greeting?"}}}' > body.json

HASH=$(openssl dgst -sha256 -hex body.json | awk '{print $NF}')
NONCE=$(openssl rand -hex 16)
TS=$(date +%s%3N)   # on macOS: TS=$(perl -MTime::HiRes=time -e 'printf "%d", time*1000')
SIG=$(printf 'v1\n%s\n%s\nPOST\n/v1/systemone\n%s' "$TS" "$NONCE" "$HASH" \
  | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $NF}')

curl -s http://127.0.0.1:22300/v1/systemone -H 'content-type: application/json' \
  -H "x-auth-timestamp: $TS" -H "x-auth-nonce: $NONCE" -H "x-auth-signature: $SIG" \
  --data-binary @body.json
```

The allowed skew is 1 second, so create `TS` right before signing and send without delay (paste and run the whole block at once).
On Windows, starting openssl is slow; if `TS` is created first, more than a second can pass before sending, giving 401 (`expired` in the log).
