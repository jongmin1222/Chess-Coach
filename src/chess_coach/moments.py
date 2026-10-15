"""'배울 만한 핵심 장면' 선별. python-chess에 의존하지 않습니다."""

from __future__ import annotations

from typing import Mapping, Optional

from .models import MoveAnalysis
from .scoring import DEFAULT_THRESHOLDS, SEVERITY_ORDER


def _to_dict(m: MoveAnalysis, turning_point: bool) -> dict:
    return {
        "label": m.label,
        "ply": m.ply,
        "move_number": m.move_number,
        "color": m.color,
        "phase": m.phase,
        "played": m.san,
        "classification": m.classification,
        "win_loss": round(m.win_loss, 1),
        "win_before": round(m.win_before, 1),
        "win_after": round(m.win_after, 1),
        "eval_before": m.eval_before,
        "eval_after": m.eval_after,
        "best_move": m.best_san,
        "best_line": list(m.best_line),
        "refutation": m.refutation_san,
        "tags": list(m.tags),
        "fen_before": m.fen_before,
        "turning_point": turning_point,
    }


def select_critical_moments(
    moves: list[MoveAnalysis],
    *,
    color: Optional[str] = None,
    max_moments: int = 5,
    min_severity: str = "mistake",
    min_gap_plies: int = 4,
    thresholds: Optional[Mapping[str, float]] = None,
) -> list[dict]:
    """승률을 크게 잃은 수를 골라 시간순으로 반환한다.

    - color 를 주면 그 색이 둔 수만 대상으로 한다.
    - min_severity 이상인 수가 하나도 없으면 'inaccuracy' 까지 기준을 낮춘다.
    - 같은 색이 둔 수끼리 너무 가까우면(min_gap_plies 미만) 같은 사건으로 보고 더 큰 쪽만 남긴다.
      (백의 블런더와 흑의 블런더는 서로 다른 교훈이므로 함께 남긴다.)
    - 가장 크게 잃은 수에는 turning_point=True 를 붙인다.
    """
    if min_severity not in SEVERITY_ORDER:
        raise ValueError(f"min_severity must be one of {SEVERITY_ORDER}")
    th = thresholds or DEFAULT_THRESHOLDS
    pool = [m for m in moves if color is None or m.color == color]

    def pick(min_loss: float) -> list[MoveAnalysis]:
        candidates = sorted(
            (m for m in pool if m.win_loss >= min_loss and not m.is_best),
            key=lambda m: m.win_loss,
            reverse=True,
        )
        chosen: list[MoveAnalysis] = []
        for m in candidates:
            if all(c.color != m.color or abs(m.ply - c.ply) >= min_gap_plies for c in chosen):
                chosen.append(m)
            if len(chosen) >= max_moments:
                break
        return chosen

    chosen = pick(th[min_severity])
    if not chosen:
        chosen = pick(th["inaccuracy"])
    chosen.sort(key=lambda m: m.ply)
    if not chosen:
        return []
    worst = max(chosen, key=lambda m: m.win_loss)
    return [_to_dict(m, turning_point=(m is worst)) for m in chosen]
