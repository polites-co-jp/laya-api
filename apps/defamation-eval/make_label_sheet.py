"""手順3: Claude が付けた正解ラベルを、人が確認するためのシート data/03_labels.csv にまとめる。

入力:
    data/01_sample.csv          手順1で抽出した200件
    data/03_claude_labels.tsv   Claude のラベルと理由（id, claude_label, claude_reason）

出力の reviewed_label に値を入れると、評価ではそちらを正解として使う（空なら claude_label）。
確認を始めたシートを上書きしないよう、既に 03_labels.csv があれば何もしない（--force で作り直す）。

使い方:
    python make_label_sheet.py [--force]
"""

from __future__ import annotations

import csv
import sys

from common import DATA_DIR, LABELS, read_csv, write_csv


def main() -> int:
    out = DATA_DIR / "03_labels.csv"
    if out.exists() and "--force" not in sys.argv:
        print(f"{out} は既にある。確認内容を消さないよう作り直さない（作り直すなら --force）")
        return 0

    sample = read_csv(DATA_DIR / "01_sample.csv")
    with (DATA_DIR / "03_claude_labels.tsv").open(encoding="utf-8", newline="") as f:
        claude = {r["id"]: r for r in csv.DictReader(f, delimiter="\t")}

    rows = []
    for s in sample:
        c = claude.get(s["id"])
        if c is None:
            raise SystemExit(f"{s['id']} のラベルがない")
        if c["claude_label"] not in LABELS:
            raise SystemExit(f"{s['id']} のラベル {c['claude_label']!r} が {LABELS} のどれでもない")
        rows.append({**s, **c, "reviewed_label": "", "review_note": ""})

    write_csv(out, rows, ["id", "text", "claude_label", "claude_reason", "reviewed_label", "review_note"])
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
