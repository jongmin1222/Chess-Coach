"""내가 가진 책(txt / md / epub / pdf)을 지식 베이스 조각(jsonl)으로 바꾼다. 외부 파이썬 패키지는 필요 없습니다.

- epub: 표준 라이브러리(zipfile, html.parser)로 본문을 뽑는다.
- pdf: 시스템의 `pdftotext`(poppler-utils)를 호출한다. 스캔본(텍스트 없음)은 지원하지 않는다.
- Project Gutenberg 텍스트의 머리말/꼬리말 라이선스 문구는 자동으로 제거한다.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from .errors import IngestError
from .knowledge import KINDS, PHASES

_HEADING_TAGS = {"h1", "h2", "h3"}
_BLOCK_TAGS = {"p", "div", "li", "tr", "section", "article", "blockquote", "pre"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in _HEADING_TAGS:
            self.parts.append("\n\n# ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in _HEADING_TAGS or tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def _epub_spine(z: zipfile.ZipFile) -> Optional[list[str]]:
    try:
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        opf_path = rootfile.attrib["full-path"]  # type: ignore[union-attr]
        opf = ET.fromstring(z.read(opf_path))
        ns = "{http://www.idpf.org/2007/opf}"
        manifest = {i.attrib["id"]: i.attrib["href"] for i in opf.iter(f"{ns}item")}
        refs = [r.attrib.get("idref") for r in opf.iter(f"{ns}itemref")]
        base = posixpath.dirname(opf_path)
        return [
            posixpath.normpath(posixpath.join(base, urllib.parse.unquote(manifest[r])))
            for r in refs
            if r in manifest
        ] or None
    except (KeyError, ET.ParseError, AttributeError):
        return None


def epub_to_text(path: str | Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = _epub_spine(z) or sorted(
                n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))
            )
            texts = []
            for name in names:
                try:
                    raw = z.read(name)
                except KeyError:
                    continue
                ex = _TextExtractor()
                ex.feed(raw.decode("utf-8", errors="replace"))
                texts.append("".join(ex.parts))
    except zipfile.BadZipFile as e:
        raise IngestError(f"EPUB 파일을 열 수 없습니다: {path}") from e
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(texts))


def pdf_to_text(path: str | Path) -> str:
    try:
        proc = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(path), "-"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError as e:
        raise IngestError("PDF를 읽으려면 pdftotext가 필요합니다. (Ubuntu/Debian: sudo apt install poppler-utils)") from e
    if proc.returncode != 0:
        raise IngestError(f"pdftotext 실행 실패: {proc.stderr.strip()[:200]}")
    if not proc.stdout.strip():
        raise IngestError("PDF에서 텍스트를 찾지 못했습니다. 스캔본(이미지)이면 OCR로 텍스트를 먼저 만들어야 합니다.")
    return proc.stdout


def read_source(path: str | Path) -> str:
    p = Path(path)
    if not p.is_file():
        raise IngestError(f"파일을 찾을 수 없습니다: {path}")
    suffix = p.suffix.lower()
    if suffix == ".epub":
        return epub_to_text(p)
    if suffix == ".pdf":
        return pdf_to_text(p)
    if suffix in (".txt", ".md", ".text"):
        return p.read_text(encoding="utf-8-sig", errors="replace")
    raise IngestError(f"지원하지 않는 형식입니다: '{suffix}' (txt, md, epub, pdf 지원)")


_GUTENBERG_START = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I | re.S)
_GUTENBERG_END = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", re.I)


def strip_gutenberg(text: str) -> str:
    start = _GUTENBERG_START.search(text)
    if start:
        text = text[start.end():]
    end = _GUTENBERG_END.search(text)
    if end:
        text = text[: end.start()]
    return text


_HEADING_RE = re.compile(
    r"^(?:#{1,3}\s+(?P<md>.+)|(?P<ch>(?:chapter|part|section|lesson)\s+[ivxlcdm\d]+\b.*))$", re.I
)


def split_sections(text: str) -> list[tuple[str, str]]:
    """제목 줄(`# 제목`, `CHAPTER IV` 등)을 기준으로 (섹션 제목, 본문) 으로 나눈다."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        m = _HEADING_RE.match(line.strip()) if len(line.strip()) <= 100 else None
        if m:
            title = (m.group("md") or m.group("ch")).strip()
            sections.append((title, []))
        else:
            sections[-1][1].append(line)
    return [(t, "\n".join(lines)) for t, lines in sections if "".join(lines).strip()]


def _split_long(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    cur = ""
    for sent in re.split(r"(?<=[.!?])\s+", paragraph):
        while len(sent) > max_chars:  # 문장 하나가 너무 길면 강제 분할
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sent[:max_chars])
            sent = sent[max_chars:]
        if cur and len(cur) + 1 + len(sent) > max_chars:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur)
    return pieces


def chunk_text(text: str, *, max_chars: int = 900, min_chars: int = 120) -> list[str]:
    """문단 경계를 지키며 max_chars 안팎으로 묶는다. 너무 짧은 조각(쪽번호 등)은 합치거나 버린다."""
    text = re.sub(r"-\n(?=[a-z])", "", text)  # PDF 줄바꿈 하이픈 제거
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    chunks: list[str] = []
    cur = ""
    for para in filter(None, paras):
        for piece in _split_long(para, max_chars):
            if cur and len(cur) + 1 + len(piece) > max_chars:
                chunks.append(cur)
                cur = piece
            else:
                cur = f"{cur} {piece}".strip()
    if cur:
        chunks.append(cur)
    out: list[str] = []
    for c in chunks:
        if len(c) < min_chars and out and len(out[-1]) + len(c) + 1 <= max_chars * 1.3:
            out[-1] += " " + c
        elif len(c) >= 60 and re.search(r"[A-Za-z가-힣]{3}", c):
            out.append(c)
    return out


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "book-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]


def ingest_book(
    path: str | Path,
    kb_dir: str | Path,
    *,
    title: str,
    author: Optional[str] = None,
    year: Optional[str] = None,
    phase: Optional[str] = None,
    kind: str = "general",
    max_chars: int = 900,
) -> tuple[Path, int]:
    """책 한 권을 `<kb_dir>/books/<slug>.jsonl` 로 저장한다. 같은 제목을 다시 가져오면 덮어쓴다."""
    if kind not in KINDS:
        raise IngestError(f"--kind 는 {list(KINDS)} 중 하나여야 합니다.")
    if phase is not None and phase not in PHASES:
        raise IngestError(f"--phase 는 {list(PHASES)} 중 하나여야 합니다.")
    text = strip_gutenberg(read_source(path))
    slug = slugify(title)
    base = ", ".join(x for x in (author, title) if x) + (f" ({year})" if year else "")

    records: list[dict] = []
    for section, body in split_sections(text):
        for piece in chunk_text(body, max_chars=max_chars):
            records.append(
                {
                    "id": f"{slug}-{len(records) + 1:04d}",
                    "title": section or title,
                    "source": f"{base}, {section}" if section else base,
                    "text": piece,
                    "kind": kind,
                    "phase": phase,
                }
            )
    if not records:
        raise IngestError("본문에서 쓸 만한 텍스트 조각을 찾지 못했습니다.")

    out_dir = Path(kb_dir) / "books"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{slug}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out, len(records)
