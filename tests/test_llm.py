import io
import json
import unittest
import urllib.error
from unittest import mock

from chess_coach.errors import LLMError
from chess_coach.llm import SYSTEM_PROMPT, build_messages, describe_tag, finalize_feedback, ollama_chat
from chess_coach.models import GameAnalysis
from chess_coach.report import build_report

from helpers import make_move


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen_returning(content):
    body = json.dumps({"message": {"role": "assistant", "content": content}}).encode("utf-8")
    return lambda req, timeout=None: FakeResponse(body)


class DescribeTagTests(unittest.TestCase):
    def test_known_tags(self):
        self.assertIn("체크메이트", describe_tag("allowed_mate"))
        self.assertIn("나이트", describe_tag("allowed_capture_of_knight"))
        self.assertIn("퀸", describe_tag("missed_capture_of_queen"))
        self.assertIn("잡혀", describe_tag("hung_moved_piece"))

    def test_unknown_tag_passthrough(self):
        self.assertEqual(describe_tag("something_new"), "something_new")


class BuildMessagesTests(unittest.TestCase):
    def setUp(self):
        moves = [make_move(1, 0.0, is_best=True), make_move(2, 30.0, tags=["allowed_mate"])]
        analysis = GameAnalysis(headers={"White": "a", "Black": "b"}, moves=moves)
        self.report = build_report(analysis, side="black")

    def test_structure(self):
        msgs = build_messages(self.report, level="beginner")
        self.assertEqual([m["role"] for m in msgs], ["system", "user"])
        self.assertIn("JSON에 있는 것만", msgs[0]["content"])
        self.assertIn("중국어", msgs[0]["content"])
        self.assertIn("흑", msgs[1]["content"])

    def test_payload_contains_korean_hints_not_raw_tags(self):
        user = build_messages(self.report)[1]["content"]
        self.assertIn("강제 체크메이트를 허용", user)
        self.assertNotIn("allowed_mate", user)
        self.assertNotIn("fen_before", user)  # LLM에 불필요한 필드는 제외

    def test_invalid_level(self):
        with self.assertRaises(ValueError):
            build_messages(self.report, level="god")


class OllamaChatTests(unittest.TestCase):
    def test_returns_content(self):
        with mock.patch("chess_coach.llm.urllib.request.urlopen", fake_urlopen_returning("안녕")):
            self.assertEqual(ollama_chat([{"role": "user", "content": "hi"}], "m"), "안녕")

    def test_strips_think_block(self):
        with mock.patch(
            "chess_coach.llm.urllib.request.urlopen",
            fake_urlopen_returning("<think>\n생각중\n</think>\n최종 답"),
        ):
            self.assertEqual(ollama_chat([], "m"), "최종 답")

    def test_connection_error_is_friendly(self):
        def boom(req, timeout=None):
            raise urllib.error.URLError("refused")

        with mock.patch("chess_coach.llm.urllib.request.urlopen", boom):
            with self.assertRaises(LLMError) as ctx:
                ollama_chat([], "m")
        self.assertIn("Ollama", str(ctx.exception))

    def test_missing_model_message(self):
        def not_found(req, timeout=None):
            raise urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b"model not found"))

        with mock.patch("chess_coach.llm.urllib.request.urlopen", not_found):
            with self.assertRaises(LLMError) as ctx:
                ollama_chat([], "qwen2.5:7b")
        self.assertIn("ollama pull qwen2.5:7b", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


KNOWLEDGE = {
    "items": [
        {"id": "K1", "title": "필리도르 디펜스", "source": "내장 노트", "text": "본문1"},
        {"id": "K2", "title": "Chapter 2", "source": "Capablanca, Chess Fundamentals (1921), Chapter 2", "text": "text2"},
    ],
    "game": ["K1"],
    "moments": {"1.Nf3": ["K1", "K2"]},
    "facts": {"1.Nf3": ["이 수를 두기 전, 킹이 아직 초기 위치(e파일)에 있었습니다."]},
    "opening": {"family": "필리도르 디펜스", "line": "1.e4 e5 2.Nf3 d6"},
}


class RagPromptTests(unittest.TestCase):
    def setUp(self):
        analysis = GameAnalysis(
            headers={"White": "a", "Black": "b"},
            moves=[make_move(1, 25.0, san="Nf3", tags=["hung_moved_piece"])],
            engine_name="SF",
            depth=12,
            movetime=None,
        )
        self.report = build_report(analysis, side="white")

    def test_without_knowledge_prompt_is_unchanged(self):
        msgs = build_messages(self.report)
        self.assertEqual(msgs[0]["content"], SYSTEM_PROMPT)
        self.assertNotIn("knowledge", msgs[1]["content"])
        self.assertEqual(msgs, build_messages(self.report, knowledge={"items": [], "facts": {}, "opening": None}))

    def test_with_knowledge(self):
        msgs = build_messages(self.report, knowledge=KNOWLEDGE)
        self.assertIn(SYSTEM_PROMPT, msgs[0]["content"])
        self.assertIn("[K1]", msgs[0]["content"])
        user = msgs[1]["content"]
        payload = json.loads(user[user.index("{"):])
        self.assertEqual([i["id"] for i in payload["knowledge"]], ["K1", "K2"])
        self.assertEqual(payload["opening"]["family"], "필리도르 디펜스")
        self.assertEqual(payload["opening"]["knowledge"], ["K1"])
        moment = payload["critical_moments"][0]
        self.assertEqual(moment["related_knowledge"], ["K1", "K2"])
        self.assertEqual(len(moment["position_facts"]), 1)
        self.assertNotIn("chunk_id", user)


class FinalizeFeedbackTests(unittest.TestCase):
    def test_renumbers_and_appends_only_cited(self):
        text = "킹 안전이 중요합니다 [K2]. 전개도 중요합니다 (K1, K2)."
        out = finalize_feedback(text, KNOWLEDGE)
        self.assertIn("중요합니다 [1].", out)
        self.assertIn("[2][1].", out)
        self.assertIn("## 참고 자료", out)
        self.assertIn("[1] Capablanca, Chess Fundamentals (1921), Chapter 2", out)
        self.assertIn("[2] 내장 노트 — 필리도르 디펜스", out)

    def test_unknown_ids_removed_and_no_section_when_uncited(self):
        out = finalize_feedback("좋습니다 [K9].", KNOWLEDGE)
        self.assertEqual(out, "좋습니다 .")
        self.assertEqual(finalize_feedback("그냥 텍스트", KNOWLEDGE), "그냥 텍스트")

    def test_no_knowledge_returns_text_untouched(self):
        self.assertEqual(finalize_feedback("[K1] 텍스트", None), "[K1] 텍스트")
