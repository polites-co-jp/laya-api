"""手順4: 各モデルの判定を正解ラベルと比べ、精度を評価する。

入力:
    data/01_emails.csv           正解ラベル（生成時のラベル）とメールの種類
    data/02_blind_labels.tsv     正解を伏せて付け直したラベル（あれば、ラベルの一致率を出す）
    data/04_<model>_results.csv  各モデルの確率
出力:
    data/05_<model>_evaluation.csv  1件ごとの正解・モデルの判定・確率・正誤
    report.md                       全モデルの比較と詳細

使い方:
    python reply_evaluate.py
"""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter

from reply_shared import BATCHES, DATA_DIR, HERE, LABEL_JA, LABELS, MODELS, POSITIVE, read_csv, results_path, write_csv

from evaluate import bootstrap_interval, precision_recall_f1, wilson_interval  # apps/defamation-eval

THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
EVALUATION_HEADERS = {
    "id": "ID", "text": "本文", "gold": "正解ラベル", "pred_label": "モデルの判定", "correct": "正誤（1=一致）",
    "p_reply_needed": "返信が必要な確率", "p_no_reply_needed": "返信は不要な確率", "p_uncertain": "どちらとも言えない確率",
    "batch": "メールの種類", "category": "分類", "blind_label": "付け直したラベル",
}


def load_blind() -> dict[str, str]:
    path = DATA_DIR / "02_blind_labels.tsv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["id"]: r["label"] for r in csv.DictReader(f, delimiter="\t")}


def build_rows(model: str, emails: dict[str, dict], blind: dict[str, str]) -> list[dict]:
    rows = []
    for r in read_csv(results_path(model)):
        e = emails[r["id"]]
        rows.append({
            "id": r["id"], "text": r["text"], "gold": e["gold_label"], "pred_label": r["pred_label"],
            "correct": int(e["gold_label"] == r["pred_label"]),
            **{f"p_{l}": float(r[f"p_{l}"]) for l in LABELS},
            "batch": e["batch"], "category": e["category"], "blind_label": blind.get(r["id"], ""),
            "served_model": r["served_model"],
        })
    return rows


def per_class(pairs: list[tuple[str, str]]) -> dict[str, tuple[float, float, float, int, int]]:
    """区分ごとの (適合率, 再現率, F 値, 正解の件数, 判定した件数)"""
    out = {}
    for label in LABELS:
        tp = sum(1 for g, p in pairs if g == label and p == label)
        fp = sum(1 for g, p in pairs if g != label and p == label)
        fn = sum(1 for g, p in pairs if g == label and p != label)
        out[label] = (*precision_recall_f1(tp, fp, fn), tp + fn, tp + fp)
    return out


def pairs_of(rows: list[dict]) -> list[tuple[str, str]]:
    return [(r["gold"], r["pred_label"]) for r in rows]


def macro(rows: list[dict]) -> tuple[float, float, float]:
    pc = per_class(pairs_of(rows))
    return tuple(sum(v[i] for v in pc.values()) / len(LABELS) for i in range(3))


def macro_f1(rows: list[dict]) -> float:
    return macro(rows)[2]


def roc_auc(rows: list[dict]) -> float:
    """POSITIVE とそれ以外を p_POSITIVE で並べたときの AUC"""
    pos = [r[f"p_{POSITIVE}"] for r in rows if r["gold"] == POSITIVE]
    neg = [r[f"p_{POSITIVE}"] for r in rows if r["gold"] != POSITIVE]
    if not pos or not neg:
        return float("nan")
    wins = sum(1.0 if p > q else 0.5 if p == q else 0.0 for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def brier_score(rows: list[dict]) -> float:
    return sum(sum((r[f"p_{l}"] - (r["gold"] == l)) ** 2 for l in LABELS) for r in rows) / len(rows)


def log_loss(rows: list[dict], eps: float = 1e-6) -> float:
    return -sum(math.log(min(max(r[f"p_{r['gold']}"], eps), 1.0)) for r in rows) / len(rows)


def threshold_table(rows: list[dict]) -> list[tuple[float, int, float, float, float]]:
    table = []
    for t in THRESHOLDS:
        tp = sum(1 for r in rows if r["gold"] == POSITIVE and r[f"p_{POSITIVE}"] >= t)
        fp = sum(1 for r in rows if r["gold"] != POSITIVE and r[f"p_{POSITIVE}"] >= t)
        fn = sum(1 for r in rows if r["gold"] == POSITIVE and r[f"p_{POSITIVE}"] < t)
        table.append((t, tp + fp, *precision_recall_f1(tp, fp, fn)))
    return table


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(ca[l] * cb[l] for l in LABELS) / (n * n)
    return (observed - expected) / (1 - expected) if expected < 1 else float("nan")


def stats(rows: list[dict]) -> dict:
    """1モデル分の指標。区間は 95% 信頼区間（割合は Wilson 法、F 値と AUC はブートストラップ）"""
    pc = per_class(pairs_of(rows))
    k = sum(r["correct"] for r in rows)
    classes = {}
    for label in LABELS:
        p, r, f, support, predicted = pc[label]
        tp = round(r * support)
        classes[label] = {
            "precision": p, "precision_ci": wilson_interval(tp, predicted),
            "recall": r, "recall_ci": wilson_interval(tp, support),
            "f1": f, "f1_ci": bootstrap_interval(rows, lambda rs, l=label: per_class(pairs_of(rs))[l][2]),
            "support": support, "predicted": predicted,
        }
    mp, mr, mf = macro(rows)
    agreed = [r for r in rows if r["blind_label"] and r["blind_label"] == r["gold"]]
    return {
        "n": len(rows), "accuracy": k / len(rows), "accuracy_ci": wilson_interval(k, len(rows)),
        "macro_precision": mp, "macro_recall": mr, "macro_f1": mf,
        "macro_f1_ci": bootstrap_interval(rows, macro_f1),
        "auc": roc_auc(rows), "auc_ci": bootstrap_interval(rows, roc_auc),
        "brier": brier_score(rows), "log_loss": log_loss(rows),
        "agreed_n": len(agreed),
        "agreed_accuracy": sum(r["correct"] for r in agreed) / len(agreed) if agreed else float("nan"),
        "best_threshold": max(threshold_table(rows), key=lambda t: t[4]),
        "classes": classes,
        "by_batch": {b: [r for r in rows if r["batch"] == b] for b in BATCHES},
    }


def pct(x: float) -> str:
    return "—" if math.isnan(x) else f"{x * 100:.1f}%"


def ci(c: tuple[float, float], percent: bool = True) -> str:
    lo, hi = c
    if math.isnan(lo):
        return "—"
    return f"{pct(lo)}〜{pct(hi)}" if percent else f"{lo:.3f}〜{hi:.3f}"


def render_report(results: list[tuple], emails: list[dict], blind: dict[str, str]) -> str:
    gold_counts = Counter(e["gold_label"] for e in emails)
    lines = [
        "# メール返信要否の判定のモデル比較",
        "",
        "`reply_evaluate.py` が出力する。判定基準と手順は [docs/reply-eval.md](../../docs/reply-eval.md)。",
        f"どのモデルにも同じ {len(emails)} 件・同じ正解ラベル・同じ質問（[reply_question.json](reply_question.json)）を使った。",
        "正解ラベル: " + "、".join(f"{LABEL_JA[l]} {gold_counts[l]}" for l in LABELS) + "。",
    ]

    if blind:
        pairs = [(e["gold_label"], blind[e["id"]]) for e in emails if e["id"] in blind]
        agree = sum(1 for a, b in pairs if a == b)
        lines += [
            "",
            "## 正解ラベルの揺れ",
            "",
            "生成時のラベル（評価の正解）と、生成に関わっていない別のエージェントが正解を伏せて本文だけから付け直したラベルの一致。",
            "",
            f"- 一致率: {pct(agree / len(pairs))}（{agree}/{len(pairs)} 件、95% 区間 {ci(wilson_interval(agree, len(pairs)))}）",
            f"- Cohen の κ: {cohen_kappa(pairs):.3f}（偶然の一致を除いた一致度。0.6〜0.8 でかなり一致、0.8 以上でほぼ一致）",
            "",
            "| 生成時 \\ 付け直し | " + " | ".join(LABEL_JA[l] for l in LABELS) + " |",
            "|---|" + "---|" * len(LABELS),
        ]
        m = Counter(pairs)
        for g in LABELS:
            lines.append(f"| {LABEL_JA[g]} | " + " | ".join(str(m[(g, b)]) for b in LABELS) + " |")
        lines += ["", "モデルの正答率がこの一致率を大きく超えることは期待しにくい（正解そのものに、この程度の揺れがある）。"]

    lines += [
        "",
        "## 適合率・再現率・F 値と実行環境",
        "",
        "| モデル | 実行環境 | 正答率 | 「返信が必要」の適合率 | 「返信が必要」の再現率 | 「返信が必要」の F 値 "
        "| 3区分平均の適合率 | 3区分平均の再現率 | 3区分平均の F 値 | ROC AUC |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for model, _, s in results:
        c = s["classes"][POSITIVE]
        lines.append(
            f"| {model.title} | {model.device} | {pct(s['accuracy'])} | {pct(c['precision'])} | {pct(c['recall'])} "
            f"| {c['f1']:.3f} | {pct(s['macro_precision'])} | {pct(s['macro_recall'])} | {s['macro_f1']:.3f} | {s['auc']:.3f} |"
        )
    lines += [
        "",
        "- 判定は最も確率の高い選択肢。3区分平均は3つの区分の値の単純平均（マクロ平均）。",
        "- ROC AUC は「返信が必要な確率」だけで「返信が必要」とそれ以外を並べたときの分離（0.5 で当てずっぽう、1.0 で完全）。",
        "- 実行環境は、この検証で判定を動かした計算資源。GPU は NVIDIA RTX 5060 Ti 16GB。",
        "",
        "## 詳細指標（95% 信頼区間つき）",
        "",
        "| モデル | 正答率 | 正答率の区間 | 3区分平均の F 値の区間 | ROC AUC の区間 | Brier スコア | 対数損失 | ラベルが一致した投稿での正答率 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, _, s in results:
        lines.append(
            f"| {model.title} | {pct(s['accuracy'])} | {ci(s['accuracy_ci'])} | {ci(s['macro_f1_ci'], False)} "
            f"| {ci(s['auc_ci'], False)} | {s['brier']:.3f} | {s['log_loss']:.3f} "
            f"| {pct(s['agreed_accuracy'])}（{s['agreed_n']} 件） |"
        )
    lines += [
        "",
        "- 正答率・適合率・再現率の区間は Wilson 法、F 値と ROC AUC の区間は投稿のブートストラップ（1,000 回、シード固定）。",
        "- Brier スコアと対数損失は確率そのものの当たり具合で、小さいほどよい。Brier は 0 が完全、確率をいつも 1/3 ずつにすると 0.667。",
        "- 「ラベルが一致した投稿」は、生成時と付け直しのラベルが同じだったメール。正解の揺れが少ない部分での正答率。",
    ]
    for label in LABELS:
        lines += [
            "",
            f"### 「{LABEL_JA[label]}」",
            "",
            "| モデル | 適合率 | 適合率の区間 | 再現率 | 再現率の区間 | F 値 | F 値の区間 | 判定した件数 | 正解の件数 |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for model, _, s in results:
            c = s["classes"][label]
            lines.append(
                f"| {model.title} | {pct(c['precision'])} | {ci(c['precision_ci'])} | {pct(c['recall'])} "
                f"| {ci(c['recall_ci'])} | {c['f1']:.3f} | {ci(c['f1_ci'], False)} | {c['predicted']} | {c['support']} |"
            )

    lines += [
        "",
        "## メールの種類ごとの正答率",
        "",
        "| モデル | " + " | ".join(f"{name}（{sum(1 for e in emails if e['batch'] == b)}）" for b, name in BATCHES.items()) + " |",
        "|---|" + "---|" * len(BATCHES),
    ]
    for model, _, s in results:
        cells = [pct(sum(r["correct"] for r in rs) / len(rs)) if rs else "—" for rs in s["by_batch"].values()]
        lines.append(f"| {model.title} | " + " | ".join(cells) + " |")

    lines += ["", "## 混同行列（行: 正解、列: モデルの判定）"]
    for model, rows, _ in results:
        m = Counter(pairs_of(rows))
        lines += ["", f"### {model.title}", "", "| 正解 \\ 判定 | " + " | ".join(LABEL_JA[l] for l in LABELS) + " |",
                  "|---|" + "---|" * len(LABELS)]
        for g in LABELS:
            lines.append(f"| {LABEL_JA[g]} | " + " | ".join(str(m[(g, p)]) for p in LABELS) + " |")

    lines += [
        "",
        "## 「返信が必要」を閾値で判定した場合",
        "",
        "「返信が必要な確率」が閾値以上なら「返信が必要」とみなしたときの、最もよい F 値とその閾値（0.1〜0.9 の 0.1 刻み）。",
        "",
        "| モデル | 最良の閾値 | 判定した件数 | 適合率 | 再現率 | F 値 |",
        "|---|---|---|---|---|---|",
    ]
    for model, _, s in results:
        t, flagged, p, r, f = s["best_threshold"]
        lines.append(f"| {model.title} | {t:.1f} | {flagged} | {pct(p)} | {pct(r)} | {f:.3f} |")

    lines += ["", "## モデルの補足", "", "| モデル | 補足 | 応答のモデル名 |", "|---|---|---|"]
    for model, rows, _ in results:
        served = "、".join(sorted({r["served_model"] for r in rows if r["served_model"]})) or "—"
        lines.append(f"| {model.title} | {model.note} | {served} |")
    return "\n".join(lines) + "\n"


def evaluate_all() -> tuple[list[tuple], list[dict], dict[str, str]]:
    emails = read_csv(DATA_DIR / "01_emails.csv")
    by_id = {e["id"]: e for e in emails}
    blind = load_blind()
    results = []
    for name, model in MODELS.items():
        if not results_path(name).exists():
            continue
        rows = build_rows(name, by_id, blind)
        if [r["id"] for r in rows] != [e["id"] for e in emails]:
            raise SystemExit(f"{name} の判定結果のメールが 01_emails.csv とそろっていない")
        results.append((model, rows, stats(rows)))
    if not results:
        raise SystemExit("手順3の結果（data/04_<model>_results.csv）がない。先に reply_classify.py を実行する")
    return results, emails, blind


def main() -> int:
    results, emails, blind = evaluate_all()
    for model, rows, _ in results:
        out = DATA_DIR / f"05_{model.name}_evaluation.csv"
        write_csv(out, rows, list(EVALUATION_HEADERS), EVALUATION_HEADERS)
        print(f"-> {out}")
    report = HERE / "report.md"
    report.write_text(render_report(results, emails, blind), encoding="utf-8")
    print(f"-> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
