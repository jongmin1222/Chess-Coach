"""지식 베이스 로딩: 직접 쓴 노트(.md)와 책 조각(.jsonl). python-chess에 의존하지 않습니다.

노트 파일 형식 (한 파일에 여러 노트를 쓸 수 있습니다):

    ---
    id: opening-italian
    title: 이탈리안 게임 (Italian Game)
    kind: opening
    phase: opening
    eco: C50-C59
    moves: 1.e4 e5 2.Nf3 Nc6 3.Bc4
    tags: development, king-safety
    keywords: italian giuoco piano
    source: 출처 표기 (생략하면 기본 출처)
    ---
    본문. (한 줄에 '---' 만 있는 줄은 본문에 쓰지 마세요.)

- kind: opening | strategy | tactics | endgame | general (기본 general)
- phase: opening | middlegame | endgame (생략하면 국면 무관)
- eco / moves: 오프닝 노트에서 오프닝을 판별하는 용도. moves 는 '|' 로 대체 수순을 쓸 수 있습니다.
- tags: 개념 키. 분석 결과에서 만든 검색어와 맞춰 보는 가중치로 쓰입니다.
- keywords: 영어 검색어. 본문에는 안 보이지만 검색에는 쓰입니다. (책 원문이 영어이므로)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .errors import KnowledgeError

KINDS = ("opening", "strategy", "tactics", "endgame", "general")
PHASES = ("opening", "middlegame", "endgame")
BUILTIN_SOURCE = "chess-coach 내장 노트 (일반 원칙 요약)"

_ECO_RE = re.compile(r"^[A-E]\d{2}$")
_MOVE_NO_RE = re.compile(r"\d+\s*\.(?:\.\.)?")


@dataclass
class Chunk:
    id: str
    title: str
    text: str
    source: str
    kind: str = "general"
    phase: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    keywords: str = ""
    eco: list[tuple[str, str]] = field(default_factory=list)
    moves: list[list[str]] = field(default_factory=list)
    origin: str = "builtin"  # builtin | user
    file: str = ""


def normalize_san(token: str) -> str:
    return token.strip().rstrip("+#!?")


def parse_moves(spec: str) -> list[list[str]]:
    """'1.e4 e5 2.Nf3 | 1.d4 d5' -> [['e4','e5','Nf3'], ['d4','d5']]"""
    out: list[list[str]] = []
    for alt in spec.split("|"):
        toks = [normalize_san(t) for t in _MOVE_NO_RE.sub(" ", alt).split()]
        toks = [t for t in toks if t]
        if toks:
            out.append(toks)
    return out


def parse_eco(spec: str) -> list[tuple[str, str]]:
    """'C50-C59, C41' -> [('C50','C59'), ('C41','C41')]"""
    out: list[tuple[str, str]] = []
    for part in spec.split(","):
        part = part.strip().upper()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        hi = hi or lo
        if not (_ECO_RE.match(lo) and _ECO_RE.match(hi)) or lo > hi:
            raise KnowledgeError(f"ECO 형식이 올바르지 않습니다: '{part}' (예: C50-C59)")
        out.append((lo, hi))
    return out


def eco_contains(ranges: list[tuple[str, str]], code: str) -> bool:
    code = code.strip().upper()
    return any(lo <= code <= hi for lo, hi in ranges)


def eco_span(ranges: list[tuple[str, str]], code: str) -> int:
    """code 를 포함하는 가장 좁은 범위의 폭. 포함하지 않으면 큰 값."""
    def n(c: str) -> int:
        return ord(c[0]) * 100 + int(c[1:])

    spans = [n(hi) - n(lo) for lo, hi in ranges if lo <= code.upper() <= hi]
    return min(spans) if spans else 10**9


def _parse_header(lines: list[str], where: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        key, sep, value = s.partition(":")
        if not sep:
            raise KnowledgeError(f"{where}: 헤더 줄 형식이 올바르지 않습니다 -> '{s}'")
        meta[key.strip().lower()] = value.strip()
    return meta


def _validate_kind_phase(kind: str, phase: Optional[str], where: str) -> tuple[str, Optional[str]]:
    if kind not in KINDS:
        raise KnowledgeError(f"{where}: kind 는 {list(KINDS)} 중 하나여야 합니다. ('{kind}')")
    if phase in ("", "any", "all"):
        phase = None
    if phase is not None and phase not in PHASES:
        raise KnowledgeError(f"{where}: phase 는 {list(PHASES)} 중 하나여야 합니다. ('{phase}')")
    return kind, phase


def _clean_body(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paras if p)


def parse_notes(
    text: str,
    *,
    origin: str = "builtin",
    default_source: str = BUILTIN_SOURCE,
    where: str = "",
) -> list[Chunk]:
    blocks: list[tuple[list[str], list[str]]] = []
    header: Optional[list[str]] = None
    body: list[str] = []
    mode = "pre"
    for raw in text.splitlines():
        if raw.strip() == "---":
            if mode == "header":
                mode = "body"
            else:
                if header is not None:
                    blocks.append((header, body))
                header, body, mode = [], [], "header"
            continue
        if mode == "header":
            assert header is not None
            header.append(raw)
        elif mode == "body":
            body.append(raw)
    if header is not None:
        if mode == "header":
            raise KnowledgeError(f"{where}: 헤더가 '---' 로 닫히지 않았습니다.")
        blocks.append((header, body))

    chunks: list[Chunk] = []
    for header_lines, body_lines in blocks:
        meta = _parse_header(header_lines, where)
        cid, title = meta.get("id"), meta.get("title")
        label = f"{where} ({cid or '?'})"
        if not cid or not title:
            raise KnowledgeError(f"{label}: 노트에는 id 와 title 이 필요합니다.")
        body_text = _clean_body(body_lines)
        if not body_text:
            raise KnowledgeError(f"{label}: 본문이 비어 있습니다.")
        kind, phase = _validate_kind_phase(meta.get("kind", "general"), meta.get("phase"), label)
        try:
            eco = parse_eco(meta["eco"]) if meta.get("eco") else []
        except KnowledgeError as e:
            raise KnowledgeError(f"{label}: {e}") from e
        chunks.append(
            Chunk(
                id=cid,
                title=title,
                text=body_text,
                source=meta.get("source") or default_source,
                kind=kind,
                phase=phase,
                tags=[t.strip() for t in meta.get("tags", "").split(",") if t.strip()],
                keywords=meta.get("keywords", ""),
                eco=eco,
                moves=parse_moves(meta["moves"]) if meta.get("moves") else [],
                origin=origin,
                file=where,
            )
        )
    return chunks


def load_jsonl(path: Path, *, origin: str = "user") -> list[Chunk]:
    chunks: list[Chunk] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            where = f"{path}:{lineno}"
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise KnowledgeError(f"{where}: JSON 형식 오류 ({e})") from e
            if not obj.get("id") or not obj.get("text"):
                raise KnowledgeError(f"{where}: id 와 text 가 필요합니다.")
            kind, phase = _validate_kind_phase(obj.get("kind", "general"), obj.get("phase"), where)
            source = obj.get("source", "")
            chunks.append(
                Chunk(
                    id=str(obj["id"]),
                    title=obj.get("title") or obj.get("section") or source,
                    text=obj["text"],
                    source=source,
                    kind=kind,
                    phase=phase,
                    tags=list(obj.get("tags", [])),
                    keywords=obj.get("keywords", ""),
                    origin=origin,
                    file=str(path),
                )
            )
    return chunks


def builtin_dir() -> Path:
    return Path(__file__).parent / "knowledge_base"


def _load_dir(directory: Path, origin: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    if not directory.is_dir():
        return chunks
    for path in sorted(directory.rglob("*")):
        if path.name.startswith(".") or not path.is_file():
            continue
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8-sig")
            source = BUILTIN_SOURCE if origin == "builtin" else f"내 노트 ({path.name})"
            chunks.extend(parse_notes(text, origin=origin, default_source=source, where=str(path)))
        elif path.suffix == ".jsonl":
            chunks.extend(load_jsonl(path, origin=origin))
    return chunks


@dataclass
class KnowledgeBase:
    chunks: list[Chunk] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.chunks)

    def by_id(self) -> dict[str, Chunk]:
        return {c.id: c for c in self.chunks}

    def files(self) -> dict[str, int]:
        """파일 경로 -> 조각 수 (kb list 용)."""
        counts: dict[str, int] = {}
        for c in self.chunks:
            counts[c.file] = counts.get(c.file, 0) + 1
        return counts

    @classmethod
    def load(cls, user_dir: Optional[str | Path] = None, *, builtin: bool = True) -> "KnowledgeBase":
        """내장 노트 + 사용자 폴더를 합친다. 같은 id 가 있으면 사용자 쪽이 내장 노트를 덮어쓴다."""
        merged: dict[str, Chunk] = {}
        for origin, directory in (
            ("builtin", builtin_dir() if builtin else None),
            ("user", Path(user_dir) if user_dir else None),
        ):
            if directory is None:
                continue
            seen: set[str] = set()
            for c in _load_dir(directory, origin):
                if c.id in seen:
                    raise KnowledgeError(f"id 가 중복되었습니다: '{c.id}' ({c.file})")
                seen.add(c.id)
                merged[c.id] = c
        return cls(list(merged.values()))
