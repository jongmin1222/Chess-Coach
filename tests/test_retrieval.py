import unittest

from chess_coach.knowledge import Chunk
from chess_coach.retrieval import BM25, Retriever, tokenize


def chunk(cid, text, **kw):
    return Chunk(id=cid, title=kw.pop("title", cid), text=text, source="S", **kw)


class TokenizeTests(unittest.TestCase):
    def test_english_stem_and_stopwords(self):
        self.assertEqual(tokenize("The pieces of chess"), ["piece", "chess"])

    def test_hangul_bigrams(self):
        self.assertEqual(tokenize("캐슬링"), ["캐슬", "슬링"])
        self.assertEqual(tokenize("킹 e4"), ["킹", "e4"])


class BM25Tests(unittest.TestCase):
    def test_ranks_matching_doc_first(self):
        docs = [tokenize(t) for t in ["rook endgame technique", "opening development knights", "queen attack"]]
        scores = BM25(docs).scores(tokenize("rook endgame"))
        self.assertEqual(scores.index(max(scores)), 0)
        self.assertEqual(scores[2], 0.0)

    def test_empty(self):
        self.assertEqual(BM25([]).scores(["a"]), [])


class RetrieverTests(unittest.TestCase):
    def setUp(self):
        self.r = Retriever(
            [
                chunk("a", "rook endgames and the Lucena position", phase="endgame"),
                chunk("b", "opening principles and development", phase="opening"),
                chunk("c", "king safety", keywords="castling"),
            ]
        )

    def test_search_and_filters(self):
        self.assertEqual(self.r.search("lucena rook")[0][1].id, "a")
        self.assertEqual([c.id for _, c in self.r.search("development", phase="endgame")], [])
        self.assertEqual(self.r.search("castling")[0][1].id, "c")  # keywords 도 검색됨

    def test_korean_query(self):
        r = Retriever([chunk("k", "킹 안전과 캐슬링", title="킹 안전")])
        self.assertEqual(r.search("캐슬링")[0][1].id, "k")


if __name__ == "__main__":
    unittest.main()
