"""手順5: 各モデルの判定を正解ラベルと比べ、精度を評価する。

入力:
    data/01_sample.csv           元データの区分（source_group）
    data/03_labels.csv           正解ラベル（reviewed_label があればそれ、なければ claude_label）
    data/04_<model>_results.csv  各モデルの確率（手順4で判定したモデルの分だけ）
出力:
    data/05_<model>_evaluation.csv  1件ごとの正解・モデルの判定・確率・正誤（本文を含むのでローカルのみ）
    reports/<model>.md              モデルごとの評価レポート（本文を含まないのでコミットする）
    report.md                       モデルを並べた比較表（同上）

使い方:
    python evaluate.py [--model laya ...]   （既定は手順4の結果があるモデルすべて）
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter

from common import DATA_DIR, HERE, LABELS, read_csv, results_path, write_csv
from models import MODELS, Model

THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
SOURCE_GROUPS = {
    "litigated_upheld": "裁判で権利侵害が認められた",
    "litigated_rejected": "裁判で権利侵害が認められなかった",
    "not_litigated": "裁判で争われていない",
}
LABEL_JA = {"defamatory": "当たる", "not_defamatory": "当たらない", "uncertain": "どちらとも言えない"}
# 05_evaluation.csv は人が読むファイルなので、見出しを日本語にする
EVALUATION_HEADERS = {
    "id": "ID",
    "text": "本文",
    "gold": "正解ラベル",
    "pred_label": "モデルの判定",
    "correct": "正誤（1=一致）",
    "p_defamatory": "誹謗中傷にあたる確率",
    "p_not_defamatory": "誹謗中傷にあたらない確率",
    "p_uncertain": "どちらとも言えない確率",
    "source_group": "元データの区分",
}


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
    """正解 → モデルの判定 の件数"""
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


BOOTSTRAP_ROUNDS = 1000
BOOTSTRAP_SEED = 20261029


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """割合 k/n の 95% 信頼区間（Wilson 法）"""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return center - half, center + half


def bootstrap_interval(rows: list[dict], metric) -> tuple[float, float]:
    """投稿を復元抽出して metric を計算し直した 95% 信頼区間（パーセンタイル法）。シード固定で再現できる"""
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for _ in range(BOOTSTRAP_ROUNDS):
        v = metric([rows[rng.randrange(len(rows))] for _ in rows])
        if not math.isnan(v):
            values.append(v)
    if not values:
        return float("nan"), float("nan")
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def brier_score(rows: list[dict]) -> float:
    """3つの確率と正解（one-hot）の二乗誤差の平均。0 が最良、2 が最悪。判定ではなく確率そのものの当たり具合"""
    return sum(sum((r[f"p_{l}"] - (r["gold"] == l)) ** 2 for l in LABELS) for r in rows) / len(rows)


def log_loss(rows: list[dict], eps: float = 1e-6) -> float:
    """正解の選択肢に付けた確率の対数の平均を負にしたもの。0 が最良で、自信を持って外すほど大きくなる"""
    return -sum(math.log(min(max(r[f"p_{r['gold']}"], eps), 1.0)) for r in rows) / len(rows)


def macro_f1(rows: list[dict]) -> float:
    pc = per_class([(r["gold"], r["pred_label"]) for r in rows])
    return sum(v[2] for v in pc.values()) / len(LABELS)


def class_f1(label: str):
    return lambda rows: per_class([(r["gold"], r["pred_label"]) for r in rows])[label][2]


def detailed_stats(rows: list[dict]) -> dict:
    """詳細指標の点推定と 95% 信頼区間"""
    pairs = [(r["gold"], r["pred_label"]) for r in rows]
    pc = per_class(pairs)
    predicted = Counter(p for _, p in pairs)
    correct = sum(1 for g, p in pairs if g == p)
    classes = {}
    for label in LABELS:
        p, r, f, support = pc[label]
        tp = sum(1 for g, q in pairs if g == label and q == label)
        classes[label] = {
            "precision": p, "precision_ci": wilson_interval(tp, predicted[label]),
            "recall": r, "recall_ci": wilson_interval(tp, support),
            "f1": f, "f1_ci": bootstrap_interval(rows, class_f1(label)),
            "support": support, "predicted": predicted[label],
        }
    return {
        "accuracy": correct / len(rows), "accuracy_ci": wilson_interval(correct, len(rows)),
        "macro_f1": macro_f1(rows), "macro_f1_ci": bootstrap_interval(rows, macro_f1),
        "auc": roc_auc(rows), "auc_ci": bootstrap_interval(rows, roc_auc),
        "brier": brier_score(rows), "log_loss": log_loss(rows),
        "classes": classes,
    }


def build_rows(model: str) -> list[dict]:
    sample = {r["id"]: r for r in read_csv(DATA_DIR / "01_sample.csv")}
    labels = {r["id"]: r for r in read_csv(DATA_DIR / "03_labels.csv")}
    rows = []
    for r in read_csv(results_path(model)):
        gold = gold_label(labels[r["id"]])
        rows.append(
            {
                "id": r["id"],
                "text": r["text"],
                "source_group": sample[r["id"]]["source_group"],
                "gold": gold,
                "pred_label": r["pred_label"],
                "served_model": r["served_model"],
                "correct": int(gold == r["pred_label"]),
                **{f"p_{label}": float(r[f"p_{label}"]) for label in LABELS},
            }
        )
    return rows


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_report(model: Model, rows: list[dict]) -> str:
    n = len(rows)
    pairs = [(r["gold"], r["pred_label"]) for r in rows]
    gold_counts = Counter(r["gold"] for r in rows)
    pred_counts = Counter(r["pred_label"] for r in rows)
    accuracy = sum(r["correct"] for r in rows) / n
    majority = max(gold_counts.values()) / n
    pc = per_class(pairs)
    macro_f1 = sum(v[2] for v in pc.values()) / len(LABELS)
    reviewed = sum(1 for r in read_csv(DATA_DIR / "03_labels.csv") if (r.get("reviewed_label") or "").strip())

    lines = [
        f"# 誹謗中傷判定の評価レポート: {model.title}",
        "",
        f"`evaluate.py` が出力する。本文は含めない（1件ごとの結果はローカルの `data/05_{model.name}_evaluation.csv`）。",
        "判定基準と手順は [docs/defamation-eval.md](../../../docs/defamation-eval.md)、モデルの比較は [report.md](../report.md)。",
        "",
        "## 条件",
        "",
        f"- モデル: {model.title}（{model.note}）",
        "- 応答のモデル名: " + "、".join(sorted({r["served_model"] for r in rows if r["served_model"]}) or ["（なし）"]),
        f"- 件数: {n}（正解ラベルのうち人が確認して直したもの: {reviewed} 件）",
        "- 正解ラベル: " + "、".join(f"{LABEL_JA[l]} {gold_counts[l]}" for l in LABELS),
        "- モデルの判定（最も確率の高い選択肢）: " + "、".join(f"{LABEL_JA[l]} {pred_counts[l]}" for l in LABELS),
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
        "### 混同行列（行: 正解、列: モデルの判定）",
        "",
        "| 正解 \\ 判定 | " + " | ".join(LABEL_JA[l] for l in LABELS) + " |",
        "|---|" + "---|" * len(LABELS),
    ]
    for g in LABELS:
        lines.append(f"| {LABEL_JA[g]} | " + " | ".join(str(m[g][p]) for p in LABELS) + " |")

    lines += [
        "",
        "## 正解ごとの確率の平均",
        "",
        "モデルが区分を見分けられていれば、対角線（正解と同じ列）の値が大きくなる。",
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
        "| 元データの区分 | 件数 | 正解が「当たる」 | p_defamatory の平均 | モデルが「当たる」 |",
        "|---|---|---|---|---|",
    ]
    for key, name in SOURCE_GROUPS.items():
        group = [r for r in rows if r["source_group"] == key]
        if not group:
            continue
        gold_d = sum(1 for r in group if r["gold"] == "defamatory")
        mean_p = sum(r["p_defamatory"] for r in group) / len(group)
        pred_d = sum(1 for r in group if r["pred_label"] == "defamatory")
        lines.append(f"| {name} | {len(group)} | {gold_d} | {mean_p:.3f} | {pred_d} |")
    return "\n".join(lines) + "\n"


def summary(rows: list[dict]) -> dict:
    """比較表の1行分の指標"""
    pairs = [(r["gold"], r["pred_label"]) for r in rows]
    pc = per_class(pairs)
    best = max(threshold_table(rows), key=lambda t: t[4])
    return {
        "accuracy": sum(r["correct"] for r in rows) / len(rows),
        "macro_f1": sum(v[2] for v in pc.values()) / len(LABELS),
        "defamatory": pc["defamatory"],
        "auc": roc_auc(rows),
        "best_threshold": best,
    }


def render_comparison(results: list[tuple[Model, list[dict]]]) -> str:
    lines = [
        "# 誹謗中傷判定のモデル比較",
        "",
        "`evaluate.py` が出力する。本文は含めない。判定基準と手順は [docs/defamation-eval.md](../../docs/defamation-eval.md)。",
        "どのモデルにも同じ200件・同じ正解ラベル・同じ質問（[laya_question.json](laya_question.json)）を使った。",
        "",
        "| モデル | 正答率 | マクロ F1 | 「当たる」の適合率 | 「当たる」の再現率 | ROC AUC | 閾値で最良の F1（閾値） | 詳細 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, rows in results:
        s = summary(rows)
        p, r, _, _ = s["defamatory"]
        t, _, _, _, f = s["best_threshold"]
        lines.append(
            f"| {model.title} | {pct(s['accuracy'])} | {s['macro_f1']:.3f} | {pct(p)} | {pct(r)} | {s['auc']:.3f} "
            f"| {f:.3f}（{t:.1f}） | [{model.name}](reports/{model.name}.md) |"
        )
    lines += [
        "",
        "- 正答率・マクロ F1・適合率・再現率は、最も確率の高い選択肢をモデルの判定としたもの（3値）。",
        "- ROC AUC と閾値の列は `p_defamatory` だけを使う（「当たる」とそれ以外の分離）。閾値は 0.1〜0.7 の 0.1 刻み。",
    ]
    lines += render_prf(results)
    lines += [
        "",
        "## モデルの補足",
        "",
        "| モデル | 補足 | 応答のモデル名 |",
        "|---|---|---|",
    ]
    for model, rows in results:
        served = "、".join(sorted({r["served_model"] for r in rows if r["served_model"]})) or "—"
        lines.append(f"| {model.title} | {model.note} | {served} |")
    lines += render_detailed(results)
    return "\n".join(lines) + "\n"


def macro_prf(rows: list[dict]) -> tuple[float, float, float]:
    """3区分の適合率・再現率・F 値をそれぞれ単純平均したもの"""
    pc = per_class([(r["gold"], r["pred_label"]) for r in rows])
    return tuple(sum(v[i] for v in pc.values()) / len(LABELS) for i in range(3))


def render_prf(results: list[tuple[Model, list[dict]]]) -> list[str]:
    lines = [
        "",
        "## 適合率・再現率・F 値と実行環境",
        "",
        "| モデル | 実行環境 | 「当たる」の適合率 | 「当たる」の再現率 | 「当たる」の F 値 | 3区分平均の適合率 | 3区分平均の再現率 | 3区分平均の F 値 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, rows in results:
        p, r, f, _ = per_class([(x["gold"], x["pred_label"]) for x in rows])["defamatory"]
        mp, mr, mf = macro_prf(rows)
        lines.append(f"| {model.title} | {model.device} | {pct(p)} | {pct(r)} | {f:.3f} | {pct(mp)} | {pct(mr)} | {mf:.3f} |")
    lines += [
        "",
        "- 実行環境は、この検証で判定を動かした計算資源。GPU は NVIDIA RTX 5060 Ti 16GB。",
        "- 3区分平均は「当たる」「当たらない」「どちらとも言えない」の値の単純平均（マクロ平均）。3区分平均の F 値はマクロ F1 と同じ。",
    ]
    return lines


def fmt_ci(ci: tuple[float, float], percent: bool = True) -> str:
    lo, hi = ci
    if math.isnan(lo):
        return "—"
    return f"{pct(lo)}〜{pct(hi)}" if percent else f"{lo:.3f}〜{hi:.3f}"


def render_detailed(results: list[tuple[Model, list[dict]]]) -> list[str]:
    stats = [(model, detailed_stats(rows)) for model, rows in results]
    lines = [
        "",
        "## 詳細指標（95% 信頼区間つき）",
        "",
        "200件は統計としては多くないので、どの指標にも誤差の幅がある。区間が重なるモデル同士の差は、偶然の範囲かもしれない。",
        "正答率・適合率・再現率の区間は Wilson 法、F1 と ROC AUC の区間は投稿のブートストラップ（1,000 回、シード固定）。",
        "",
        "### 全体",
        "",
        "| モデル | 正答率 | 正答率の区間 | マクロ F1 | マクロ F1 の区間 | ROC AUC | ROC AUC の区間 | Brier スコア | 対数損失 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for model, s in stats:
        lines.append(
            f"| {model.title} | {pct(s['accuracy'])} | {fmt_ci(s['accuracy_ci'])} | {s['macro_f1']:.3f} "
            f"| {fmt_ci(s['macro_f1_ci'], False)} | {s['auc']:.3f} | {fmt_ci(s['auc_ci'], False)} "
            f"| {s['brier']:.3f} | {s['log_loss']:.3f} |"
        )
    lines += [
        "",
        "- Brier スコアと対数損失は、判定ではなく確率そのものの当たり具合。どちらも小さいほどよい。"
        "Brier スコアは 0 が完全で、3つの確率をいつも 1/3 ずつにすると 0.667。",
        "- 有害コメント分類器は「どちらとも言えない」の確率が常に 0 なので、正解が「どちらとも言えない」の投稿で対数損失が大きくなる（D-11）。",
    ]
    for label in LABELS:
        lines += [
            "",
            f"### 「{LABEL_JA[label]}」",
            "",
            "| モデル | 適合率 | 適合率の区間 | 再現率 | 再現率の区間 | F1 | F1 の区間 | 判定した件数 | 正解の件数 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for model, s in stats:
            c = s["classes"][label]
            lines.append(
                f"| {model.title} | {pct(c['precision'])} | {fmt_ci(c['precision_ci'])} | {pct(c['recall'])} "
                f"| {fmt_ci(c['recall_ci'])} | {c['f1']:.3f} | {fmt_ci(c['f1_ci'], False)} | {c['predicted']} | {c['support']} |"
            )
    lines += [
        "",
        "- 適合率: モデルがその区分と判定したもののうち、正解と一致した割合。判定した件数が 0 のときは 0% とし、区間は出さない。",
        "- 再現率: 正解がその区分の投稿のうち、モデルが同じ区分と判定できた割合。",
    ]
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", nargs="+", choices=list(MODELS), help="既定は手順4の結果があるモデルすべて")
    args = ap.parse_args()
    names = args.model or [name for name in MODELS if results_path(name).exists()]
    if not names:
        raise SystemExit("手順4の結果（data/04_<model>_results.csv）がない。先に classify.py を実行する")

    results = []
    (HERE / "reports").mkdir(exist_ok=True)
    for name in names:
        model = MODELS[name]
        rows = build_rows(name)
        out = DATA_DIR / f"05_{name}_evaluation.csv"
        write_csv(
            out,
            rows,
            ["id", "text", "gold", "pred_label", "correct", *(f"p_{l}" for l in LABELS), "source_group"],
            EVALUATION_HEADERS,
        )
        report = HERE / "reports" / f"{name}.md"
        report.write_text(render_report(model, rows), encoding="utf-8")
        print(f"-> {out}")
        print(f"-> {report}")
        results.append((model, rows))

    comparison = HERE / "report.md"
    comparison.write_text(render_comparison(results), encoding="utf-8")
    print(f"-> {comparison}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
