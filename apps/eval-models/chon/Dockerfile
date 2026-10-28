# 誹謗中傷判定の比較用（docs/decisions.md D-10）。Chon の公式サーバ chon.serve を動かすイメージ。
# 公式の docker/Dockerfile.serve は「迷ったときに考える」推論用に vLLM を同梱するが、16GB の GPU では
# vLLM に回す空きがなく、chon.serve 自身が static KV cache に切り替えて同じモデルで答える。そのため vLLM は入れない。
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/hf
# Triton が初回の推論で小さな補助モジュールをコンパイルするので C コンパイラが要る
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libc6-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 版は公式 Dockerfile.serve（v1.1.1）の chon.serve 側の環境に合わせる。torch の cu128 版は RTX 50 系（sm_120）も動く
ARG CHON_VERSION=1.1.1
RUN pip install "torch==2.9.1" --index-url https://download.pytorch.org/whl/cu128 \
    && pip install "chon[serve,fp8] @ https://github.com/xoai/chon/archive/refs/tags/v${CHON_VERSION}.tar.gz" \
        "transformers==5.20.2" "peft==0.18.1" "torchao==0.14.1" "huggingface_hub[hf_xet]>=1.0"

COPY serve.py /app/serve.py
WORKDIR /app
EXPOSE 8000
# 重みの取得（初回のみ。12B は基盤モデルを含め約25GB）と読み込みに時間がかかる
HEALTHCHECK --interval=30s --timeout=5s --start-period=60m --start-interval=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["python", "/app/serve.py"]
