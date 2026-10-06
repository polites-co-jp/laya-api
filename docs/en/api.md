# Using the API from External Applications

[日本語](../ja/api.md) | **English** ・ [← README](../../README.en.md)

How to call Laya as an HTTP API from your own applications.
The API relays the endpoints of Laya itself (`laya-serve`) with the same input and output, after checking the caller with an HMAC signature.

```
External app ──(HTTP with HMAC signature)──> api :22300 ──> laya :8000 (not exposed to the host)
```

## Contents

- [1. Preparation](#1-preparation)
- [2. Calling with a sample client](#2-calling-with-a-sample-client)
- [3. Endpoints](#3-endpoints)
- [4. Request format](#4-request-format)
- [5. Response format](#5-response-format)
- [6. Status codes and limits](#6-status-codes-and-limits)
- [7. Calling from another host](#7-calling-from-another-host)
- [Troubleshooting](#troubleshooting)

## 1. Preparation

1. Start the containers as described in [Deploying the Docker containers](deploy.md). By default the API listens on `http://127.0.0.1:22300`.
2. Give your application the same value as `API_AUTH_SECRET` in `laya-api-containers/.env` (through an environment variable or similar; do not hard-code it).
3. Keep the clocks of the caller and the API host in sync (the allowed skew of a signature's timestamp is ±1 second by default).

To check connectivity only, call `/healthz`, which needs no authentication.

```sh
curl http://127.0.0.1:22300/healthz
# {"ok":true}
```

## 2. Calling with a sample client

The signature scheme is described in the [Authentication spec](auth.md), but with these samples you do not have to implement it yourself. Both run without any dependencies.

| Language | File | Requires |
|---|---|---|
| Node.js | [apps/examples/node/laya_client.mjs](../../apps/examples/node/laya_client.mjs) | Node.js 18 or later |
| Python | [apps/examples/python/laya_client.py](../../apps/examples/python/laya_client.py) | Python 3.9 or later |

### Run it as is

Calls `/health`, then `/v1/systemone` with three example questions, and prints the results.
Without a text argument it sends a Japanese example. The example questions are in Japanese if the text contains Japanese and in English otherwise (Laya picks the checkpoint from the language of the text, so the questions should match it).

```sh
# macOS / Linux / Git Bash
export API_AUTH_SECRET='(API_AUTH_SECRET from .env)'
node apps/examples/node/laya_client.mjs "The item I ordered arrived broken. Please replace it today."
python apps/examples/python/laya_client.py "The item I ordered arrived broken. Please replace it today."
```

```powershell
# Windows PowerShell
$env:API_AUTH_SECRET = '(API_AUTH_SECRET from .env)'
node apps/examples/node/laya_client.mjs "The item I ordered arrived broken. Please replace it today."
```

If the API is not at the default URL, set `LAYA_API_URL` (e.g. `LAYA_API_URL=https://laya.example.com`).

### Use it in your application

Copy the file into your project and use `LayaClient`.

```js
// Node.js
import { LayaClient } from "./laya_client.mjs";

const laya = new LayaClient("http://127.0.0.1:22300", process.env.API_AUTH_SECRET);
const res = await laya.decide({
  state: "The item I ordered arrived broken. Please replace it today.",
  questions: {
    urgent: { type: "noul", instructions: "Does this need a response today?" }
  }
});
if (res.status === 200) console.log(res.data.answers.urgent.noul); // probability of true (0-1)
```

```python
# Python
import os
from laya_client import LayaClient

laya = LayaClient("http://127.0.0.1:22300", os.environ["API_AUTH_SECRET"])
res = laya.decide({
    "state": "The item I ordered arrived broken. Please replace it today.",
    "questions": {
        "urgent": {"type": "noul", "instructions": "Does this need a response today?"},
    },
})
if res.status == 200:
    print(res.data["answers"]["urgent"]["noul"])  # probability of true (0-1)
```

Both provide `health()`, `decide()` and `decide_batch()` (`decideBatch()` in Node.js).
They return the status code, the inference time (`X-Inference-Time-Ms`), `Retry-After` and the response body.
They do not throw on 4xx / 5xx; they return the status code and body instead.

For calling with curl, see [curl + openssl in the Authentication spec](auth.md#curl--openssl).

## 3. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/v1/systemone` | Required | Decide each question in `questions` for one `state` |
| POST | `/v1/systemone/batch` | Required | Decide the same `questions` for each of several `states` |
| GET | `/health` | Required | Laya's state (loaded checkpoints, the device actually computing) |
| GET | `/healthz` | None | Whether the API container is up (returns no information) |

Any other path returns `404 {"error":"not_found"}`.

## 4. Request format

Send JSON with `Content-Type: application/json`. Input and output are Laya's own format, so see also [Laya's README](https://github.com/NandhaKishorM/laya).

### POST /v1/systemone

```json
{
  "state": "The item I ordered arrived broken. Please replace it today.",
  "questions": {
    "urgent":    { "type": "noul",   "instructions": "Does this need a response today?" },
    "queue":     { "type": "choice", "instructions": "Which team should handle this?",
                   "criteria": { "returns": "Returns or damaged items", "delivery": "Delivery status", "other": "Other" } },
    "intensity": { "type": "score",  "instructions": "How urgent is this?",
                   "criteria": ["Routine", "Soon", "Today", "Immediate"] }
  }
}
```

| Field | Required | Meaning |
|---|---|---|
| `state` | Yes | What to judge. A string, or any JSON value (object, array) |
| `questions` | Yes | The questions. Keys are question IDs, values are questions (below) |
| `model` | No | `english` / `multilingual` / `typed-decisions`. If omitted, Laya routes to english or multilingual by the language of `state`. `typed-decisions` is for fixed workflows and is used only when named |
| `session_id`, `user` | No | Caller identifiers, passed to Laya unchanged |

There are three question types.

| `type` | Answers | `criteria` |
|---|---|---|
| `noul` | Yes / no | Optional. `{"true": "meaning of true", "false": "meaning of false"}` |
| `choice` | One of several options | Required. `{"label": "description", ...}` or an array of labels (up to 100) |
| `score` | A level on a scale | Required. An array of labels from low to high (up to 32) |

In `instructions`, describe in plain language what you want decided.

### POST /v1/systemone/batch

Pass `states` (an array, up to 64) instead of `state`. The same `questions` are applied to each state.

```json
{
  "states": ["Where is my package?", "The item arrived broken"],
  "questions": { "urgent": { "type": "noul", "instructions": "Is it urgent?" } }
}
```

## 5. Response format

### POST /v1/systemone

The actual response to the request above (run on CPU; `routing.detection` is abbreviated).

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "urgent": {
      "type": "noul", "noul": 0.5795, "confidence": 0.5795, "answer_confidence": 0.5795,
      "action": { "act_probability": 1.0 }
    },
    "queue": {
      "type": "choice", "choice": "returns",
      "probabilities": { "returns": 0.952, "delivery": 0.0319, "other": 0.0161 },
      "confidence": 0.7968, "answer_confidence": 0.952,
      "action": { "act_probability": 1.0 }
    },
    "intensity": {
      "type": "score", "score": 2.2704,
      "legend": { "0": "Routine", "1": "Soon", "2": "Today", "3": "Immediate" },
      "probabilities": { "0": 0.0102, "1": 0.0158, "2": 0.6676, "3": 0.3065 },
      "confidence": 0.4631, "answer_confidence": 0.6676,
      "action": { "act_probability": 1.0 }
    }
  },
  "usage": {
    "input_tokens": 132, "output_tokens": 0, "state_tokens": 12,
    "state_tokens_dropped": 0, "truncated": false, "truncated_questions": []
  },
  "routing": {
    "model": "english",
    "repo": "convaiinnovations/laya",
    "reason": "English Latin text",
    "detection": { "script": "latin", "language": "en", "is_english": true, "...": "..." },
    "workflow": null
  }
}
```

| Item | How to read it |
|---|---|
| `answers.<ID>.noul` | Probability that the answer is true (0–1). "Yes" at 0.5 or above |
| `answers.<ID>.choice` | Label of the most likely option. Each option's probability is in `probabilities` |
| `answers.<ID>.score` | Expected level number (0-based). `legend` maps numbers to labels; `probabilities` has each level's probability |
| `answers.<ID>.confidence` | The confidence reported by Laya |
| `usage` | Token counts. If `truncated` is true, the input was too long and was cut |
| `routing.model` | The checkpoint actually used, and why (`reason`) |

### POST /v1/systemone/batch

Returns `{"results": [...]}`, with one result in the format above for each of `states`, in the same order.

### GET /health

```json
{
  "status": "ok",
  "loaded": ["english", "multilingual"],
  "device": "cpu",
  "checkpoint_devices": { "english": "cpu", "multilingual": "cpu" },
  "...": "..."
}
```

### Response headers

| Header | Meaning |
|---|---|
| `X-Inference-Time-Ms` | Inference time in Laya, in milliseconds |
| `Retry-After` | Seconds to wait before retrying, sent with 503 when busy |

## 6. Status codes and limits

| Code | Example body | Meaning and what to do |
|---|---|---|
| 200 | The decision | Success |
| 400 | `{"detail":"'state' is required"}` | A required field is missing |
| 401 | `{"error":"unauthorized"}` | Signature verification failed ([Troubleshooting](#troubleshooting)) |
| 404 | `{"error":"not_found"}` | Wrong path |
| 413 | `{"detail":"too many choice options for 'q' (101 > 100)"}` | A limit in the table below was exceeded |
| 422 | `{"detail":"question 'q': unknown type 'foo'; ..."}` | A question is not written correctly |
| 500 | — | Laya's inference failed. Check `docker compose logs laya` |
| 502 | `{"error":"upstream_unreachable"}` | The API cannot reach Laya. Usually Laya is still starting (downloading weights) |
| 503 | `{"detail":"server busy, try again later"}` | Too many requests at once. Wait `Retry-After` seconds and retry |

The limits are set by Laya (`laya-serve`).

| Item | Limit |
|---|---|
| Body size | 2 MiB |
| Questions per request | 64 |
| Length of `state` | 50,000 characters |
| `states` in a batch | 64 |
| Choice options / score levels | 100 / 32 |
| Options and levels across all questions | 512 |
| Requests processed at once | 16 (change with `LAYA_MAX_CONCURRENT`) |

## 7. Calling from another host

By default the API is published only on `127.0.0.1`, so it can only be called from the same host. To call it from an application on another host:

- Set `API_HOST_BIND=0.0.0.0` in `.env` and run `docker compose up -d` again.
- **Put a reverse proxy that terminates TLS (HTTPS) in front.** Signatures prevent tampering and replay, but do not encrypt the body (your questions and the text being judged).
- Use a firewall so that only the callers can reach the API port. On Linux, note that ports published by Docker bypass ufw rules.
- Keep both hosts' clocks in sync with NTP. If you cannot, widen `AUTH_MAX_SKEW_MS`.
- Only server-side applications should hold the secret. Do not call the API directly from browser JavaScript (users would see the key).
- Never expose the chat (`:22301`); it signs requests on behalf of whoever reaches it.

## Troubleshooting

### Requests fail with 401 unauthorized

The API never puts the reason in the response; it only writes it to its log.

```sh
cd laya-api-containers
docker compose logs api | grep "auth rejected"
```

| `reason` in the log | Cause | Fix |
|---|---|---|
| `missing_headers` | One of the three `X-Auth-*` headers is missing | Check the header names and that all three are sent |
| `bad_timestamp` | The timestamp is not an integer in milliseconds | Send milliseconds (13 digits), not seconds |
| `bad_nonce` | The nonce is not 16–64 characters of `[A-Za-z0-9_-]` | Check how it is generated |
| `bad_signature` | The signature does not match | Different key, body rebuilt after signing, different path, different encoding (below) |
| `expired` | The timestamp is outside the allowed skew (±1 s by default) | Sync clocks. Send right after signing |
| `replay` | The same nonce was used twice | Create a new nonce for every request (sign again when retrying) |

Common causes of `bad_signature`:

- The caller's key differs from `API_AUTH_SECRET` in `.env` (watch for stray spaces or line breaks).
- The JSON is serialized again after signing (a different key order or whitespace changes the hash).
- The path that was signed differs from the path that was sent (if you add a query string, sign it too).
- On Windows Git Bash, non-ASCII text is passed with `curl --data "$BODY"`. Write the body to a file and send it with `--data-binary @file`.

### Requests fail with 502 upstream_unreachable

Laya has not finished starting. The first start takes a few minutes to download the weights. Wait until `docker compose ps` shows `laya` as `healthy`.
