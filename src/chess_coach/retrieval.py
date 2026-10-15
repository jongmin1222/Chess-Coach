"""검색: 외부 의존성 없는 BM25. python-chess에 의존하지 않습니다."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Optional

from .knowledge import Chunk

_TOKEN_RE = re.compile(r"[a-z0-9]+|[가-힣]+")
_STOPWORDS = frozenset(
    "the an of to and or in on is are for with as at by it this that be from into its was were".split()
)


def _stem(tok: str) -> str:
    # 아주 단순한 복수형 처리: pieces -> piece, 단 chess/pass 같은 ss 어미는 유지
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    """영어는 소문자 단어, 한글은 글자 2-gram 으로 쪼갠다. (조사가 붙어도 어느 정도 매칭)"""
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        tok = m.group()
        if "가" <= tok[0] <= "힣":
            if len(tok) == 1:
                out.append(tok)
            else:
                out.extend(tok[i : i + 2] for i in range(len(tok) - 1))
        elif len(tok) > 1 and tok not in _STOPWORDS:
            out.append(_stem(tok))
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.n = len(docs)
        self.avgdl = sum(len(d) for d in docs) / self.n if self.n else 0.0
        self.tf = [Counter(d) for d in docs]
        self.df: Counter[str] = Counter()
        for d in docs:
            self.df.update(set(d))

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1 + (self.n - n + 0.5) / (n + 0.5))

    def scores(self, query_tokens: Iterable[str]) -> list[float]:
        terms = [t for t in set(query_tokens) if t in self.df]
        out = [0.0] * self.n
        if not terms or not self.avgdl:
            return out
        idf = {t: self._idf(t) for t in terms}
        for i, tf in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * len(self.docs[i]) / self.avgdl)
            s = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    s += idf[t] * f * (self.k1 + 1) / (f + norm)
            out[i] = s
        return out


class Retriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        docs = [
            tokenize(" ".join([c.title, c.keywords, " ".join(c.tags), c.text])) for c in chunks
        ]
        self._bm25 = BM25(docs)

    def raw_scores(self, query_text: str) -> list[float]:
        return self._bm25.scores(tokenize(query_text))

    def search(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        phase: Optional[str] = None,
        kinds: Optional[Iterable[str]] = None,
    ) -> list[tuple[float, Chunk]]:
        """자유 텍스트 검색 (kb search 용). 점수 0 은 제외."""
        kind_set = set(kinds) if kinds else None
        scored = []
        for chunk, s in zip(self.chunks, self.raw_scores(query_text)):
            if s <= 0:
                continue
            if phase and chunk.phase and chunk.phase != phase:
                continue
            if kind_set and chunk.kind not in kind_set:
                continue
            scored.append((s, chunk))
        scored.sort(key=lambda x: (-x[0], x[1].id))
        return scored[:top_k]
