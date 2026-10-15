from chess_coach.models import MoveAnalysis
from chess_coach.scoring import classify


def make_move(ply, loss, *, color=None, is_best=False, san="Nf3", tags=None, classification=None):
    color = color or ("white" if ply % 2 == 1 else "black")
    number = (ply + 1) // 2
    return MoveAnalysis(
        ply=ply,
        move_number=number,
        color=color,
        san=san,
        uci="g1f3",
        label=f"{number}.{san}" if color == "white" else f"{number}...{san}",
        fen_before="",
        phase="middlegame",
        cp_before=0,
        cp_after=0,
        eval_before="+0.00",
        eval_after="+0.00",
        win_before=50.0,
        win_after=50.0 - loss,
        win_loss=loss,
        classification=classification or classify(loss, is_best),
        best_san="e4",
        best_uci="e2e4",
        best_line=["e4", "e5"],
        refutation_san=None,
        tags=list(tags or []),
        is_best=is_best,
    )
