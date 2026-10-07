"""手順5: Laya の判定を正解ラベルと比べ、精度を評価する。

入力:
    data/01_sample.csv        元データの区分（source_group）
    data/03_labels.csv        正解ラベル（reviewed_label があればそれ、なければ claude_label）
    data/04_laya_results.csv  Laya の確率
出力:
    data/05_evaluation.csv    1件ごとの正解・Laya の判定・確率・正誤（本文を含むのでローカルのみ）
    report.md                 集計だけの評価レポート（本文を含まないのでコミットする）

使い方:
    python evaluate.py
"""

from __future__ import annotations

import sys
from collections import Counter

from common import DATA_DIR, HERE, LABELS, read_csv, write_csv

THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
SOURCE_GROUPS = {
    "litigated_upheld": "裁判で権利侵害が認められた",
    "litigated_rejected": "裁判で権利侵害が認められなかった",
    "not_litigated": "裁判で争われていない",
}
LABEL_JA = {"defamatory": "当たる", "not_defamatory": "当たらない", "uncertain": "どちらとも言えない"}


def gold_label(row: dict) -> str:
    label = (row.get("reviewed_label") or "").strip() or row["claude_label"]
    if label not in LABELS:
        raise SystemExit(f"{row['id']} の正解ラベル {label!r} が {LABELS} のどれでもない")
    return label


def precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def confusion(pairs: list[tuple[str, str]]) -> dict[str, Counter]:
    """正解 → Laya の判定 の件数"""
    m: dict[str, Counter] = {g: Counter() for g in LABELS}
    for gold, pred in pairs:
        m[gold][pred] += 1
    return m


def per_class(pairs: list[tuple[str, str]]) -> dict[str, tuple[float, float, float, int]]:
    out = {}
    for label in LABELS:
        tp = sum(1 for g, p in pairs if g == label and p == label)
        fp = sum(1 for g, p in pairs if g != label and p == label)
        fn = sum(1 for g, p in pairs if g == label and p != label)
        out[label] = (*precision_recall_f1(tp, fp, fn), tp + fn)
    return out


def threshold_table(rows: list[dict]) -> list[tuple[float, int, float, float, float]]:
    """p_defamatory が閾値以上なら「当たる」とみなしたときの、「当たる」の検出精度"""
    table = []
    for t in THRESHOLDS:
        tp = sum(1 for r in rows if r["gold"] == "defamatory" and r["p_defamatory"] >= t)
        fp = sum(1 for r in rows if r["gold"] != "defamatory" and r["p_defamatory"] >= t)
        fn = sum(1 for r in rows if r["gold"] == "defamatory" and r["p_defamatory"] < t)
        table.append((t, tp + fp, *precision_recall_f1(tp, fp, fn)))
    return table


def roc_auc(rows: list[dict]) -> float:
    """「当たる」とそれ以外を p_defamatory で並べたときの AUC。0.5 で当てずっぽう、1.0 で完全に分離"""
    pos = [r["p_defamatory"] for r in rows if r["gold"] == "defamatory"]
    neg = [r["p_defamatory"] for r in rows if r["gold"] != "defamatory"]
    if not pos or not neg:
        return float("nan")
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def build_rows() -> list[dict]:
    sample = {r["id"]: r for r in read_csv(DATA_DIR / "01_sample.csv")}
    labels = {r["id"]: r for r in read_csv(DATA_DIR / "03_labels.csv")}
    rows = []
    for r in read_csv(DATA_DIR / "04_laya_results.csv"):
        gold = gold_label(labels[r["id"]])
        rows.append(
            {
                "id": r["id"],
                "text": r["text"],
                "source_group": sample[r["id"]]["source_group"],
                "gold": gold,
                "laya_label": r["laya_label"],
                "correct": int(gold == r["laya_label"]),
                **{f"p_{label}": float(r[f"p_{label}"]) for label in LABELS},
            }
        )
    return rows


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_report(rows: list[dict]) -> str:
    n = len(rows)
    pairs = [(r["gold"], r["laya_label"]) for r in rows]
    gold_counts = Counter(r["gold"] for r in rows)
    pred_counts = Counter(r["laya_label"] for r in rows)
    accuracy = sum(r["correct"] for r in rows) / n
    majority = max(gold_counts.values()) / n
    pc = per_class(pairs)
    macro_f1 = sum(v[2] for v in pc.values()) / len(LABELS)
    reviewed = sum(1 for r in read_csv(DATA_DIR / "03_labels.csv") if (r.get("reviewed_label") or "").strip())

    lines = [
        "# 誹謗中傷判定の評価レポート",
        "",
        "`evaluate.py` が出力する。本文は含めない（1件ごとの結果はローカルの `data/05_evaluation.csv`）。",
        "判定基準と手順は [docs/defamation-eval.md](../../docs/defamation-eval.md)。",
        "",
        "## 条件",
        "",
        f"- 件数: {n}（正解ラベルのうち人が確認して直したもの: {reviewed} 件）",
        "- 正解ラベル: " + "、".join(f"{LABEL_JA[l]} {gold_counts[l]}" for l in LABELS),
        "- Laya の判定（最も確率の高い選択肢）: " + "、".join(f"{LABEL_JA[l]} {pred_counts[l]}" for l in LABELS),
        "",
        "## 3値の正答率",
        "",
        "| 指標 | 値 |",
        "|---|---|",
        f"| 正答率 | {pct(accuracy)} |",
        f"| 参考: 常に多数派（{LABEL_JA[gold_counts.most_common(1)[0][0]]}）と答えた場合 | {pct(majority)} |",
        f"| マクロ F1 | {macro_f1:.3f} |",
        "",
        "| 区分 | 適合率 | 再現率 | F1 | 正解の件数 |",
        "|---|---|---|---|---|",
    ]
    for label in LABELS:
        p, r, f, support = pc[label]
        lines.append(f"| {LABEL_JA[label]} | {pct(p)} | {pct(r)} | {f:.3f} | {support} |")

    m = confusion(pairs)
    lines += [
        "",
        "### 混同行列（行: 正解、列: Laya の判定）",
        "",
        "| 正解 \\ Laya | " + " | ".join(LABEL_JA[l] for l in LABELS) + " |",
        "|---|" + "---|" * len(LABELS),
    ]
    for g in LABELS:
        lines.append(f"| {LABEL_JA[g]} | " + " | ".join(str(m[g][p]) for p in LABELS) + " |")

    lines += [
        "",
        "## 正解ごとの確率の平均",
        "",
        "Laya が区分を見分けられていれば、対角線（正解と同じ列）の値が大きくなる。",
        "",
        "| 正解 | 件数 | " + " | ".join(f"p_{l}" for l in LABELS) + " |",
        "|---|---|" + "---|" * len(LABELS),
    ]
    for g in LABELS:
        group = [r for r in rows if r["gold"] == g]
        means = [sum(r[f"p_{l}"] for r in group) / len(group) if group else 0.0 for l in LABELS]
        lines.append(f"| {LABEL_JA[g]} | {len(group)} | " + " | ".join(f"{v:.3f}" for v in means) + " |")

    lines += [
        "",
        "## 「当たる」を閾値で判定した場合",
        "",
        "`p_defamatory` が閾値以上なら「当たる」、未満なら「当たらない・どちらとも言えない」とみなしたときの、「当たる」の検出精度。",
        "",
        f"`p_defamatory` の ROC AUC（「当たる」とそれ以外の分離。0.5 で当てずっぽう、1.0 で完全）: {roc_auc(rows):.3f}",
        "",
        "| 閾値 | 「当たる」と判定した件数 | 適合率 | 再現率 | F1 |",
        "|---|---|---|---|---|",
    ]
    for t, flagged, p, r, f in threshold_table(rows):
        lines.append(f"| {t:.1f} | {flagged} | {pct(p)} | {pct(r)} | {f:.3f} |")

    lines += [
        "",
        "## 元データの区分ごと",
        "",
        "元データの区分は法的な判断と「裁判で争われたか」で、この検証の正解（プラットフォーム基準）とは別物。参考として示す。",
        "",
        "| 元データの区分 | 件数 | 正解が「当たる」 | p_defamatory の平均 | Laya が「当たる」 |",
        "|---|---|---|---|---|",
    ]
    for key, name in SOURCE_GROUPS.items():
        group = [r for r in rows if r["source_group"] == key]
        if not group:
            continue
        gold_d = sum(1 for r in group if r["gold"] == "defamatory")
        mean_p = sum(r["p_defamatory"] for r in group) / len(group)
        laya_d = sum(1 for r in group if r["laya_label"] == "defamatory")
        lines.append(f"| {name} | {len(group)} | {gold_d} | {mean_p:.3f} | {laya_d} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = build_rows()
    out = DATA_DIR / "05_evaluation.csv"
    write_csv(
        out,
        rows,
        ["id", "text", "gold", "laya_label", "correct", *(f"p_{l}" for l in LABELS), "source_group"],
    )
    report = HERE / "report.md"
    report.write_text(render_report(rows), encoding="utf-8")
    print(f"-> {out}")
    print(f"-> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
