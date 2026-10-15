import unittest

from chess_coach.moments import select_critical_moments

from helpers import make_move


class SelectMomentsTests(unittest.TestCase):
    def setUp(self):
        # ply 1..10, 홀수=백, 짝수=흑
        self.moves = [
            make_move(1, 0.0, is_best=True),
            make_move(2, 3.0),
            make_move(3, 25.0),   # 백 블런더
            make_move(4, 12.0),   # 흑 실수 (ply 3과 가까움)
            make_move(5, 1.0),
            make_move(6, 30.0),   # 흑 블런더 (가장 큼)
            make_move(7, 6.0),    # 백 부정확
            make_move(8, 0.0, is_best=True),
            make_move(9, 15.0),   # 백 실수
            make_move(10, 2.0),
        ]

    def test_picks_worst_and_is_chronological(self):
        result = select_critical_moments(self.moves, max_moments=3)
        self.assertEqual([m["ply"] for m in result], sorted(m["ply"] for m in result))
        self.assertEqual([m["ply"] for m in result], [3, 6, 9])

    def test_min_gap_removes_same_side_neighbours(self):
        # 흑 ply 4(12%p)는 흑 ply 6(30%p)와 2 ply 차이 = 같은 사건 -> 제외
        result = select_critical_moments(self.moves, max_moments=5)
        self.assertNotIn(4, [m["ply"] for m in result])

    def test_opposite_sides_are_not_merged(self):
        # 백 ply 3(25)과 흑 ply 4(12)는 붙어 있어도 서로 다른 교훈이므로 둘 다 남는다
        moves = [make_move(3, 25.0), make_move(4, 12.0)]
        self.assertEqual([m["ply"] for m in select_critical_moments(moves)], [3, 4])

    def test_color_filter(self):
        result = select_critical_moments(self.moves, color="black", max_moments=5)
        self.assertTrue(all(m["color"] == "black" for m in result))
        # ply 4는 ply 6과 같은 사건으로 합쳐져 더 큰 ply 6만 남는다
        self.assertEqual([m["ply"] for m in result], [6])

    def test_turning_point_is_largest_loss(self):
        result = select_critical_moments(self.moves, max_moments=3)
        turning = [m for m in result if m["turning_point"]]
        self.assertEqual(len(turning), 1)
        self.assertEqual(turning[0]["ply"], 6)

    def test_fallback_to_inaccuracy_when_no_mistakes(self):
        moves = [make_move(1, 6.0), make_move(2, 1.0), make_move(3, 1.0), make_move(4, 1.0), make_move(5, 7.0)]
        result = select_critical_moments(moves, min_severity="mistake")
        self.assertEqual([m["ply"] for m in result], [1, 5])

    def test_empty_when_all_good(self):
        moves = [make_move(1, 1.0), make_move(2, 0.5)]
        self.assertEqual(select_critical_moments(moves), [])

    def test_best_moves_are_never_selected(self):
        moves = [make_move(1, 50.0, is_best=True), make_move(2, 30.0)]
        self.assertEqual([m["ply"] for m in select_critical_moments(moves)], [2])

    def test_invalid_severity(self):
        with self.assertRaises(ValueError):
            select_critical_moments(self.moves, min_severity="terrible")

    def test_output_fields(self):
        m = select_critical_moments(self.moves, max_moments=1)[0]
        for key in ("label", "phase", "played", "best_move", "best_line", "tags", "fen_before", "turning_point"):
            self.assertIn(key, m)


if __name__ == "__main__":
    unittest.main()
