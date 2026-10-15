# 지식 베이스(RAG) 사용 가이드

`chess-coach coach` 는 Stockfish 분석 결과에 **체스 지식 자료**를 붙여서 LLM에게 넘깁니다.
자료는 두 종류입니다.

| 종류 | 위치 | 설명 |
|---|---|---|
| 내장 노트 49개 | `src/chess_coach/knowledge_base/*.md` | 오프닝 20개 + 전략·전술·엔드게임 원칙 29개. **직접 쓴 요약**이며 특정 책의 문장을 옮긴 것이 아닙니다. 출처는 "chess-coach 내장 노트"로 표시됩니다. |
| 내 책/노트 | `knowledge/` (현재 폴더, 또는 `CHESS_COACH_KB_DIR`) | `chess-coach kb add` 로 가져온 책 조각과 직접 쓴 노트. 출처에 **책 제목·저자·장 제목**이 표시됩니다. |

## 어떻게 검색하나요?

1. **오프닝 판별**: PGN의 `ECO` 헤더 → (없으면) 게임의 첫 수들을 노트의 `moves` 와 비교(최장 일치).
2. **장면별 검색어**: 핵심 장면의 *분석 태그*(예: `hung_moved_piece`), *국면*, 그리고 FEN에서 코드가 직접 계산한 *포지션 사실*(킹이 중앙에 남음, 전개 안 된 기물 수, 룩 엔드게임, 통과폰 등)에서 개념 키와 영어 검색어를 만듭니다.
3. **점수 = 개념 키 일치(태그) + BM25 + 국면 일치 보너스**. 책 조각은 태그가 없으므로 BM25 점수가 임계값을 넘어야 후보가 되고, 후보가 있으면 장면당 최소 한 자리는 책 조각에 배정됩니다.
4. 프롬프트 길이 예산(`--kb-budget`, 기본 2400자) 안에서 중복 없이 고르고 `K1, K2…` 번호를 붙입니다.
5. LLM이 문장 끝에 `[K1]` 로 표시한 것만 골라, **출처 목록은 코드가** 응답 끝에 `## 참고 자료` 로 붙입니다. (모델이 출처를 지어내지 못하게)

LLM에는 "자료는 일반 원칙일 뿐 엔진 평가가 아니다 / `hints`·`position_facts` 가 뒷받침할 때만 이 장면의 원인으로 말하라 / 자료에 없는 오프닝 이름이나 수순을 만들지 마라 / 문장을 베끼지 말고 요약하라"는 규칙이 추가로 들어갑니다.

## 내 책 추가하기

```bash
# txt / md / epub / pdf 지원 (pdf 는 pdftotext 필요: sudo apt install poppler-utils)
chess-coach kb add ~/books/chess-fundamentals.epub --title "Chess Fundamentals" --author "Capablanca" --year 1921
chess-coach kb add ~/books/endgames.pdf --title "My Endgame Book" --phase endgame --kind endgame

chess-coach kb list                         # 가져온 자료 보기
chess-coach kb search "rook behind passed pawn"   # 검색이 잘 되는지 확인
chess-coach coach games.pgn --user me --show-prompt   # 실제로 프롬프트에 뭐가 들어가는지 확인
```

- `--phase` 를 주면 그 국면의 장면에서만 우선 검색됩니다. (오프닝 책 → `opening`, 엔드게임 책 → `endgame`)
- 같은 `--title` 로 다시 추가하면 덮어씁니다.
- 결과는 `knowledge/books/<제목>.jsonl` 에 저장됩니다. **이 폴더는 `.gitignore` 에 들어 있으니 저장소에 올리지 마세요.**
- 책 원문은 영어가 많아서, 검색어는 영어로 만들어집니다. 한국어 책도 쓸 수 있지만(한글 2-gram 검색) 내장 검색어와의 매칭은 영어 책보다 약합니다.

### 어떤 책을 넣으면 좋을까요 (예시)

저작권이 있는 책은 **본인이 가진 전자책/PDF를 개인 학습용으로** 넣으세요.

- 전략: Silman *How to Reassess Your Chess*, Seirawan *Winning Chess Strategies*, Nimzowitsch *My System*, Kotov *Think Like a Grandmaster*
- 엔드게임: Silman *The Complete Endgame Course*, Dvoretsky *Endgame Manual*
- 오프닝: 두는 오프닝 전용 서적(오프닝 책은 `--phase opening`)
- 저작권이 만료된 고전: Capablanca *Chess Fundamentals*(1921), Lasker *Common Sense in Chess*(1896) 등은 Project Gutenberg 같은 곳에서 받을 수 있는 것으로 알고 있습니다. 나라별 저작권 기간이 다르므로 받을 때 해당 사이트의 안내를 확인하세요. Gutenberg 텍스트의 라이선스 머리말/꼬리말은 자동으로 제거됩니다.

## 내 노트 쓰기

`knowledge/` 아래에 `.md` 파일을 만들면 내장 노트와 같은 형식으로 읽힙니다. 내 코칭 메모나 책을 읽고 정리한 요약을 넣기에 가장 좋은 방법입니다. 내장 노트와 같은 `id` 를 쓰면 내 버전이 내장 노트를 덮어씁니다.

```markdown
---
id: my-note-1
title: 내가 자주 하는 실수
kind: strategy
phase: middlegame
tags: blunder-check, piece-safety
keywords: hanging piece check before moving
source: 내 복기 메모
---
본문은 한국어로 짧게(700자 이내) 쓰세요. 한 줄에 '---' 만 있는 줄은 쓰지 마세요.
```

`tags` 에 쓸 수 있는 개념 키는 내장 노트의 `tags` 를 참고하세요. 태그가 맞아야 분석 결과와 연결되어 우선 검색됩니다.
(`blunder-check`, `piece-safety`, `loose-pieces`, `checkmate-patterns`, `king-safety`, `castling`, `development`, `early-queen-moves`, `opening-principles`, `middlegame-planning`, `endgame-principles`, `rook-endgames`, `king-and-pawn-endgames`, `passed-pawn` …)

## 한계와 조정

- 검색은 어휘 기반(BM25)이라 **의미가 같아도 단어가 다르면 못 찾을 수 있습니다.** 임베딩 검색(Ollama 임베딩 모델)을 섞는 것이 다음 개선 후보입니다.
- 책 조각 후보 임계값(`rag.py` 의 `BOOK_MIN_RAW` 등)은 합성 텍스트로만 시험했습니다. 실제 책에서 `kb search` 와 `--show-prompt` 로 결과를 보면서 조정하세요. 너무 안 붙으면 낮추고, 엉뚱한 구절이 붙으면 높이세요.
- 참고 자료를 넣으면 프롬프트가 길어집니다. 7B 모델과 `num_ctx=8192` 기준으로 기본 예산을 잡았으니, 컨텍스트를 늘렸다면 `--kb-budget` 도 늘릴 수 있습니다.
- 7B급 모델은 자료를 장면에 억지로 갖다 붙일 수 있습니다. 응답 끝의 `참고 자료` 번호와 원문을 대조해 보세요.
- 내장 노트의 오프닝 설명은 널리 알려진 일반 아이디어를 요약한 것이라 특정 변형의 최신 이론은 담고 있지 않습니다.
