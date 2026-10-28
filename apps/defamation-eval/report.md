# 誹謗中傷判定のモデル比較

`evaluate.py` が出力する。本文は含めない。判定基準と手順は [docs/defamation-eval.md](../../docs/defamation-eval.md)。
どのモデルにも同じ200件・同じ正解ラベル・同じ質問（[laya_question.json](laya_question.json)）を使った。

| モデル | 正答率 | マクロ F1 | 「当たる」の適合率 | 「当たる」の再現率 | ROC AUC | 閾値で最良の F1（閾値） | 詳細 |
|---|---|---|---|---|---|---|---|
| Laya | 55.5% | 0.344 | 93.3% | 21.2% | 0.691 | 0.544（0.2） | [laya](reports/laya.md) |
| H2O-Lightning-4B | 68.0% | 0.637 | 84.2% | 48.5% | 0.835 | 0.667（0.1） | [h2o-lightning](reports/h2o-lightning.md) |
| Basal-Omni-1.0-Max | 74.5% | 0.635 | 88.5% | 69.7% | 0.923 | 0.785（0.2） | [basal](reports/basal.md) |
| Multilingual Toxicity Base | 54.0% | 0.334 | 70.0% | 21.2% | 0.821 | 0.679（0.2） | [toxicity-base](reports/toxicity-base.md) |
| XLM-R Large Toxicity Classifier | 67.5% | 0.493 | 56.5% | 92.4% | 0.846 | 0.702（0.6） | [xlmr-large-toxicity](reports/xlmr-large-toxicity.md) |
| DistilBERT Multilingual Toxicity Classifier | 63.0% | 0.454 | 53.4% | 71.2% | 0.778 | 0.627（0.3） | [distilbert-toxicity](reports/distilbert-toxicity.md) |

- 正答率・マクロ F1・適合率・再現率は、最も確率の高い選択肢をモデルの判定としたもの（3値）。
- ROC AUC と閾値の列は `p_defamatory` だけを使う（「当たる」とそれ以外の分離）。閾値は 0.1〜0.7 の 0.1 刻み。

## モデルの補足

| モデル | 補足 | 応答のモデル名 |
|---|---|---|
| Laya | multilingual チェックポイント | multilingual |
| H2O-Lightning-4B | BF16 の GGUF（量子化なし）を llama-server で | h2o-lightning-4b |
| Basal-Omni-1.0-Max | 依頼の Ultra（31B）は 16GB に載らないため 12B の max の GGUF で代替 | basal-omni-1.0-max-Q8_0 |
| Multilingual Toxicity Base | 有害コメント分類器。toxicity ラベルの確率を「当たる」とみなす | Horizon-Labs/multilingual-toxicity-base@a732048 |
| XLM-R Large Toxicity Classifier | 有害コメント分類器（v2）。toxic の確率を「当たる」とみなす | textdetox/xlmr-large-toxicity-classifier-v2@38ab1b7 |
| DistilBERT Multilingual Toxicity Classifier | 有害コメント分類器。toxic の確率を「当たる」とみなす | gravitee-io/distilbert-multilingual-toxicity-classifier@865ad1b |
