"""PGN 한 판 -> 수별 분석. 엔진은 evaluate(board) -> PositionEval 만 구현하면 된다."""

from __future__ import annotations

from typing import Callable, Mapping, Optional, Protocol

import chess
import chess.pgn

from .models import (
    MATE_CP,
    MATE_THRESHOLD,
    GameAnalysis,
    MoveAnalysis,
    PositionEval,
)
from .scoring import DEFAULT_THRESHOLDS, classify, format_eval, win_percent


class Evaluator(Protocol):
    def evaluate(self, board: chess.Board) -> PositionEval: ...


_NON_PAWN_VALUES = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
_MAJOR_OR_MINOR = {"knight", "bishop", "rook", "queen"}


def game_phase(board: chess.Board) -> str:
    """단순 휴리스틱: 폰·킹을 뺀 기물 가치 합이 26 이하면 엔드게임, 그 외 10수 이내면 오프닝."""
    material = sum(
        value * len(board.pieces(piece_type, color))
        for piece_type, value in _NON_PAWN_VALUES.items()
        for color in (chess.WHITE, chess.BLACK)
    )
    if material <= 26:
        return "endgame"
    if board.fullmove_number <= 10:
        return "opening"
    return "middlegame"


def terminal_eval(board: chess.Board) -> Optional[PositionEval]:
    """이미 끝난 포지션은 엔진 없이 직접 평가한다."""
    if board.is_checkmate():
        white_wins = board.turn == chess.BLACK  # 차례인 쪽이 메이트당함
        return PositionEval(cp=MATE_CP if white_wins else -MATE_CP, mate=0)
    if board.is_stalemate() or board.is_insufficient_material():
        return PositionEval(cp=0)
    return None


def _captured_piece_name(board: chess.Board, move: chess.Move) -> Optional[str]:
    if not board.is_capture(move):
        return None
    if board.is_en_passant(move):
        return "pawn"
    piece_type = board.piece_type_at(move.to_square)
    return chess.piece_name(piece_type) if piece_type else None


def _safe_move(board: chess.Board, uci: Optional[str]) -> Optional[chess.Move]:
    if not uci:
        return None
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def _pv_to_san(board: chess.Board, pv_uci: list[str], limit: int = 6) -> list[str]:
    b = board.copy(stack=False)
    out: list[str] = []
    for uci in pv_uci[:limit]:
        move = _safe_move(b, uci)
        if move is None:
            break
        out.append(b.san(move))
        b.push(move)
    return out


def _make_tags(
    board_before: chess.Board,
    board_after: chess.Board,
    move: chess.Move,
    before: PositionEval,
    after: PositionEval,
    mover_white: bool,
    win_loss: float,
    thresholds: Mapping[str, float],
) -> list[str]:
    """규칙 기반 힌트 태그. LLM이 이유를 지어내지 않도록 근거를 주는 용도."""
    sign = 1 if mover_white else -1
    mover_before = sign * before.cp
    mover_after = sign * after.cp
    tags: list[str] = []

    if mover_before >= MATE_THRESHOLD and mover_after < MATE_THRESHOLD:
        tags.append("missed_mate")
    if mover_after <= -MATE_THRESHOLD and mover_before > -MATE_THRESHOLD:
        tags.append("allowed_mate")

    if win_loss >= thresholds["inaccuracy"]:
        best = _safe_move(board_before, before.best_move)
        if best is not None and not board_before.is_capture(move):
            cap = _captured_piece_name(board_before, best)
            if cap:
                tags.append(f"missed_capture_of_{cap}")

        reply = _safe_move(board_after, after.best_move)
        if reply is not None:
            cap = _captured_piece_name(board_after, reply)
            if cap:
                tags.append(f"allowed_capture_of_{cap}")
                if reply.to_square == move.to_square and cap in _MAJOR_OR_MINOR:
                    tags.append("hung_moved_piece")
    return tags


def analyze_game(
    game: chess.pgn.Game,
    engine: Evaluator,
    *,
    thresholds: Optional[Mapping[str, float]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> GameAnalysis:
    th = dict(thresholds or DEFAULT_THRESHOLDS)

    start = game.board()
    played = list(game.mainline_moves())
    cursor = start.copy(stack=False)
    boards = [start.copy(stack=False)]
    for mv in played:
        cursor.push(mv)
        boards.append(cursor.copy(stack=False))

    evals: list[PositionEval] = []
    for i, b in enumerate(boards):
        ev = terminal_eval(b)
        if ev is None:
            ev = engine.evaluate(b)
        evals.append(ev)
        if progress:
            progress(i + 1, len(boards))

    moves: list[MoveAnalysis] = []
    for i, mv in enumerate(played):
        board_before, board_after = boards[i], boards[i + 1]
        before, after = evals[i], evals[i + 1]
        mover_white = board_before.turn == chess.WHITE
        sign = 1 if mover_white else -1

        win_before = win_percent(sign * before.cp)
        win_after = win_percent(sign * after.cp)
        played_uci = mv.uci()
        is_best = before.best_move is not None and before.best_move == played_uci
        win_loss = 0.0 if is_best else max(0.0, win_before - win_after)

        san = board_before.san(mv)
        number = board_before.fullmove_number
        best_move = _safe_move(board_before, before.best_move)
        best_line = _pv_to_san(board_before, before.pv or ([before.best_move] if before.best_move else []))
        reply = _safe_move(board_after, after.best_move)

        moves.append(
            MoveAnalysis(
                ply=i + 1,
                move_number=number,
                color="white" if mover_white else "black",
                san=san,
                uci=played_uci,
                label=f"{number}.{san}" if mover_white else f"{number}...{san}",
                fen_before=board_before.fen(),
                phase=game_phase(board_before),
                cp_before=before.cp,
                cp_after=after.cp,
                eval_before=format_eval(before.cp, before.mate),
                eval_after=format_eval(after.cp, after.mate),
                win_before=win_before,
                win_after=win_after,
                win_loss=win_loss,
                classification=classify(win_loss, is_best, th),
                best_san=board_before.san(best_move) if best_move else None,
                best_uci=before.best_move,
                best_line=best_line,
                refutation_san=board_after.san(reply) if reply else None,
                tags=_make_tags(board_before, board_after, mv, before, after, mover_white, win_loss, th),
                is_best=is_best,
            )
        )

    return GameAnalysis(
        headers=dict(game.headers),
        moves=moves,
        engine_name=getattr(engine, "name", "unknown"),
        depth=getattr(engine, "depth", None),
        movetime=getattr(engine, "movetime", None),
    )
