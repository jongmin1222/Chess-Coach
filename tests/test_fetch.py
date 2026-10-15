import unittest
from unittest import mock

from chess_coach.errors import FetchError
from chess_coach.fetch import fetch_recent_games


def fake_get_json(url, user_agent, timeout=20.0):
    if url.endswith("/games/archives"):
        return {"archives": ["https://x/2026/08", "https://x/2026/09"]}
    if url.endswith("2026/09"):
        return {
            "games": [
                {"pgn": "OLD-SEP", "rules": "chess", "time_class": "blitz"},
                {"pgn": "960", "rules": "chess960", "time_class": "blitz"},
                {"pgn": "NEW-SEP", "rules": "chess", "time_class": "rapid"},
            ]
        }
    return {"games": [{"pgn": "AUG", "rules": "chess", "time_class": "blitz"}]}


class FetchTests(unittest.TestCase):
    def run_fetch(self, **kw):
        with mock.patch("chess_coach.fetch._get_json", fake_get_json):
            return fetch_recent_games("Someone", pause=0, user_agent="test", **kw)

    def test_newest_first_and_skips_variants(self):
        self.assertEqual(self.run_fetch(count=10), ["NEW-SEP", "OLD-SEP", "AUG"])

    def test_count_limit(self):
        self.assertEqual(self.run_fetch(count=1), ["NEW-SEP"])

    def test_time_class_filter(self):
        self.assertEqual(self.run_fetch(count=10, time_class="blitz"), ["OLD-SEP", "AUG"])

    def test_empty_username(self):
        with self.assertRaises(FetchError):
            fetch_recent_games("  ")

    def test_no_archives(self):
        with mock.patch("chess_coach.fetch._get_json", lambda *a, **k: {"archives": []}):
            with self.assertRaises(FetchError):
                fetch_recent_games("x", pause=0, user_agent="t")


if __name__ == "__main__":
    unittest.main()
