"""분석 결과를 JSON 리포트로 정리. python-chess에 의존하지 않습니다."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Mapping, Optional

from .models import GameAnalysis, MoveAnalysis
from .moments import select_critical_moments
from .scoring import accuracy_from_loss

_CLASSES = ["best", "good", "inaccuracy", "mistake", "blunder"]


def summarize_side(moves: list[MoveAnalysis], color: str) -> dict:
    side = [m for m in moves if m.color == color]
    counts = Counter(m.classification for m in side)
    accuracy = None
    if side:
        accuracy = round(sum(accuracy_from_loss(m.win_loss) for m in side) / len(side), 1)
    out: dict = {"moves": len(side)}
    for c in _CLASSES:
        out[c] = counts.get(c, 0)
    out["accuracy"] = accuracy  # 단순 평균 기반 근사치 (chess.com/Lichess 값과 다를 수 있음)
    return out


OPENING_PLIES = 16


def _game_info(headers: Mapping[str, str]) -> dict:
    keys = {
        "white": "White",
        "black": "Black",
        "white_elo": "WhiteElo",
        "black_elo": "BlackElo",
        "result": "Result",
        "date": "Date",
        "event": "Event",
        "site": "Site",
        "time_control": "TimeControl",
        "termination": "Termination",
        "eco": "ECO",
        "eco_url": "ECOUrl",
        "opening": "Opening",
    }
    return {k: headers[h] for k, h in keys.items() if h in headers}


def _move_to_dict(m: MoveAnalysis) -> dict:
    d = asdict(m)
    for k in ("win_before", "win_after", "win_loss"):
        d[k] = round(d[k], 1)
    return d


def build_report(
    analysis: GameAnalysis,
    *,
    side: Optional[str] = None,
    max_moments: int = 5,
    min_severity: str = "mistake",
    include_moves: bool = False,
) -> dict:
    report: dict = {
        "game": _game_info(analysis.headers),
        "analyzed_side": side,
        "engine": {
            "name": analysis.engine_name,
            "depth": analysis.depth,
            "movetime": analysis.movetime,
        },
        "total_plies": len(analysis.moves),
        # 오프닝 판별(RAG)용: 게임의 첫 수들(SAN)
        "opening_moves": [m.san for m in analysis.moves[:OPENING_PLIES]],
        "summary": {
            "white": summarize_side(analysis.moves, "white"),
            "black": summarize_side(analysis.moves, "black"),
        },
        "critical_moments": select_critical_moments(
            analysis.moves,
            color=side,
            max_moments=max_moments,
            min_severity=min_severity,
        ),
    }
    if include_moves:
        report["moves"] = [_move_to_dict(m) for m in analysis.moves]
    return report
