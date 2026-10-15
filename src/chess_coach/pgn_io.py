"""PGN 파일 읽기 보조."""

from __future__ import annotations

from typing import Mapping, Optional

import chess.pgn

from .errors import ChessCoachError


def read_games(path: str) -> list[chess.pgn.Game]:
    try:
        # utf-8-sig: chess.com 등에서 내려받은 파일의 BOM 제거
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            games: list[chess.pgn.Game] = []
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                games.append(game)
    except OSError as e:
        raise ChessCoachError(f"PGN 파일을 열 수 없습니다: {path} ({e})") from e
    return games


def detect_color(headers: Mapping[str, str], user: Optional[str]) -> Optional[str]:
    """PGN 헤더의 White/Black 이름과 사용자 아이디를 비교해 내 색을 판별한다."""
    if not user:
        return None
    name = user.strip().lower()
    if headers.get("White", "").strip().lower() == name:
        return "white"
    if headers.get("Black", "").strip().lower() == name:
        return "black"
    return None


def describe_game(index: int, game: chess.pgn.Game) -> str:
    h = game.headers
    return (
        f"{index}. {h.get('White', '?')} vs {h.get('Black', '?')} "
        f"({h.get('Result', '*')}) {h.get('Date', '')} {h.get('TimeControl', '')}".rstrip()
    )
