"""python-chess가 설치된 환경에서만 실행됩니다. 엔진 대신 미리 짜둔 평가값(ScriptedEngine)을 사용합니다."""

import io
import unittest
from pathlib import Path

try:
    import chess
    import chess.pgn

    HAS_CHESS = True
except ImportError:  # pragma: no cover
    HAS_CHESS = False

from chess_coach.models import MATE_CP, PositionEval

if HAS_CHESS:
    from chess_coach.analysis import analyze_game, game_phase
    from chess_coach.moments import select_critical_moments
    from chess_coach.pgn_io import detect_color, read_games

ROOT = Path(__file__).resolve().parent.parent


class ScriptedEngine:
    """비터미널 포지션마다 순서대로 미리 정한 평가를 돌려준다."""

    name = "Scripted"

    def __init__(self, evals):
        self._it = iter(evals)

    def evaluate(self, board):
        return next(self._it)


def game_from(pgn_text):
    return chess.pgn.read_game(io.StringIO(pgn_text))


@unittest.skipUnless(HAS_CHESS, "python-chess 필요")
class ScholarsMateTests(unittest.TestCase):
    """1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6?? 4.Qxf7#"""

    def setUp(self):
        game = game_from("1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0")
        engine = ScriptedEngine(
            [
                PositionEval(30, None, "e2e4", ["e2e4", "e7e5"]),
                PositionEval(25, None, "e7e5", ["e7e5"]),
                PositionEval(30, None, "g1f3", ["g1f3"]),
                PositionEval(10, None, "b8c6", ["b8c6"]),
                PositionEval(15, None, "f1c4", ["f1c4"]),
                PositionEval(20, None, "g7g6", ["g7g6"]),
                PositionEval(MATE_CP - 1, 1, "h5f7", ["h5f7"]),
            ]  # 마지막 포지션(체크메이트)은 엔진을 부르지 않는다
        )
        self.analysis = analyze_game(game, engine)

    def test_move_count_and_labels(self):
        self.assertEqual(len(self.analysis.moves), 7)
        self.assertEqual(self.analysis.moves[0].label, "1.e4")
        self.assertEqual(self.analysis.moves[5].label, "3...Nf6")
        self.assertEqual(self.analysis.moves[6].san, "Qxf7#")

    def test_blunder_detected_with_allowed_mate(self):
        nf6 = self.analysis.moves[5]
        self.assertEqual(nf6.classification, "blunder")
        self.assertGreater(nf6.win_loss, 40)
        self.assertIn("allowed_mate", nf6.tags)
        self.assertEqual(nf6.best_san, "g6")
        self.assertEqual(nf6.refutation_san, "Qxf7#")
        self.assertEqual(nf6.eval_after, "+M1")

    def test_engine_moves_are_best(self):
        for i in (0, 1, 3, 4, 6):
            self.assertEqual(self.analysis.moves[i].classification, "best", i)

    def test_small_loss_is_good_not_flagged(self):
        qh5 = self.analysis.moves[2]
        self.assertEqual(qh5.classification, "good")
        self.assertEqual(qh5.tags, [])

    def test_critical_moments_by_side(self):
        black = select_critical_moments(self.analysis.moves, color="black")
        self.assertEqual([m["label"] for m in black], ["3...Nf6"])
        self.assertEqual(select_critical_moments(self.analysis.moves, color="white"), [])


@unittest.skipUnless(HAS_CHESS, "python-chess 필요")
class HungPieceTests(unittest.TestCase):
    """1.e4 e5 2.Nf3 Nc6 3.Nxe5?  (나이트를 폰과 맞바꾸는 실수)"""

    def test_hung_moved_piece_tag(self):
        game = game_from("1. e4 e5 2. Nf3 Nc6 3. Nxe5 *")
        engine = ScriptedEngine(
            [
                PositionEval(30, None, "e2e4", ["e2e4"]),
                PositionEval(25, None, "e7e5", ["e7e5"]),
                PositionEval(30, None, "g1f3", ["g1f3"]),
                PositionEval(20, None, "b8c6", ["b8c6"]),
                PositionEval(30, None, "f1b5", ["f1b5"]),
                PositionEval(-250, None, "c6e5", ["c6e5"]),
            ]
        )
        move = analyze_game(game, engine).moves[4]
        self.assertEqual(move.san, "Nxe5")
        self.assertEqual(move.classification, "blunder")
        self.assertIn("allowed_capture_of_knight", move.tags)
        self.assertIn("hung_moved_piece", move.tags)
        self.assertNotIn("missed_capture_of_pawn", move.tags)


@unittest.skipUnless(HAS_CHESS, "python-chess 필요")
class HelperTests(unittest.TestCase):
    def test_game_phase(self):
        self.assertEqual(game_phase(chess.Board()), "opening")
        self.assertEqual(game_phase(chess.Board("8/8/4k3/8/8/4K3/4P3/8 w - - 0 40")), "endgame")
        middlegame = chess.Board("r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 0 12")
        self.assertEqual(game_phase(middlegame), "middlegame")

    def test_detect_color(self):
        headers = {"White": "Alice", "Black": "Bob"}
        self.assertEqual(detect_color(headers, "alice"), "white")
        self.assertEqual(detect_color(headers, " BOB "), "black")
        self.assertIsNone(detect_color(headers, "carol"))
        self.assertIsNone(detect_color(headers, None))

    def test_sample_pgn_is_legal(self):
        games = read_games(str(ROOT / "examples" / "sample_game.pgn"))
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].errors, [])
        moves = list(games[0].mainline_moves())
        self.assertEqual(len(moves), 33)
        self.assertTrue(games[0].end().board().is_checkmate())


if __name__ == "__main__":
    unittest.main()
