"""手順1: 裁判例データセットを取得し、判定対象の200件を抽出する（Python 3.9 以上、標準ライブラリのみ）。

出典: 久田祥平, 若宮翔子, 荒牧英治. 日本語オンライン誹謗中傷検出に向けた裁判例データセット. 自然言語処理, 31(4), 2024.
      https://github.com/horshohei/japanese-offensive-language-from-court-case（CC BY-NC 4.0）

ライセンスが CC BY-NC のため、本文を含む出力は data/（git 管理外）にだけ書く。
本文を含まない抽出 ID の一覧 sample_ids.csv はコミットし、同じ200件を再現できることの確認に使う。

使い方:
    python fetch_sample.py
"""

from __future__ import annotations

import json
import random
import sys
import urllib.request

from common import DATA_DIR, HERE, write_csv

DATASET_REPO = "horshohei/japanese-offensive-language-from-court-case"
DATASET_COMMIT = "03d3b65cb5d7f8bb6732174736afdf157d2da38a"
FOLDS = 5
SEED = 20261007

# 内訳（docs/decisions.md D-09）。裁判で争われた投稿100件は、境界の例を厚くするため否認を多めに取る
QUOTA = {
    "litigated_upheld": 70,  # 裁判で権利侵害が認められた投稿
    "litigated_rejected": 30,  # 裁判で権利侵害が認められなかった投稿
    "not_litigated": 100,  # 裁判で争われていない投稿
}

CACHE_DIR = DATA_DIR / "source"


def fetch_fold(fold: int) -> dict:
    """experimentdata/test_{fold}.json を取得する。5分割の test を合わせると全件になる"""
    path = CACHE_DIR / f"test_{fold}.json"
    if not path.exists():
        url = f"https://raw.githubusercontent.com/{DATASET_REPO}/{DATASET_COMMIT}/experimentdata/test_{fold}.json"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as res:
            path.write_bytes(res.read())
    return json.loads(path.read_text(encoding="utf-8"))


def load_posts() -> list[dict]:
    posts: list[dict] = []
    seen: set[str] = set()
    for fold in range(FOLDS):
        d = fetch_fold(fold)
        rows = zip(d["caseID"], d["text"], d["context"], d["result"], d["labels"])
        for index, (case_id, text, context, result, labels) in enumerate(rows):
            text = (text or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            if case_id == "negative":
                group = "not_litigated"
            elif str(case_id).startswith("trial"):
                continue  # アノテーションの練習用。裁判例ではない
            else:
                group = "litigated_upheld" if result else "litigated_rejected"
            posts.append(
                {
                    "source_key": f"test_{fold}#{index}",
                    "source_case_id": case_id,
                    "source_group": group,
                    "source_rights": json.dumps(labels),
                    "text": text,
                    "context": "" if context in (None, "None") else str(context).strip(),
                }
            )
    return posts


def sample(posts: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    picked: list[dict] = []
    for group, n in QUOTA.items():
        pool = [p for p in posts if p["source_group"] == group]
        if len(pool) < n:
            raise SystemExit(f"{group} が {len(pool)} 件しかない（必要 {n} 件）")
        picked.extend(rng.sample(pool, n))
    # ラベル付けで元の区分が推測されないよう、順番を混ぜてから ID を振る
    rng.shuffle(picked)
    return [{"id": f"S{i:03d}", **p} for i, p in enumerate(picked, start=1)]


def main() -> int:
    posts = load_posts()
    rows = sample(posts)
    write_csv(
        DATA_DIR / "01_sample.csv",
        rows,
        ["id", "text", "context", "source_group", "source_case_id", "source_rights", "source_key"],
    )
    write_csv(HERE / "sample_ids.csv", rows, ["id", "source_key", "source_group"])
    counts = {g: sum(1 for r in rows if r["source_group"] == g) for g in QUOTA}
    print(f"全 {len(posts)} 件から {len(rows)} 件を抽出: {counts}")
    print(f"-> {DATA_DIR / '01_sample.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
