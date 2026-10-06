# API 利用手順（外部のアプリケーションから使う）

**日本語** | [English](../en/api.md) ・ [← README](../../README.md)

外部のアプリケーションから、HTTP API として Laya を呼ぶ手順。
API は Laya 本体（`laya-serve`）のエンドポイントを同じ入出力のまま中継し、その前に HMAC 署名で呼び出し元を確かめる。

```
外部アプリ ──(HMAC 署名付き HTTP)──> api :22300 ──> laya :8000（ホストには非公開）
```

## 目次

- [1. 準備](#1-準備)
- [2. サンプルクライアントで呼ぶ](#2-サンプルクライアントで呼ぶ)
- [3. エンドポイント](#3-エンドポイント)
- [4. リクエストの形式](#4-リクエストの形式)
- [5. 応答の形式](#5-応答の形式)
- [6. ステータスコードと上限](#6-ステータスコードと上限)
- [7. 別ホストから呼ぶ場合](#7-別ホストから呼ぶ場合)
- [トラブルシューティング](#トラブルシューティング)

## 1. 準備

1. [Docker コンテナ展開手順](deploy.md) に沿ってコンテナを起動する。API は既定で `http://127.0.0.1:22300` で待ち受ける。
2. 呼び出し側のアプリに、`laya-api-containers/.env` の `API_AUTH_SECRET` と同じ値を渡す（環境変数などで。ソースコードに書かない）。
3. 呼び出し側と API のホストの時刻を合わせておく（署名の時刻の許容幅は既定 ±1秒）。

疎通だけを確かめるなら、認証のいらない `/healthz` を呼ぶ。

```sh
curl http://127.0.0.1:22300/healthz
# {"ok":true}
```

## 2. サンプルクライアントで呼ぶ

署名の作り方は [認証仕様](auth.md) にあるが、次のサンプルを使えば実装しなくて済む。どちらも依存パッケージなしで動く。

| 言語 | ファイル | 必要なもの |
|---|---|---|
| Node.js | [apps/examples/node/laya_client.mjs](../../apps/examples/node/laya_client.mjs) | Node.js 18 以上 |
| Python | [apps/examples/python/laya_client.py](../../apps/examples/python/laya_client.py) | Python 3.9 以上 |

### そのまま実行して試す

`/health` と、例題の質問3つで `/v1/systemone` を呼び、結果を表示する。
文章を省くと日本語の例文を送る。例題の質問は、文章に日本語が含まれていれば日本語、なければ英語になる（Laya は文章の言語でチェックポイントを選ぶため、質問の言語もそろえる）。

```sh
# macOS / Linux / Git Bash
export API_AUTH_SECRET='（.env の API_AUTH_SECRET）'
node apps/examples/node/laya_client.mjs "注文した商品が壊れて届きました。今日中に交換してほしいです。"
python apps/examples/python/laya_client.py "注文した商品が壊れて届きました。今日中に交換してほしいです。"
```

```powershell
# Windows PowerShell
$env:API_AUTH_SECRET = '（.env の API_AUTH_SECRET）'
node apps/examples/node/laya_client.mjs "注文した商品が壊れて届きました。今日中に交換してほしいです。"
```

API の URL が既定と違うときは `LAYA_API_URL` を設定する（例 `LAYA_API_URL=https://laya.example.com`）。

### 自分のアプリに組み込む

ファイルを自分のプロジェクトへコピーし、`LayaClient` を使う。

```js
// Node.js
import { LayaClient } from "./laya_client.mjs";

const laya = new LayaClient("http://127.0.0.1:22300", process.env.API_AUTH_SECRET);
const res = await laya.decide({
  state: "注文した商品が壊れて届きました。今日中に交換してほしいです。",
  questions: {
    urgent: { type: "noul", instructions: "今日中の対応が必要か？" }
  }
});
if (res.status === 200) console.log(res.data.answers.urgent.noul); // true の確率（0〜1）
```

```python
# Python
import os
from laya_client import LayaClient

laya = LayaClient("http://127.0.0.1:22300", os.environ["API_AUTH_SECRET"])
res = laya.decide({
    "state": "注文した商品が壊れて届きました。今日中に交換してほしいです。",
    "questions": {
        "urgent": {"type": "noul", "instructions": "今日中の対応が必要か？"},
    },
})
if res.status == 200:
    print(res.data["answers"]["urgent"]["noul"])  # true の確率（0〜1）
```

どちらも `health()`・`decide()`・`decide_batch()`（Node.js は `decideBatch()`）を持ち、
戻り値は状態コード・推論時間（`X-Inference-Time-Ms`）・`Retry-After`・応答本文の組。
4xx / 5xx でも例外にせず、状態コードと本文を返す。

curl で呼ぶ例は [認証仕様の curl + openssl](auth.md#curl--openssl) にある。

## 3. エンドポイント

| メソッド | パス | 認証 | 内容 |
|---|---|---|---|
| POST | `/v1/systemone` | 要 | 1つの `state` について、`questions` の各質問を判断する |
| POST | `/v1/systemone/batch` | 要 | 複数の `states` それぞれについて、同じ `questions` を判断する |
| GET | `/health` | 要 | Laya の状態（ロード済みチェックポイント、実際の計算デバイス） |
| GET | `/healthz` | 不要 | API コンテナが動いているか（情報は返さない） |

上記以外のパスは `404 {"error":"not_found"}`。

## 4. リクエストの形式

`Content-Type: application/json` で JSON を送る。入出力は Laya の形式そのままなので、詳細は [Laya の README](https://github.com/NandhaKishorM/laya) も参照。

### POST /v1/systemone

```json
{
  "state": "注文した商品が壊れて届きました。今日中に交換してほしいです。",
  "questions": {
    "urgent":    { "type": "noul",   "instructions": "今日中の対応が必要か？" },
    "queue":     { "type": "choice", "instructions": "どの窓口が担当すべきか？",
                   "criteria": { "returns": "返品・破損", "delivery": "配送状況", "other": "その他" } },
    "intensity": { "type": "score",  "instructions": "どのくらい急ぎか？",
                   "criteria": ["Routine", "Soon", "Today", "Immediate"] }
  }
}
```

| フィールド | 必須 | 内容 |
|---|---|---|
| `state` | 要 | 判断させる対象。文字列のほか、JSON の値（オブジェクトや配列）も渡せる |
| `questions` | 要 | 質問の集まり。キーが質問 ID、値が質問（下表） |
| `model` | 任意 | `english` / `multilingual` / `typed-decisions`。省略すると Laya が `state` の言語を見て english か multilingual に振り分ける（日本語は multilingual）。`typed-decisions` は定型業務向けで、指定したときだけ使われる |
| `session_id`, `user` | 任意 | 呼び出し側の識別子。Laya にそのまま渡る |

質問の型は3つ。

| `type` | 聞けること | `criteria` |
|---|---|---|
| `noul` | はい / いいえ | 任意。`{"true": "true の意味", "false": "false の意味"}` |
| `choice` | 選択肢から1つ | 必須。`{"ラベル": "説明", ...}` またはラベルの配列（最大100個） |
| `score` | 段階評価 | 必須。低い→高い順のラベルの配列（最大32個） |

`instructions` には、何を判断させたいかを文章で書く。

### POST /v1/systemone/batch

`state` の代わりに `states`（配列、最大64件）を渡す。各 `state` に同じ `questions` を当てる。

```json
{
  "states": ["Where is my package?", "The item arrived broken"],
  "questions": { "urgent": { "type": "noul", "instructions": "Is it urgent?" } }
}
```

## 5. 応答の形式

### POST /v1/systemone

上のリクエストへの実際の応答（CPU で実行。`routing.detection` は一部省略）。

```json
{
  "model": "laya-rl-agent",
  "answers": {
    "urgent": {
      "type": "noul", "noul": 0.7097, "confidence": 0.7097, "answer_confidence": 0.7097,
      "action": { "act_probability": 1.0 }
    },
    "queue": {
      "type": "choice", "choice": "delivery",
      "probabilities": { "returns": 0.0318, "delivery": 0.9674, "other": 0.0008 },
      "confidence": 0.8657, "answer_confidence": 0.9674,
      "action": { "act_probability": 1.0 }
    },
    "intensity": {
      "type": "score", "score": 2.2712,
      "legend": { "0": "Routine", "1": "Soon", "2": "Today", "3": "Immediate" },
      "probabilities": { "0": 0.0011, "1": 0.0172, "2": 0.6912, "3": 0.2905 },
      "confidence": 0.5011, "answer_confidence": 0.6912,
      "action": { "act_probability": 1.0 }
    }
  },
  "usage": {
    "input_tokens": 149, "output_tokens": 0, "state_tokens": 15,
    "state_tokens_dropped": 0, "truncated": false, "truncated_questions": []
  },
  "routing": {
    "model": "multilingual",
    "repo": "convaiinnovations/laya/multilingual",
    "reason": "non-Latin script (kana, 100% of letters); the English checkpoint cannot read it",
    "detection": { "script": "kana", "is_english": false, "...": "..." },
    "workflow": null
  }
}
```

| 項目 | 読み方 |
|---|---|
| `answers.<ID>.noul` | true である確率（0〜1）。0.5 以上なら「はい」 |
| `answers.<ID>.choice` | 最も確率の高い選択肢のラベル。各選択肢の確率は `probabilities` |
| `answers.<ID>.score` | 段階番号（0 始まり）の期待値。番号とラベルの対応は `legend`、各段階の確率は `probabilities` |
| `answers.<ID>.confidence` | Laya が返す確信度 |
| `usage` | 使用トークン数。`truncated` が true なら入力が長すぎて切り詰められた |
| `routing.model` | 実際に使われたチェックポイントと、その理由（`reason`） |

### POST /v1/systemone/batch

`{"results": [...]}` の形で、`states` と同じ順に上と同じ形式の結果が並ぶ。

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

### 応答ヘッダ

| ヘッダ | 内容 |
|---|---|
| `X-Inference-Time-Ms` | Laya での推論時間（ミリ秒） |
| `Retry-After` | 混雑で 503 を返したときの、再試行までの秒数 |

## 6. ステータスコードと上限

| コード | 本文の例 | 意味と対処 |
|---|---|---|
| 200 | 判断結果 | 成功 |
| 400 | `{"detail":"'state' is required"}` | 必須項目がない |
| 401 | `{"error":"unauthorized"}` | 署名の検証に失敗した（[トラブルシューティング](#トラブルシューティング)） |
| 404 | `{"error":"not_found"}` | パスが違う |
| 413 | `{"detail":"too many choice options for 'q' (101 > 100)"}` | 下表の上限を超えた |
| 422 | `{"detail":"question 'q': unknown type 'foo'; ..."}` | 質問の書き方が正しくない |
| 500 | — | Laya の推論が失敗した。`docker compose logs laya` を確認する |
| 502 | `{"error":"upstream_unreachable"}` | API から Laya に届かない。Laya の起動中（重みの取得中）が多い |
| 503 | `{"detail":"server busy, try again later"}` | 同時リクエストが多すぎる。`Retry-After` 秒待って再試行する |

上限は Laya（`laya-serve`）が決めている。

| 項目 | 上限 |
|---|---|
| 本文のサイズ | 2 MiB |
| 1リクエストの質問数 | 64 |
| `state` の長さ | 50,000 文字 |
| batch の `states` の件数 | 64 |
| choice の選択肢 / score の段階 | 100 / 32 |
| 全質問の選択肢と段階の合計 | 512 |
| 同時に処理するリクエスト | 16（`LAYA_MAX_CONCURRENT` で変更） |

## 7. 別ホストから呼ぶ場合

既定では API は `127.0.0.1` にだけ公開され、同じホストからしか呼べない。別ホストのアプリから呼ぶときは次を守る。

- `.env` で `API_HOST_BIND=0.0.0.0` にし、`docker compose up -d` し直す。
- **TLS（HTTPS）を終端するリバースプロキシを前段に置く。** 署名は改ざんと再送を防ぐが、本文（質問と判断対象の文章）は暗号化しない。
- ファイアウォールで、呼び出し元以外から API のポートに届かないようにする。Linux では Docker の公開ポートが ufw の設定を迂回することに注意する。
- 両ホストの時刻を NTP で合わせる。合わせられないときは `AUTH_MAX_SKEW_MS` を広げる。
- 秘密鍵はサーバ側のアプリだけが持つ。ブラウザの JavaScript から直接呼ばない（鍵が利用者に見えてしまう）。
- チャット（`:22301`）は署名を代行するため、どこにも公開しない。

## トラブルシューティング

### 401 unauthorized になる

API は失敗の理由を応答に出さず、ログにだけ出す。

```sh
cd laya-api-containers
docker compose logs api | grep "auth rejected"
```

| ログの `reason` | 原因 | 対処 |
|---|---|---|
| `missing_headers` | 3つの `X-Auth-*` ヘッダのどれかがない | ヘッダ名と付け忘れを確認する |
| `bad_timestamp` | 時刻がミリ秒の整数でない | 秒ではなくミリ秒（13桁）で送る |
| `bad_nonce` | nonce が16〜64文字の `[A-Za-z0-9_-]` でない | 生成方法を確認する |
| `bad_signature` | 署名が一致しない | 鍵の違い、署名後の本文の作り直し、パスの違い、文字コードの違い（下記） |
| `expired` | 時刻が許容幅（既定 ±1秒）を外れた | 時刻を合わせる。署名してから送るまでの間を空けない |
| `replay` | 同じ nonce を2回使った | リクエストごとに新しい nonce を作る（リトライ時も署名し直す） |

`bad_signature` の主な原因:

- 呼び出し側の鍵が `.env` の `API_AUTH_SECRET` と違う（前後の空白や改行が混ざっていないか）。
- 署名したあとで JSON を作り直して送っている（キーの順序や空白が変わるとハッシュが変わる）。
- 署名したパスと送ったパスが違う（クエリ文字列を付けたなら署名にも含める）。
- Windows の Git Bash で `curl --data "$BODY"` に日本語を入れている。本文はファイルに書いて `--data-binary @file` で送る。

### 502 upstream_unreachable になる

Laya の起動が終わっていない。初回は重みの取得に数分かかる。`docker compose ps` で `laya` が `healthy` になるまで待つ。
