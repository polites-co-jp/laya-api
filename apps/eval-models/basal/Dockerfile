# 誹謗中傷判定の比較用（docs/decisions.md D-10）。basal の公式サーバ basal-serve を GGUF モードで動かすイメージ。
# GGUF モードは llama-cpp-python が推論するので、torch は CPU 版で足りる（basal の依存として要るだけ）。
# llama-cpp-python は CUDA 付きでソースからビルドする（PyPI の wheel は CPU 版）。
FROM nvidia/cuda:12.8.1-devel-ubuntu24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-dev cmake ninja-build git \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ARG BASAL_VERSION=2.4.1
ARG LLAMA_CPP_PYTHON_VERSION=0.3.36
# 120 = RTX 50 系（sm_120）。ビルド機に GPU がなくても通るよう、アーキテクチャを明示する。
# libcuda.so はビルド時にはないので、CUDA の stub にリンクする
ARG CUDA_ARCHITECTURES=120
RUN pip install "torch==2.11.0" --index-url https://download.pytorch.org/whl/cpu \
    && CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCHITECTURES} -DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined" \
       LDFLAGS="-L/usr/local/cuda/lib64/stubs" \
       pip install --no-binary llama-cpp-python "llama-cpp-python==${LLAMA_CPP_PYTHON_VERSION}" \
    && pip install "basal[gguf] @ https://github.com/rkinas/basal/archive/refs/tags/v${BASAL_VERSION}.tar.gz" \
        "huggingface_hub[hf_xet]>=1.0"

FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false HF_HOME=/hf PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends python3 curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/venv /opt/venv
COPY entrypoint.sh /entrypoint.sh
EXPOSE 8000
# 初回は GGUF（Q8_0 で約12.7GB）を取得するので時間がかかる
HEALTHCHECK --interval=30s --timeout=5s --start-period=60m --start-interval=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["sh", "/entrypoint.sh"]
