"""手順5: 全モデルの結果を1つの Excel ファイル data/06_reply_comparison.xlsx にまとめる。

シート:
    適合率・再現率・F値  モデルごとの「返信が必要」と3区分平均の適合率・再現率・F 値、正答率、ROC AUC、実行環境
    詳細指標            区分ごとの指標と 95% 信頼区間、確率の当たり具合、メールの種類ごとの正答率
    メールごと          1行1メール。本文・正解ラベル・付け直したラベルと、全モデルの判定・3つの確率・正誤
    正解ラベル          正解ラベルと、生成時の理由・付け直したラベル
    <モデル名>          モデルごとの 05_<model>_evaluation.csv と同じ内容

使い方:
    python reply_excel.py
"""

from __future__ import annotations

import math
import sys

from reply_evaluate import evaluate_all
from reply_shared import BATCHES, DATA_DIR, LABEL_JA, LABELS, POSITIVE

from export_excel import DECIMAL, PERCENT, WRAP, Sheet, write_xlsx  # apps/defamation-eval

OUT = DATA_DIR / "06_reply_comparison.xlsx"


def num(v: float, style: int):
    return None if math.isnan(v) else (v, style)


def prf_sheet(results) -> Sheet:
    sheet = Sheet("適合率・再現率・F値", [24, 10, 10, 12, 12, 12, 12, 12, 12, 10], freeze=(1, 1), autofilter=False)
    sheet.header("モデル", "実行環境", "正答率", "「返信が必要」の適合率", "「返信が必要」の再現率", "「返信が必要」の F 値",
                 "3区分平均の適合率", "3区分平均の再現率", "3区分平均の F 値", "ROC AUC")
    for model, _, s in results:
        c = s["classes"][POSITIVE]
        sheet.add(model.title, model.device, (s["accuracy"], PERCENT), (c["precision"], PERCENT), (c["recall"], PERCENT),
                  (c["f1"], DECIMAL), (s["macro_precision"], PERCENT), (s["macro_recall"], PERCENT),
                  (s["macro_f1"], DECIMAL), (s["auc"], DECIMAL))
    sheet.add()
    sheet.add("判定は最も確率の高い選択肢。3区分平均は3つの区分の値の単純平均（マクロ平均）。")
    sheet.add("実行環境は、この検証で判定を動かした計算資源。GPU は NVIDIA RTX 5060 Ti 16GB。")
    return sheet


def detailed_sheet(results) -> Sheet:
    sheet = Sheet("詳細指標", [24, 18, 10, 10, 10, 10, 10, 10, 10, 10, 10, 12, 12], freeze=(0, 1), autofilter=False)
    sheet.header("モデル", "正答率", "下限", "上限", "3区分平均の F 値", "下限", "上限", "ROC AUC", "下限", "上限",
                 "Brier スコア", "対数損失", "ラベルが一致したメールでの正答率")
    for model, _, s in results:
        sheet.add(model.title, (s["accuracy"], PERCENT), *(num(v, PERCENT) for v in s["accuracy_ci"]),
                  (s["macro_f1"], DECIMAL), *(num(v, DECIMAL) for v in s["macro_f1_ci"]),
                  num(s["auc"], DECIMAL), *(num(v, DECIMAL) for v in s["auc_ci"]),
                  (s["brier"], DECIMAL), (s["log_loss"], DECIMAL), num(s["agreed_accuracy"], PERCENT))
    sheet.add()
    sheet.header("モデル", "区分", "適合率", "下限", "上限", "再現率", "下限", "上限", "F 値", "下限", "上限",
                 "判定した件数", "正解の件数")
    for label in LABELS:
        for model, _, s in results:
            c = s["classes"][label]
            sheet.add(model.title, LABEL_JA[label], (c["precision"], PERCENT), *(num(v, PERCENT) for v in c["precision_ci"]),
                      (c["recall"], PERCENT), *(num(v, PERCENT) for v in c["recall_ci"]),
                      (c["f1"], DECIMAL), *(num(v, DECIMAL) for v in c["f1_ci"]), c["predicted"], c["support"])
    sheet.add()
    sheet.header("モデル", *BATCHES.values())
    for model, _, s in results:
        sheet.add(model.title, *(num(sum(r["correct"] for r in rs) / len(rs), PERCENT) if rs else None
                                 for rs in s["by_batch"].values()))
    sheet.add()
    sheet.add("区間は 95% 信頼区間。正答率・適合率・再現率は Wilson 法、F 値と ROC AUC は投稿のブートストラップ（1,000 回、シード固定）。")
    sheet.add("Brier スコアと対数損失は確率そのものの当たり具合で、小さいほどよい。Brier は 0 が完全、確率をいつも 1/3 ずつにすると 0.667。")
    return sheet


def per_email_sheet(results, emails, blind) -> Sheet:
    widths = [7, 70, 16, 16, 22]
    names = ["ID", "本文", "正解ラベル", "付け直したラベル", "メールの種類"]
    for model, _, _ in results:
        widths += [16, 10, 10, 10, 8]
        names += [f"{model.title}: 判定", f"{model.title}: 返信が必要な確率", f"{model.title}: 返信は不要な確率",
                  f"{model.title}: どちらとも言えない確率", f"{model.title}: 正誤"]
    sheet = Sheet("メールごと", widths, freeze=(1, 2))
    sheet.header(*names)
    by_model = [{r["id"]: r for r in rows} for _, rows, _ in results]
    for e in emails:
        cells = [e["id"], (e["text"], WRAP), LABEL_JA[e["gold_label"]], LABEL_JA.get(blind.get(e["id"], ""), ""),
                 BATCHES[e["batch"]]]
        for rows in by_model:
            r = rows[e["id"]]
            cells += [LABEL_JA.get(r["pred_label"], r["pred_label"]), *((r[f"p_{l}"], DECIMAL) for l in LABELS),
                      "○" if r["correct"] else "×"]
        sheet.add(*cells)
    return sheet


def labels_sheet(emails, blind) -> Sheet:
    sheet = Sheet("正解ラベル", [7, 70, 16, 60, 16, 22, 20])
    sheet.header("ID", "本文", "正解ラベル（生成時）", "生成時の理由", "付け直したラベル", "メールの種類", "分類")
    for e in emails:
        sheet.add(e["id"], (e["text"], WRAP), LABEL_JA[e["gold_label"]], (e["gold_reason"], WRAP),
                  LABEL_JA.get(blind.get(e["id"], ""), ""), BATCHES[e["batch"]], e["category"])
    return sheet


def model_sheet(model, rows) -> Sheet:
    sheet = Sheet(model.name, [7, 70, 16, 16, 8, 12, 12, 12, 22], freeze=(1, 2))
    sheet.header("ID", "本文", "正解ラベル", "モデルの判定", "正誤", "返信が必要な確率", "返信は不要な確率",
                 "どちらとも言えない確率", "メールの種類")
    for r in rows:
        sheet.add(r["id"], (r["text"], WRAP), LABEL_JA[r["gold"]], LABEL_JA.get(r["pred_label"], r["pred_label"]),
                  "○" if r["correct"] else "×", *((r[f"p_{l}"], DECIMAL) for l in LABELS), BATCHES[r["batch"]])
    return sheet


def main() -> int:
    results, emails, blind = evaluate_all()
    sheets = [prf_sheet(results), detailed_sheet(results), per_email_sheet(results, emails, blind), labels_sheet(emails, blind)]
    sheets += [model_sheet(model, rows) for model, rows, _ in results]
    write_xlsx(OUT, sheets)
    print(f"{len(results)} モデル: {', '.join(m.name for m, _, _ in results)}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
