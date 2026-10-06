# 認証仕様（HMAC 署名 + nonce）

**日本語** | [English](../en/auth.md) ・ [← README](../../README.md)

API（既定 `http://127.0.0.1:22300`）へのリクエストは、呼び出し側と API が共有する秘密鍵 `API_AUTH_SECRET` で署名する。
秘密鍵そのものは通信に載らないため、通信を傍受されても鍵は漏れない。

署名を自分で実装せずに済ませたい場合は、[API 利用手順](api.md) のサンプルクライアント（Node.js / Python）をそのまま使える。

## 守れること

| 傍受者がやりたいこと | 防ぐ仕組み |
|---|---|
| 鍵を盗む | 鍵は送らず、署名（HMAC-SHA256）だけを送る |
| 傍受した通信を後で送り直す | 時刻が許容幅（既定 ±1秒）を外れたら拒否 |
| 傍受した通信を1秒以内に送り直す | nonce を1回限りにし、使用済みなら拒否 |
| 署名はそのまま、本文（質問）だけ差し替える | 本文の SHA-256 を署名に含める |
| 署名を別のエンドポイントへ流用する | メソッドとパスを署名に含める |

防げないこと: 本文の盗み見。本文を秘匿したい場合は TLS（HTTPS）を前段に置く。
LAN 外や別ホストから呼ぶときは TLS 終端を必ず置く。

## リクエストヘッダ

| ヘッダ | 値 |
|---|---|
| `X-Auth-Timestamp` | 送信時刻の UNIX エポックミリ秒（例 `1790000000123`） |
| `X-Auth-Nonce` | 毎回新しく作るランダム文字列。`[A-Za-z0-9_-]` の16〜64文字 |
| `X-Auth-Signature` | 下記の正規化文字列に対する HMAC-SHA256 の16進小文字（64文字） |

## 正規化文字列

次の6行を `\n` で連結する（末尾に改行は付けない）。

```
v1
<X-Auth-Timestamp の値>
<X-Auth-Nonce の値>
<HTTP メソッド（大文字）>
<パス＋クエリ文字列（例 /v1/systemone）>
<本文バイト列の SHA-256 の16進小文字。本文なしは空文字列のハッシュ>
```

本文は送るバイト列そのものをハッシュする。署名後に JSON を整形し直したり再シリアライズしたりしない。
日本語などを含む本文は UTF-8 のバイト列としてハッシュし、同じバイト列を送る。

## 検証の順序（API 側）

1. 3つのヘッダが揃っていて形式が正しいこと
2. 署名が一致すること（定数時間比較）
3. 時刻が API の現在時刻 ±`AUTH_MAX_SKEW_MS`（既定1000）以内であること
4. nonce が未使用であること（許容幅の2倍の時間だけ記憶する）

失敗した場合は理由を問わず `401 {"error":"unauthorized"}` を返す。理由は API のログにだけ出す（[API 利用手順のトラブルシューティング](api.md#トラブルシューティング)）。
署名が正しくないリクエストでは nonce を消費しない。

## 運用上の注意

- 許容幅が1秒なので、呼び出し側と API のホストは NTP で時刻を合わせておく。ずれる環境では `AUTH_MAX_SKEW_MS` を広げる。
- nonce の記憶は API プロセスのメモリ上にある。API を複数台に増やす場合は共有ストア（Redis 等）へ移す必要がある。
- 鍵を変えるときは API と呼び出し側の `API_AUTH_SECRET` を同時に差し替える。
- 鍵をブラウザの JavaScript に埋め込まない。署名はサーバ側で行う。

## 実装例

| 言語 | ファイル |
|---|---|
| Node.js（依存なし） | [apps/examples/node/laya_client.mjs](../../apps/examples/node/laya_client.mjs) |
| Python（標準ライブラリのみ） | [apps/examples/python/laya_client.py](../../apps/examples/python/laya_client.py) |
| TypeScript（チャットが使う参照実装） | [apps/chat/src/layaClient.ts](../../apps/chat/src/layaClient.ts) |

### curl + openssl

本文はファイルに書き、そのファイルのハッシュを取って `--data-binary @ファイル` で送る。
`--data "$BODY"` で送ると、Windows の Git Bash では日本語が別の文字コードで curl に渡り、署名と本文がずれて 401 になる。

```sh
SECRET='（.env の API_AUTH_SECRET）'
printf '%s' '{"state":"こんにちは","questions":{"q":{"type":"noul","instructions":"挨拶か？"}}}' > body.json

HASH=$(openssl dgst -sha256 -hex body.json | awk '{print $NF}')
NONCE=$(openssl rand -hex 16)
TS=$(date +%s%3N)   # macOS では TS=$(perl -MTime::HiRes=time -e 'printf "%d", time*1000')
SIG=$(printf 'v1\n%s\n%s\nPOST\n/v1/systemone\n%s' "$TS" "$NONCE" "$HASH" \
  | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $NF}')

curl -s http://127.0.0.1:22300/v1/systemone -H 'content-type: application/json' \
  -H "x-auth-timestamp: $TS" -H "x-auth-nonce: $NONCE" -H "x-auth-signature: $SIG" \
  --data-binary @body.json
```

許容幅は1秒なので、`TS` は署名の直前に作り、curl まで間を空けずに実行する（まとめて貼り付けて実行する）。
Windows では openssl の起動に時間がかかり、`TS` を先に作ると送信までに1秒を超えて 401（ログ上は `expired`）になることがある。
