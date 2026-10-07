"""各手順のスクリプトで共通に使う定数と CSV の読み書き。"""

from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
# CC BY-NC の本文を含むため git 管理外（docs/decisions.md D-09）
DATA_DIR = HERE / "data"

# laya_question.json の選択肢と同じ並び
LABELS = ("defamatory", "not_defamatory", "uncertain")


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Excel で文字化けしないよう BOM 付き UTF-8 にする
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
