"""FEN 문자열만으로 계산하는 포지션 사실(facts). python-chess에 의존하지 않습니다.

여기서 만든 문장은 코드가 직접 확인한 사실이라서, LLM이 '이 장면의 근거'로 인용해도 됩니다.
(RAG로 가져온 일반 원칙과 구분하기 위한 용도입니다.)
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

_FILES = "abcdefgh"
_HOME_MINORS = {
    "w": {"b1": "N", "g1": "N", "c1": "B", "f1": "B"},
    "b": {"b8": "n", "g8": "n", "c8": "b", "f8": "b"},
}
_KING_HOME = {"w": ("e1", "K"), "b": ("e8", "k")}
_QUEEN_HOME = {"w": ("d1", "Q"), "b": ("d8", "q")}


def parse_fen(fen: str) -> tuple[dict[str, str], str, int]:
    """FEN -> (칸->기물 글자, 차례 'w'/'b', 풀무브 번호). 형식이 이상하면 ValueError."""
    fields = fen.split()
    if len(fields) < 2:
        raise ValueError("FEN 필드가 부족합니다")
    rows = fields[0].split("/")
    if len(rows) != 8:
        raise ValueError("FEN 랭크 수가 8이 아닙니다")
    board: dict[str, str] = {}
    for i, row in enumerate(rows):
        rank, file = 8 - i, 0
        for ch in row:
            if ch.isdigit():
                file += int(ch)
            else:
                if file > 7:
                    raise ValueError("FEN 한 랭크가 8칸을 넘습니다")
                board[f"{_FILES[file]}{rank}"] = ch
                file += 1
    if fields[1] not in ("w", "b"):
        raise ValueError("FEN 차례 표기가 올바르지 않습니다")
    fullmove = int(fields[5]) if len(fields) >= 6 and fields[5].isdigit() else 1
    return board, fields[1], fullmove


def _is_light(square: str) -> bool:
    return (_FILES.index(square[0]) + int(square[1])) % 2 == 0


def _passed_pawns(board: dict[str, str], white: bool) -> int:
    mine, theirs = ("P", "p") if white else ("p", "P")
    enemy = [(_FILES.index(s[0]), int(s[1])) for s, p in board.items() if p == theirs]
    count = 0
    for sq, p in board.items():
        if p != mine:
            continue
        f, r = _FILES.index(sq[0]), int(sq[1])
        blocked = any(abs(ef - f) <= 1 and ((er > r) if white else (er < r)) for ef, er in enemy)
        if not blocked:
            count += 1
    return count


def position_facts(fen: Optional[str], phase: Optional[str] = None) -> list[tuple[str, str]]:
    """(키, 한국어 사실 문장) 목록. 수를 두기 전 포지션 기준이며, '수를 둔 쪽' 시점으로 서술한다."""
    if not fen:
        return []
    try:
        board, turn, fullmove = parse_fen(fen)
    except ValueError:
        return []

    facts: list[tuple[str, str]] = []
    pieces = list(board.values())
    undeveloped = sum(1 for sq, p in _HOME_MINORS[turn].items() if board.get(sq) == p)

    if phase != "endgame":
        king_sq, king = _KING_HOME[turn]
        opp_queen = "q" if turn == "w" else "Q"
        if fullmove >= 8 and board.get(king_sq) == king and opp_queen in pieces:
            facts.append(("king_in_center", "이 수를 두기 전, 킹이 아직 초기 위치(e파일)에 있고 캐슬링을 하지 않은 상태였습니다."))
        if fullmove >= 8 and undeveloped >= 2:
            facts.append(("undeveloped_minors", f"이 수를 두기 전, 아직 처음 자리에 있는 나이트·비숍이 {undeveloped}개 있었습니다."))
        q_sq, q = _QUEEN_HOME[turn]
        if fullmove <= 8 and q in pieces and board.get(q_sq) != q and undeveloped >= 2:
            facts.append(("queen_out_early", f"이 수를 두기 전, 퀸이 이미 초기 위치를 떠나 있었고 아직 제자리에 있는 나이트·비숍이 {undeveloped}개 있었습니다."))

    counts = Counter(p.lower() for p in pieces)
    n, b, r, q_cnt, pawns = (counts[k] for k in "nbrqp")
    if n + b + r + q_cnt == 0 and pawns > 0:
        facts.append(("pawn_endgame", "이 수를 두기 전 포지션은 킹과 폰만 남은 폰 엔드게임이었습니다."))
    elif r > 0 and n + b + q_cnt == 0:
        facts.append(("rook_endgame", "이 수를 두기 전 포지션은 룩과 폰만 남은 룩 엔드게임이었습니다."))
    elif q_cnt > 0 and n + b + r == 0:
        facts.append(("queen_endgame", "이 수를 두기 전 포지션은 퀸과 폰만 남은 퀸 엔드게임이었습니다."))
    elif n + b > 0 and q_cnt + r == 0:
        facts.append(("minor_piece_endgame", "이 수를 두기 전 포지션은 나이트·비숍과 폰만 남은 엔드게임이었습니다."))

    if n == 0 and r == 0 and q_cnt == 0:
        wb = [sq for sq, p in board.items() if p == "B"]
        bb = [sq for sq, p in board.items() if p == "b"]
        if len(wb) == 1 and len(bb) == 1 and _is_light(wb[0]) != _is_light(bb[0]):
            facts.append(("opposite_colored_bishops", "이 수를 두기 전, 양쪽에 서로 다른 색 칸의 비숍이 하나씩 남아 있었습니다."))

    if phase == "endgame":
        mine = _passed_pawns(board, turn == "w")
        theirs = _passed_pawns(board, turn != "w")
        if mine:
            facts.append(("passed_pawn_mover", f"이 수를 두기 전, 수를 둔 쪽에 통과폰이 {mine}개 있었습니다."))
        if theirs:
            facts.append(("passed_pawn_opponent", f"이 수를 두기 전, 상대에게 통과폰이 {theirs}개 있었습니다."))
    return facts
