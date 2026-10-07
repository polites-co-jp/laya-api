# 誹謗中傷判定の検証スクリプト

掲示板・SNS の投稿200件を Laya で「誹謗中傷にあたる / あたらない / どちらとも言えない」に分類し、正解ラベルと比べる。
判定基準・成果物の一覧・結果の読み方は [docs/defamation-eval.md](../../docs/defamation-eval.md)、方針は [決定事項 D-09](../../docs/decisions.md)。

Python 3.9 以上の標準ライブラリだけで動く。Laya の呼び出しには [apps/examples/python/laya_client.py](../examples/python/laya_client.py) を使う。

## 実行手順

[Docker コンテナ展開手順](../../docs/ja/deploy.md) に沿って Laya と API を起動してから、このディレクトリで順に実行する。

```sh
# 1. データセットを取得し、200件を抽出する -> data/01_sample.csv, sample_ids.csv
python fetch_sample.py

# 3. 正解ラベル（data/03_claude_labels.tsv）を確認用シートにまとめる -> data/03_labels.csv
python make_label_sheet.py

# 4. Laya で判定する -> data/04_laya_results.csv, data/04_laya_raw.jsonl
export API_AUTH_SECRET='（laya-api-containers/.env の API_AUTH_SECRET）'
python classify.py

# 5. 評価する -> data/05_evaluation.csv, report.md
python evaluate.py
```

手順2は判定基準の文書（[docs/defamation-eval.md](../../docs/defamation-eval.md#判定基準)）で、スクリプトはない。

## 正解ラベルを確認して直す

1. `data/03_labels.csv` を Excel などで開く。
2. `claude_label` に異議があれば、`reviewed_label` に `defamatory` / `not_defamatory` / `uncertain` のどれかを入れる。理由は `review_note` に書く。空欄のままなら `claude_label` を正解として使う。
3. UTF-8（BOM 付き）の CSV のまま保存し、`python evaluate.py` を実行し直す。Laya の判定（手順4）はやり直さなくてよい。

`make_label_sheet.py` は、既に `03_labels.csv` があると上書きしない（確認内容を守るため）。

## data/ について

`data/` は git 管理外。元データの [日本語オンライン誹謗中傷裁判例データセット](https://github.com/horshohei/japanese-offensive-language-from-court-case) が CC BY-NC 4.0 のため、本文を含むファイルはコミットしない。
`03_claude_labels.tsv` も `data/` にあるので、別の環境で手順3から再現するときは、このファイルを別途受け渡す。

## テスト

```sh
python -m unittest
```
