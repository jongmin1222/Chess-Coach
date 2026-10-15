"""chess.com 공개 API(Published-Data API)에서 최근 게임 PGN 가져오기.

사용 전 chess.com 이용 약관과 API 정책을 확인하세요. 호출 사이에 짧은 간격을 둡니다.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional

from .config import chesscom_user_agent
from .errors import FetchError

BASE_URL = "https://api.chess.com/pub"


def _get_json(url: str, user_agent: str, timeout: float = 20.0) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FetchError("chess.com에서 해당 사용자를 찾을 수 없습니다. 아이디를 확인하세요.") from e
        if e.code == 429:
            raise FetchError("chess.com 요청 제한에 걸렸습니다. 잠시 후 다시 시도하세요.") from e
        raise FetchError(f"chess.com API 오류 (HTTP {e.code}): {url}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"chess.com에 연결할 수 없습니다. 인터넷 연결을 확인하세요. ({e.reason})") from e


def fetch_recent_games(
    username: str,
    count: int = 5,
    time_class: Optional[str] = None,
    user_agent: Optional[str] = None,
    pause: float = 0.3,
) -> list[str]:
    """최근 게임 PGN 문자열을 최신순으로 최대 count개 반환한다.

    time_class: "bullet" | "blitz" | "rapid" | "daily" (None 이면 전부)
    """
    user = username.strip().lower()
    if not user:
        raise FetchError("사용자 아이디가 비어 있습니다.")
    ua = user_agent or chesscom_user_agent()

    data = _get_json(f"{BASE_URL}/player/{user}/games/archives", ua)
    archives = data.get("archives", [])
    if not archives:
        raise FetchError("이 사용자의 게임 기록(아카이브)이 없습니다.")

    pgns: list[str] = []
    for url in reversed(archives):  # 최신 달부터
        month = _get_json(url, ua)
        for game in reversed(month.get("games", [])):  # 달 안에서도 최신부터
            if game.get("rules", "chess") != "chess":
                continue  # 변형 규칙(체스960 등)은 제외
            if time_class and game.get("time_class") != time_class:
                continue
            pgn = game.get("pgn")
            if not pgn:
                continue
            pgns.append(pgn.strip())
            if len(pgns) >= count:
                return pgns
        time.sleep(pause)
    return pgns
