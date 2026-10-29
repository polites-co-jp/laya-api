"""手順3: メールをモデルで判定し、3つの確率を CSV に出す。

入力:
    data/01_emails.csv     手順1のデータセット（本文だけをモデルに送る）
    reply_question.json    どのモデルにも同じ choice 型の質問
出力:
    data/04_<model>_results.csv  id, text, p_reply_needed, p_no_reply_needed, p_uncertain, pred_label, ...
    data/04_<model>_raw.jsonl    モデルの応答そのもの

使い方:
    python reply_classify.py --model laya|h2o-lightning|basal|chon
    Laya は API_AUTH_SECRET が要る。ほかは laya-api-containers で profile を指定して起動しておく（apps/defamation-eval/README.md）。
"""

from __future__ import annotations

import argparse
import json
import sys

from reply_shared import DATA_DIR, HERE, LABELS, MODELS, QUESTION_ID, read_csv, results_path, write_csv


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
    ap.add_argument("--model", choices=list(MODELS), required=True)
    args = ap.parse_args()
    model = MODELS[args.model]

    questions = json.loads((HERE / "reply_question.json").read_text(encoding="utf-8"))
    if tuple(questions[QUESTION_ID]["criteria"]) != LABELS:
        raise SystemExit(f"reply_question.json の選択肢が {LABELS} と違う")
    decide = model.make_decider()

    emails = read_csv(DATA_DIR / "01_emails.csv")
    rows: list[dict] = []
    raw_path = DATA_DIR / f"04_{model.name}_raw.jsonl"
    with raw_path.open("w", encoding="utf-8", newline="\n") as raw:
        for start in range(0, len(emails), model.batch_size):
            chunk = emails[start : start + model.batch_size]
            for e, result in zip(chunk, decide([e["text"] for e in chunk], questions)):
                raw.write(json.dumps({"id": e["id"], "response": result}, ensure_ascii=False) + "\n")
                rows.append(to_row(e, result))
            print(f"{model.name}: {start + len(chunk)}/{len(emails)} 件", flush=True)

    out = results_path(model.name)
    write_csv(out, rows, ["id", "text", *(f"p_{l}" for l in LABELS), "pred_label", "pred_confidence",
                          "served_model", "truncated"])
    print(f"-> {out}")
    print(f"-> {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
