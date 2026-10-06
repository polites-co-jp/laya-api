# Docker コンテナ展開手順

**日本語** | [English](../en/deploy.md) ・ [← README](../../README.md)

Laya と、それを使うための API・チャットを docker compose で起動する手順。

## 目次

- [構成](#構成)
- [前提](#前提)
- [1. リポジトリを取得する](#1-リポジトリを取得する)
- [2. .env を作る](#2-env-を作る)
- [3. GPU か CPU かを決める](#3-gpu-か-cpu-かを決める)
- [4. 起動する](#4-起動する)
- [5. 動作を確かめる](#5-動作を確かめる)
- [停止・更新・削除](#停止更新削除)
- [npm スクリプトでの起動（開発向け）](#npm-スクリプトでの起動開発向け)
- [設定一覧](#設定一覧)
- [別ホストから API を使う場合](#別ホストから-api-を使う場合)
- [トラブルシューティング](#トラブルシューティング)

## 構成

compose ファイルは [laya-api-containers/](../../laya-api-containers/) にある。起動するコンテナは3つ。

| サービス | 内容 | ホストへの公開 |
|---|---|---|
| `laya` | Laya 本体（公式パッケージ `laya[serve]` の `laya-serve`） | しない（compose 内のネットワークからのみ） |
| `api` | HMAC 署名を検証して `laya` へ中継する API（Node.js） | `127.0.0.1:22300` |
| `chat` | ブラウザで試す判断チャット。`.env` の `COMPOSE_PROFILES=dev` のときだけ起動 | `127.0.0.1:22301`（固定） |

```
ブラウザ ──> chat :22301 ──(署名して中継)──┐
外部アプリ ──(HMAC 署名)────────────────> api :22300 ──> laya :8000
```

Laya の重み（english と multilingual で約1.5GB）は初回起動時に Hugging Face から取得し、名前付きボリューム `model-cache` に残す。

## 前提

| 項目 | 内容 |
|---|---|
| Docker | Docker Engine と Docker Compose v2.24 以上（Windows / macOS は Docker Desktop） |
| ディスク | イメージ: GPU 版の laya 約9.3GB / CPU 版の laya 約1.8GB、ほか約0.5GB。重み: 約1.5GB |
| メモリ | laya が english と multilingual を読み込んだ状態で約3.3GB（CPU で計測） |
| ネットワーク | 初回のビルドと重みの取得にインターネット接続（PyPI・PyTorch・Hugging Face） |
| GPU（任意） | NVIDIA GPU と NVIDIA ドライバ 580 以上。Linux は [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)、Windows は Docker Desktop の WSL2 バックエンド |
| Node.js（任意） | 22 以上。npm スクリプト（`npm run dev:gpu` など）とサンプルクライアントを使うときだけ |

GPU がなくても CPU で動く。判断1回あたりの目安は GPU で数十ms、CPU で0.2〜0.5秒。

## 1. リポジトリを取得する

```sh
git clone https://github.com/polites-co-jp/laya-api.git
cd laya-api/laya-api-containers
```

以降のコマンドは、特に断りがなければ `laya-api-containers/` で実行する。

## 2. .env を作る

```sh
cp .env.example .env
```

`.env` の `API_AUTH_SECRET` に、32文字以上のランダムな文字列を入れる。API と呼び出し側が共有する署名用の秘密鍵で、通信には載らない。
次のどれかで作れる。

```sh
openssl rand -base64 32
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```
API_AUTH_SECRET=ここに生成した文字列
```

`.env` は `.gitignore` 済みで、リポジトリには入らない。

## 3. GPU か CPU かを決める

既定は NVIDIA GPU で動く。GPU がないとき、または CPU で試したいときは、`.env` の次の2行のコメントを外す。

```sh
COMPOSE_PATH_SEPARATOR=:
COMPOSE_FILE=docker-compose.yml:docker-compose.cpu.yml
```

NVIDIA ドライバが 580 未満の GPU ホストでは、CUDA 12.8 版の torch を使うよう `.env` に次の2行を足す。

```sh
LAYA_TORCH_INDEX=cu128
LAYA_TORCH_VERSION=2.11.0
```

## 4. 起動する

```sh
docker compose up -d --build
```

初回はイメージのビルド（GPU 版は torch の取得で数GB）と重みの取得があり、使えるようになるまで数分〜十数分かかる。
`laya` が `healthy` になれば使える。

```sh
docker compose ps
# NAME              STATUS
# laya-api-laya-1   Up 3 minutes (healthy)
# laya-api-api-1    Up 3 minutes (healthy)
# laya-api-chat-1   Up 3 minutes (healthy)

docker compose logs -f laya   # 進み具合を見る（Ctrl+C で抜ける。コンテナは止まらない）
```

## 5. 動作を確かめる

- **チャット**: ブラウザで <http://127.0.0.1:22301> を開く。右上に `Laya ready ・ cpu ・ english, multilingual` のように出れば準備完了。使い方は [チャットの使い方](chat.md)。
- **API**: リポジトリのルートでサンプルクライアントを実行する（Node.js が要る）。詳しくは [API 利用手順](api.md)。

  ```sh
  cd ..
  export API_AUTH_SECRET='（.env の API_AUTH_SECRET）'
  node apps/examples/node/laya_client.mjs
  # GET /health 200 {...}
  # POST /v1/systemone 200 inference 130 ms
  ```

## 停止・更新・削除

| したいこと | コマンド |
|---|---|
| 止める（コンテナは残す） | `docker compose stop` |
| 止めて片付ける（重みは残す） | `docker compose down` |
| 重みも消す | `docker compose down -v`（次回の起動で再取得する） |
| 最新版に更新する | `git pull` のあと `docker compose up -d --build` |
| GPU と CPU を切り替える | `.env` を書き換えて `docker compose up -d --build` |

チャットを起動したくないときは、`.env` の `COMPOSE_PROFILES=dev` の行を消して `docker compose up -d` する。

## npm スクリプトでの起動（開発向け）

リポジトリのルートで実行する（Node.js が要る）。laya と chat（と chat が依存する api）をフォアグラウンドで起動し、Ctrl+C で止まる。

```sh
npm run dev:gpu   # GPU で起動
npm run dev:cpu   # CPU で起動
npm run stats     # 起動中の laya について、重みのサイズと1回の問い合わせの推論時間・メモリを表示する
```

`dev:gpu` / `dev:cpu` は compose ファイルを `-f` で直接指定するので、`.env` の `COMPOSE_FILE` より優先される。`.env`（`API_AUTH_SECRET`）は事前に用意しておく。
GPU と CPU を切り替えるときは、動いている方を Ctrl+C で止めてからもう一方を起動する。

## 設定一覧

`.env` で設定する。`API_AUTH_SECRET` 以外は省略すると既定値になる。

| 変数 | 既定値 | 内容 |
|---|---|---|
| `API_AUTH_SECRET` | （必須） | 署名用の秘密鍵。32文字以上 |
| `COMPOSE_PROFILES` | `dev`（.env.example） | `dev` のときチャットも起動する |
| `COMPOSE_FILE` | — | CPU で動かすときに `docker-compose.yml:docker-compose.cpu.yml` |
| `AUTH_MAX_SKEW_MS` | `1000` | 署名時刻の許容幅（ミリ秒、前後それぞれ） |
| `UPSTREAM_TIMEOUT_MS` | `60000` | API が Laya の応答を待つ時間（ミリ秒） |
| `LOG_LEVEL` | `info` | API のログレベル |
| `LAYA_MODELS` | `english,multilingual` | 起動時に読み込むチェックポイント（`english` / `multilingual` / `typed-decisions`） |
| `LAYA_DEFAULT_MODEL` | `multilingual` | 言語を判定できない入力に使うチェックポイント |
| `LAYA_GPU_ID` | `0` | 使う GPU の番号 |
| `LAYA_THREADS` | `4` | CPU 推論のスレッド数（物理コア数以下にする） |
| `LAYA_MAX_CONCURRENT` | `16`（Laya の既定） | 同時に処理するリクエスト数。超えると 503 |
| `LAYA_REVISION` | `reviewed` | 重みの取得元を固定する Hugging Face のリビジョン。`reviewed` は laya に同梱された検証済みのコミット |
| `LAYA_TORCH_INDEX` / `LAYA_TORCH_VERSION` | `cu130` / `2.14.0` | GPU 版 torch の配布元とバージョン |
| `API_HOST_BIND` | `127.0.0.1` | API を公開するアドレス |
| `API_HOST_PORT` | `22300` | API のホスト側ポート |
| `CHAT_HOST_PORT` | `22301` | チャットのホスト側ポート |

`typed-decisions` は既定では起動時に読み込まない。リクエストで指定すると、その時点で取得・読み込みする（初回は時間がかかる）。

## 別ホストから API を使う場合

既定では API もチャットも `127.0.0.1` にだけ公開される。別ホストのアプリから API を呼ぶときは、`.env` で `API_HOST_BIND=0.0.0.0` にしたうえで次を守る。

- TLS（HTTPS）を終端するリバースプロキシを前段に置く。署名は本文を暗号化しない。
- ファイアウォールで呼び出し元以外を遮断する。Linux では Docker の公開ポートが ufw を迂回する。
- 両ホストの時刻を NTP で合わせる。
- チャットは公開しない（届いた人は誰でも API を使えてしまう）。本番では `COMPOSE_PROFILES=dev` を消す。

詳しくは [API 利用手順の「別ホストから呼ぶ場合」](api.md#7-別ホストから呼ぶ場合)。

## トラブルシューティング

| 症状 | 原因と対処 |
|---|---|
| `laya` がなかなか `healthy` にならない | 初回は重みの取得に時間がかかる。`docker compose logs -f laya` で進み具合を見る |
| `could not select device driver "nvidia"` で起動しない | NVIDIA Container Toolkit が入っていない、または GPU がない。CPU に切り替える（[手順3](#3-gpu-か-cpu-かを決める)） |
| GPU 版で CUDA のエラーが出る | ドライバが 580 未満。`LAYA_TORCH_INDEX=cu128` と `LAYA_TORCH_VERSION=2.11.0` を設定してビルドし直す |
| `/health` の `device` が `cpu` のまま | GPU を確保できず、Laya が CPU に切り替えて動いている。`docker compose logs laya` を確認する |
| `API_AUTH_SECRET is required` で起動しない | `.env` の `API_AUTH_SECRET` が空 |
| api が `API_AUTH_SECRET must be set and at least 32 characters` で止まる | 秘密鍵が32文字未満 |
| `port is already allocated` | ポートが使用中。`API_HOST_PORT` / `CHAT_HOST_PORT` を変える |
| チャット右上が「Laya に接続できません」 | Laya の起動中。`healthy` になるまで待つ |
| API が 401 を返す | [API 利用手順のトラブルシューティング](api.md#トラブルシューティング) |
