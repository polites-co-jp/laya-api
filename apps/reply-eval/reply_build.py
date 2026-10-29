"""手順1: サブエージェントが生成したメール（data/gen/batch_*.jsonl）を検査し、ID を振って1つのデータセットにする。

出力:
    data/01_emails.csv        id, text, gold_label, gold_reason, batch, category（正解付き）
    data/02_blind_input.jsonl id, text だけ（正解を伏せて別のエージェントがラベルを付け直すための入力）

使い方:
    python reply_build.py
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter

from reply_shared import BATCHES, DATA_DIR, GEN_DIR, LABELS, write_csv

SEED = 20261029
HEADER_LINES = ("件名: ", "差出人: ", "宛先: ")


def load() -> list[dict]:
    emails: list[dict] = []
    seen: set[str] = set()
    for batch in BATCHES:
        path = GEN_DIR / f"batch_{batch}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} がない")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            e = json.loads(line)
            where = f"{path.name}:{n}"
            text = e["text"].replace("\r\n", "\n").strip()
            if e["label"] not in LABELS:
                raise SystemExit(f"{where} のラベル {e['label']!r} が {LABELS} のどれでもない")
            if not text.startswith("件名: ") or any(h not in text for h in HEADER_LINES):
                raise SystemExit(f"{where} の先頭に件名・差出人・宛先の行がない")
            if text in seen:
                raise SystemExit(f"{where} が他のメールと同じ本文")
            seen.add(text)
            emails.append({"batch": batch, "category": e["category"], "gold_label": e["label"],
                           "gold_reason": e["reason"], "text": text})
    return emails


def main() -> int:
    emails = load()
    rng = random.Random(SEED)
    # ラベル付け直しのときに種類やラベルが並びから推測されないよう、混ぜてから ID を振る
    rng.shuffle(emails)
    rows = [{"id": f"M{i:03d}", **e} for i, e in enumerate(emails, 1)]
    write_csv(DATA_DIR / "01_emails.csv", rows, ["id", "text", "gold_label", "gold_reason", "batch", "category"])
    with (DATA_DIR / "02_blind_input.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], "text": r["text"]}, ensure_ascii=False) + "\n")
    print(f"{len(rows)} 件: {dict(Counter(r['gold_label'] for r in rows))}")
    print(f"種類ごと: {dict(Counter(r['batch'] for r in rows))}")
    print(f"-> {DATA_DIR / '01_emails.csv'}")
    print(f"-> {DATA_DIR / '02_blind_input.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
