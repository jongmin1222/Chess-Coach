"""데이터 구조. 이 모듈은 python-chess에 의존하지 않습니다."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# 강제 메이트를 센티폰 값으로 환산할 때 쓰는 기준값
MATE_CP = 10_000
# |cp| 가 이 값 이상이면 "강제 메이트가 보이는 평가"로 간주
MATE_THRESHOLD = MATE_CP - 1_000


@dataclass
class PositionEval:
    """엔진이 한 포지션에 내린 평가. cp/mate 는 항상 백 기준(White POV)."""

    cp: int
    mate: Optional[int] = None  # 백 기준 메이트까지 남은 ply. 없으면 None, 이미 체크메이트면 0
    best_move: Optional[str] = None  # UCI 표기
    pv: list[str] = field(default_factory=list)  # UCI 표기 주요 변화


@dataclass
class MoveAnalysis:
    """한 수에 대한 분석 결과. 승률(win_*)은 '그 수를 둔 쪽' 기준입니다."""

    ply: int
    move_number: int
    color: str  # "white" | "black"
    san: str
    uci: str
    label: str  # 예: "3...Nf6"
    fen_before: str
    phase: str  # "opening" | "middlegame" | "endgame"
    cp_before: int  # 백 기준
    cp_after: int  # 백 기준
    eval_before: str
    eval_after: str
    win_before: float
    win_after: float
    win_loss: float  # 이 수로 잃은 승률(%p). 0 이상
    classification: str  # best | good | inaccuracy | mistake | blunder
    best_san: Optional[str]
    best_uci: Optional[str]
    best_line: list[str]  # 엔진 최선 변화(SAN)
    refutation_san: Optional[str]  # 이 수 뒤 상대의 엔진 최선 응수(SAN)
    tags: list[str]
    is_best: bool


@dataclass
class GameAnalysis:
    headers: dict[str, str]
    moves: list[MoveAnalysis]
    engine_name: str = "Stockfish"
    depth: Optional[int] = None
    movetime: Optional[float] = None
