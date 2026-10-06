# 公式パッケージ laya[serve] の laya-serve を動かすイメージ。
# 公式 Dockerfile（github.com/NandhaKishorM/laya）と同じく、torch の配布元を TORCH_INDEX で切り替える。
#   cu130: NVIDIA GPU（既定。NVIDIA ドライバ 580 以上が要る。RTX 50 系の sm_120 も含む）
#   cpu  : GPU なし
# torch 2.14.0 の CUDA 版は cu130 以降にしかない（cu128 は 2.11.0 まで）。
# ドライバが古いホストでは TORCH_INDEX=cu128 TORCH_VERSION=2.11.0 を渡す。
ARG PYTHON_IMAGE=python:3.11-slim-trixie

FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv --upgrade-deps /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ARG TORCH_INDEX=cu130
ARG TORCH_VERSION=2.14.0
ARG LAYA_VERSION=0.3.28
RUN pip install "torch==${TORCH_VERSION}" --index-url "https://download.pytorch.org/whl/${TORCH_INDEX}" \
    && pip install "laya[serve]==${LAYA_VERSION}" \
    && pip check

FROM ${PYTHON_IMAGE}
# TORCH_DISABLE_NATIVE_JIT: torch 2.14 は初回推論で Triton カーネルをコンパイルしようとし、
# C コンパイラのないイメージでは全リクエストが失敗する（公式 issue #365）。標準カーネルでも結果と速度は同じ。
ENV PATH="/opt/venv/bin:$PATH" \
    TORCH_DISABLE_NATIVE_JIT=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    USE_TF=0 \
    USE_TORCH=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/home/laya/.cache/huggingface \
    LAYA_HOST=0.0.0.0 \
    LAYA_PORT=8000

RUN groupadd --gid 10001 laya \
    && useradd --uid 10001 --gid laya --create-home laya \
    && mkdir -p /home/laya/.cache/huggingface \
    && chown -R laya:laya /home/laya/.cache

COPY --from=build /opt/venv /opt/venv
USER laya
WORKDIR /home/laya
EXPOSE 8000

# laya-serve は事前ロードが終わってから listen するので、/health が返れば推論できる
HEALTHCHECK --interval=30s --timeout=5s --start-period=15m --start-interval=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["laya-serve"]
