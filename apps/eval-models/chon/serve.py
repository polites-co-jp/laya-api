"""chon.serve を、16GB の GPU でも FP8 の 12B を載せられるように起動する。

chon.serve の --quantize fp8 は bf16 の重みを丸ごと GPU に載せてから FP8 にするため、12B（bf16 で約24GB）は
変換の前に GPU からあふれる。ここでは重みを CPU で読み込み、量子化する Linear を1つずつ GPU へ移して FP8 にし、
最後に残り（埋め込み・正規化など）を GPU へ移す。量子化の対象と設定は chon.quantize.fp8_quantize と同じ。

環境変数:
    CHON_MODEL     Hugging Face の repo id（@revision 付き可）。既定は Chon-1.0-12B
    CHON_QUANTIZE  fp8 なら上の方法で FP8 にする。空なら chon.serve の既定（bf16 のまま GPU へ）
"""

from __future__ import annotations

import os
import sys

import chon.infer
import chon.quantize
from chon import serve

MODEL = os.environ.get("CHON_MODEL") or "ninhnv/chon-1.0-12b"
QUANTIZE = os.environ.get("CHON_QUANTIZE", "")


def fp8_quantize_to_cuda(model):
    import torch
    from torch import nn
    from torchao.quantization import Float8DynamicActivationFloat8WeightConfig, PerRow, quantize_

    config = Float8DynamicActivationFloat8WeightConfig(granularity=PerRow())
    # 12B は「迷ったときに考える」ために LoRA を基盤モデルへ合成せずに残し、LoRA の重みは float32 のまま。
    # torchao の FP8（PerRow）は bf16 の重みしか受け付けないので、bf16 でない Linear（LoRA の A・B）はそのまま残す
    targets = [
        name
        for name, mod in model.named_modules()
        if isinstance(mod, nn.Linear)
        and mod.weight.dtype == torch.bfloat16
        and "lm_head" not in name.lower()
        and not any(x in name.lower() for x in chon.quantize.NON_TEXT)
    ]
    for name in targets:
        parent_name, _, child = name.rpartition(".")
        parent = model.get_submodule(parent_name)
        getattr(parent, child).to("cuda")
        quantize_(parent, config, filter_fn=lambda _m, fqn, child=child: fqn == child)
    model.to("cuda")
    torch.cuda.empty_cache()
    print(f"[serve.py] FP8 にした Linear: {len(targets)} 個", flush=True)
    return model


def main() -> None:
    args = ["--model", MODEL, "--host", "0.0.0.0", "--port", "8000"]
    if QUANTIZE == "fp8":
        load_causal_lm = chon.infer.load_causal_lm

        def load_on_cpu(path, *a, device_map=None, **kw):
            return load_causal_lm(path, *a, device_map=None, **kw)

        chon.infer.load_causal_lm = load_on_cpu
        chon.quantize.fp8_quantize = fp8_quantize_to_cuda
        args += ["--quantize", "fp8"]
    elif QUANTIZE:
        sys.exit(f"CHON_QUANTIZE={QUANTIZE!r} は使えない（fp8 か空）")
    serve.main(args + sys.argv[1:])


if __name__ == "__main__":
    main()
