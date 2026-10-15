"""평가값 계산: 승률 변환, 정확도, 수 분류. python-chess에 의존하지 않습니다."""

from __future__ import annotations

import math
from typing import Mapping, Optional

from .models import MATE_CP, MATE_THRESHOLD

# 승률 손실(%p) 기준. Lichess 방식을 참고한 값이며 필요하면 조정할 수 있습니다.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "inaccuracy": 5.0,
    "mistake": 10.0,
    "blunder": 20.0,
}

SEVERITY_ORDER = ["inaccuracy", "mistake", "blunder"]


def win_percent(cp: float) -> float:
    """센티폰(해당 색 기준) -> 승률(0~100). Lichess가 공개한 로지스틱 근사식."""
    cp = max(-MATE_CP, min(MATE_CP, cp))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def accuracy_from_loss(win_loss: float) -> float:
    """한 수의 승률 손실 -> 정확도(0~100). Lichess의 수 정확도 공식 기반 근사."""
    loss = max(0.0, win_loss)
    acc = 103.1668 * math.exp(-0.04354 * loss) - 3.1669
    return max(0.0, min(100.0, acc))


def classify(
    win_loss: float,
    is_best: bool,
    thresholds: Optional[Mapping[str, float]] = None,
) -> str:
    th = thresholds or DEFAULT_THRESHOLDS
    if is_best:
        return "best"
    if win_loss >= th["blunder"]:
        return "blunder"
    if win_loss >= th["mistake"]:
        return "mistake"
    if win_loss >= th["inaccuracy"]:
        return "inaccuracy"
    return "good"


def is_mate_cp(cp: float) -> bool:
    return abs(cp) >= MATE_THRESHOLD


def format_eval(cp: int, mate: Optional[int]) -> str:
    """백 기준 평가 문자열. 예: '+0.35', '-1.20', '+M3', 'checkmate'."""
    if mate is not None:
        if mate == 0:
            return "checkmate"
        moves = (abs(mate) + 1) // 2
        return f"{'+' if mate > 0 else '-'}M{moves}"
    return f"{cp / 100:+.2f}"
