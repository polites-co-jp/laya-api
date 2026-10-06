"""laya-api を外部アプリから呼ぶサンプルクライアント（Python 3.9 以上、標準ライブラリのみ）。

署名方式は docs/ja/auth.md（英語版 docs/en/auth.md）を参照。

使い方:
    API_AUTH_SECRET=... python laya_client.py "判断させたい文章"
    LAYA_API_URL を指定しなければ http://127.0.0.1:22300 を呼ぶ。

自分のアプリでは LayaClient をそのまま import して使える。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LayaResponse:
    status: int
    inference_ms: Optional[float]
    retry_after: Optional[str]
    data: Any


class LayaClient:
    def __init__(self, base_url: str, secret: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.secret = secret.encode("utf-8")
        self.timeout = timeout

    def sign_headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        """署名ヘッダを作る。body は送るバイト列そのもの。"""
        timestamp = str(int(time.time() * 1000))
        nonce = secrets.token_urlsafe(18)
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = "\n".join(["v1", timestamp, nonce, method.upper(), path, body_hash])
        signature = hmac.new(self.secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "x-auth-timestamp": timestamp,
            "x-auth-nonce": nonce,
            "x-auth-signature": signature,
        }

    def request(self, method: str, path: str, payload: Any = None) -> LayaResponse:
        # 署名したバイト列をそのまま送る。署名後に JSON を作り直すと本文のハッシュが変わり 401 になる
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self.sign_headers(method, path, body)
        if method == "POST":
            headers["content-type"] = "application/json"
        req = urllib.request.Request(
            self.base_url + path,
            data=body if method == "POST" else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return self._response(res.status, res.headers, res.read())
        except urllib.error.HTTPError as err:
            # 401 / 429 / 502 などもエラーにせず、状態コードと本文を返す
            return self._response(err.code, err.headers, err.read())

    @staticmethod
    def _response(status: int, headers: Any, raw: bytes) -> LayaResponse:
        text = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except ValueError:
            data = text
        inference = headers.get("x-inference-time-ms")
        return LayaResponse(
            status=status,
            inference_ms=float(inference) if inference is not None else None,
            retry_after=headers.get("retry-after"),
            data=data,
        )

    def health(self) -> LayaResponse:
        """Laya の状態（ロード済みチェックポイント、計算デバイス）"""
        return self.request("GET", "/health")

    def decide(self, payload: dict[str, Any]) -> LayaResponse:
        """1件の state を判断する。payload は {state, questions, model?, session_id?, user?}"""
        return self.request("POST", "/v1/systemone", payload)

    def decide_batch(self, payload: dict[str, Any]) -> LayaResponse:
        """複数の states に同じ questions をまとめて判断する。payload は {states, questions, model?}"""
        return self.request("POST", "/v1/systemone/batch", payload)


QUESTIONS_JA = {
    "urgent": {"type": "noul", "instructions": "今日中の対応が必要か？"},
    "queue": {
        "type": "choice",
        "instructions": "どの窓口が担当すべきか？",
        "criteria": {"returns": "返品・破損", "delivery": "配送状況", "other": "その他"},
    },
    "intensity": {
        "type": "score",
        "instructions": "どのくらい急ぎか？",
        "criteria": ["Routine", "Soon", "Today", "Immediate"],
    },
}

QUESTIONS_EN = {
    "urgent": {"type": "noul", "instructions": "Does this need a response today?"},
    "queue": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {"returns": "Returns or damaged items", "delivery": "Delivery status", "other": "Other"},
    },
    "intensity": {
        "type": "score",
        "instructions": "How urgent is this?",
        "criteria": ["Routine", "Soon", "Today", "Immediate"],
    },
}


def main() -> int:
    secret = os.environ.get("API_AUTH_SECRET")
    if not secret:
        print("API_AUTH_SECRET を環境変数に設定してください / Set API_AUTH_SECRET in the environment", file=sys.stderr)
        return 1
    client = LayaClient(os.environ.get("LAYA_API_URL", "http://127.0.0.1:22300"), secret)

    health = client.health()
    print("GET /health", health.status, json.dumps(health.data, ensure_ascii=False))

    state = sys.argv[1] if len(sys.argv) > 1 else "注文した商品が壊れて届きました。今日中に交換してほしいです。"
    # Laya は state の言語でチェックポイントを選ぶ。english に日本語の質問が届かないよう、例題も state の言語に合わせる
    questions = QUESTIONS_JA if re.search("[぀-ヿ一-鿿]", state) else QUESTIONS_EN
    res = client.decide({"state": state, "questions": questions})
    print("POST /v1/systemone", res.status, f"inference {res.inference_ms} ms")
    print(json.dumps(res.data, ensure_ascii=False, indent=2))
    return 0 if res.status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
