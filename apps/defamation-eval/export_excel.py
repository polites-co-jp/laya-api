"""手順6: 全モデルの判定結果を1つの Excel ファイル data/06_model_comparison.xlsx にまとめる。

入力は evaluate.py と同じ（data/01_sample.csv、data/03_labels.csv、data/04_<model>_results.csv）。
手順4の結果があるモデルをすべて載せる。本文を含むので data/（git 管理外）に書く。

シート:
    比較              モデルごとの指標（report.md の比較表と同じ）と判定の件数
    詳細指標          区分ごとの適合率・再現率・F1、正答率などの 95% 信頼区間、確率の当たり具合（report.md の詳細指標と同じ）
    投稿ごと          1行1投稿。本文・正解ラベルと、全モデルの判定・3つの確率・正誤を横に並べる
    混同行列          モデルごとの混同行列
    正解ラベル        正解ラベルと、Claude が付けた理由・人の確認欄
    <モデル名>        モデルごとの 05_<model>_evaluation.csv と同じ内容

Excel を入れていない環境でも動くよう、標準ライブラリだけで xlsx（Office Open XML）を書く。

使い方:
    python export_excel.py [--model <モデル名> ...]
"""

from __future__ import annotations

import argparse
import math
import sys
import zipfile
from collections import Counter
from xml.sax.saxutils import escape

from common import DATA_DIR, LABELS, read_csv, results_path
from evaluate import LABEL_JA, SOURCE_GROUPS, build_rows, confusion, detailed_stats, gold_label, summary
from models import MODELS

OUT = DATA_DIR / "06_model_comparison.xlsx"

# styles.xml の cellXfs の並び
PLAIN, HEADER, PERCENT, DECIMAL, WRAP = range(5)
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="0.0%"/><numFmt numFmtId="165" formatCode="0.000"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Yu Gothic"/></font><font><b/><sz val="11"/><name val="Yu Gothic"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDDEBF7"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="5">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
</styleSheet>"""


class Sheet:
    def __init__(self, name: str, widths: list[float], freeze: tuple[int, int] = (1, 0), autofilter: bool = True):
        self.name = name[:31]  # Excel のシート名は31文字まで
        self.widths = widths
        self.freeze = freeze  # 固定する行数・列数
        self.autofilter = autofilter  # 1行目を見出しとしてフィルタを付ける
        self.rows: list[list[tuple[object, int]]] = []

    def add(self, *cells, style: int = PLAIN) -> None:
        """cells の要素は値か (値, スタイル)"""
        self.rows.append([c if isinstance(c, tuple) else (c, style) for c in cells])

    def header(self, *names: str) -> None:
        self.add(*names, style=HEADER)

    def xml(self) -> str:
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        rows, cols = self.freeze
        if rows or cols:
            cell = f"{col_name(cols)}{rows + 1}"
            pane = "bottomRight" if rows and cols else ("bottomLeft" if rows else "topRight")
            split = (f' xSplit="{cols}"' if cols else "") + (f' ySplit="{rows}"' if rows else "")
            out.append(f'<sheetViews><sheetView workbookViewId="0"><pane{split} topLeftCell="{cell}" '
                       f'activePane="{pane}" state="frozen"/></sheetView></sheetViews>')
        out.append("<cols>" + "".join(
            f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(self.widths, 1)) + "</cols>")
        out.append("<sheetData>")
        for r, row in enumerate(self.rows, 1):
            cells = []
            for c, (value, style) in enumerate(row):
                ref = f"{col_name(c)}{r}"
                if value is None or value == "":
                    cells.append(f'<c r="{ref}" s="{style}"/>')
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    cells.append(f'<c r="{ref}" s="{style}"><v>{value}</v></c>')
                else:
                    text = escape(str(value)).replace("\r", "")
                    cells.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
            out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
        out.append("</sheetData>")
        if self.rows and self.autofilter:
            out.append(f'<autoFilter ref="A1:{col_name(len(self.rows[0]) - 1)}{len(self.rows)}"/>')
        out.append("</worksheet>")
        return "".join(out)


def col_name(index: int) -> str:
    """0 始まりの列番号を A, B, ..., AA の形にする"""
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def write_xlsx(path, sheets: list[Sheet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                             'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(1, len(sheets) + 1))
                   + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   "</Relationships>")
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(s.name)}" sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(sheets, 1))
                   + "</sheets>"
                   # オートフィルタの範囲は Excel が _FilterDatabase という名前で持つ
                   + "<definedNames>"
                   + "".join(f'<definedName name="_xlnm._FilterDatabase" localSheetId="{i}" hidden="1">'
                             f"'{escape(s.name)}'!$A$1:${col_name(len(s.rows[0]) - 1)}${len(s.rows)}</definedName>"
                             for i, s in enumerate(sheets) if s.rows and s.autofilter)
                   + "</definedNames></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                             f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml", STYLES)
        for i, s in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", s.xml())


def comparison_sheet(results) -> Sheet:
    sheet = Sheet("比較", [34, 12, 10, 12, 12, 12, 10, 10, 10, 10, 10, 12, 60, 40], freeze=(1, 1), autofilter=False)
    sheet.header("モデル", "正答率（3値）", "マクロ F1", "「当たる」の適合率", "「当たる」の再現率", "「当たる」の F1",
                 "ROC AUC", "最良の閾値", "閾値での最良 F1", "判定: 当たる", "判定: 当たらない", "判定: どちらとも言えない",
                 "補足", "応答のモデル名")
    for model, rows in results:
        s = summary(rows)
        p, r, f, _ = s["defamatory"]
        t, _, _, _, best_f = s["best_threshold"]
        counts = Counter(row["pred_label"] for row in rows)
        served = "、".join(sorted({row["served_model"] for row in rows if row["served_model"]}))
        sheet.add(model.title, (s["accuracy"], PERCENT), (s["macro_f1"], DECIMAL), (p, PERCENT), (r, PERCENT),
                  (f, DECIMAL), (s["auc"], DECIMAL), t, (best_f, DECIMAL),
                  counts["defamatory"], counts["not_defamatory"], counts["uncertain"], model.note, served)
    sheet.add()
    sheet.add("条件: どのモデルにも同じ200件・同じ正解ラベル・同じ質問（laya_question.json）を使った。")
    sheet.add("正答率・マクロ F1・適合率・再現率は、最も確率の高い選択肢をモデルの判定としたもの（3値）。")
    sheet.add("ROC AUC と閾値の列は「誹謗中傷にあたる確率」だけを使う（「当たる」とそれ以外の分離）。閾値は 0.1〜0.7 の 0.1 刻み。")
    sheet.add("有害コメント分類器は質問を受け取らず「有害か」の確率だけを返すので、「どちらとも言えない確率」は常に 0（D-11）。")
    return sheet


def per_post_sheet(results) -> Sheet:
    labels = {r["id"]: gold_label(r) for r in read_csv(DATA_DIR / "03_labels.csv")}
    first = results[0][1]
    by_model = [{row["id"]: row for row in rows} for _, rows in results]
    widths = [7, 60, 14, 24]
    names = ["ID", "本文", "正解ラベル", "元データの区分"]
    for model, _ in results:
        widths += [14, 10, 10, 10, 8]
        names += [f"{model.title}: 判定", f"{model.title}: 当たる確率", f"{model.title}: 当たらない確率",
                  f"{model.title}: どちらとも言えない確率", f"{model.title}: 正誤"]
    sheet = Sheet("投稿ごと", widths, freeze=(1, 2))
    sheet.header(*names)
    for base in first:
        cells: list[object] = [base["id"], (base["text"], WRAP), LABEL_JA[labels[base["id"]]],
                               SOURCE_GROUPS[base["source_group"]]]
        for rows in by_model:
            row = rows[base["id"]]
            cells += [LABEL_JA.get(row["pred_label"], row["pred_label"]),
                      *((row[f"p_{l}"], DECIMAL) for l in LABELS), "○" if row["correct"] else "×"]
        sheet.add(*cells)
    return sheet


def detailed_sheet(results) -> Sheet:
    """report.md の「詳細指標」と同じ内容。区間は下限と上限を別の列にして、Excel で並べ替えや計算をしやすくする"""
    sheet = Sheet("詳細指標", [34, 18, 10, 10, 10, 10, 10, 10, 10, 10, 10, 12, 12], freeze=(0, 1), autofilter=False)
    stats = [(model, detailed_stats(rows)) for model, rows in results]
    sheet.header("モデル", "正答率", "下限", "上限", "マクロ F1", "下限", "上限", "ROC AUC", "下限", "上限",
                 "Brier スコア", "対数損失")
    for model, s in stats:
        sheet.add(model.title, (s["accuracy"], PERCENT), *((v, PERCENT) for v in s["accuracy_ci"]),
                  (s["macro_f1"], DECIMAL), *((v, DECIMAL) for v in s["macro_f1_ci"]),
                  (s["auc"], DECIMAL), *((v, DECIMAL) for v in s["auc_ci"]),
                  (s["brier"], DECIMAL), (s["log_loss"], DECIMAL))
    sheet.add()
    sheet.header("モデル", "区分", "適合率", "下限", "上限", "再現率", "下限", "上限", "F1", "下限", "上限",
                 "判定した件数", "正解の件数")
    for label in LABELS:
        for model, s in stats:
            c = s["classes"][label]
            # 判定した件数が 0 の適合率の区間は求まらないので空欄にする
            ci = [None if math.isnan(v) else (v, PERCENT) for v in c["precision_ci"]]
            sheet.add(model.title, LABEL_JA[label], (c["precision"], PERCENT), *ci,
                      (c["recall"], PERCENT), *((v, PERCENT) for v in c["recall_ci"]),
                      (c["f1"], DECIMAL), *((v, DECIMAL) for v in c["f1_ci"]), c["predicted"], c["support"])
    sheet.add()
    sheet.add("区間は 95% 信頼区間。正答率・適合率・再現率は Wilson 法、F1・マクロ F1・ROC AUC は投稿のブートストラップ（1,000 回、シード固定）。")
    sheet.add("200件は統計としては多くないので、区間が重なるモデル同士の差は偶然の範囲かもしれない。")
    sheet.add("Brier スコアと対数損失は確率そのものの当たり具合で、小さいほどよい。Brier は 0 が完全、確率をいつも 1/3 ずつにすると 0.667。")
    sheet.add("適合率は判定した件数が 0 のとき 0% とし、区間は空欄にした。")
    return sheet


def confusion_sheet(results) -> Sheet:
    sheet = Sheet("混同行列", [34, 22, 14, 14, 18], freeze=(0, 0), autofilter=False)
    for model, rows in results:
        m = confusion([(r["gold"], r["pred_label"]) for r in rows])
        sheet.add(model.title, "正解 \\ モデルの判定", *(LABEL_JA[l] for l in LABELS), style=HEADER)
        for g in LABELS:
            sheet.add("", LABEL_JA[g], *(m[g][p] for p in LABELS))
        sheet.add()
    return sheet


def labels_sheet() -> Sheet:
    sheet = Sheet("正解ラベル", [7, 60, 18, 18, 60, 18, 40])
    sheet.header("ID", "本文", "正解ラベル（評価に使用）", "Claude のラベル", "Claude の理由", "人が直したラベル", "確認メモ")
    for r in read_csv(DATA_DIR / "03_labels.csv"):
        reviewed = (r.get("reviewed_label") or "").strip()
        sheet.add(r["id"], (r["text"], WRAP), LABEL_JA[gold_label(r)], LABEL_JA[r["claude_label"]],
                  (r["claude_reason"], WRAP), LABEL_JA.get(reviewed, reviewed), r.get("review_note", ""))
    return sheet


def model_sheet(model, rows) -> Sheet:
    sheet = Sheet(model.name, [7, 60, 14, 14, 10, 12, 12, 12, 24], freeze=(1, 2))
    sheet.header("ID", "本文", "正解ラベル", "モデルの判定", "正誤", "誹謗中傷にあたる確率", "誹謗中傷にあたらない確率",
                 "どちらとも言えない確率", "元データの区分")
    for r in rows:
        sheet.add(r["id"], (r["text"], WRAP), LABEL_JA[r["gold"]], LABEL_JA.get(r["pred_label"], r["pred_label"]),
                  "○" if r["correct"] else "×", *((r[f"p_{l}"], DECIMAL) for l in LABELS),
                  SOURCE_GROUPS[r["source_group"]])
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", nargs="+", choices=list(MODELS), help="既定は手順4の結果があるモデルすべて")
    args = ap.parse_args()
    names = args.model or [name for name in MODELS if results_path(name).exists()]
    if not names:
        raise SystemExit("手順4の結果（data/04_<model>_results.csv）がない。先に classify.py を実行する")

    results = [(MODELS[name], build_rows(name)) for name in names]
    ids = [r["id"] for r in results[0][1]]
    for model, rows in results:
        if [r["id"] for r in rows] != ids:
            raise SystemExit(f"{model.name} の判定結果の投稿が {results[0][0].name} とそろっていない")

    sheets = [comparison_sheet(results), detailed_sheet(results), per_post_sheet(results), confusion_sheet(results), labels_sheet()]
    sheets += [model_sheet(model, rows) for model, rows in results]
    write_xlsx(OUT, sheets)
    print(f"{len(results)} モデル: {', '.join(names)}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
