import unittest

from chess_coach.features import parse_fen, position_facts

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"


def keys(fen, phase=None):
    return [k for k, _ in position_facts(fen, phase)]


class FeaturesTests(unittest.TestCase):
    def test_parse_fen(self):
        board, turn, full = parse_fen(f"{START} b KQkq - 0 7")
        self.assertEqual((board["e1"], board["e8"], turn, full), ("K", "k", "b", 7))
        with self.assertRaises(ValueError):
            parse_fen("garbage")

    def test_bad_or_empty_fen_gives_no_facts(self):
        self.assertEqual(position_facts("", "opening"), [])
        self.assertEqual(position_facts(None), [])
        self.assertEqual(position_facts("not a fen"), [])

    def test_king_in_center_and_undeveloped(self):
        ks = keys(f"{START} w KQkq - 0 9", "middlegame")
        self.assertIn("king_in_center", ks)
        self.assertIn("undeveloped_minors", ks)

    def test_early_game_is_not_flagged(self):
        ks = keys(f"{START} w KQkq - 0 3", "opening")
        self.assertNotIn("king_in_center", ks)
        self.assertNotIn("undeveloped_minors", ks)

    def test_queen_out_early(self):
        fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3"
        self.assertIn("queen_out_early", keys(fen, "opening"))
        self.assertNotIn("queen_out_early", keys(f"{START} w KQkq - 0 3", "opening"))

    def test_black_perspective(self):
        # 흑 차례, 흑 킹이 e8에 남아 있고 풀무브 10
        self.assertIn("king_in_center", keys(f"{START} b KQkq - 0 10", "middlegame"))

    def test_pawn_endgame_and_passed_pawn(self):
        fen = "8/8/8/4k3/8/4K3/4P3/8 w - - 0 50"
        facts = dict(position_facts(fen, "endgame"))
        self.assertIn("pawn_endgame", facts)
        self.assertIn("passed_pawn_mover", facts)
        self.assertNotIn("passed_pawn_opponent", facts)
        self.assertIn("1개", facts["passed_pawn_mover"])

    def test_passed_pawn_blocked_by_adjacent_file(self):
        # 백 e2, 흑 d7 (인접 파일의 앞쪽 폰) -> 백 e2 는 통과폰이 아님. 흑 d7 도 e2 가 인접 파일 앞쪽이라 아님.
        fen = "8/3p4/8/4k3/8/4K3/4P3/8 w - - 0 50"
        ks = keys(fen, "endgame")
        self.assertNotIn("passed_pawn_mover", ks)
        self.assertNotIn("passed_pawn_opponent", ks)

    def test_rook_endgame(self):
        self.assertIn("rook_endgame", keys("8/5pk1/6p1/8/8/6P1/5PK1/3R4 w - - 0 40", "endgame"))

    def test_opposite_colored_bishops(self):
        fen = "8/5pk1/8/8/8/2B5/5PK1/5b2 w - - 0 40"  # c3(어두운 칸) vs f1(밝은 칸)
        ks = keys(fen, "endgame")
        self.assertIn("opposite_colored_bishops", ks)
        self.assertIn("minor_piece_endgame", ks)
        same = "8/5pk1/8/8/8/2B5/5PK1/6b1 w - - 0 40"  # c3 vs g1(어두운 칸)
        self.assertNotIn("opposite_colored_bishops", keys(same, "endgame"))


if __name__ == "__main__":
    unittest.main()
