import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from chess_coach.config import DEFAULT_MODEL, default_model, load_dotenv, ollama_host


class ConfigTests(unittest.TestCase):
    def test_default_model_is_qwen(self):
        self.assertEqual(DEFAULT_MODEL, "qwen2.5:7b")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(default_model(), "qwen2.5:7b")

    def test_env_override(self):
        with mock.patch.dict(os.environ, {"CHESS_COACH_MODEL": "llama3.2:3b"}, clear=True):
            self.assertEqual(default_model(), "llama3.2:3b")

    def test_default_host(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ollama_host(), "http://localhost:11434")

    def test_load_dotenv_parses_and_does_not_override(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text(
                "# 주석\nSTOCKFISH_PATH=/usr/games/stockfish\nQUOTED=\"hello world\"\nEMPTY=\nKEEP=new\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"KEEP": "old"}, clear=True):
                load_dotenv(env_file)
                self.assertEqual(os.environ["STOCKFISH_PATH"], "/usr/games/stockfish")
                self.assertEqual(os.environ["QUOTED"], "hello world")
                self.assertNotIn("EMPTY", os.environ)
                self.assertEqual(os.environ["KEEP"], "old")

    def test_missing_file_is_ok(self):
        load_dotenv("/nonexistent/.env")


if __name__ == "__main__":
    unittest.main()
