"""명령줄 인터페이스: games / fetch / analyze / coach / kb."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import __version__
from .config import default_model, kb_dir, load_dotenv, ollama_host
from .errors import ChessCoachError
from .llm import LEVELS, build_messages, finalize_feedback, ollama_chat
from .report import build_report
from .rag import DEFAULT_BUDGET_CHARS, DEFAULT_TOP_K
from .scoring import SEVERITY_ORDER


def _progress(done: int, total: int) -> None:
    print(f"\r엔진 분석 중... {done}/{total}", end="", file=sys.stderr, flush=True)


def _add_analysis_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("pgn", help="PGN 파일 경로")
    p.add_argument("--game", type=int, default=1, help="PGN 안의 게임 번호 (1부터, 기본 1)")
    p.add_argument("--user", help="내 chess.com 아이디 (PGN 헤더와 비교해 내 색을 자동 판별)")
    p.add_argument("--color", choices=["white", "black"], help="분석 대상 색을 직접 지정")
    p.add_argument("--engine", help="Stockfish 실행 파일 경로 (기본: STOCKFISH_PATH 또는 PATH)")
    p.add_argument("--depth", type=int, default=16, help="분석 깊이 (기본 16). 클수록 정확하지만 느림")
    p.add_argument("--movetime", type=float, help="포지션당 분석 시간(초). 지정하면 --depth 대신 사용")
    p.add_argument("--threads", type=int, help="엔진 스레드 수 (기본: CPU 스레드의 절반)")
    p.add_argument("--hash", type=int, default=256, dest="hash_mb", help="엔진 해시 메모리 MB (기본 256)")
    p.add_argument("--max-moments", type=int, default=5, help="뽑을 핵심 장면 수 (기본 5)")
    p.add_argument(
        "--min-severity",
        choices=SEVERITY_ORDER,
        default="mistake",
        help="핵심 장면으로 볼 최소 심각도 (기본 mistake)",
    )


def _run_analysis(args: argparse.Namespace, include_moves: bool = False) -> dict:
    # python-chess가 필요한 모듈은 여기서 불러온다 (--help 등은 없어도 동작)
    from .analysis import analyze_game
    from .engine import StockfishEngine, find_stockfish
    from .pgn_io import detect_color, read_games

    games = read_games(args.pgn)
    if not games:
        raise ChessCoachError("PGN에서 게임을 찾지 못했습니다.")
    if not 1 <= args.game <= len(games):
        raise ChessCoachError(f"--game 은 1~{len(games)} 사이여야 합니다. (`chess-coach games {args.pgn}` 로 목록 확인)")
    game = games[args.game - 1]
    if not any(True for _ in game.mainline_moves()):
        raise ChessCoachError("이 게임에는 수가 없습니다.")

    side = args.color or detect_color(game.headers, args.user)
    if args.user and side is None and not args.color:
        print(
            f"경고: '{args.user}' 이(가) PGN의 White/Black 이름과 일치하지 않아 양쪽을 모두 분석합니다.",
            file=sys.stderr,
        )

    path = find_stockfish(args.engine)
    with StockfishEngine(
        path,
        depth=args.depth,
        movetime=args.movetime,
        threads=args.threads,
        hash_mb=args.hash_mb,
    ) as engine:
        analysis = analyze_game(game, engine, progress=_progress)
    print(file=sys.stderr)

    return build_report(
        analysis,
        side=side,
        max_moments=args.max_moments,
        min_severity=args.min_severity,
        include_moves=include_moves,
    )


def cmd_games(args: argparse.Namespace) -> int:
    from .pgn_io import describe_game, read_games

    games = read_games(args.pgn)
    if not games:
        raise ChessCoachError("PGN에서 게임을 찾지 못했습니다.")
    for i, g in enumerate(games, start=1):
        print(describe_game(i, g))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from .fetch import fetch_recent_games

    pgns = fetch_recent_games(args.username, count=args.count, time_class=args.time_class)
    if not pgns:
        raise ChessCoachError("조건에 맞는 게임을 찾지 못했습니다.")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n\n".join(pgns) + "\n")
    print(f"{len(pgns)}개 게임을 {args.out} 에 저장했습니다. (`chess-coach games {args.out}` 로 목록 확인)")
    return 0


def _write_or_print(text: str, out: Optional[str]) -> None:
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"저장했습니다: {out}", file=sys.stderr)
    else:
        print(text)


def cmd_analyze(args: argparse.Namespace) -> int:
    report = _run_analysis(args, include_moves=args.full)
    _write_or_print(json.dumps(report, ensure_ascii=False, indent=2), args.out)
    return 0


def _retrieve_knowledge(report: dict, args: argparse.Namespace) -> Optional[dict]:
    from .knowledge import KnowledgeBase
    from .rag import retrieve_for_report

    kb = KnowledgeBase.load(args.kb_dir)
    knowledge = retrieve_for_report(report, kb, top_k=args.kb_top_k, budget_chars=args.kb_budget)
    opening = (knowledge.get("opening") or {}).get("family")
    print(
        f"참고 자료 {len(knowledge['items'])}건 검색됨" + (f" (오프닝: {opening})" if opening else ""),
        file=sys.stderr,
    )
    return knowledge


def cmd_coach(args: argparse.Namespace) -> int:
    report = _run_analysis(args)
    knowledge = None if args.no_rag else _retrieve_knowledge(report, args)
    messages = build_messages(report, level=args.level, knowledge=knowledge)
    if args.show_prompt:
        for m in messages:
            print(f"--- {m['role']} ---\n{m['content']}\n")
        return 0
    print(f"\nLLM({args.model})에게 피드백을 요청하는 중... (첫 호출은 모델 로딩 때문에 오래 걸릴 수 있어요)", file=sys.stderr)
    feedback = ollama_chat(messages, model=args.model, host=args.host)
    feedback = finalize_feedback(feedback, knowledge)
    _write_or_print(feedback, args.out)
    return 0


def cmd_kb_add(args: argparse.Namespace) -> int:
    from .ingest import ingest_book

    path, n = ingest_book(
        args.path,
        args.kb_dir,
        title=args.title,
        author=args.author,
        year=args.year,
        phase=args.phase,
        kind=args.kind,
        max_chars=args.max_chars,
    )
    print(f"{n}개 조각을 {path} 에 저장했습니다. (`chess-coach kb search \"...\"` 로 확인해 보세요)")
    print("참고: 책 내용은 개인 학습용으로만 쓰고, 이 폴더(knowledge/)는 저장소나 공개 위치에 올리지 마세요.")
    return 0


def cmd_kb_list(args: argparse.Namespace) -> int:
    from .knowledge import KnowledgeBase

    kb = KnowledgeBase.load(args.kb_dir)
    builtin = [c for c in kb.chunks if c.origin == "builtin"]
    print(f"내장 노트: {len(builtin)}개 (오프닝 {sum(c.kind == 'opening' for c in builtin)}개)")
    user_files = {f: n for f, n in kb.files().items() if any(c.file == f and c.origin == "user" for c in kb.chunks)}
    if not user_files:
        print(f"내 자료: 없음 ({args.kb_dir}/ 에 `chess-coach kb add` 로 책을 추가하세요)")
    for f, n in sorted(user_files.items()):
        print(f"내 자료: {f}  ({n}개 조각)")
    return 0


def cmd_kb_search(args: argparse.Namespace) -> int:
    from .knowledge import KnowledgeBase
    from .rag import search_text

    kb = KnowledgeBase.load(args.kb_dir)
    hits = search_text(kb, args.query, phase=args.phase, top_k=args.top_k)
    if not hits:
        print("검색 결과가 없습니다.")
        return 0
    for score, c in hits:
        snippet = c.text[:160].replace("\n", " ")
        print(f"[{score:5.1f}] {c.id}  ({c.origin})\n        {c.title} / {c.source}\n        {snippet}…\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-coach",
        description="Stockfish 분석 + 로컬 LLM으로 내 체스 게임을 복기합니다.",
    )
    parser.add_argument("--version", action="version", version=f"chess-coach {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("games", help="PGN 파일 안의 게임 목록 보기")
    p.add_argument("pgn")
    p.set_defaults(func=cmd_games)

    p = sub.add_parser("fetch", help="chess.com에서 최근 게임을 PGN으로 저장")
    p.add_argument("username", help="chess.com 아이디")
    p.add_argument("--count", type=int, default=5, help="가져올 게임 수 (기본 5)")
    p.add_argument("--time-class", choices=["bullet", "blitz", "rapid", "daily"], help="게임 유형 필터")
    p.add_argument("--out", default="games.pgn", help="저장 파일 (기본 games.pgn)")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("analyze", help="Stockfish로 분석해 핵심 장면 JSON 만들기 (LLM 불필요)")
    _add_analysis_args(p)
    p.add_argument("--full", action="store_true", help="모든 수의 분석 결과도 JSON에 포함")
    p.add_argument("--out", help="JSON 저장 파일 (기본: 화면 출력)")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("coach", help="분석 결과를 로컬 LLM(Ollama)에 넘겨 한국어 피드백 받기")
    _add_analysis_args(p)
    p.add_argument("--model", default=default_model(), help=f"Ollama 모델 이름 (기본 {default_model()})")
    p.add_argument("--host", default=ollama_host(), help="Ollama 서버 주소")
    p.add_argument("--level", choices=list(LEVELS), default="intermediate", help="설명 수준")
    p.add_argument("--show-prompt", action="store_true", help="LLM을 호출하지 않고 프롬프트만 출력")
    p.add_argument("--out", help="피드백 저장 파일 (기본: 화면 출력)")
    p.add_argument("--no-rag", action="store_true", help="참고 자료 검색(RAG)을 끄고 엔진 분석만으로 피드백")
    p.add_argument("--kb-dir", default=kb_dir(), help=f"내 책/노트 폴더 (기본 {kb_dir()})")
    p.add_argument("--kb-top-k", type=int, default=DEFAULT_TOP_K, help=f"장면당 참고 자료 수 (기본 {DEFAULT_TOP_K})")
    p.add_argument("--kb-budget", type=int, default=DEFAULT_BUDGET_CHARS, help=f"참고 자료 본문 총 글자 수 한도 (기본 {DEFAULT_BUDGET_CHARS})")
    p.set_defaults(func=cmd_coach)

    p = sub.add_parser("kb", help="지식 베이스(내 책/노트) 관리: add / list / search")
    kb_sub = p.add_subparsers(dest="kb_command", required=True)

    q = kb_sub.add_parser("add", help="내가 가진 책(txt/md/epub/pdf)을 지식 베이스에 추가")
    q.add_argument("path", help="책 파일 경로")
    q.add_argument("--title", required=True, help="책 제목 (출처 표기에 쓰임)")
    q.add_argument("--author", help="저자")
    q.add_argument("--year", help="출판 연도")
    q.add_argument("--phase", choices=["opening", "middlegame", "endgame"], help="이 책이 다루는 국면 (오프닝 책, 엔드게임 책 등)")
    q.add_argument("--kind", choices=["strategy", "tactics", "endgame", "general"], default="general", help="책 성격")
    q.add_argument("--max-chars", type=int, default=900, help="조각 하나의 최대 글자 수 (기본 900)")
    q.add_argument("--kb-dir", default=kb_dir(), help=f"저장 폴더 (기본 {kb_dir()})")
    q.set_defaults(func=cmd_kb_add)

    q = kb_sub.add_parser("list", help="지식 베이스 현황 보기")
    q.add_argument("--kb-dir", default=kb_dir())
    q.set_defaults(func=cmd_kb_list)

    q = kb_sub.add_parser("search", help="지식 베이스를 직접 검색해 보기 (검색 품질 확인용)")
    q.add_argument("query")
    q.add_argument("--phase", choices=["opening", "middlegame", "endgame"])
    q.add_argument("--top-k", type=int, default=5)
    q.add_argument("--kb-dir", default=kb_dir())
    q.set_defaults(func=cmd_kb_search)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    # Windows 콘솔에서도 한글이 깨지지 않도록
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ChessCoachError as e:
        print(f"\n오류: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n중단했습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
