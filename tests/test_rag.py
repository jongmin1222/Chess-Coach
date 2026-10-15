import unittest

from chess_coach.knowledge import Chunk, KnowledgeBase
from chess_coach.rag import (
    build_query,
    format_line,
    has_content,
    identify_opening,
    retrieve_for_report,
    search_text,
)

from rag_helpers import START, moment, report

BUILTIN = KnowledgeBase.load(None)
MIDDLE_FEN = f"{START.split()[0]} w KQkq - 0 9"  # 풀무브 9 -> king_in_center / undeveloped 사실이 생김


def user_chunk(cid, text, **kw):
    return Chunk(id=cid, title="Chapter 1", text=text, source="Author, Book (1900), Chapter 1", origin="user", **kw)


class OpeningDetectionTests(unittest.TestCase):
    def test_by_eco_header(self):
        c, how = identify_opening(report(eco="C41"), BUILTIN.chunks)
        self.assertEqual((c.id, how), ("opening-philidor", "eco"))

    def test_eco_range_hit(self):
        c, _ = identify_opening(report(eco="B90"), BUILTIN.chunks)
        self.assertEqual(c.id, "opening-sicilian")

    def test_by_moves_longest_prefix(self):
        r = report(opening_moves=["d4", "d5", "c4", "e6", "Nc3", "Nf6"])
        c, how = identify_opening(r, BUILTIN.chunks)
        self.assertEqual((c.id, how), ("opening-qgd", "moves"))

    def test_moves_fallback_when_eco_not_covered(self):
        r = report(eco="A00", opening_moves=["e4", "e5", "Nf3", "d6", "d4"])
        self.assertEqual(identify_opening(r, BUILTIN.chunks)[0].id, "opening-philidor")

    def test_alternative_move_orders_and_check_suffix(self):
        r = report(opening_moves=["d4", "Nf6", "Nf3", "d5", "Bf4"])
        self.assertEqual(identify_opening(r, BUILTIN.chunks)[0].id, "opening-london")

    def test_unknown_opening(self):
        self.assertIsNone(identify_opening(report(opening_moves=["a3", "a6"]), BUILTIN.chunks))
        self.assertIsNone(identify_opening(report(), BUILTIN.chunks))

    def test_format_line(self):
        self.assertEqual(format_line(["e4", "e5", "Nf3"]), "1.e4 e5 2.Nf3")


class QueryTests(unittest.TestCase):
    def test_tags_and_phase_become_concepts(self):
        q = build_query(moment("5...Qxd4", 10, phase="opening", tags=["hung_moved_piece", "allowed_capture_of_queen"]))
        self.assertEqual(q.concepts["blunder-check"], 1.5)
        self.assertIn("opening-principles", q.concepts)
        self.assertIn("hanging piece", q.text)

    def test_position_facts_feed_query(self):
        q = build_query(moment("9.Nf3", 17, fen=MIDDLE_FEN))
        self.assertTrue(q.facts)
        self.assertIn("development", q.concepts)

    def test_unknown_tag_is_ignored(self):
        q = build_query(moment("9.Nf3", 17, tags=["mystery"]))
        self.assertEqual(q.phase, "middlegame")


class RetrieveTests(unittest.TestCase):
    def test_hung_piece_finds_safety_notes(self):
        r = report([moment("12.Bxf7", 23, tags=["hung_moved_piece"])])
        k = retrieve_for_report(r, BUILTIN)
        titles = [i["title"] for i in k["items"]]
        self.assertTrue(any("안전 점검" in t or "무방비" in t for t in titles), titles)
        self.assertEqual(k["moments"]["12.Bxf7"], [i["id"] for i in k["items"]])

    def test_endgame_moment_gets_endgame_notes_not_opening(self):
        fen = "8/5pk1/6p1/8/8/6P1/5PK1/3R4 w - - 0 40"
        r = report([moment("40.Rd7", 79, phase="endgame", fen=fen)])
        k = retrieve_for_report(r, BUILTIN)
        titles = " ".join(i["title"] for i in k["items"])
        self.assertIn("룩 엔드게임", titles)
        self.assertNotIn("오프닝 기본 원칙", titles)

    def test_opening_note_attached_to_game_and_opening_moments(self):
        r = report(
            [moment("4...Bg4", 8, phase="opening", tags=["hung_moved_piece"])],
            opening_moves=["e4", "e5", "Nf3", "d6", "d4", "Bg4"],
        )
        k = retrieve_for_report(r, BUILTIN)
        self.assertEqual(k["opening"]["family"], "필리도르 디펜스 (Philidor Defense)")
        self.assertEqual(k["opening"]["line"], "1.e4 e5 2.Nf3 d6 3.d4 Bg4")
        self.assertEqual(len(k["game"]), 1)
        self.assertEqual(k["moments"]["4...Bg4"][0], k["game"][0])
        self.assertIn("필리도르", k["items"][0]["text"] + k["items"][0]["title"])

    def test_numbering_is_sequential_and_deduplicated(self):
        r = report([moment("a", 10, tags=["hung_moved_piece"]), moment("b", 20, tags=["hung_moved_piece"])])
        k = retrieve_for_report(r, BUILTIN)
        ids = [i["id"] for i in k["items"]]
        self.assertEqual(ids, [f"K{n}" for n in range(1, len(ids) + 1)])
        self.assertEqual(len({i["title"] for i in k["items"]}), len(ids))

    def test_budget_is_respected(self):
        r = report([moment("a", 10, tags=["hung_moved_piece"]), moment("b", 20, tags=["missed_mate"])])
        k = retrieve_for_report(r, BUILTIN, budget_chars=500)
        self.assertLessEqual(sum(len(i["text"]) for i in k["items"]), 500)
        k0 = retrieve_for_report(r, BUILTIN, budget_chars=0)
        self.assertEqual(k0["items"], [])

    def test_empty_kb_and_no_moments(self):
        k = retrieve_for_report(report(), KnowledgeBase([]))
        self.assertFalse(has_content(k))

    def test_facts_are_returned_even_without_matching_notes(self):
        r = report([moment("9.Nf3", 17, fen=MIDDLE_FEN)])
        k = retrieve_for_report(r, KnowledgeBase([]))
        self.assertTrue(k["facts"]["9.Nf3"])
        self.assertTrue(has_content(k))

    def test_user_book_chunk_gets_a_slot(self):
        book = user_chunk(
            "bk-1",
            "A hanging piece is an undefended piece. Before moving, run a blunder check: "
            "look at checks, captures and threats, and make sure the piece is protected safety.",
        )
        kb = KnowledgeBase(BUILTIN.chunks + [book])
        r = report([moment("a", 10, tags=["hung_moved_piece"])])
        k = retrieve_for_report(r, kb, top_k=2)
        self.assertIn("Author, Book (1900), Chapter 1", [i["source"] for i in k["items"]])

    def test_irrelevant_book_chunk_is_not_used(self):
        book = user_chunk("bk-2", "The history of the tournament in Hastings 1895 and its prize fund.")
        kb = KnowledgeBase([book])
        r = report([moment("a", 10, tags=["hung_moved_piece"])])
        self.assertEqual(retrieve_for_report(r, kb)["items"], [])

    def test_long_text_is_trimmed_at_sentence(self):
        long = user_chunk("bk-3", ("Hanging piece blunder check safety undefended. " * 40).strip())
        kb = KnowledgeBase(BUILTIN.chunks + [long])  # 실제처럼 내장 노트와 함께 (IDF 가 의미를 가지려면 코퍼스가 필요)
        k = retrieve_for_report(report([moment("a", 10, tags=["hung_moved_piece"])]), kb, max_item_chars=200)
        item = next(i for i in k["items"] if i["source"].startswith("Author"))
        self.assertLessEqual(len(item["text"]), 200)
        self.assertTrue(item["text"].endswith("."))

    def test_search_text(self):
        hits = search_text(BUILTIN, "scholar's mate f7", top_k=3)
        self.assertEqual(hits[0][1].id, "scholars-mate")


if __name__ == "__main__":
    unittest.main()
