#!/usr/bin/env bash
# chess-coach 리눅스 설치 도우미.
#   bash scripts/setup_linux.sh
# 하는 일: 가상환경 생성 -> 패키지 설치 -> .env 준비 -> Stockfish / Ollama / 모델 상태 점검
# sudo 는 쓰지 않습니다. 필요한 설치 명령은 안내만 합니다.
set -euo pipefail

cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
MODEL="${CHESS_COACH_MODEL:-qwen2.5:7b}"
OLLAMA_HOST_URL="${OLLAMA_HOST:-http://localhost:11434}"

step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '  [OK]   %s\n' "$*"; }
warn() { printf '  [할일] %s\n' "$*"; }

step "1/5 Python 확인"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "python3 를 찾을 수 없습니다. (Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip)"
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 이상이 필요합니다. 현재: $("$PYTHON" --version 2>&1)"
  exit 1
fi
ok "$("$PYTHON" --version 2>&1)"

step "2/5 가상환경(.venv) + 패키지 설치"
if [ ! -d .venv ]; then
  if ! "$PYTHON" -m venv .venv; then
    echo "venv 생성 실패. (Ubuntu/Debian: sudo apt install python3-venv)"
    rm -rf .venv
    exit 1
  fi
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[dev]"
ok "chess-coach $(python -c 'import chess_coach; print(chess_coach.__version__)') 설치 완료"

step "3/5 .env 준비"
if [ ! -f .env ]; then
  cp .env.example .env
  ok ".env 를 만들었습니다 (필요하면 편집하세요)"
else
  ok ".env 가 이미 있습니다"
fi

step "4/5 Stockfish 확인"
SF=""
if command -v stockfish >/dev/null 2>&1; then
  SF="$(command -v stockfish)"
elif [ -x /usr/games/stockfish ]; then
  SF="/usr/games/stockfish"   # Debian/Ubuntu 의 apt 패키지는 여기에 설치됩니다
fi
if [ -n "$SF" ]; then
  ok "Stockfish: $SF"
else
  warn "Stockfish 가 없습니다. 아래 중 하나로 설치한 뒤 .env 의 STOCKFISH_PATH 를 설정하세요."
  echo "         Ubuntu/Debian : sudo apt install stockfish"
  echo "         Fedora        : sudo dnf install stockfish"
  echo "         Arch          : sudo pacman -S stockfish"
  echo "         직접 설치     : https://stockfishchess.org/download/ (Linux 빌드 압축 해제)"
fi

step "5/5 Ollama / 모델($MODEL) 확인 — coach 명령에만 필요"
if ! command -v ollama >/dev/null 2>&1; then
  warn "Ollama 가 없습니다. 설치: curl -fsSL https://ollama.com/install.sh | sh"
  echo "         (analyze 명령은 Ollama 없이도 사용할 수 있습니다)"
elif ! command -v curl >/dev/null 2>&1 || ! curl -fsS "$OLLAMA_HOST_URL/api/tags" >/dev/null 2>&1; then
  warn "Ollama 서버가 응답하지 않습니다. 시작: ollama serve  (systemd 설치라면 sudo systemctl start ollama)"
elif ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$MODEL"; then
  ok "모델 $MODEL 준비됨"
else
  warn "모델이 없습니다. 받기(약 5GB): ollama pull $MODEL"
fi

cat <<MSG

설치 점검이 끝났습니다. 사용 시작:

  source .venv/bin/activate
  chess-coach analyze examples/sample_game.pgn --color black
  chess-coach coach   examples/sample_game.pgn --color black --level beginner

MSG
