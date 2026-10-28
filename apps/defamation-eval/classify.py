"""手順4: 抽出した200件を決定モデルで判定し、3つの確率を CSV に出す。

入力:
    data/01_sample.csv     手順1で抽出した200件（本文だけをモデルに送る。文脈は送らない）
    laya_question.json     モデルに送る choice 型の質問（どのモデルにも同じものを送る）
出力（<model> は下のモデル名）:
    data/04_<model>_results.csv  id, text, p_defamatory, p_not_defamatory, p_uncertain, pred_label, ...
    data/04_<model>_raw.jsonl    モデルの応答そのもの（1行1件）

使い方:
    python classify.py [--model <モデル名>]   （既定は laya。名前の一覧は python classify.py --help）

    laya           API_AUTH_SECRET が要る。LAYA_API_URL を指定しなければ http://127.0.0.1:22300 を呼ぶ
    jev            TYPESAFE_API_KEY が要る。JEV_MODEL で版を選べる（既定 jev-latest）
    h2o-lightning  laya-api-containers で profile eval-h2o を起動しておく（127.0.0.1:22310）
    basal          同じく profile eval-basal（127.0.0.1:22311）
    chon           同じく profile eval-chon（127.0.0.1:22312）
    toxicity-base / xlmr-large-toxicity / distilbert-toxicity
                   同じく profile eval-toxicity（127.0.0.1:22313）
"""

from __future__ import annotations

import argparse
import json
import sys

from common import DATA_DIR, HERE, LABELS, read_csv, results_path, write_csv
from models import MODELS

QUESTION_ID = "defamation"


def to_row(sample: dict, result: dict) -> dict:
    answer = result["answers"][QUESTION_ID]
    probs = answer["probabilities"]
    if set(probs) != set(LABELS):
        raise SystemExit(f"{sample['id']} の確率の選択肢 {sorted(probs)} が {LABELS} と違う")
    return {
        "id": sample["id"],
        "text": sample["text"],
        **{f"p_{label}": f"{probs[label]:.4f}" for label in LABELS},
        "pred_label": answer["choice"],
        # confidence を返さないサーバもあるので、そのときは最も高い確率で代える
        "pred_confidence": f"{answer.get('confidence', max(probs.values())):.4f}",
        # Laya の batch は routing.model、/v1/systemone は model に、実際に答えたモデルが入る
        "served_model": result.get("routing", {}).get("model") or result.get("model", ""),
        "truncated": result.get("usage", {}).get("truncated", ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=list(MODELS), default="laya")
    args = ap.parse_args()
    model = MODELS[args.model]
    decide = model.make_decider()

    questions = json.loads((HERE / "laya_question.json").read_text(encoding="utf-8"))
    if tuple(questions[QUESTION_ID]["criteria"]) != LABELS:
        raise SystemExit(f"laya_question.json の選択肢が {LABELS} と違う")

    sample = read_csv(DATA_DIR / "01_sample.csv")
    rows: list[dict] = []
    raw_path = DATA_DIR / f"04_{model.name}_raw.jsonl"
    with raw_path.open("w", encoding="utf-8") as raw:
        for start in range(0, len(sample), model.batch_size):
            chunk = sample[start : start + model.batch_size]
            results = decide([s["text"] for s in chunk], questions)
            for s, result in zip(chunk, results):
                raw.write(json.dumps({"id": s["id"], "response": result}, ensure_ascii=False) + "\n")
                rows.append(to_row(s, result))
            done = start + len(chunk)
            if model.batch_size > 1 or done % 10 == 0 or done == len(sample):
                print(f"{done}/{len(sample)} 件")

    out = results_path(model.name)
    write_csv(
        out,
        rows,
        ["id", "text", *(f"p_{label}" for label in LABELS), "pred_label", "pred_confidence", "served_model", "truncated"],
    )
    print(f"-> {out}")
    print(f"-> {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
