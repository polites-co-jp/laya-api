"""手順4: 抽出した200件を Laya で判定し、3つの確率を CSV に出す。

入力:
    data/01_sample.csv     手順1で抽出した200件（本文だけを Laya に送る。文脈は送らない）
    laya_question.json     Laya に送る choice 型の質問
出力:
    data/04_laya_results.csv  id, text, p_defamatory, p_not_defamatory, p_uncertain, laya_label, ...
    data/04_laya_raw.jsonl    Laya の応答そのもの（1行1件）

使い方:
    API_AUTH_SECRET=... python classify.py
    LAYA_API_URL を指定しなければ http://127.0.0.1:22300 を呼ぶ。
"""

from __future__ import annotations

import json
import os
import sys
import time

from common import DATA_DIR, HERE, LABELS, read_csv, write_csv

sys.path.insert(0, str(HERE.parent / "examples" / "python"))
from laya_client import LayaClient  # noqa: E402

BATCH_SIZE = 64  # laya-serve の batch の上限
MAX_RETRIES = 5
QUESTION_ID = "defamation"
# 質問が日本語なので、英語の投稿も english ではなく multilingual で判定する
MODEL = "multilingual"


def decide_batch(client: LayaClient, states: list[str], questions: dict) -> list[dict]:
    for _ in range(MAX_RETRIES):
        res = client.decide_batch({"states": states, "questions": questions, "model": MODEL})
        if res.status == 200:
            return res.data["results"]
        if res.status in (502, 503):
            # 混雑中か Laya の起動中。Retry-After があれば従う
            time.sleep(float(res.retry_after or 5))
            continue
        raise SystemExit(f"Laya の判定に失敗した: {res.status} {res.data}")
    raise SystemExit(f"{MAX_RETRIES} 回再試行しても Laya が応答しない")


def main() -> int:
    secret = os.environ.get("API_AUTH_SECRET")
    if not secret:
        print("API_AUTH_SECRET を環境変数に設定してください", file=sys.stderr)
        return 1
    client = LayaClient(os.environ.get("LAYA_API_URL", "http://127.0.0.1:22300"), secret)
    questions = json.loads((HERE / "laya_question.json").read_text(encoding="utf-8"))
    if tuple(questions[QUESTION_ID]["criteria"]) != LABELS:
        raise SystemExit(f"laya_question.json の選択肢が {LABELS} と違う")

    sample = read_csv(DATA_DIR / "01_sample.csv")
    rows: list[dict] = []
    raw_path = DATA_DIR / "04_laya_raw.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw:
        for start in range(0, len(sample), BATCH_SIZE):
            chunk = sample[start : start + BATCH_SIZE]
            results = decide_batch(client, [s["text"] for s in chunk], questions)
            for s, result in zip(chunk, results):
                raw.write(json.dumps({"id": s["id"], "response": result}, ensure_ascii=False) + "\n")
                answer = result["answers"][QUESTION_ID]
                probs = answer["probabilities"]
                rows.append(
                    {
                        "id": s["id"],
                        "text": s["text"],
                        **{f"p_{label}": f"{probs[label]:.4f}" for label in LABELS},
                        "laya_label": answer["choice"],
                        "laya_confidence": f"{answer['confidence']:.4f}",
                        "laya_model": result.get("routing", {}).get("model", ""),
                        "truncated": result.get("usage", {}).get("truncated", ""),
                    }
                )
            print(f"{start + len(chunk)}/{len(sample)} 件")

    out = DATA_DIR / "04_laya_results.csv"
    write_csv(
        out,
        rows,
        ["id", "text", *(f"p_{label}" for label in LABELS), "laya_label", "laya_confidence", "laya_model", "truncated"],
    )
    print(f"-> {out}")
    print(f"-> {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
