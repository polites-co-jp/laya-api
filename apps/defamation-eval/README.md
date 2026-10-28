# 誹謗中傷判定の検証スクリプト

掲示板・SNS の投稿200件を Laya などのモデルで「誹謗中傷にあたる / あたらない / どちらとも言えない」に分類し、正解ラベルと比べる。
判定基準・成果物の一覧・結果の読み方は [docs/defamation-eval.md](../../docs/defamation-eval.md)、方針は [決定事項 D-09・D-10・D-11](../../docs/decisions.md)。

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

# 5. 評価する -> data/05_<model>_evaluation.csv, reports/<model>.md, report.md（比較表）
python evaluate.py
```

## ほかのモデルで判定する

`classify.py --model <モデル名>` で、Laya の代わりに次のモデルで判定できる。結果はモデルごとのファイル（`data/04_<モデル名>_results.csv`）に分かれ、`evaluate.py` は結果のあるモデルをすべて評価して `report.md` に並べる。

| モデル名 | モデル | 動かし方 |
|---|---|---|
| `laya` | Laya（既定） | 上の手順4 |
| `jev` | Jev（TypeSafe のクラウド API） | `TYPESAFE_API_KEY` を設定する。投稿200件が TypeSafe へ送られる |
| `h2o-lightning` | H2O-Lightning-4B（BF16 の GGUF） | profile `eval-h2o`（GPU） |
| `basal` | Basal-Omni-1.0-Max（GGUF Q8_0）。依頼の Ultra は 16GB に載らないための代替 | profile `eval-basal`（GPU） |
| `chon` | Chon-1.0-12B（FP8）。載らなければ E2B | profile `eval-chon`（GPU） |
| `toxicity-base` | Multilingual Toxicity Base | profile `eval-toxicity`（CPU） |
| `xlmr-large-toxicity` | XLM-R Large Toxicity Classifier（v2） | profile `eval-toxicity`（CPU） |
| `distilbert-toxicity` | DistilBERT Multilingual Toxicity Classifier | profile `eval-toxicity`（CPU） |

ローカルのモデルは `laya-api-containers` で profile を指定して起動する。初回は重みを取得するので時間がかかる（`docker compose ps` が healthy になれば使える）。
GPU が 16GB なので、GPU を使うモデルは1つずつ起動し、終わったら止める。Laya のコンテナも GPU を使うので、12B のモデルを動かす間は止めておく。

```sh
cd ../../laya-api-containers
docker compose --profile eval-h2o up -d          # 起動（basal / chon も同様）
cd ../apps/defamation-eval && python classify.py --model h2o-lightning
cd ../../laya-api-containers
docker compose --profile eval-h2o stop h2o-lightning   # 終わったら止める

docker compose --profile eval-toxicity up -d --build   # 有害コメント分類器3つ（CPU。ほかと同時に動かしてよい）
```

- GPU に載らないとき: Basal は `.env` に `EVAL_BASAL_QUANT=Q6_K`、Chon は `EVAL_CHON_MODEL=ninhnv/chon-1.0-e2b@5ef9c07c77bfb7637637f1882743703ea139ee8e` と `EVAL_CHON_QUANTIZE=`（空）を書いて起動し直す。
- 有害コメント分類器は質問を受け取らず「有害か」の確率だけを返す。その確率を `p_defamatory`、残りを `p_not_defamatory` とし、`p_uncertain` は 0 にする（D-11）。

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
