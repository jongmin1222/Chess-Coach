import re
import tempfile
import unittest
from pathlib import Path

from chess_coach.errors import KnowledgeError
from chess_coach.knowledge import (
    KnowledgeBase,
    eco_contains,
    eco_span,
    load_jsonl,
    parse_eco,
    parse_moves,
    parse_notes,
)
from chess_coach.rag import all_concept_keys

NOTE = """\
머리말은 무시됩니다.
---
id: a
title: 노트 A
kind: opening
phase: opening
eco: C50-C54, C41
moves: 1.e4 e5 2.Nf3 | 1.d4 d5
tags: x, y
keywords: foo bar
---
첫 문단입니다.
이어지는 줄.

둘째 문단.
---
id: b
title: 노트 B: 콜론 포함
---
본문 B
"""

SAN_RE = re.compile(r"^(O-O(-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](=[QRBN])?)$")


class ParseTests(unittest.TestCase):
    def test_parse_notes(self):
        a, b = parse_notes(NOTE, where="t.md")
        self.assertEqual((a.id, a.kind, a.phase), ("a", "opening", "opening"))
        self.assertEqual(a.eco, [("C50", "C54"), ("C41", "C41")])
        self.assertEqual(a.moves, [["e4", "e5", "Nf3"], ["d4", "d5"]])
        self.assertEqual(a.tags, ["x", "y"])
        self.assertEqual(a.text, "첫 문단입니다. 이어지는 줄.\n\n둘째 문단.")
        self.assertEqual(b.title, "노트 B: 콜론 포함")
        self.assertIsNone(b.phase)

    def test_errors(self):
        with self.assertRaises(KnowledgeError):
            parse_notes("---\nid: a\n---\n본문", where="t")  # title 없음
        with self.assertRaises(KnowledgeError):
            parse_notes("---\nid: a\ntitle: t\nkind: nope\n---\n본문", where="t")
        with self.assertRaises(KnowledgeError):
            parse_notes("---\nid: a\ntitle: t\n---\n", where="t")  # 본문 없음
        with self.assertRaises(KnowledgeError):
            parse_notes("---\nid: a\ntitle: t", where="t")  # 헤더 안 닫힘
        with self.assertRaises(KnowledgeError):
            parse_notes("---\nid: a\ntitle: t\neco: Z99\n---\n본문", where="t")

    def test_moves_and_eco_helpers(self):
        self.assertEqual(parse_moves("1.e4 c5 2.Nf3+ d6"), [["e4", "c5", "Nf3", "d6"]])
        self.assertEqual(parse_moves("1.e4 e5 2...Nc6"), [["e4", "e5", "Nc6"]])
        r = parse_eco("C50-C59")
        self.assertTrue(eco_contains(r, "c54"))
        self.assertFalse(eco_contains(r, "C60"))
        self.assertLess(eco_span(parse_eco("C41"), "C41"), eco_span(r, "C54"))

    def test_jsonl_roundtrip_and_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "b.jsonl"
            p.write_text('{"id":"x-1","text":"hello","source":"S","section":"Ch1"}\n\n', encoding="utf-8")
            (c,) = load_jsonl(p)
            self.assertEqual((c.id, c.title, c.origin), ("x-1", "Ch1", "user"))
            p.write_text("not json\n", encoding="utf-8")
            with self.assertRaises(KnowledgeError):
                load_jsonl(p)


class BuiltinKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = KnowledgeBase.load(None)

    def test_loads_and_ids_unique(self):
        ids = [c.id for c in self.kb.chunks]
        self.assertGreaterEqual(len(ids), 40)
        self.assertEqual(len(ids), len(set(ids)))

    def test_openings_have_detection_keys(self):
        openings = [c for c in self.kb.chunks if c.kind == "opening"]
        self.assertGreaterEqual(len(openings), 15)
        for c in openings:
            self.assertTrue(c.eco or c.moves, c.id)
            for alt in c.moves:
                for tok in alt:
                    self.assertRegex(tok, SAN_RE, f"{c.id}: {tok}")

    def test_non_openings_have_tags(self):
        for c in self.kb.chunks:
            if c.kind != "opening":
                self.assertTrue(c.tags, c.id)

    def test_every_concept_key_used_by_rag_exists_in_notes(self):
        tags = {t for c in self.kb.chunks for t in c.tags}
        self.assertEqual(all_concept_keys() - tags, set())

    def test_note_length_is_reasonable_for_prompt(self):
        for c in self.kb.chunks:
            self.assertLess(len(c.text), 700, c.id)

    def test_user_note_overrides_builtin_id(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "mine.md").write_text("---\nid: blunder-check\ntitle: 내 버전\n---\n내 본문", encoding="utf-8")
            kb = KnowledgeBase.load(d)
            c = kb.by_id()["blunder-check"]
            self.assertEqual((c.title, c.origin), ("내 버전", "user"))

    def test_duplicate_id_in_same_origin_raises(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("---\nid: z\ntitle: t\n---\n본문", encoding="utf-8")
            (Path(d) / "b.md").write_text("---\nid: z\ntitle: t\n---\n본문", encoding="utf-8")
            with self.assertRaises(KnowledgeError):
                KnowledgeBase.load(d, builtin=False)


if __name__ == "__main__":
    unittest.main()
