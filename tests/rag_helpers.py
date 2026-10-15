"""RAG 테스트용: python-chess 없이 만드는 가짜 리포트."""

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def moment(label, ply, *, phase="middlegame", tags=(), fen=START, turning_point=False):
    return {
        "label": label,
        "ply": ply,
        "phase": phase,
        "played": label.split(".")[-1],
        "classification": "blunder",
        "win_before": 50.0,
        "win_after": 20.0,
        "eval_before": "+0.00",
        "eval_after": "-3.00",
        "best_move": "Nf3",
        "best_line": ["Nf3"],
        "refutation": None,
        "tags": list(tags),
        "turning_point": turning_point,
        "fen_before": fen,
    }


def report(moments=(), *, eco=None, opening_moves=()):
    game = {"white": "A", "black": "B"}
    if eco:
        game["eco"] = eco
    return {
        "game": game,
        "analyzed_side": "black",
        "summary": {},
        "opening_moves": list(opening_moves),
        "critical_moments": list(moments),
    }
