import unittest

from chess_coach.models import MATE_CP
from chess_coach.scoring import (
    accuracy_from_loss,
    classify,
    format_eval,
    is_mate_cp,
    win_percent,
)


class WinPercentTests(unittest.TestCase):
    def test_equal_position_is_fifty(self):
        self.assertAlmostEqual(win_percent(0), 50.0)

    def test_symmetry(self):
        for cp in (10, 100, 350, 900):
            self.assertAlmostEqual(win_percent(cp) + win_percent(-cp), 100.0, places=6)

    def test_monotonic(self):
        values = [win_percent(cp) for cp in range(-1000, 1001, 100)]
        self.assertEqual(values, sorted(values))

    def test_mate_is_extreme_and_does_not_overflow(self):
        self.assertGreater(win_percent(MATE_CP), 99.99)
        self.assertLess(win_percent(-MATE_CP), 0.01)
        self.assertLess(win_percent(-10**9), 0.01)  # 클램프 확인


class ClassifyTests(unittest.TestCase):
    def test_best_move_flag_wins(self):
        self.assertEqual(classify(50.0, True), "best")

    def test_thresholds(self):
        self.assertEqual(classify(0.0, False), "good")
        self.assertEqual(classify(4.99, False), "good")
        self.assertEqual(classify(5.0, False), "inaccuracy")
        self.assertEqual(classify(10.0, False), "mistake")
        self.assertEqual(classify(20.0, False), "blunder")

    def test_custom_thresholds(self):
        th = {"inaccuracy": 1.0, "mistake": 2.0, "blunder": 3.0}
        self.assertEqual(classify(2.5, False, th), "mistake")


class AccuracyTests(unittest.TestCase):
    def test_no_loss_is_about_100(self):
        self.assertAlmostEqual(accuracy_from_loss(0), 100.0, places=2)

    def test_decreases_with_loss_and_is_bounded(self):
        a, b, c = accuracy_from_loss(5), accuracy_from_loss(20), accuracy_from_loss(80)
        self.assertGreater(a, b)
        self.assertGreater(b, c)
        self.assertGreaterEqual(c, 0.0)


class FormatEvalTests(unittest.TestCase):
    def test_centipawns(self):
        self.assertEqual(format_eval(35, None), "+0.35")
        self.assertEqual(format_eval(-120, None), "-1.20")
        self.assertEqual(format_eval(0, None), "+0.00")

    def test_mate(self):
        self.assertEqual(format_eval(MATE_CP - 5, 5), "+M3")  # 5 ply = 3수
        self.assertEqual(format_eval(-(MATE_CP - 2), -2), "-M1")
        self.assertEqual(format_eval(MATE_CP, 0), "checkmate")

    def test_is_mate_cp(self):
        self.assertTrue(is_mate_cp(MATE_CP - 3))
        self.assertTrue(is_mate_cp(-(MATE_CP - 3)))
        self.assertFalse(is_mate_cp(900))


if __name__ == "__main__":
    unittest.main()
