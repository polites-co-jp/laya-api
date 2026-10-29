"""メール返信要否の検証（docs/decisions.md D-13）の各スクリプトで共通に使う定数と import。

モデルの呼び出し・CSV の読み書き・統計・Excel の書き出しは apps/defamation-eval のものを使う。
このディレクトリのファイル名に reply_ を付けているのは、defamation-eval のモジュール（common・models・evaluate など）と名前がぶつからないようにするため。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(1, str(HERE.parent / "defamation-eval"))

from common import read_csv, write_csv  # noqa: E402,F401
from models import MODELS as ALL_MODELS  # noqa: E402

# 架空のデータなので data/ もコミットする（D-13）
DATA_DIR = HERE / "data"
GEN_DIR = DATA_DIR / "gen"

QUESTION_ID = "reply"
# reply_question.json の選択肢と同じ並び
LABELS = ("reply_needed", "no_reply_needed", "uncertain")
LABEL_JA = {"reply_needed": "返信が必要", "no_reply_needed": "返信は不要", "uncertain": "どちらとも言えない"}
POSITIVE = "reply_needed"  # ROC AUC と閾値の表で「当たり」とみなす区分

# 質問を受け取れる決定モデルのうち、ローカルで動くもの（有害コメント分類器と Jev は使わない）
MODEL_NAMES = ("laya", "h2o-lightning", "basal", "chon")
MODELS = {name: ALL_MODELS[name] for name in MODEL_NAMES}

BATCHES = {
    "A": "社外のビジネスメール",
    "B": "社内メール",
    "C": "自動送信・通知・広告",
    "D": "私用のメール",
    "E": "境界・ひっかけのケース",
    "F": "顧客対応・外部の窓口",
}


def results_path(model: str) -> Path:
    return DATA_DIR / f"04_{model}_results.csv"
