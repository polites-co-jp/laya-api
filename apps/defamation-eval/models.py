"""判定に使えるモデルと、その呼び出し方（docs/decisions.md D-10）。

どのモデルも TypeSafe の /v1/systemone と同じ形式（state と questions を送り、選択肢ごとの probabilities が返る）で答える。
Laya だけは本リポジトリの API（署名認証）を経由し、64件ずつまとめて送る。それ以外は1件ずつ送る。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from common import HERE

sys.path.insert(0, str(HERE.parent / "examples" / "python"))
from laya_client import LayaClient  # noqa: E402

MAX_RETRIES = 5
LAYA_BATCH_SIZE = 64  # laya-serve の batch の上限


@dataclass(frozen=True)
class Model:
    name: str  # ファイル名とコマンドの引数に使う
    title: str  # レポートに出す名前
    note: str  # レポートに出す補足（依頼との違いなど）
    batch_size: int
    make_decider: Callable[[], Callable[[list[str], dict], list[dict]]]
    device: str = "—"  # この検証で判定を動かした計算資源（GPU / CPU / クラウド）


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} を環境変数に設定してください")
    return value


def _laya() -> Callable[[list[str], dict], list[dict]]:
    client = LayaClient(os.environ.get("LAYA_API_URL", "http://127.0.0.1:22300"), _env("API_AUTH_SECRET"))

    def decide(states: list[str], questions: dict) -> list[dict]:
        # 質問が日本語なので、英語の投稿も english ではなく multilingual で判定する
        payload = {"states": states, "questions": questions, "model": "multilingual"}
        for _ in range(MAX_RETRIES):
            res = client.decide_batch(payload)
            if res.status == 200:
                return res.data["results"]
            if res.status in (502, 503):
                # 混雑中か Laya の起動中。Retry-After があれば従う
                time.sleep(float(res.retry_after or 5))
                continue
            raise SystemExit(f"Laya の判定に失敗した: {res.status} {res.data}")
        raise SystemExit(f"{MAX_RETRIES} 回再試行しても Laya が応答しない")

    return decide


def _systemone(url: str, headers: dict[str, str] | None = None, model: str | None = None, timeout: float = 300.0):
    """1件ずつ POST /v1/systemone へ送る decide を作る"""

    def post(state: str, questions: dict) -> dict:
        body = {"state": state, "questions": questions}
        if model:
            body["model"] = model
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        for _ in range(MAX_RETRIES):
            req = urllib.request.Request(
                f"{url.rstrip('/')}/v1/systemone",
                data=data,
                method="POST",
                headers={"Content-Type": "application/json", **(headers or {})},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as res:
                    return json.loads(res.read())
            except urllib.error.HTTPError as err:
                if err.code in (429, 502, 503):
                    time.sleep(float(err.headers.get("retry-after") or 5))
                    continue
                raise SystemExit(f"{url} の判定に失敗した: {err.code} {err.read().decode('utf-8', 'replace')}")
            except urllib.error.URLError as err:
                raise SystemExit(f"{url} に接続できない（コンテナは起動しているか）: {err.reason}")
        raise SystemExit(f"{MAX_RETRIES} 回再試行しても {url} が応答しない")

    def decide(states: list[str], questions: dict) -> list[dict]:
        return [post(s, questions) for s in states]

    return decide


def _toxicity(repo: str, label: str):
    """有害コメント分類器（D-11）。質問は受け取らず、label の確率を「当たる」とみなして systemone と同じ形にする"""
    url = f"http://127.0.0.1:{os.environ.get('EVAL_TOXICITY_HOST_PORT', 22313)}/v1/classify"

    def decide(states: list[str], questions: dict) -> list[dict]:
        req = urllib.request.Request(
            url,
            data=json.dumps({"model": repo, "texts": states}, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as res:
                body = json.loads(res.read())
        except urllib.error.HTTPError as err:
            raise SystemExit(f"{url} の分類に失敗した: {err.code} {err.read().decode('utf-8', 'replace')}")
        except urllib.error.URLError as err:
            raise SystemExit(f"{url} に接続できない（コンテナは起動しているか）: {err.reason}")
        (qid,) = questions
        results = []
        for scores in body["scores"]:
            p = scores[label]
            probs = {"defamatory": p, "not_defamatory": 1 - p, "uncertain": 0.0}
            results.append(
                {
                    "model": f"{body['model']}@{body['revision'][:7]}",
                    "answers": {qid: {"choice": max(probs, key=probs.get), "probabilities": probs}},
                    "scores": scores,
                }
            )
        return results

    return lambda: decide


def _local(port_env: str, default_port: int):
    return lambda: _systemone(f"http://127.0.0.1:{os.environ.get(port_env, default_port)}")


def _jev():
    return _systemone(
        os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai"),
        headers={"Authorization": f"Bearer {_env('TYPESAFE_API_KEY')}"},
        model=os.environ.get("JEV_MODEL", "jev-latest"),
    )


MODELS = {
    m.name: m
    for m in [
        Model("laya", "Laya", "multilingual チェックポイント", LAYA_BATCH_SIZE, _laya, device="CPU"),
        Model("jev", "Jev（TypeSafe）", "クラウド API。依頼の「JEB」", 1, _jev, device="クラウド"),
        Model("h2o-lightning", "H2O-Lightning-4B", "BF16 の GGUF（量子化なし）を llama-server で", 1,
              _local("EVAL_H2O_HOST_PORT", 22310), device="GPU"),
        Model("basal", "Basal-Omni-1.0-Max", "依頼の Ultra（31B）は 16GB に載らないため 12B の max の GGUF で代替", 1,
              _local("EVAL_BASAL_HOST_PORT", 22311), device="GPU"),
        Model("chon", "Chon-1.0", "12B を FP8（torchao）で。迷ったときの推論は vLLM ではなく hf-static", 1,
              _local("EVAL_CHON_HOST_PORT", 22312), device="GPU"),
        # 有害コメント分類器（D-11）。p_defamatory = 有害の確率、p_uncertain = 0
        Model("toxicity-base", "Multilingual Toxicity Base", "有害コメント分類器。toxicity ラベルの確率を「当たる」とみなす",
              16, _toxicity("Horizon-Labs/multilingual-toxicity-base", "toxicity"), device="CPU"),
        Model("xlmr-large-toxicity", "XLM-R Large Toxicity Classifier", "有害コメント分類器（v2）。toxic の確率を「当たる」とみなす",
              16, _toxicity("textdetox/xlmr-large-toxicity-classifier-v2", "toxic"), device="CPU"),
        Model("distilbert-toxicity", "DistilBERT Multilingual Toxicity Classifier",
              "有害コメント分類器。toxic の確率を「当たる」とみなす", 16,
              _toxicity("gravitee-io/distilbert-multilingual-toxicity-classifier", "toxic"), device="CPU"),
    ]
}
