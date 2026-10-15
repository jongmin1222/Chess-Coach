"""설정 로딩. 외부 의존성 없이 아주 단순한 .env 파서를 사용합니다."""

from __future__ import annotations

import os
from pathlib import Path

from . import __version__

DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def load_dotenv(path: str | Path = ".env") -> None:
    """현재 폴더의 .env 를 읽어 환경변수로 등록한다. 이미 설정된 값은 덮어쓰지 않는다."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            os.environ.setdefault(key, value)


def default_model() -> str:
    return os.environ.get("CHESS_COACH_MODEL") or DEFAULT_MODEL


def ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST


def chesscom_user_agent() -> str:
    contact = os.environ.get("CHESSCOM_CONTACT") or "no-contact-provided"
    return f"chess-coach/{__version__} (contact: {contact})"


DEFAULT_KB_DIR = "knowledge"


def kb_dir() -> str:
    """내 책/노트를 두는 폴더. 현재 폴더 기준 `knowledge/` (환경변수 CHESS_COACH_KB_DIR 로 변경)."""
    return os.environ.get("CHESS_COACH_KB_DIR") or DEFAULT_KB_DIR
