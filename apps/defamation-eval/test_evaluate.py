"""evaluate.py の集計のテスト。python -m unittest で実行する。"""

from __future__ import annotations

import unittest

from evaluate import confusion, gold_label, per_class, precision_recall_f1, roc_auc, threshold_table


def row(gold: str, p: float) -> dict:
    return {"gold": gold, "p_defamatory": p}


class PrecisionRecallTest(unittest.TestCase):
    def test_values(self):
        p, r, f = precision_recall_f1(tp=3, fp=1, fn=3)
        self.assertAlmostEqual(p, 0.75)
        self.assertAlmostEqual(r, 0.5)
        self.assertAlmostEqual(f, 0.6)

    def test_no_predictions_is_zero_not_error(self):
        self.assertEqual(precision_recall_f1(0, 0, 5), (0.0, 0.0, 0.0))


class ConfusionTest(unittest.TestCase):
    def test_counts_gold_to_pred(self):
        pairs = [("defamatory", "defamatory"), ("defamatory", "not_defamatory"), ("uncertain", "not_defamatory")]
        m = confusion(pairs)
        self.assertEqual(m["defamatory"]["defamatory"], 1)
        self.assertEqual(m["defamatory"]["not_defamatory"], 1)
        self.assertEqual(m["uncertain"]["not_defamatory"], 1)
        self.assertEqual(m["not_defamatory"]["not_defamatory"], 0)

    def test_per_class_support(self):
        pairs = [("defamatory", "defamatory"), ("defamatory", "not_defamatory"), ("not_defamatory", "defamatory")]
        p, r, _, support = per_class(pairs)["defamatory"]
        self.assertAlmostEqual(p, 0.5)
        self.assertAlmostEqual(r, 0.5)
        self.assertEqual(support, 2)


class ThresholdTest(unittest.TestCase):
    def test_flags_at_or_above_threshold(self):
        rows = [row("defamatory", 0.5), row("defamatory", 0.15), row("uncertain", 0.3), row("not_defamatory", 0.05)]
        table = {t: (flagged, p, r) for t, flagged, p, r, _ in threshold_table(rows)}
        self.assertEqual(table[0.1], (3, 2 / 3, 1.0))
        self.assertEqual(table[0.5], (1, 1.0, 0.5))


class RocAucTest(unittest.TestCase):
    def test_perfect_and_reversed(self):
        self.assertEqual(roc_auc([row("defamatory", 0.9), row("not_defamatory", 0.1)]), 1.0)
        self.assertEqual(roc_auc([row("defamatory", 0.1), row("uncertain", 0.9)]), 0.0)

    def test_ties_count_half(self):
        self.assertEqual(roc_auc([row("defamatory", 0.5), row("not_defamatory", 0.5)]), 0.5)


class GoldLabelTest(unittest.TestCase):
    def test_reviewed_label_wins(self):
        self.assertEqual(gold_label({"id": "S1", "claude_label": "defamatory", "reviewed_label": "uncertain"}), "uncertain")

    def test_blank_review_falls_back_to_claude(self):
        self.assertEqual(gold_label({"id": "S1", "claude_label": "defamatory", "reviewed_label": " "}), "defamatory")

    def test_unknown_label_is_rejected(self):
        with self.assertRaises(SystemExit):
            gold_label({"id": "S1", "claude_label": "defamatory", "reviewed_label": "maybe"})


if __name__ == "__main__":
    unittest.main()
