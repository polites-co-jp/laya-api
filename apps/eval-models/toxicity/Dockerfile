# 誹謗中傷判定の比較用（docs/decisions.md D-11）。有害コメント分類器を CPU で動かすイメージ。
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 TOKENIZERS_PARALLELISM=false HF_HOME=/hf
RUN pip install "torch==2.11.0" --index-url https://download.pytorch.org/whl/cpu \
    && pip install "transformers==5.17.0" "sentencepiece==0.2.1" "protobuf>=5" "huggingface_hub[hf_xet]>=1.0"
COPY server.py /app/server.py
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30m --start-interval=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["python", "/app/server.py"]
