# laya-api

オープンソースの判断用AI [Laya](https://github.com/NandhaKishorM/laya)（Apache 2.0）をローカルで動かし、社内サービスから使うための API。
Laya 本体（公式パッケージ `laya[serve]` の `laya-serve`）はコンテナ内のネットワークに閉じ、
外から届くのは共有秘密鍵の HMAC 署名で認証する Node.js の API だけにしている。

## 構成

| パス | 内容 |
|---|---|
| `apps/laya` | Laya 本体のイメージ（`laya[serve]==0.3.28`、torch は CUDA 版と CPU 版を切り替え） |
| `apps/api` | 署名を検証して Laya へ中継する API（Node.js / Fastify / TypeScript） |
| `apps/chat` | 開発用の動作確認チャット（判断チャット UI）。呼び出し側クライアントの参照実装 `src/layaClient.ts` を含む |
| `docs/` | 認証仕様 [auth.md](docs/auth.md)、決定事項 [decisions.md](docs/decisions.md)、ポート台帳の写し [port-registry.md](docs/port-registry.md) |
| `laya-api-containers/` | docker compose 一式 |

## 起動

```sh
cd laya-api-containers
cp .env.example .env
# API_AUTH_SECRET を埋める
docker compose up -d --build
```

- API: `http://127.0.0.1:22300`
- チャット（`COMPOSE_PROFILES=dev` のときだけ起動）: `http://127.0.0.1:22301`

初回起動時は Laya の重み（english と multilingual で約1.5GB）を Hugging Face から取得するため、使えるようになるまで数分かかる。
重みは名前付きボリューム `model-cache` に残るので、2回目以降は取得しない。

本番では `.env` から `COMPOSE_PROFILES=dev` を消し、チャットを起動しない。
別ホストのサービスから呼ぶときは `API_HOST_BIND=0.0.0.0` にし、TLS 終端（リバースプロキシ）を前段に置く。

### GPU と CPU

既定は NVIDIA GPU で動く。ホストに NVIDIA ドライバ 580 以上と NVIDIA Container Toolkit が要る。
CPU で動かすときは `.env` の次の2行のコメントを外し、`docker compose up -d --build` する。

```sh
COMPOSE_PATH_SEPARATOR=:
COMPOSE_FILE=docker-compose.yml:docker-compose.cpu.yml
```

判断1回あたりの目安は GPU で数十ms、CPU で0.2〜0.5秒。
ドライバが 580 未満の GPU ホストでは `LAYA_TORCH_INDEX=cu128` と `LAYA_TORCH_VERSION=2.11.0` を設定する。

### 開発時の起動（npm スクリプト）

リポジトリのルートで実行する。laya と chat（と chat が依存する api）をフォアグラウンドで起動し、Ctrl+C で止まる。

```sh
npm run dev:gpu   # GPU で起動
npm run dev:cpu   # CPU で起動
```

どちらも compose ファイルを `-f` で直接指定するので、`.env` の `COMPOSE_FILE` の設定より優先される。
`.env`（`API_AUTH_SECRET`）は事前に用意しておく。
GPU と CPU を切り替えるときは、動いている方を Ctrl+C で止めてからもう一方を起動する。
2つを同時に走らせると同じ laya コンテナを取り合い、意図しないモードで作り直されることがある。

### メモリ使用量の確認

```sh
npm run stats             # 各コンテナの RAM・CPU と、laya のモード（GPU / CPU）を1回表示
npm run stats -- --watch  # 2秒ごとに表示し続ける（推論中のピークを見るとき。Ctrl+C で終了）
```

Docker Desktop（WSL2）ではプロセスごとの VRAM が取れないため、VRAM は GPU 全体の使用量（他のアプリの分を含む）を表示する。

## エンドポイント

laya-serve の全エンドポイントを同じ入出力のまま中継する。入出力の形式は [Laya の README](https://github.com/NandhaKishorM/laya) を参照。

| メソッド | パス | 内容 |
|---|---|---|
| POST | `/v1/systemone` | 判断（`state` + `questions`。質問の型は `noul` / `choice` / `score`） |
| POST | `/v1/systemone/batch` | 複数の `states` に同じ `questions` をまとめて判断 |
| GET | `/health` | Laya の状態（ロード済みチェックポイント、実際の計算デバイス） |
| GET | `/healthz` | コンテナのヘルスチェック（認証なし・情報なし） |

`/healthz` 以外はすべて署名が必要。署名の作り方は [docs/auth.md](docs/auth.md)。
`model` は `english` / `multilingual` / `typed-decisions` のいずれかで、省略すると Laya が入力の言語を見て振り分ける。
応答ヘッダの `X-Inference-Time-Ms`（推論時間）と、混雑時の `Retry-After` は呼び出し側へそのまま返す。

## 開発

```sh
cd apps/api   # または apps/chat
npm ci
npm run typecheck
npm test
```
