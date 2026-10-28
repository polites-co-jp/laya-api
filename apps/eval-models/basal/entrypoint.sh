#!/bin/sh
# GGUF のリポジトリから、使う量子化の GGUF と、basal-serve がプロンプトを組むのに使う設定・トークナイザだけを取得して起動する。
#   BASAL_REPO      GGUF のリポジトリ（既定: basal-omni-1.0-max）
#   BASAL_REVISION  取得するコミット（再現性のため固定する）
#   BASAL_QUANT     Q8_0（推奨）か Q6_K（GPU に載らないとき）
set -eu
REPO="${BASAL_REPO:-Remek/basal-omni-1.0-max-GGUF}"
REVISION="${BASAL_REVISION:-147f87b850627a187395888a0133dfb912a31448}"
QUANT="${BASAL_QUANT:-Q8_0}"
DIR="/hf/models/$(basename "$REPO")"
NAME="$(basename "$REPO" -GGUF)"

hf download "$REPO" --revision "$REVISION" --local-dir "$DIR" \
  --include "${NAME}-${QUANT}.gguf" "*.json" "*.jinja"

exec basal-serve --mode gguf --model "$DIR" --gguf "$DIR/${NAME}-${QUANT}.gguf" --name "${NAME}-${QUANT}" \
  --host 0.0.0.0 --port 8000 "$@"
