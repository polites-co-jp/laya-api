# laya-api

判断用AI [Laya AI](https://laya-ai.pro/docs) を社内サービスから使うための中継 API。
Laya の API キーはこの API だけが持ち、呼び出し側は共有秘密鍵による HMAC 署名で認証する。

## 構成

| パス | 内容 |
|---|---|
| `apps/api` | 中継 API（Node.js / Fastify / TypeScript） |
| `apps/chat` | 開発用の動作確認チャット（判断チャット UI）。呼び出し側クライアントの参照実装 `src/layaClient.ts` を含む |
| `docs/` | 認証仕様 [auth.md](docs/auth.md)、決定事項 [decisions.md](docs/decisions.md)、ポート台帳の写し [port-registry.md](docs/port-registry.md) |
| `laya-api-containers/` | docker compose 一式 |

## 起動

```sh
cd laya-api-containers
cp .env.example .env
# API_AUTH_SECRET と LAYA_AI_API_KEY を埋める
docker compose up -d --build
```

- API: `http://127.0.0.1:22300`
- チャット（`COMPOSE_PROFILES=dev` のときだけ起動）: `http://127.0.0.1:22301`

本番では `.env` から `COMPOSE_PROFILES=dev` を消し、チャットを起動しない。
別ホストのサービスから呼ぶときは `API_HOST_BIND=0.0.0.0` にし、TLS 終端（リバースプロキシ）を前段に置く。

## エンドポイント

Laya の全エンドポイントを同じ入出力のまま中継する。リクエスト・レスポンスの形式は Laya の仕様どおり。

| メソッド | パス | Laya 側 |
|---|---|---|
| POST | `/v1/systemone` | 判断（state + typed questions） |
| POST | `/alpha/decisions` | Decisions API 互換形式 |
| GET | `/v1/models` | 使えるモデルの一覧 |
| GET | `/laya/status` | 稼働状態 |
| GET | `/healthz` | コンテナのヘルスチェック（認証なし・情報なし） |

`/healthz` 以外はすべて署名が必要。署名の作り方は [docs/auth.md](docs/auth.md)。
Laya の応答ヘッダのうち `X-Laya-*`（課金・残量）と `Retry-After` は呼び出し側へそのまま返す。

## 開発

```sh
cd apps/api   # または apps/chat
npm ci
npm run typecheck
npm test
```
