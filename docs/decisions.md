# 決定事項

## D-01 認証は HMAC 署名 + nonce + 時刻（2026-10-02）

当初案は「現在時刻を共有鍵で暗号化して送り、1秒以内なら通す」だった。
この方式だと時刻が本文と結び付かず、傍受者が1秒以内に同じトークンで別のプロンプトを送れる。
そのため、時刻・nonce・メソッド・パス・本文ハッシュに HMAC-SHA256 で署名し、nonce を1回限りにする方式を採った。
時刻の許容幅は当初案どおり既定1秒（`AUTH_MAX_SKEW_MS` で変更可）。仕様は [ja/auth.md](ja/auth.md)。

## D-02 API は Laya 互換のプロキシにする（2026-10-02、中継先は D-05 で変更）

独自の簡易 API に変換するのではなく、Laya のエンドポイントを同じ入出力のまま中継する。
当初は有料ホスティング laya-ai.pro を中継先にしていたが、D-05 でローカル実行に置き換えた。

## D-03 動作確認チャットは「判断チャット」にする（2026-10-02）

Laya は会話を生成しない判断モデルなので、入力欄に state を書き、画面上で質問（noul / choice / score）を編集して送る形にした。
返答は質問ごとの答え・確率・confidence・使用トークンを表示する。生 JSON は各返答の折りたたみで見られる。
チャットはサーバ側で署名し、ブラウザには秘密鍵を渡さない。開発専用で profile `dev` のときだけ起動し、127.0.0.1 にのみ公開する。

## D-04 ホスト公開ポートは 22300-22399（2026-10-02）

Notion「ポート管理」の空きから採番した。api=22300、chat=22301。詳細は [port-registry.md](port-registry.md)。

## D-05 Laya はローカルで実行する（2026-10-06）

Laya はオープンソース（Apache 2.0）の判断モデルで、公式パッケージ `laya[serve]` の `laya-serve` が HTTP サーバとして動く。
当初の実装は「Laya AI API」の検索結果に出た有料ホスティング laya-ai.pro への中継で、依頼の意図（ローカルの Laya を使う）と食い違っていた。
laya-ai.pro は公式リポジトリから参照されておらず、公式かどうかも確認できない。

- 同じ compose 内に `laya-serve` のコンテナを置き、Node.js の API はそこへ中継する。
- 中継するのは laya-serve の全エンドポイント（`POST /v1/systemone`、`POST /v1/systemone/batch`、`GET /health`）。
- laya のコンテナはホストへ公開しない。外から届くのは署名付きの Node.js API だけ。
- `LAYA_AI_API_KEY` と laya-ai.pro への中継は削除する。

## D-06 GPU を既定とし、.env で CPU に切り替えられるようにする（2026-10-06）

既定は NVIDIA GPU（CUDA 版 torch とデバイス予約）。`.env` の設定で CPU 版に切り替えられるようにする。
判断1回あたりの目安は GPU で約35ms、CPU で約0.2〜0.5秒。

## D-07 GitHub 公開用のドキュメント構成（2026-10-06）

プロジェクト名は「Laya 検証のための Docker コンテナ」（英語版は "Docker Containers for Evaluating Laya"）とする。
Laya を手元で検証するためのコンテナとして位置付け、手順は localhost での利用を中心に書く。
別ホストから呼ぶ場合は TLS・ファイアウォール・時刻同期の注意を短い節で示す。Laya 公式とは無関係である旨を明記する。

- README.md を日本語（既定）、README.en.md を英語とし、冒頭の言語リンクで相互に行き来する。
- 手順書は docs/ja/ と docs/en/ に同名で置く: deploy.md（コンテナ展開）、chat.md（チャットの使い方）、api.md（外部アプリからの利用）、auth.md（認証仕様）。
- 認証仕様 auth.md は外部から呼ぶ人に必要なので日英化する。decisions.md と port-registry.md は開発記録として docs/ 直下・日本語のみで残す。
- ライセンスは Laya 本体と同じ Apache-2.0。

## D-08 外部アプリ向けのサンプルクライアントとチャット UI の日英対応（2026-10-06）

外部アプリから API を呼ぶ手順書に合わせて、次を実装する。

- apps/examples/ に依存なしの署名付きクライアントを置く（Node.js 版と Python 版。Python は標準ライブラリだけ）。ルート直下は apps / docs / laya-api-containers の3構成を守るため examples/ は作らない。
- 手順書の curl 例は本文をファイル経由（`--data-binary @file`）で送る形に直す。Windows の Git Bash では `--data "$BODY"` の日本語が別の文字コードで curl に渡り、署名と本文がずれて 401 になるため。
- チャット UI はブラウザの言語で初期表示を決め、ヘッダのボタンで日本語と英語を切り替えられるようにする。既定の例題も表示言語に合わせる。
- チャットの使い方にはスクリーンショット（日本語版・英語版）を載せ、docs/images/ に置く。

## D-09 誹謗中傷判定の検証は裁判例データセットで行う（2026-10-07）

掲示板・SNS の投稿200件を Laya で「誹謗中傷にあたる / あたらない / どちらとも言えない」に分類し、各確率を CSV に出す検証を、ブランチ `feature/defamation-classification` で行う。

- 5ch・Threads からの自動収集はしない。両者の規約が無断の自動収集・転載を制限しており、このリポジトリは公開されていて、実投稿をコミットすると中傷を再び公開することになるため。
- データは公開の研究用データセット「日本語オンライン誹謗中傷裁判例データセット」（久田・若宮・荒牧 2024、[horshohei/japanese-offensive-language-from-court-case](https://github.com/horshohei/japanese-offensive-language-from-court-case)、commit `03d3b65`）から取る。Twitter・爆サイ・5ちゃんねるなどの実投稿で、人名は匿名化済み。
  - 候補だった inspection-ai/japanese-toxic-dataset（Apache-2.0）は、平均12文字の短文で誹謗中傷の例が数十件しかなく、精度評価の根拠として弱いため採らなかった。
- 裁判例データセットは CC BY-NC 4.0 なので、データ本体と、本文を含む中間ファイル・結果 CSV はコミットしない。取得スクリプトだけを置き、データはローカルに取得する。営業目的の利用には当たらない前提で使う。
- 200件の内訳は、裁判で争われた投稿100件（侵害が認められたもの・認められなかったものの両方を含む）と、争われていない投稿100件。乱数シードを固定して抽出する。
- 誹謗中傷の基準はプラットフォーム基準とする。特定の相手への侮辱・人格攻撃・根拠のない悪評・脅迫を誹謗中傷とし、正当な批判は外す。データセット元来のラベルは法的判断と「争われたかどうか」なので、正解には使わない（争われていない投稿にも明らかな暴言が混ざっている）。
- 正解ラベルは、判定基準を文書にしたうえで Claude が3値と理由を付け、人が一覧を確認して異議のあるものを直す。
- Laya には `choice` 型の質問を1つ送り、3つの選択肢（defamatory / not_defamatory / uncertain）の確率を CSV の3列にする。`/v1/systemone/batch` で64件ずつ送る。
- 成果物は確率 CSV と、正解ラベルと比べた精度評価（正答率・混同行列・クラスごとの適合率と再現率・閾値ごとの結果）。
- 各手順の成果物はあとから確認できるよう、手順番号を付けたファイルとして残す（`data/01_sample.csv` 〜 `data/05_evaluation.csv`）。本文を含まないもの（抽出 ID の一覧・Laya への質問・評価レポート）はコミットする。一覧は [defamation-eval.md](defamation-eval.md#成果物)。
- Laya には投稿本文だけを渡し、文脈（前後の投稿）は渡さない。正解ラベルも本文だけで判断する。
- 質問が日本語なので、英語の投稿も含めて `model` を `multilingual` に固定する（自動の振り分けでは英語の投稿が english に回り、日本語の質問を読めない）。
- コミットする文書（判定基準・結果の要約）には、データセットの実投稿を引用しない。例は架空の文にする。

## D-10 誹謗中傷判定の検証で Laya 以外の決定モデルも比べられるようにする（2026-10-29）

D-09 の検証（同じ200件・同じ正解ラベル・同じ質問）を、Laya 以外の決定モデルでも実行し、精度を並べて比べられるようにする。
対象は依頼された4モデル。どれも選択肢ごとの確率を返す決定モデルで、日本語への対応は明記されていない。

| 依頼の名前 | 使うもの | 動かし方 |
|---|---|---|
| Chon-1.0-12B | `ninhnv/chon-1.0-12b`（Gemma 4 12B への LoRA） | 公式の chon サーバを FP8 で動かす。16GB に載らなければ `ninhnv/chon-1.0-e2b` に切り替え、どちらで測ったかをレポートに書く |
| Basal-Omni-1.0-Ultra | `Remek/basal-omni-1.0-max`（12B）の GGUF Q8_0 | Ultra（31B）は量子化しても約33GB で 16GB に載らないため、同じ系統の max に替える。Ultra の結果ではないことをレポートに書く |
| H2O-Lightning-4B | `h2oai/h2o-lightning-4b-gguf` の BF16 | llama.cpp の llama-server。16GB に載るので量子化しない |
| JEB | TypeSafe の Jev（クラウド API） | `https://api.typesafe.ai/v1/systemone`。API キー（`TYPESAFE_API_KEY`）が要り、投稿200件を外部へ送る。AutoTrust の JEV-9B ではない |

- ローカルのモデルは `laya-api-containers` に compose の profile として置き、1つずつ起動する。GPU が 16GB なので同時には載せない。
- ローカルのモデルのサーバは認証を持たないので、127.0.0.1 にだけ公開する（22310-22312、[port-registry.md](port-registry.md)）。
- 判定スクリプトはモデルを選べるようにし、結果はモデルごとのファイルに分けて残す。評価レポートはモデルを並べた比較表と、モデルごとの詳細にする。

## D-11 有害コメント分類器3つも比べる（2026-10-29）

D-10 の比較に、次の3つの有害コメント分類器を加える。どれも日本語を学習言語に含む。

| 依頼の名前 | 使うもの |
|---|---|
| Multilingual Toxicity Base | `Horizon-Labs/multilingual-toxicity-base`（mmBERT-base、7ラベルの多ラベル分類） |
| XLM-R Large Toxicity Classifier | `textdetox/xlmr-large-toxicity-classifier-v2`（初版は日本語を含まないため、2025年の後継版） |
| DistilBERT Multilingual Toxicity Classifier | `gravitee-io/distilbert-multilingual-toxicity-classifier` |

- これらは質問を受け取らず、「有害か」の確率だけを返す。そのため toxic の確率を `p_defamatory`、1 からそれを引いた値を `p_not_defamatory` とし、`p_uncertain` は 0 にする。最も確率の高い選択肢が判定になるので、0.5 以上なら「当たる」になる。
- Multilingual Toxicity Base は `toxicity` ラベルの確率を使う。ほかのラベル（insult・threat など）の確率は応答の生データに残す。
- 「有害」は誹謗中傷より広く（相手のいない暴言も含む）、狭くもある（侮辱語のない悪評の断定は含みにくい）。比較では ROC AUC と閾値ごとの結果を主に見る。
- 小さいモデルなので CPU で動かす。3つを1つのコンテナ（profile `eval-toxicity`、127.0.0.1:22313）にまとめ、GPU を使う他のモデルと同時に動かせるようにする。

## D-12 全モデルの結果を1つの Excel にまとめる（2026-10-29）

D-09〜D-11 の検証結果を、モデルを横に並べて見られる Excel 1ファイルにまとめる。

- 対象は手順4の結果があるモデルすべて（Laya・H2O-Lightning-4B・Basal-Omni-1.0-Max・Chon-1.0・有害コメント分類器3つの計7モデル）。どれも同じ200件・同じ正解ラベル・同じ質問で 2026-10-29 に判定したもので、判定はやり直さずにその結果を使う。
- Jev（TypeSafe）は `TYPESAFE_API_KEY` がなく実行できないため含めない。キーを用意すれば `classify.py --model jev` のあとに `export_excel.py` を実行し直すだけで加わる。
- 出力は `data/06_model_comparison.xlsx`。本文を含むので git 管理外。シートは「比較」「投稿ごと」「混同行列」「正解ラベル」とモデルごとの結果。
- スクリプトは標準ライブラリだけで xlsx を書く（D-08 以来の「依存なし」を守るため openpyxl は使わない）。
