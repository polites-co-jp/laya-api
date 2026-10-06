# Deploying the Docker Containers

[日本語](../ja/deploy.md) | **English** ・ [← README](../../README.en.md)

How to start Laya, together with the API and chat that use it, with docker compose.

## Contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [1. Get the repository](#1-get-the-repository)
- [2. Create .env](#2-create-env)
- [3. Choose GPU or CPU](#3-choose-gpu-or-cpu)
- [4. Start](#4-start)
- [5. Check that it works](#5-check-that-it-works)
- [Stop, update, remove](#stop-update-remove)
- [Starting with npm scripts (for development)](#starting-with-npm-scripts-for-development)
- [Settings](#settings)
- [Using the API from another host](#using-the-api-from-another-host)
- [Troubleshooting](#troubleshooting)

## Architecture

The compose files are in [laya-api-containers/](../../laya-api-containers/). Three containers run.

| Service | Role | Exposed to the host |
|---|---|---|
| `laya` | Laya itself (`laya-serve` from the official `laya[serve]` package) | No (reachable only inside the compose network) |
| `api` | API that verifies HMAC signatures and forwards to `laya` (Node.js) | `127.0.0.1:22300` |
| `chat` | Decision chat for the browser. Starts only when `.env` has `COMPOSE_PROFILES=dev` | `127.0.0.1:22301` (fixed) |

```
Browser ──────> chat :22301 ──(signs and forwards)──┐
External app ──(HMAC signature)───────────────────> api :22300 ──> laya :8000
```

Laya's weights (about 1.5 GB for english and multilingual) are downloaded from Hugging Face on first start and kept in the named volume `model-cache`.

## Requirements

| Item | Details |
|---|---|
| Docker | Docker Engine and Docker Compose v2.24 or later (Docker Desktop on Windows / macOS) |
| Disk | Images: about 9.3 GB for the GPU laya image / about 1.8 GB for the CPU one, plus about 0.5 GB for the rest. Weights: about 1.5 GB |
| Memory | About 3.3 GB for laya with english and multilingual loaded (measured on CPU) |
| Network | Internet access for the first build and weight download (PyPI, PyTorch, Hugging Face) |
| GPU (optional) | NVIDIA GPU with driver 580 or later. On Linux, the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html); on Windows, Docker Desktop with the WSL2 backend |
| Node.js (optional) | 22 or later. Only for the npm scripts (`npm run dev:gpu` etc.) and the sample clients |

It also runs without a GPU. One decision takes roughly tens of milliseconds on a GPU and 0.2–0.5 seconds on a CPU.

## 1. Get the repository

```sh
git clone https://github.com/polites-co-jp/laya-api.git
cd laya-api/laya-api-containers
```

Unless stated otherwise, run the following commands in `laya-api-containers/`.

## 2. Create .env

```sh
cp .env.example .env
```

Set `API_AUTH_SECRET` in `.env` to a random string of at least 32 characters. It is the signing key shared by the API and its callers, and it is never sent over the wire.
Any of these will generate one:

```sh
openssl rand -base64 32
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```
API_AUTH_SECRET=the-string-you-generated
```

`.env` is listed in `.gitignore` and never enters the repository. The comments in `.env.example` are in Japanese; [Settings](#settings) below describes every variable.

## 3. Choose GPU or CPU

By default it runs on an NVIDIA GPU. If you have no GPU, or want to try it on CPU, uncomment these two lines in `.env`:

```sh
COMPOSE_PATH_SEPARATOR=:
COMPOSE_FILE=docker-compose.yml:docker-compose.cpu.yml
```

On GPU hosts with an NVIDIA driver older than 580, add these two lines to `.env` to use the CUDA 12.8 build of torch:

```sh
LAYA_TORCH_INDEX=cu128
LAYA_TORCH_VERSION=2.11.0
```

## 4. Start

```sh
docker compose up -d --build
```

The first run builds the images (the GPU image downloads several GB of torch) and downloads the weights, so it takes several minutes to a quarter of an hour before it is usable.
It is ready once `laya` is `healthy`.

```sh
docker compose ps
# NAME              STATUS
# laya-api-laya-1   Up 3 minutes (healthy)
# laya-api-api-1    Up 3 minutes (healthy)
# laya-api-chat-1   Up 3 minutes (healthy)

docker compose logs -f laya   # follow progress (Ctrl+C exits the log; the container keeps running)
```

## 5. Check that it works

- **Chat**: open <http://127.0.0.1:22301> in a browser. When the top right shows something like `Laya ready ・ cpu ・ english, multilingual`, it is ready. See [Using the chat](chat.md).
- **API**: run a sample client from the repository root (requires Node.js). See [Using the API](api.md) for details.

  ```sh
  cd ..
  export API_AUTH_SECRET='(API_AUTH_SECRET from .env)'
  node apps/examples/node/laya_client.mjs "The item I ordered arrived broken. Please replace it today."
  # GET /health 200 {...}
  # POST /v1/systemone 200 inference 345 ms
  ```

## Stop, update, remove

| Task | Command |
|---|---|
| Stop (keep the containers) | `docker compose stop` |
| Stop and remove the containers (keep the weights) | `docker compose down` |
| Also delete the weights | `docker compose down -v` (they are downloaded again on next start) |
| Update to the latest version | `git pull`, then `docker compose up -d --build` |
| Switch between GPU and CPU | Edit `.env`, then `docker compose up -d --build` |

To run without the chat, delete the `COMPOSE_PROFILES=dev` line from `.env` and run `docker compose up -d`.

## Starting with npm scripts (for development)

Run these in the repository root (requires Node.js). They start laya and chat (plus api, which chat depends on) in the foreground; Ctrl+C stops them.

```sh
npm run dev:gpu   # start on GPU
npm run dev:cpu   # start on CPU
npm run stats     # for the running laya, show weight file sizes and the time and memory of one request
```

`dev:gpu` / `dev:cpu` pass the compose files with `-f`, which takes precedence over `COMPOSE_FILE` in `.env`. Prepare `.env` (`API_AUTH_SECRET`) beforehand.
To switch between GPU and CPU, stop the running one with Ctrl+C before starting the other.

## Settings

Set these in `.env`. Everything except `API_AUTH_SECRET` has a default.

| Variable | Default | Meaning |
|---|---|---|
| `API_AUTH_SECRET` | (required) | Signing key, 32+ characters |
| `COMPOSE_PROFILES` | `dev` (in .env.example) | With `dev`, the chat starts too |
| `COMPOSE_FILE` | — | `docker-compose.yml:docker-compose.cpu.yml` to run on CPU |
| `AUTH_MAX_SKEW_MS` | `1000` | Allowed clock skew of signatures, in milliseconds, each way |
| `UPSTREAM_TIMEOUT_MS` | `60000` | How long the API waits for Laya, in milliseconds |
| `LOG_LEVEL` | `info` | API log level |
| `LAYA_MODELS` | `english,multilingual` | Checkpoints loaded at startup (`english` / `multilingual` / `typed-decisions`) |
| `LAYA_DEFAULT_MODEL` | `multilingual` | Checkpoint for input whose language cannot be detected |
| `LAYA_GPU_ID` | `0` | Which GPU to use |
| `LAYA_THREADS` | `4` | CPU inference threads (keep at or below the number of physical cores) |
| `LAYA_MAX_CONCURRENT` | `16` (Laya's default) | Requests processed at once; beyond that, 503 |
| `LAYA_REVISION` | `reviewed` | Hugging Face revision the weights are pinned to. `reviewed` is the verified commit bundled with laya |
| `LAYA_TORCH_INDEX` / `LAYA_TORCH_VERSION` | `cu130` / `2.14.0` | Source and version of the GPU build of torch |
| `API_HOST_BIND` | `127.0.0.1` | Address the API is published on |
| `API_HOST_PORT` | `22300` | Host port of the API |
| `CHAT_HOST_PORT` | `22301` | Host port of the chat |

`typed-decisions` is not loaded at startup by default. When a request names it, it is downloaded and loaded at that point (slow the first time).

## Using the API from another host

By default both the API and the chat are published only on `127.0.0.1`. To call the API from an application on another host, set `API_HOST_BIND=0.0.0.0` in `.env` and also:

- Put a reverse proxy that terminates TLS (HTTPS) in front. Signatures do not encrypt the body.
- Use a firewall to block everyone except the callers. On Linux, ports published by Docker bypass ufw.
- Keep both hosts' clocks in sync with NTP.
- Never expose the chat (anyone who reaches it can use the API). In production, remove `COMPOSE_PROFILES=dev`.

See [Calling from another host](api.md#7-calling-from-another-host) in the API guide for details.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `laya` takes a long time to become `healthy` | The first start downloads the weights. Watch progress with `docker compose logs -f laya` |
| Fails to start with `could not select device driver "nvidia"` | The NVIDIA Container Toolkit is missing, or there is no GPU. Switch to CPU ([step 3](#3-choose-gpu-or-cpu)) |
| CUDA errors with the GPU image | Driver older than 580. Set `LAYA_TORCH_INDEX=cu128` and `LAYA_TORCH_VERSION=2.11.0` and rebuild |
| `device` in `/health` stays `cpu` | Laya could not get the GPU and fell back to CPU. Check `docker compose logs laya` |
| Fails to start with `API_AUTH_SECRET is required` | `API_AUTH_SECRET` in `.env` is empty |
| api stops with `API_AUTH_SECRET must be set and at least 32 characters` | The secret is shorter than 32 characters |
| `port is already allocated` | The port is in use. Change `API_HOST_PORT` / `CHAT_HOST_PORT` |
| The chat shows "Cannot reach Laya" at the top right | Laya is still starting. Wait until it is `healthy` |
| The API returns 401 | See [Troubleshooting in the API guide](api.md#troubleshooting) |
