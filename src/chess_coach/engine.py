"""Stockfish(UCI) 래퍼."""

from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path
from typing import Optional

import chess
import chess.engine

from .errors import EngineNotFoundError
from .models import MATE_CP, PositionEval

_INSTALL_HINT = (
    "Stockfish를 찾지 못했습니다.\n"
    "  1) https://stockfishchess.org/download/ 에서 내 OS용 파일을 받아 압축을 풀거나\n"
    "     (Ubuntu/Debian: sudo apt install stockfish — /usr/games/stockfish 에 설치됨)\n"
    "  2) .env 에 STOCKFISH_PATH=<실행파일 전체 경로> 를 적거나, --engine <경로> 옵션을 사용하세요."
)

_SEARCH_GLOBS = [
    "C:/stockfish/stockfish*.exe",
    "C:/stockfish/*/stockfish*.exe",
    "C:/Program Files/stockfish/stockfish*.exe",
    "~/stockfish/stockfish*",
    "~/stockfish/*/stockfish*",
    "/usr/games/stockfish",
    "/usr/local/bin/stockfish",
    "/opt/homebrew/bin/stockfish",
]


def _looks_like_binary(path: str) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    return p.suffix.lower() in ("", ".exe")


def find_stockfish(explicit: Optional[str] = None) -> str:
    """--engine 옵션 > STOCKFISH_PATH 환경변수 > PATH > 흔한 설치 위치 순으로 찾는다."""
    if explicit:
        if Path(explicit).is_file():
            return explicit
        raise EngineNotFoundError(f"--engine 경로에 파일이 없습니다: {explicit}")

    env = os.environ.get("STOCKFISH_PATH")
    if env:
        if Path(env).is_file():
            return env
        raise EngineNotFoundError(f"STOCKFISH_PATH 경로에 파일이 없습니다: {env}")

    found = shutil.which("stockfish")
    if found:
        return found

    for pattern in _SEARCH_GLOBS:
        for candidate in sorted(glob.glob(os.path.expanduser(pattern))):
            if Path(candidate).name.lower().startswith("stockfish") and _looks_like_binary(candidate):
                return candidate

    raise EngineNotFoundError(_INSTALL_HINT)


class StockfishEngine:
    """with 문으로 사용한다. evaluate(board) 가 PositionEval 을 돌려준다."""

    def __init__(
        self,
        path: str,
        *,
        depth: Optional[int] = 16,
        movetime: Optional[float] = None,
        threads: Optional[int] = None,
        hash_mb: int = 256,
    ) -> None:
        self.path = path
        self.depth = None if movetime else depth
        self.movetime = movetime
        self.threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self.hash_mb = hash_mb
        self.name = "Stockfish"
        self._engine: Optional[chess.engine.SimpleEngine] = None
        if movetime:
            self._limit = chess.engine.Limit(time=movetime)
        else:
            self._limit = chess.engine.Limit(depth=depth or 16)

    def __enter__(self) -> "StockfishEngine":
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(str(self.path))
        except (OSError, chess.engine.EngineError) as e:
            raise EngineNotFoundError(f"Stockfish를 실행하지 못했습니다: {self.path}\n{e}") from e
        self.name = self._engine.id.get("name", "Stockfish")
        try:
            self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        except chess.engine.EngineError:
            pass  # 옵션을 지원하지 않는 엔진이면 기본값 사용
        return self

    def __exit__(self, *exc) -> None:
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                pass
            self._engine = None

    def evaluate(self, board: chess.Board) -> PositionEval:
        assert self._engine is not None, "with StockfishEngine(...) 안에서 사용하세요"
        info = self._engine.analyse(board, self._limit)
        white = info["score"].white()
        pv = info.get("pv", [])
        return PositionEval(
            cp=white.score(mate_score=MATE_CP),
            mate=white.mate(),
            best_move=pv[0].uci() if pv else None,
            pv=[m.uci() for m in pv],
        )
