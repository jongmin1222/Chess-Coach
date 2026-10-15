"""RAG: 분석 결과에서 검색어를 만들고, 지식 베이스에서 관련 자료를 골라 프롬프트용으로 정리한다.

python-chess에 의존하지 않습니다. 흐름:
  1. 게임 전체: ECO 헤더 또는 첫 수들로 오프닝을 판별 -> 해당 오프닝 노트
  2. 핵심 장면마다: 분석 태그 + 포지션 사실 + 국면 -> 개념 키와 영어 검색어 -> 점수 계산 -> 상위 k개
  3. 프롬프트 길이 예산(글자 수) 안에서 중복 없이 고르고 K1, K2... 번호를 붙인다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .features import position_facts
from .knowledge import Chunk, KnowledgeBase, eco_contains, eco_span, normalize_san
from .retrieval import Retriever

DEFAULT_BUDGET_CHARS = 2400  # 프롬프트에 넣을 참고 자료 본문 총량 (7B 모델의 num_ctx=8192 를 고려한 값)
DEFAULT_TOP_K = 2  # 장면당 최대 자료 수
MAX_ITEM_CHARS = 700

# 점수 계산 상수. 실제 책으로 써 보면서 조정할 수 있습니다.
MIN_SCORE = 1.0
BM25_WEIGHT = 1.2
BM25_SAT = 12.0  # raw/(raw+SAT) 로 0~1 로 눌러 담는다
PHASE_MATCH_BONUS = 0.5
PHASE_MISMATCH_PENALTY = 1.5
BOOK_MIN_RAW = 10.0  # 태그가 없는 조각(책)은 검색어와 이 정도 이상 겹쳐야 후보가 된다
OPENING_PLIES = 16

# (개념 키 -> 가중치, 영어 검색어). 개념 키는 노트의 tags 와 맞춰 봅니다.
_Spec = tuple[dict[str, float], str]

PHASE_CONCEPTS: dict[str, _Spec] = {
    "opening": ({"opening-principles": 0.7}, "opening principles development"),
    "middlegame": ({"middlegame-planning": 0.5}, "middlegame plan"),
    "endgame": ({"endgame-principles": 0.7}, "endgame principles"),
}

TAG_CONCEPTS: dict[str, _Spec] = {
    "missed_mate": (
        {"checkmate-patterns": 1.5, "calculation": 1.0},
        "checkmate mating attack forcing moves checks calculation",
    ),
    "allowed_mate": (
        {"king-safety": 1.5, "checkmate-patterns": 1.0, "blunder-check": 1.0},
        "king safety mating attack back rank defend threats",
    ),
    "hung_moved_piece": (
        {"piece-safety": 1.5, "blunder-check": 1.5},
        "hanging piece undefended blunder check safety before moving",
    ),
}
TAG_PREFIX_CONCEPTS: dict[str, _Spec] = {
    "missed_capture_of_": (
        {"loose-pieces": 1.5, "tactics-basics": 1.0, "blunder-check": 0.5},
        "loose piece undefended capture win material tactic",
    ),
    "allowed_capture_of_": (
        {"piece-safety": 1.5, "blunder-check": 1.5, "tactics-basics": 0.5},
        "hanging piece protect attacked threat blunder check",
    ),
}

FEATURE_CONCEPTS: dict[str, _Spec] = {
    "king_in_center": ({"king-safety": 1.5, "castling": 1.5}, "castling king safety center open files"),
    "undeveloped_minors": ({"development": 1.5, "opening-principles": 0.7}, "development undeveloped pieces tempo"),
    "queen_out_early": ({"early-queen-moves": 1.5, "development": 0.7}, "early queen moves development tempo"),
    "pawn_endgame": ({"king-and-pawn-endgames": 2.0}, "king and pawn endgame opposition key squares"),
    "rook_endgame": ({"rook-endgames": 2.0}, "rook endgame active rook passed pawn"),
    "queen_endgame": ({"queen-endgames": 2.0}, "queen endgame perpetual check"),
    "minor_piece_endgame": ({"minor-piece-endgames": 2.0}, "bishop knight endgame"),
    "opposite_colored_bishops": ({"opposite-colored-bishops": 2.0}, "opposite colored bishops drawish"),
    "passed_pawn_mover": ({"passed-pawn": 1.5}, "passed pawn push promote"),
    "passed_pawn_opponent": ({"passed-pawn": 1.5}, "passed pawn blockade stop"),
}


def all_concept_keys() -> set[str]:
    """검색 규칙이 참조하는 모든 개념 키 (노트 tags 와 어긋나지 않는지 테스트하는 용도)."""
    specs = [*PHASE_CONCEPTS.values(), *TAG_CONCEPTS.values(), *TAG_PREFIX_CONCEPTS.values(), *FEATURE_CONCEPTS.values()]
    return {k for concepts, _ in specs for k in concepts}


@dataclass
class Query:
    phase: Optional[str]
    concepts: dict[str, float] = field(default_factory=dict)
    text: str = ""
    facts: list[str] = field(default_factory=list)


def _tag_spec(tag: str) -> Optional[_Spec]:
    if tag in TAG_CONCEPTS:
        return TAG_CONCEPTS[tag]
    for prefix, spec in TAG_PREFIX_CONCEPTS.items():
        if tag.startswith(prefix):
            return spec
    return None


def build_query(moment: dict) -> Query:
    """핵심 장면(dict) 하나에서 검색어를 만든다."""
    phase = moment.get("phase")
    concepts: dict[str, float] = {}
    terms: list[str] = []

    def add(spec: Optional[_Spec]) -> None:
        if not spec:
            return
        for key, weight in spec[0].items():
            concepts[key] = max(concepts.get(key, 0.0), weight)
        terms.append(spec[1])

    add(PHASE_CONCEPTS.get(phase or ""))
    for tag in moment.get("tags", []):
        add(_tag_spec(tag))
    facts: list[str] = []
    for key, sentence in position_facts(moment.get("fen_before"), phase):
        add(FEATURE_CONCEPTS.get(key))
        facts.append(sentence)
    return Query(phase=phase, concepts=concepts, text=" ".join(terms), facts=facts)


def format_line(sans: list[str]) -> str:
    parts = []
    for i, san in enumerate(sans):
        parts.append(f"{i // 2 + 1}.{san}" if i % 2 == 0 else san)
    return " ".join(parts)


def identify_opening(report: dict, chunks: list[Chunk]) -> Optional[tuple[Chunk, str]]:
    """ECO 헤더 -> (없거나 맞는 노트가 없으면) 첫 수들의 최장 일치 순으로 오프닝 노트를 찾는다."""
    openings = [c for c in chunks if c.kind == "opening"]
    eco = ((report.get("game") or {}).get("eco") or "").strip().upper()
    if re.match(r"^[A-E]\d{2}$", eco):
        hits = [c for c in openings if eco_contains(c.eco, eco)]
        if hits:
            return min(hits, key=lambda c: (eco_span(c.eco, eco), c.id)), "eco"
    sans = [normalize_san(s) for s in (report.get("opening_moves") or [])]
    best: Optional[Chunk] = None
    best_len = 0
    for c in openings:
        for alt in c.moves:
            if len(alt) <= len(sans) and sans[: len(alt)] == alt and len(alt) > best_len:
                best, best_len = c, len(alt)
    return (best, "moves") if best else None


def _rank(query: Query, retriever: Retriever) -> list[tuple[float, Chunk]]:
    out: list[tuple[float, Chunk]] = []
    raw_scores = retriever.raw_scores(query.text) if query.text else [0.0] * len(retriever.chunks)
    for chunk, raw in zip(retriever.chunks, raw_scores):
        if chunk.kind == "opening":  # 오프닝 노트는 오프닝 판별 경로로만 쓴다
            continue
        sat = raw / (raw + BM25_SAT) if raw > 0 else 0.0
        overlap = min(sum(w for k, w in query.concepts.items() if k in chunk.tags), 3.0)
        if chunk.tags:
            score = overlap + BM25_WEIGHT * sat
        elif raw >= BOOK_MIN_RAW:
            score = MIN_SCORE + BM25_WEIGHT * sat
        else:
            continue
        if chunk.phase and query.phase:
            score += PHASE_MATCH_BONUS if chunk.phase == query.phase else -PHASE_MISMATCH_PENALTY
        if score >= MIN_SCORE:
            out.append((score, chunk))
    out.sort(key=lambda x: (-x[0], x[1].id))
    return out


def _pick_top(ranked: list[tuple[float, Chunk]], top_k: int) -> list[tuple[float, Chunk]]:
    """상위 k개. 사용자가 넣은 책 조각이 후보에 있으면 최소 한 자리는 보장한다."""
    top = ranked[:top_k]
    if top_k >= 2 and not any(c.origin == "user" for _, c in top):
        user = next(((s, c) for s, c in ranked if c.origin == "user"), None)
        if user:
            top = top[: top_k - 1] + [user]
    return top


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    ends = [m.end() for m in re.finditer(r"[.!?](?:\s|$)", cut)]
    if ends and ends[-1] >= max_chars * 0.5:
        return cut[: ends[-1]].rstrip()
    return cut.rstrip() + "…"


def retrieve_for_report(
    report: dict,
    kb: KnowledgeBase,
    *,
    top_k: int = DEFAULT_TOP_K,
    budget_chars: int = DEFAULT_BUDGET_CHARS,
    max_item_chars: int = MAX_ITEM_CHARS,
) -> dict:
    """프롬프트에 넣을 참고 자료 묶음을 만든다.

    반환 형식:
      items:    [{"id": "K1", "title", "source", "text"}]  (프롬프트에 들어가는 순서)
      game:     오프닝 노트 id 목록
      moments:  {장면 label: [K id]}
      facts:    {장면 label: [코드가 확인한 포지션 사실 문장]}
      opening:  {"family", "matched_by", "line"} 또는 {"line"} 또는 None
    """
    moments = report.get("critical_moments") or []
    result: dict = {"items": [], "game": [], "moments": {}, "facts": {}, "opening": None}
    retriever = Retriever(kb.chunks) if kb.chunks else None

    line = format_line([normalize_san(s) for s in (report.get("opening_moves") or [])[:OPENING_PLIES]])
    found = identify_opening(report, kb.chunks)
    if found:
        result["opening"] = {"family": found[0].title, "matched_by": found[1]}
        if line:
            result["opening"]["line"] = line
    elif line:
        result["opening"] = {"line": line}

    # 후보 수집
    candidates: dict[str, list[tuple[float, Chunk]]] = {}
    for m in moments:
        q = build_query(m)
        if q.facts:
            result["facts"][m["label"]] = q.facts
        candidates[m["label"]] = _pick_top(_rank(q, retriever), top_k) if retriever else []

    # 예산 안에서 선택: 오프닝 노트 -> 전환점 장면 -> 나머지 장면
    order: list[tuple[Optional[str], Chunk]] = []
    if found:
        order.append((None, found[0]))
    for m in sorted(moments, key=lambda m: (not m.get("turning_point"), m.get("ply", 0))):
        order.extend((m["label"], c) for _, c in candidates[m["label"]])

    texts: dict[str, str] = {}
    chunk_by_id: dict[str, Chunk] = {}
    game_ids: list[str] = []
    moment_ids: dict[str, list[str]] = {m["label"]: [] for m in moments}
    used = 0
    for label, chunk in order:
        if chunk.id not in texts:
            text = _trim(chunk.text, max_item_chars)
            if used + len(text) > budget_chars:
                continue
            texts[chunk.id], chunk_by_id[chunk.id] = text, chunk
            used += len(text)
        target = game_ids if label is None else moment_ids[label]
        if chunk.id not in target:
            target.append(chunk.id)

    # 오프닝 국면의 장면에는 판별된 오프닝 노트도 함께 연결
    if found and found[0].id in texts:
        for m in moments:
            if m.get("phase") == "opening" and found[0].id not in moment_ids[m["label"]]:
                moment_ids[m["label"]].insert(0, found[0].id)

    # 프롬프트에 나오는 순서(오프닝 -> 장면 시간순)대로 K 번호 부여
    numbering: dict[str, str] = {}
    sequence = list(game_ids)
    for m in sorted(moments, key=lambda m: m.get("ply", 0)):
        sequence.extend(moment_ids[m["label"]])
    for cid in sequence:
        if cid not in numbering:
            numbering[cid] = f"K{len(numbering) + 1}"
    result["items"] = [
        {"id": kid, "title": chunk_by_id[cid].title, "source": chunk_by_id[cid].source, "text": texts[cid]}
        for cid, kid in numbering.items()
    ]
    result["game"] = [numbering[c] for c in game_ids]
    result["moments"] = {label: [numbering[c] for c in ids] for label, ids in moment_ids.items() if ids}
    return result


def has_content(knowledge: Optional[dict]) -> bool:
    if not knowledge:
        return False
    return bool(knowledge.get("items") or knowledge.get("opening") or any((knowledge.get("facts") or {}).values()))


def search_text(kb: KnowledgeBase, query: str, *, phase: Optional[str] = None, top_k: int = 5) -> list[tuple[float, Chunk]]:
    """kb search 용: 자유 텍스트로 지식 베이스를 직접 검색."""
    return Retriever(kb.chunks).search(query, top_k=top_k, phase=phase)
