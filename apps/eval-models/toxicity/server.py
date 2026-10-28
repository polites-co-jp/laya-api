"""有害コメント分類器（Hugging Face の text-classification）を HTTP で呼べるようにする（docs/decisions.md D-11）。

起動時に TOXICITY_MODELS の分類器をすべて CPU に読み込む。

    GET  /health
    POST /v1/classify  {"model": "<repo id>", "texts": ["...", ...]}
      -> {"model": "<repo id>", "revision": "<commit>", "scores": [{"<label>": p, ...}, ...]}

多ラベル分類（problem_type が multi_label_classification）はラベルごとの sigmoid、それ以外は softmax を返す。
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MAX_TOKENS = 512
# repo id@revision をカンマ区切り
SPECS = [s.strip() for s in os.environ["TOXICITY_MODELS"].split(",") if s.strip()]

torch.set_num_threads(int(os.environ.get("TOXICITY_THREADS", "4")))
MODELS: dict[str, tuple] = {}
for spec in SPECS:
    repo, _, revision = spec.partition("@")
    tok = AutoTokenizer.from_pretrained(repo, revision=revision or None)
    model = AutoModelForSequenceClassification.from_pretrained(repo, revision=revision or None).eval()
    MODELS[repo] = (tok, model, revision)
    print(f"loaded {repo}@{revision or 'main'}: {model.config.id2label}", flush=True)
# torch のスレッドを奪い合わないよう、推論は1件ずつ
LOCK = threading.Lock()


@torch.inference_mode()
def classify(repo: str, texts: list[str]) -> list[dict[str, float]]:
    tok, model, _ = MODELS[repo]
    enc = tok(texts, padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
    logits = model(**enc).logits
    if model.config.problem_type == "multi_label_classification":
        probs = torch.sigmoid(logits)
    else:
        probs = torch.softmax(logits, dim=-1)
    labels = model.config.id2label
    return [{labels[i]: round(float(p), 6) for i, p in enumerate(row)} for row in probs]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok", "models": list(MODELS)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/v1/classify":
            self._send(404, {"error": "not found"})
            return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            repo, texts = req["model"], req["texts"]
        except (ValueError, KeyError):
            self._send(400, {"error": 'body must be {"model": ..., "texts": [...]}'})
            return
        if repo not in MODELS:
            self._send(400, {"error": f"unknown model {repo!r}", "models": list(MODELS)})
            return
        with LOCK:
            scores = classify(repo, texts)
        self._send(200, {"model": repo, "revision": MODELS[repo][2], "scores": scores})

    def log_message(self, *args) -> None:  # リクエストごとのログは出さない
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
