import json
import unittest

from chess_coach.models import GameAnalysis
from chess_coach.report import build_report, summarize_side

from helpers import make_move


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.moves = [
            make_move(1, 0.0, is_best=True),
            make_move(2, 25.0),
            make_move(3, 1.0),
            make_move(4, 0.0, is_best=True),
        ]
        self.analysis = GameAnalysis(
            headers={"White": "alice", "Black": "bob", "Result": "1-0", "Site": "Chess.com"},
            moves=self.moves,
            engine_name="Stockfish 17",
            depth=16,
        )

    def test_report_has_opening_moves_for_rag(self):
        self.analysis.headers["Opening"] = "Philidor Defense"
        report = build_report(self.analysis, side="black")
        self.assertEqual(report["opening_moves"], ["Nf3", "Nf3", "Nf3", "Nf3"])
        self.assertEqual(report["game"]["opening"], "Philidor Defense")

    def test_opening_moves_capped(self):
        many = [make_move(i, 0.0, is_best=True) for i in range(1, 41)]
        analysis = GameAnalysis(headers={}, moves=many, engine_name="SF", depth=1)
        self.assertEqual(len(build_report(analysis)["opening_moves"]), 16)

    def test_summarize_side_counts(self):
        white = summarize_side(self.moves, "white")
        black = summarize_side(self.moves, "black")
        self.assertEqual(white["moves"], 2)
        self.assertEqual(white["best"], 1)
        self.assertEqual(white["good"], 1)
        self.assertEqual(black["blunder"], 1)
        self.assertEqual(black["best"], 1)
        self.assertGreater(white["accuracy"], black["accuracy"])

    def test_summarize_empty_side(self):
        self.assertIsNone(summarize_side([], "white")["accuracy"])

    def test_build_report_structure_and_json(self):
        report = build_report(self.analysis, side="black")
        self.assertEqual(report["analyzed_side"], "black")
        self.assertEqual(report["game"]["white"], "alice")
        self.assertEqual(report["total_plies"], 4)
        self.assertEqual([m["ply"] for m in report["critical_moments"]], [2])
        self.assertNotIn("moves", report)
        json.dumps(report, ensure_ascii=False)  # 직렬화 가능해야 함

    def test_include_moves(self):
        report = build_report(self.analysis, include_moves=True)
        self.assertEqual(len(report["moves"]), 4)
        self.assertEqual(report["moves"][1]["classification"], "blunder")


if __name__ == "__main__":
    unittest.main()
