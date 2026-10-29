"""reply_evaluate.py と reply_classify.py のテスト。python -m unittest で実行する。"""

from __future__ import annotations

import unittest

from reply_classify import to_row
from reply_evaluate import cohen_kappa, per_class, roc_auc, threshold_table


def row(gold: str, p: float) -> dict:
    return {"gold": gold, "p_reply_needed": p}


class PerClassTest(unittest.TestCase):
    def test_counts_support_and_predicted(self):
        pairs = [("reply_needed", "reply_needed"), ("reply_needed", "uncertain"), ("no_reply_needed", "reply_needed")]
        p, r, f, support, predicted = per_class(pairs)["reply_needed"]
        self.assertEqual((p, r, support, predicted), (0.5, 0.5, 2, 2))
        self.assertAlmostEqual(f, 0.5)


class KappaTest(unittest.TestCase):
    def test_perfect_and_chance(self):
        same = [("reply_needed", "reply_needed"), ("no_reply_needed", "no_reply_needed")]
        self.assertAlmostEqual(cohen_kappa(same), 1.0)
        # 一致率 0.5、偶然の一致の期待値 0.5 なので κ = 0
        chance = [("reply_needed", "reply_needed"), ("reply_needed", "no_reply_needed"),
                  ("no_reply_needed", "reply_needed"), ("no_reply_needed", "no_reply_needed")]
        self.assertAlmostEqual(cohen_kappa(chance), 0.0)


class RocAucTest(unittest.TestCase):
    def test_positive_is_reply_needed(self):
        self.assertEqual(roc_auc([row("reply_needed", 0.9), row("uncertain", 0.2)]), 1.0)
        self.assertEqual(roc_auc([row("reply_needed", 0.1), row("no_reply_needed", 0.8)]), 0.0)

    def test_threshold_flags_at_or_above(self):
        table = {t: flagged for t, flagged, *_ in threshold_table([row("reply_needed", 0.5), row("uncertain", 0.3)])}
        self.assertEqual((table[0.3], table[0.5], table[0.6]), (2, 1, 0))


class ToRowTest(unittest.TestCase):
    def test_maps_probabilities(self):
        result = {"model": "m", "answers": {"reply": {"choice": "reply_needed", "probabilities": {
            "reply_needed": 0.7, "no_reply_needed": 0.2, "uncertain": 0.1}}}}
        r = to_row({"id": "M001", "text": "t"}, result)
        self.assertEqual((r["pred_label"], r["p_reply_needed"], r["pred_confidence"], r["served_model"]),
                         ("reply_needed", "0.7000", "0.7000", "m"))

    def test_rejects_other_options(self):
        with self.assertRaises(SystemExit):
            to_row({"id": "M001", "text": "t"}, {"answers": {"reply": {"choice": "yes", "probabilities": {"yes": 1.0}}}})


if __name__ == "__main__":
    unittest.main()
