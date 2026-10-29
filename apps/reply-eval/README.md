# メール返信要否の判定の検証スクリプト

架空の日本語メール300件を、モデルで「返信が必要 / 返信は不要 / どちらとも言えない」に分類し、正解ラベルと比べる。
判定基準とデータの作り方は [docs/reply-eval.md](../../docs/reply-eval.md)、方針は [決定事項 D-13](../../docs/decisions.md)。
仕組みは [誹謗中傷判定の検証](../defamation-eval/README.md) と同じで、モデルの呼び出し・統計・Excel の書き出しはそちらのモジュールを使う。

Python 3.9 以上の標準ライブラリだけで動く。

## 実行手順

```sh
# 1. 生成したメール（data/gen/batch_*.jsonl）を検査して1つにまとめる -> data/01_emails.csv, data/02_blind_input.jsonl
python reply_build.py

# 2. 正解を伏せて付け直したラベル data/02_blind_labels.tsv（id, label, reason）を置く（スクリプトはない）

# 3. モデルで判定する -> data/04_<model>_results.csv, data/04_<model>_raw.jsonl
export API_AUTH_SECRET='（laya-api-containers/.env の API_AUTH_SECRET）'
python reply_classify.py --model laya
python reply_classify.py --model h2o-lightning   # basal / chon も同様

# 4. 評価する -> data/05_<model>_evaluation.csv, report.md
python reply_evaluate.py

# 5. Excel にまとめる -> data/06_reply_comparison.xlsx
python reply_excel.py
```

モデルのコンテナの起動と停止は [apps/defamation-eval/README.md](../defamation-eval/README.md#ほかのモデルで判定する) と同じ。GPU を使うモデル（H2O・Basal・Chon）は1つずつ起動する。

| モデル名 | モデル | 実行環境 |
|---|---|---|
| `laya` | Laya | CPU |
| `h2o-lightning` | H2O-Lightning-4B | GPU |
| `basal` | Basal-Omni-1.0-Max | GPU |
| `chon` | Chon-1.0-12B | GPU |

## data/ について

メールはすべて架空なので、`data/` も本文を含めてコミットする（誹謗中傷の検証と違い、ライセンスの制約がない）。

## テスト

```sh
python -m unittest
```
