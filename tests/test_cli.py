import unittest

from chess_coach.cli import build_parser


class ParserTests(unittest.TestCase):
    def test_analyze_defaults(self):
        args = build_parser().parse_args(["analyze", "g.pgn", "--user", "me"])
        self.assertEqual(args.depth, 16)
        self.assertEqual(args.game, 1)
        self.assertEqual(args.max_moments, 5)
        self.assertEqual(args.user, "me")

    def test_coach_options(self):
        args = build_parser().parse_args(
            ["coach", "g.pgn", "--level", "beginner", "--show-prompt", "--model", "qwen2.5:7b"]
        )
        self.assertEqual(args.level, "beginner")
        self.assertTrue(args.show_prompt)
        self.assertEqual(args.model, "qwen2.5:7b")

    def test_fetch(self):
        args = build_parser().parse_args(["fetch", "someone", "--count", "3", "--time-class", "rapid"])
        self.assertEqual((args.count, args.time_class, args.out), (3, "rapid", "games.pgn"))

    def test_subcommand_required(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])


if __name__ == "__main__":
    unittest.main()
