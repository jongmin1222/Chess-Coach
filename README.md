# Chess-Coach ♟️

내 체스 게임(PGN)을 **Stockfish**로 분석하고, 그 결과를 **내 PC에서 돌아가는 LLM(기본: Qwen2.5-7B)** 에게 넘겨 한국어 복기 피드백을 받는 도구입니다.
서버·유료 API 없이 전부 로컬(리눅스)에서 동작하고, 게임 데이터가 내 PC 밖으로 나가지 않습니다.

> **(v0.2)** PGN → Stockfish 분석 → 핵심 장면 선별 → LLM 피드백(RAG) 까지 동작하는 코어입니다.
> 향후 업데이트 계획은 [로드맵](#로드맵)에 있습니다.

## How it works?

```
PGN 파일 (chess.com 등)
   ↓
Stockfish  ── 수마다 평가값 계산 (승률 손실로 실수/블런더 분류)
   ↓
핵심 장면 선별 ── 게임 전체가 아니라 "배울 만한 몇 장면"만 추림
   ↓
규칙 기반 힌트 ── 놓친 메이트, 공짜로 잡힌 기물 등 근거를 태그로 붙임
   ↓
로컬 LLM (Ollama + Qwen2.5-7B) ── 위 사실들만 근거로 한국어 코칭 문장 작성
```

핵심 설계: **수의 좋고 나쁨은 Stockfish가 판단하고, LLM은 그것을 사람이 이해할 말로 풀어 쓰기만 합니다.**
프롬프트에서 엔진 데이터에 없는 내용은 말하지 못하게 제한합니다.

## Requirements

| 필요한 것 | 용도 | 설치 |
|---|---|---|
| Python 3.10+ (+ venv) | 실행 | `sudo apt install python3 python3-venv python3-pip` |
| Git | 코드 받기 | `sudo apt install git` |
| Stockfish | 수 분석 | `sudo apt install stockfish` |
| Ollama + 모델 | `coach` 명령에서만 필요 | `curl -fsSL https://ollama.com/install.sh \| sh` |

`analyze` 명령(엔진 분석 → JSON)은 Ollama 없이도 동작합니다. 위 명령은 Ubuntu/Debian 기준이며, Fedora는 `dnf`, Arch는 `pacman`으로 같은 패키지를 설치하면 됩니다.

## Quick start

```bash
git clone https://github.com/<내-깃허브-아이디>/chess-coach.git
cd chess-coach
bash scripts/setup_linux.sh
```

스크립트가 하는 일: 가상환경(`.venv`) 생성 → 패키지 설치 → `.env` 준비 → Stockfish / Ollama / 모델 상태 점검.
**sudo는 쓰지 않으며**, 빠진 것이 있으면 설치 명령을 안내만 합니다. 끝나면 가상환경을 켜고 시작하세요.

```bash
source .venv/bin/activate
```

### Manual install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

### Stockfish path

`apt`로 설치하면 `/usr/games/stockfish`에 들어가는데, 이 경로는 자동으로 찾습니다. 직접 받은 바이너리를 쓴다면:

1. [stockfishchess.org/download](https://stockfishchess.org/download/)에서 Linux 빌드를 받아 압축을 풀고 실행 권한을 줍니다. (`chmod +x <파일>`)
2. `.env`에 전체 경로를 적습니다.

```ini
STOCKFISH_PATH=/home/me/stockfish/stockfish-ubuntu-x86-64-avx2
```

`--engine <경로>` 옵션으로도 지정할 수 있습니다. 탐색 순서는 `--engine` → `STOCKFISH_PATH` → PATH → 흔한 설치 위치입니다.

### LLM (Ollama)

```bash
ollama pull qwen2.5:7b      # 처음 한 번, 약 5GB
```

- 기본 모델은 **`qwen2.5:7b`** 입니다. (Apache-2.0)
- 8GB VRAM 급 GPU라면 7B 모델(4bit 양자화)이 GPU 메모리에 들어갑니다. VRAM보다 큰 모델은 일부가 CPU로 넘어가 많이 느려집니다.
- GPU가 없어도 동작하지만 응답까지 몇 분 걸릴 수 있습니다. 저사양이면 `--model qwen2.5:3b`를 써보세요. (품질은 떨어집니다)
- Qwen은 가끔 한국어 답변에 중국어가 섞일 수 있어서, 프롬프트에서 한국어만 쓰도록 지시해 두었습니다. 그래도 섞이면 `--level`을 바꾸거나 다시 실행해 보세요.
- 모델 변경: `--model <이름>` 옵션 또는 `.env`의 `CHESS_COACH_MODEL`. 사용 가능한 이름은 [ollama.com/library](https://ollama.com/library)에서 확인하세요.
- Ollama 서버가 꺼져 있으면 `ollama serve` (systemd로 설치했다면 `sudo systemctl start ollama`).

## Usage

### 0. Example

저장소에 모건의 "오페라 게임"이 들어 있습니다. (백이 이긴 게임이므로 흑 입장에서 분석합니다.)

```bash
chess-coach analyze examples/sample_game.pgn --color black
```

### 1. My own game

```bash
chess-coach fetch <내-chesscom-아이디> --count 5 --time-class rapid
chess-coach games games.pgn          # 게임 목록 확인
```

chess.com 사이트에서 PGN을 직접 내려받아 써도 됩니다. `fetch`는 chess.com 공개 API를 쓰므로 이용 약관과 호출 제한을 지켜주세요. `.env`의 `CHESSCOM_CONTACT`에 연락처를 적어두면 좋습니다.

### 2. Analyze (W/O LLM)

```bash
chess-coach analyze games.pgn --game 1 --user <내-chesscom-아이디> --out result.json
```

- `--user`를 주면 PGN의 White/Black 이름과 비교해서 **내 수만** 분석합니다. 직접 지정하려면 `--color white|black`.
- `--depth 16`(기본): 클수록 정확하지만 느립니다. 빠르게는 `--depth 12`, 정밀하게는 `--depth 20`.
- `--movetime 0.5`: 포지션당 시간(초)으로 제한. 지정하면 `--depth` 대신 사용됩니다.
- `--threads N`: 엔진 스레드 수 (기본: CPU 스레드의 절반)
- `--full`: 모든 수의 분석 결과까지 JSON에 포함.

### 3. Feedback with LLM

```bash
chess-coach coach games.pgn --game 1 --user <내-chesscom-아이디> --level beginner
```

- `--level beginner | intermediate | advanced`: 설명 수준
- `--show-prompt`: LLM을 호출하지 않고 LLM에게 넘어갈 프롬프트만 출력 (디버깅용)
- `--out feedback.md`: 결과를 파일로 저장
- `--no-rag`: 참고 자료 검색을 끄고 엔진 분석만으로 피드백 (기본은 RAG 켜짐)
- `--kb-dir`, `--kb-top-k`, `--kb-budget`: 내 책 폴더 / 장면당 자료 수 / 자료 총량 조절

### 4. RAG: (Opening/Middle game/End game) strategy

내장 노트 49개(오프닝 20개 + 전략·전술·엔드게임 원칙)가 기본으로 검색에 쓰이고, 내가 가진 책을 추가할 수도 있습니다.

```bash
chess-coach kb add ~/books/my-book.epub --title "책 제목" --author "저자" --year 2008
chess-coach kb list
chess-coach kb search "rook behind passed pawn"
```

피드백 끝에는 실제로 인용된 자료만 `## 참고 자료` 로 붙습니다. 

### Report JSON format

```jsonc
{
  "game": { "white": "...", "black": "...", "result": "1-0" },
  "analyzed_side": "black",
  "summary": {
    "white": { "moves": 17, "best": 0, "good": 0, "inaccuracy": 0, "mistake": 0, "blunder": 0, "accuracy": 0.0 },
    "black": { "...": "같은 구조" }
  },
  "critical_moments": [
    {
      "label": "3...Nf6",          // 몇 번째 수인지
      "phase": "opening",          // opening | middlegame | endgame (단순 휴리스틱)
      "classification": "blunder", // best | good | inaccuracy | mistake | blunder
      "win_before": 46.3, "win_after": 0.0, "win_loss": 46.3,   // 그 수를 둔 쪽 기준 승률(%)
      "best_move": "g6", "best_line": ["g6", "..."],
      "refutation": "Qxf7#",       // 그 수 뒤 상대의 엔진 최선 응수
      "tags": ["allowed_mate"],
      "turning_point": true
    }
  ]
}
```

위는 필드 구성을 보여주는 **형식 예시**이며 실제 분석 결과 값이 아닙니다.

### Threshold

수를 두기 전과 후의 **승률 차이**로 분류합니다. (평가값 → 승률 변환은 Lichess가 공개한 근사식 사용)

| 분류 | 조건 |
|---|---|
| best | 엔진 1순위 수와 같음 |
| good | 승률 손실 5%p 미만 |
| inaccuracy | 5%p 이상 |
| mistake | 10%p 이상 |
| blunder | 20%p 이상 |

기준값은 `src/chess_coach/scoring.py`의 `DEFAULT_THRESHOLDS`에서 바꿀 수 있습니다.
`summary.accuracy`는 단순 평균 기반 근사치라서 chess.com·Lichess의 정확도 값과 다를 수 있습니다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `Stockfish를 찾지 못했습니다` | `sudo apt install stockfish` 또는 `.env`의 `STOCKFISH_PATH`에 실행 파일 **전체 경로** 지정 |
| `Stockfish를 실행하지 못했습니다` | 실행 권한(`chmod +x`)을 확인하고, 내 CPU에 맞지 않는 빌드라면 `avx2` 대신 더 일반적인 `x86-64` 빌드를 받으세요 |
| `externally-managed-environment` 오류 | 시스템 pip에 직접 설치하지 말고 `.venv`를 만들어 그 안에서 설치하세요 (위 설치 방법) |
| `ensurepip is not available` / venv 생성 실패 | `sudo apt install python3-venv` |
| 분석이 너무 느림 | `--depth 12` 또는 `--movetime 0.2`. 긴 게임일수록 오래 걸립니다 |
| `Ollama 서버에 연결할 수 없습니다` | `ollama serve` 실행 또는 `sudo systemctl start ollama` |
| `Ollama에 모델 ... 이(가) 없습니다` | `ollama pull qwen2.5:7b` |
| LLM 응답이 엉뚱하거나 다른 언어가 섞임 | `--level` 조정, 재실행, `--show-prompt`로 입력 확인 |
| `chess.com API 오류` / 요청 제한 | 잠시 후 재시도하거나 사이트에서 PGN을 직접 내려받아 사용 |

## 프로젝트 구조

```
scripts/setup_linux.sh   # 리눅스 설치 도우미
src/chess_coach/
├── cli.py        # 명령줄 (games / fetch / analyze / coach / kb)
├── engine.py     # Stockfish 래퍼 (python-chess UCI)
├── analysis.py   # PGN → 수별 분석, 힌트 태그
├── scoring.py    # 승률 변환, 정확도, 수 분류
├── moments.py    # 핵심 장면 선별
├── report.py     # JSON 리포트 조립
├── llm.py        # 프롬프트 + Ollama 호출, 참고 자료 번호/출처 후처리
├── rag.py        # 오프닝 판별, 장면별 검색어 생성, 자료 선택(예산·중복 제거)
├── knowledge.py  # 노트(.md)·책 조각(.jsonl) 로딩
├── retrieval.py  # BM25 검색
├── features.py   # FEN 기반 포지션 사실 (킹 중앙, 전개, 엔드게임 유형, 통과폰)
├── ingest.py     # 내 책(txt/md/epub/pdf) → 지식 조각
├── knowledge_base/  # 내장 노트 (오프닝·전략·전술·엔드게임)
├── fetch.py      # chess.com API
├── pgn_io.py     # PGN 읽기, 내 색 판별
└── config.py     # .env 로딩
tests/            # 단위 테스트
examples/         # 샘플 PGN
docs/             # 배포 안내
```

## Test

```bash
source .venv/bin/activate
pytest
```

엔진 분석 테스트는 Stockfish 대신 미리 정해둔 평가값을 쓰므로 Stockfish 없이도 실행됩니다.

## Loadmap

- [x] **v0.1** PGN → Stockfish → 핵심 장면 → 로컬 LLM 피드백 (CLI)
- [x] **v0.2** RAG: 오프닝·전술 패턴·엔드게임 지식 문서 검색 반영
- [ ] **v0.3** MCP 서버 (`fetch_games`, `analyze_game`, `analyze_position`, …)
- [ ] RAG 개선: 임베딩 검색 병행, 반복 실수 유형별 자료 추천
- [ ] 분석 결과 캐시(SQLite), 반복 실수 유형 추적, 로컬 웹 보드 뷰어

## License & Reference

- 이 저장소의 코드: [MIT License](LICENSE)
- **Stockfish**는 GPLv3 프로그램입니다. 이 저장소에 포함하지 않으며, 사용자가 직접 설치해 별도 프로세스로 실행합니다.
- 승률·정확도 공식은 Lichess가 공개한 방식을 참고했습니다.
- 내장 노트(`knowledge_base/`)는 이 프로젝트에서 직접 작성한 요약이며 코드와 같은 MIT 라이선스입니다. `kb add` 로 가져온 책의 저작권은 각 저자·출판사에 있으며, 개인 학습용으로만 쓰고 `knowledge/` 폴더는 공유하지 마세요.
- LLM 모델은 각자의 라이선스를 따릅니다. (Qwen2.5-7B-Instruct: Apache-2.0)
>>>>>>> 09d125c (Initial commit: PGN -> Stockfish -> critical moments -> LLM feedback)
